import os
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .database import (
    insert_inquiry,
    get_inquiry_by_id,
    resolve_inquiry,
    get_user_inquiries,
    get_all_inquiries,
)

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN must be set in environment variables")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID must be set in environment variables")


# ── User Commands ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *እንኳን ደህና መጡ!*\n\n"
        "ጥያቄዎትን ወይም ጥቆማዎትን ይላኩ። ቡድናችን በፍጥነት ምላሽ ይሰጥዎታል።\n\n"
        "📌 ትኬቱን ለማወቅ /status ይጠቀሙ።\n"
        "❓ ለእርዳታ /help ይጠቀሙ።",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *እርዳታ*\n\n"
        "• ጥያቄዎትን ወይም ጥቆማዎትን ይላኩ — ቡድናችን ምላሽ ይሰጥዎታል\n"
        "• /status — የቅርብ ጊዜ ትኬቶቻቸውን ያሳያል\n"
        "• /start — እንኳን ደህና ይምጡ",
        parse_mode="Markdown",
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    inquiries = get_user_inquiries(user_id)

    if not inquiries:
        await update.message.reply_text("📭 ምንም ትኬት አልተገኘም።")
        return

    lines = ["📋 *የቅርብ ጊዜ ትኬቶችዎ:*\n"]
    for inq in inquiries:
        icon = "✅" if inq["status"] == "resolved" else "⏳"
        msg_preview = inq["message"][:50] + ("..." if len(inq["message"]) > 50 else "")
        lines.append(f"{icon} *ትኬት #{inq['id']}*")
        lines.append(f"   💬 {msg_preview}")
        if inq.get("admin_reply"):
            reply_preview = inq["admin_reply"][:50] + ("..." if len(inq["admin_reply"]) > 50 else "")
            lines.append(f"   📩 ምላሽ: {reply_preview}")
        lines.append(f"   🔖 ሁኔታ: {'ተፈቷል' if inq['status'] == 'resolved' else 'በመጠባበቅ'}\n")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Message Handler ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

    user = update.message.from_user
    display_name = user.username or user.first_name or str(user.id)
    logger.info(f"[Message] @{display_name} ({user.id}): {update.message.text}")

    try:
        inquiry = insert_inquiry(
            user_id=user.id,
            username=display_name,
            message=update.message.text,
        )
        ticket_id = inquiry["id"]

        await update.message.reply_text(
            f"✅ *ጥቆማዎትን ተቀብለናል!*\n\n"
            f"🎫 ትኬት ቁጥር: *#{ticket_id}*\n"
            f"ቡድናችን በቅርቡ ምላሽ ይሰጥዎታል።\n\n"
            f"_ትኬቱን ለማረጋገጥ /status ይላኩ_",
            parse_mode="Markdown",
        )
        logger.info(f"[DB] Inquiry #{ticket_id} saved")

        # Notify admin
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📨 *አዲስ ጥቆማ ደረሰ!*\n\n"
                f"👤 ተጠቃሚ: @{display_name} (ID: `{user.id}`)\n"
                f"🎫 ትኬት: *#{ticket_id}*\n"
                f"💬 ጥቆማ:\n{update.message.text}\n\n"
                f"_ምላሽ ለመስጠት:_\n`/reply {ticket_id} ምላሽዎ`"
            ),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"[Error] Failed to save inquiry: {e}")
        await update.message.reply_text(
            "❌ ይቅርታ! ጥቆማዎ አልተቀበለም። እባክዎ እንደገና ይሞክሩ።"
        )


# ── Admin Commands ─────────────────────────────────────────────────────────────

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        logger.warning(f"[Unauthorized] {update.message.from_user.id} tried /reply")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❗ *አጠቃቀም:*\n`/reply <ticket_id> <message>`\n\n"
            "ምሳሌ:\n`/reply 5 ጥቆማዎ ደርሷል፣ እናመሰግናለን።`",
            parse_mode="Markdown",
        )
        return

    ticket_id_str = context.args[0]
    reply_text = " ".join(context.args[1:])

    try:
        ticket_id = int(ticket_id_str)
    except ValueError:
        await update.message.reply_text(f"❌ ልክ ያልሆነ ትኬት ቁጥር: {ticket_id_str}")
        return

    inquiry = get_inquiry_by_id(ticket_id)
    if not inquiry:
        await update.message.reply_text(f"❌ ትኬት #{ticket_id} አልተገኘም።")
        return

    if inquiry["status"] == "resolved":
        await update.message.reply_text(
            f"⚠️ ትኬት #{ticket_id} አስቀድሞ ተፈቷል።\n"
            f"ዳግም ምላሽ ለመስጠት ቀጥሉ።"
        )

    try:
        await context.bot.send_message(
            chat_id=inquiry["user_id"],
            text=(
                f"📩 *ምላሽ ደረሰ!*\n\n"
                f"ለጥቆማዎ (ትኬት *#{ticket_id}*):\n\n"
                f"{reply_text}"
            ),
            parse_mode="Markdown",
        )
        resolve_inquiry(ticket_id, reply_text)
        await update.message.reply_text(f"✅ ምላሽ ተልኳል! ትኬት #{ticket_id} ተፈቷል።")
        logger.info(f"[Admin] Ticket #{ticket_id} resolved")

    except Exception as e:
        logger.error(f"[Error] Failed to send reply: {e}")
        await update.message.reply_text(f"❌ ምላሽ መላክ አልተቻለም: {e}")


async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    all_inquiries = get_all_inquiries()
    pending = [i for i in all_inquiries if i["status"] == "pending"]

    if not pending:
        await update.message.reply_text("✅ ምንም ያልተፈቱ ጥቆማዎች የሉም!")
        return

    lines = [f"⏳ *{len(pending)} ያልተፈቱ ጥቆማዎች:*\n"]
    for inq in pending[:10]:
        preview = inq["message"][:60] + ("..." if len(inq["message"]) > 60 else "")
        lines.append(f"🎫 *#{inq['id']}* — @{inq['username']}")
        lines.append(f"   {preview}\n")

    if len(pending) > 10:
        lines.append(f"_...እና {len(pending) - 10} ተጨማሪ። ዳሽቦርዱን ይጎብኙ።_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Application Factory ────────────────────────────────────────────────────────

def create_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("pending", list_pending))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
