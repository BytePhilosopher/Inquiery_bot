import os
from dotenv import load_dotenv
from datetime import datetime
from bson import ObjectId

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)
from database import collection

# Load environment variables
load_dotenv()  # ensure .env is in project root

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
MONGO_URI = os.getenv("MONGO_URI")

# Validate environment variables
if not BOT_TOKEN or not ADMIN_ID:
    raise ValueError("BOT_TOKEN and ADMIN_ID must be set in your .env file")

try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise ValueError(f"ADMIN_ID in .env must be a valid integer, got: {ADMIN_ID}")


# --- Handler for user messages ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
        return

    user = update.message.from_user
    print(f"[User Message] {user.username} ({user.id}): {update.message.text}")

    # Save inquiry to MongoDB
    inquiry = {
        "user_id": user.id,
        "username": user.username,
        "message": update.message.text,
        "status": "pending",
        "admin_reply": None,
        "timestamp": datetime.utcnow()
    }

    result = collection.insert_one(inquiry)
    print(f"[DB] Inquiry inserted with ID: {result.inserted_id}")

    # Reply to user
    await update.message.reply_text(
        f"✅ ጥቆማዎትን ተቀብለናል.\nTicket ID: {result.inserted_id}"
    )
    print("[Bot] Reply sent to user")


# --- Handler for admin replies ---
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        print(f"[Unauthorized] {update.message.from_user.id} tried to use /reply")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <ticket_id> <message>")
        return

    ticket_id = context.args[0]
    reply_text = " ".join(context.args[1:])

    try:
        inquiry = collection.find_one({"_id": ObjectId(ticket_id)})
    except Exception as e:
        await update.message.reply_text(f"Invalid ticket ID: {ticket_id}")
        print(f"[Error] Invalid ObjectId: {ticket_id} ({e})")
        return

    if not inquiry:
        await update.message.reply_text("Ticket not found.")
        return

    # Send reply to the user
    await context.bot.send_message(
        chat_id=inquiry["user_id"],
        text=f"📩 ምላሽ:\n{reply_text}"
    )

    # Update inquiry in DB
    collection.update_one(
        {"_id": ObjectId(ticket_id)},
        {"$set": {"admin_reply": reply_text, "status": "resolved"}}
    )

    await update.message.reply_text("Reply sent and ticket resolved.")
    print(f"[Admin Reply] Ticket {ticket_id} resolved.")


# --- Run bot ---
def run_bot():
    print("[Bot] Starting bot...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handle all text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Handle admin reply
    app.add_handler(CommandHandler("reply", reply))

    app.run_polling()


if __name__ == "__main__":
    run_bot()
