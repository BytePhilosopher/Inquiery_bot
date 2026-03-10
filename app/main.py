import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from io import StringIO

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from telegram import Update

from .database import get_all_inquiries
from .bot import create_application

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")

bot_app = create_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────
    await bot_app.initialize()

    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        logger.info(f"[Bot] Webhook registered: {webhook_url}")
    else:
        logger.warning("[Bot] WEBHOOK_URL not set — Telegram updates won't arrive")

    await bot_app.start()
    yield

    # ── Shutdown ─────────────────────────────────────────────────
    await bot_app.stop()
    await bot_app.shutdown()


app = FastAPI(title="Inquiry Bot Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# ── Webhook endpoint (Telegram → bot) ─────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    inquiries = get_all_inquiries()
    total = len(inquiries)
    pending = sum(1 for i in inquiries if i["status"] == "pending")
    resolved = total - pending

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "inquiries": inquiries,
        "total": total,
        "pending": pending,
        "resolved": resolved,
    })


@app.get("/export")
async def export_csv():
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


@app.get("/health")
async def health():
    return {"status": "ok"}
