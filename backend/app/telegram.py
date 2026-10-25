import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_telegram_config() -> Dict[str, str]:
    """Retrieve Telegram configuration from environment variables."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return {
        "bot_token": bot_token,
        "chat_id": chat_id,
    }


def get_telegram_status() -> Dict[str, Any]:
    """Get the current configuration and operational status of Telegram integration."""
    cfg = get_telegram_config()
    bot_token = cfg["bot_token"]
    chat_id = cfg["chat_id"]

    bot_token_configured = bool(bot_token)
    chat_id_configured = bool(chat_id)
    is_configured = bot_token_configured and chat_id_configured

    masked_token = None
    if bot_token_configured:
        if len(bot_token) > 10:
            masked_token = f"{bot_token[:4]}...{bot_token[-4:]}"
        else:
            masked_token = "****"

    masked_chat = None
    if chat_id_configured:
        if len(chat_id) > 6:
            masked_chat = f"{chat_id[:3]}...{chat_id[-2:]}"
        else:
            masked_chat = chat_id

    return {
        "configured": is_configured,
        "bot_token_configured": bot_token_configured,
        "chat_id_configured": chat_id_configured,
        "bot_token_masked": masked_token,
        "chat_id_masked": masked_chat,
        "default_chat_id": chat_id if chat_id_configured else None,
        "message": (
            "Telegram integration is active and ready to dispatch alerts."
            if is_configured
            else "Telegram credentials (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) are missing or incomplete in backend/.env. Simulated mode will be used."
        ),
    }


def send_telegram_message(
    message: str,
    chat_id: Optional[str] = None,
    bot_token: Optional[str] = None,
    parse_mode: str = "HTML",
) -> Dict[str, Any]:
    """
    Send an alert message via Telegram Bot API (sendMessage).
    If credentials are not set, logs the alert and returns a graceful simulated delivery result.
    """
    clean_msg = message.strip() if message else ""
    if not clean_msg:
        raise ValueError("Alert message content cannot be empty.")

    cfg = get_telegram_config()
    effective_token = (bot_token or cfg["bot_token"]).strip()
    effective_chat_id = (chat_id or cfg["chat_id"]).strip()

    if not effective_token or not effective_chat_id:
        info_msg = (
            f"[Simulated Alert] Telegram bot token or chat ID is not configured. "
            f"Alert message: '{clean_msg}' (Target chat: {effective_chat_id or 'none'})"
        )
        logger.warning(info_msg)
        return {
            "success": True,
            "simulated": True,
            "chat_id": effective_chat_id or "not_configured",
            "message": info_msg,
            "text": clean_msg,
        }

    api_url = f"https://api.telegram.org/bot{effective_token}/sendMessage"
    payload = {
        "chat_id": effective_chat_id,
        "text": clean_msg,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            res_code = response.status
            res_body = json.loads(response.read().decode("utf-8"))
            if res_code == 200 and res_body.get("ok"):
                logger.info(
                    "[Telegram] Successfully dispatched alert to chat '%s'",
                    effective_chat_id,
                )
                return {
                    "success": True,
                    "simulated": False,
                    "chat_id": effective_chat_id,
                    "message_id": res_body.get("result", {}).get("message_id"),
                    "message": f"Alert successfully sent to Telegram chat {effective_chat_id}",
                    "text": clean_msg,
                }
            else:
                err_detail = res_body.get("description", "Unknown error from Telegram API")
                logger.error("[Telegram] API error: %s", err_detail)
                return {
                    "success": False,
                    "simulated": False,
                    "chat_id": effective_chat_id,
                    "error": f"Telegram API error: {err_detail}",
                    "text": clean_msg,
                }

    except urllib.error.HTTPError as http_err:
        try:
            err_body = json.loads(http_err.read().decode("utf-8"))
            err_desc = err_body.get("description", str(http_err))
        except Exception:
            err_desc = str(http_err)
        err_msg = f"Telegram API HTTP error {http_err.code}: {err_desc}"
        logger.error("[Telegram] %s", err_msg)
        return {
            "success": False,
            "simulated": False,
            "chat_id": effective_chat_id,
            "error": err_msg,
            "text": clean_msg,
        }

    except urllib.error.URLError as url_err:
        err_msg = f"Network connection error while reaching Telegram API: {url_err.reason}"
        logger.error("[Telegram] %s", err_msg)
        return {
            "success": False,
            "simulated": False,
            "chat_id": effective_chat_id,
            "error": err_msg,
            "text": clean_msg,
        }

    except Exception as exc:
        err_msg = f"Unexpected error while sending Telegram alert: {exc}"
        logger.exception("[Telegram] %s", err_msg)
        return {
            "success": False,
            "simulated": False,
            "chat_id": effective_chat_id,
            "error": err_msg,
            "text": clean_msg,
        }
