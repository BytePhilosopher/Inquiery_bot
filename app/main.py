import os
import hmac
import hashlib
import secrets
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from io import StringIO

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from telegram import Update

from .database import get_all_inquiries, delete_inquiry
from .bot import create_application

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WEBHOOK_URL       = os.getenv("WEBHOOK_URL", "").rstrip("/")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")

bot_app = create_application()


# ── Session helpers ────────────────────────────────────────────────────────────

def _make_token() -> str:
    return hmac.new(b"inquiry-bot-session", DASHBOARD_PASSWORD.encode(), hashlib.sha256).hexdigest()


def _authenticated(request: Request) -> bool:
    if not DASHBOARD_PASSWORD:
        return True
    cookie = request.cookies.get("session", "")
    return bool(cookie) and secrets.compare_digest(cookie, _make_token())


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()

    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        logger.info(f"[Bot] Webhook registered: {webhook_url}")
    else:
        await bot_app.updater.start_polling()
        logger.info("[Bot] Polling started (local dev mode)")

    await bot_app.start()
    yield

    if not WEBHOOK_URL:
        await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


app = FastAPI(title="Inquiry Bot Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _authenticated(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": False})


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if DASHBOARD_PASSWORD and secrets.compare_digest(password.encode(), DASHBOARD_PASSWORD.encode()):
        response = RedirectResponse("/", status_code=302)
        response.set_cookie("session", _make_token(), httponly=True, samesite="lax", max_age=86400 * 7)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": True})


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


# ── Webhook ────────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not _authenticated(request):
        return RedirectResponse("/login", status_code=302)
    inquiries = get_all_inquiries()
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
    inquiries = get_all_inquiries()
    df = pd.DataFrame(inquiries) if inquiries else pd.DataFrame()
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
    deleted = delete_inquiry(inquiry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
