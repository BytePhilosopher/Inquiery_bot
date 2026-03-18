import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def insert_inquiry(user_id: int, username: str, message: str) -> dict:
    try:
        result = supabase.table("inquiries").insert({
            "user_id":  user_id,
            "username": username or "unknown",
            "message":  message,
            "status":   "pending",
        }).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"[DB] insert_inquiry failed: {e}")
        raise


def get_all_inquiries() -> list:
    try:
        result = (
            supabase.table("inquiries")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"[DB] get_all_inquiries failed: {e}")
        raise


def get_inquiry_by_id(inquiry_id: int) -> dict | None:
    try:
        result = (
            supabase.table("inquiries")
            .select("*")
            .eq("id", inquiry_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"[DB] get_inquiry_by_id({inquiry_id}) failed: {e}")
        raise


def resolve_inquiry(inquiry_id: int, reply: str) -> dict | None:
    try:
        result = (
            supabase.table("inquiries")
            .update({"admin_reply": reply, "status": "resolved"})
            .eq("id", inquiry_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"[DB] resolve_inquiry({inquiry_id}) failed: {e}")
        raise


def delete_inquiry(inquiry_id: int) -> bool:
    try:
        result = (
            supabase.table("inquiries")
            .delete()
            .eq("id", inquiry_id)
            .execute()
        )
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"[DB] delete_inquiry({inquiry_id}) failed: {e}")
        raise


def get_user_inquiries(user_id: int) -> list:
    try:
        result = (
            supabase.table("inquiries")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"[DB] get_user_inquiries({user_id}) failed: {e}")
        raise
