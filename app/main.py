import os
import hmac
import hashlib
import secrets
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from io import StringIO

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from telegram import Update

from .database import get_all_inquiries, delete_inquiry
from .bot import create_application

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Startup validation ─────────────────────────────────────────────────────────
_REQUIRED = ["BOT_TOKEN", "ADMIN_ID", "SUPABASE_URL", "SUPABASE_KEY", "DASHBOARD_PASSWORD"]
_missing  = [v for v in _REQUIRED if not os.getenv(v)]
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}")

# ── Config ─────────────────────────────────────────────────────────────────────
WEBHOOK_URL        = os.getenv("WEBHOOK_URL", "").rstrip("/")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
_IS_PROD           = bool(WEBHOOK_URL)

# ── Rate limiting (brute-force protection on /login) ───────────────────────────
_attempts: dict[str, list[float]] = defaultdict(list)
_MAX_ATTEMPTS = 5
_WINDOW_SECS  = 300  # 5 minutes


def _is_rate_limited(ip: str) -> bool:
    now   = time.monotonic()
    valid = [t for t in _attempts[ip] if now - t < _WINDOW_SECS]
    _attempts[ip] = valid
    return len(valid) >= _MAX_ATTEMPTS


def _record_attempt(ip: str) -> None:
    _attempts[ip].append(time.monotonic())


# ── Security headers middleware ────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.update({
            "X-Content-Type-Options":  "nosniff",
            "X-Frame-Options":         "DENY",
            "X-XSS-Protection":        "1; mode=block",
            "Referrer-Policy":         "strict-origin-when-cross-origin",
            "Permissions-Policy":      "geolocation=(), microphone=(), camera=()",
        })
        return response


# ── Session helpers ────────────────────────────────────────────────────────────
def _make_token() -> str:
    return hmac.new(b"inquiry-bot-v1", DASHBOARD_PASSWORD.encode(), hashlib.sha256).hexdigest()


def _authenticated(request: Request) -> bool:
    cookie = request.cookies.get("session", "")
    return bool(cookie) and secrets.compare_digest(cookie, _make_token())


# ── Bot & lifespan ─────────────────────────────────────────────────────────────
bot_app = create_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"[Bot] Webhook set: {WEBHOOK_URL}/webhook")
    else:
        await bot_app.updater.start_polling()
        logger.info("[Bot] Polling started (local dev mode)")
    await bot_app.start()
    yield
    if not WEBHOOK_URL:
        await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Inquiry Bot",
    docs_url=None,   # disable Swagger UI in production
    redoc_url=None,  # disable ReDoc in production
    lifespan=lifespan,
)
app.add_middleware(SecurityHeadersMiddleware)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# ── Error handlers ─────────────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": 404, "message": "This page doesn't exist."},
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    logger.error(f"[500] {request.method} {request.url} — {exc}")
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": 500, "message": "Something went wrong. Please try again."},
        status_code=500,
    )


# ── Auth ───────────────────────────────────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _authenticated(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request, "error": False, "rate_limited": False,
    })


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    ip = request.client.host if request.client else "unknown"

    if _is_rate_limited(ip):
        logger.warning(f"[Auth] Rate limit hit — {ip}")
        return templates.TemplateResponse("login.html", {
            "request": request, "error": False, "rate_limited": True,
        }, status_code=429)

    if secrets.compare_digest(password.encode(), DASHBOARD_PASSWORD.encode()):
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(
            "session", _make_token(),
            httponly=True, samesite="lax",
            max_age=86400 * 7,
            secure=_IS_PROD,   # HTTPS-only cookie in production
        )
        logger.info(f"[Auth] Login successful — {ip}")
        return response

    _record_attempt(ip)
    logger.warning(f"[Auth] Failed login attempt — {ip}")
    return templates.TemplateResponse("login.html", {
        "request": request, "error": True, "rate_limited": False,
    }, status_code=401)


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


# ── Telegram webhook ───────────────────────────────────────────────────────────
@app.post("/webhook")
async def webhook(request: Request):
    data   = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


# ── Dashboard ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not _authenticated(request):
        return RedirectResponse("/login", status_code=302)
    try:
        inquiries = get_all_inquiries()
    except Exception as e:
        logger.error(f"[DB] Failed to fetch inquiries: {e}")
        inquiries = []
    total    = len(inquiries)
    pending  = sum(1 for i in inquiries if i["status"] == "pending")
    resolved = total - pending
    return templates.TemplateResponse("dashboard.html", {
        "request":   request,
        "inquiries": inquiries,
        "total":     total,
        "pending":   pending,
        "resolved":  resolved,
    })


@app.get("/export")
async def export_csv(request: Request):
    if not _authenticated(request):
        return RedirectResponse("/login", status_code=302)
    try:
        inquiries = get_all_inquiries()
    except Exception as e:
        logger.error(f"[DB] Export failed: {e}")
        raise HTTPException(status_code=500, detail="Export failed")
    df     = pd.DataFrame(inquiries) if inquiries else pd.DataFrame()
    stream = StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inquiries.csv"},
    )


@app.delete("/inquiry/{inquiry_id}")
async def delete_inquiry_endpoint(inquiry_id: int, request: Request):
    if not _authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        deleted = delete_inquiry(inquiry_id)
    except Exception as e:
        logger.error(f"[DB] Delete failed for #{inquiry_id}: {e}")
        raise HTTPException(status_code=500, detail="Delete failed")
    if not deleted:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    logger.info(f"[Admin] Inquiry #{inquiry_id} deleted")
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
