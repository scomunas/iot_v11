import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from app.database import db_get_setting, db_set_setting
    from app.telegram import send_telegram_message
except ImportError:
    from database import db_get_setting, db_set_setting
    from telegram import send_telegram_message

logger = logging.getLogger(__name__)

SETTING_KEY_CHANNELS = "notification_channels"

DEFAULT_CHANNELS = [
    {
        "id": "telegram",
        "name": "Telegram",
        "type": "telegram",
        "enabled": True,
        "description": "Send alerts and automation notifications to a Telegram chat",
        "config": {
            "bot_token": "",
            "chat_id": "",
        },
    }
]


def get_notification_channels() -> List[Dict[str, Any]]:
    """
    Retrieve all configured notification channels, merging stored configuration
    with environment fallbacks and live operational status.
    """
    raw = db_get_setting(SETTING_KEY_CHANNELS)
    channels = []
    if raw:
        try:
            channels = json.loads(raw)
        except Exception as exc:
            logger.warning("[notifications] Error parsing stored notification channels: %s", exc)
            channels = []

    if not channels:
        channels = [dict(c) for c in DEFAULT_CHANNELS]

    has_telegram = any(c.get("id") == "telegram" for c in channels)
    if not has_telegram:
        channels.insert(0, dict(DEFAULT_CHANNELS[0]))

    # Merge live status for channels
    for ch in channels:
        ch_type = ch.get("type", ch.get("id"))
        if ch_type == "telegram":
            cfg = ch.get("config") or {}
            custom_token = (cfg.get("bot_token") or "").strip()
            custom_chat = (cfg.get("chat_id") or "").strip()

            env_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            env_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()

            effective_token = custom_token or env_token
            effective_chat = custom_chat or env_chat

            is_configured = bool(effective_token and effective_chat)

            masked_token = None
            if effective_token:
                masked_token = (
                    f"{effective_token[:4]}...{effective_token[-4:]}"
                    if len(effective_token) > 10
                    else "****"
                )

            masked_chat = None
            if effective_chat:
                masked_chat = (
                    f"{effective_chat[:3]}...{effective_chat[-2:]}"
                    if len(effective_chat) > 6
                    else effective_chat
                )

            ch["status"] = {
                "configured": is_configured,
                "bot_token_configured": bool(effective_token),
                "chat_id_configured": bool(effective_chat),
                "bot_token_masked": masked_token,
                "chat_id_masked": masked_chat,
                "using_env_token": bool(not custom_token and env_token),
                "using_env_chat": bool(not custom_chat and env_chat),
                "effective_chat_id": effective_chat,
                "message": (
                    "Telegram channel is active and configured."
                    if is_configured
                    else "Missing Bot Token or Chat ID. Configure below or in backend/.env."
                ),
            }

    return channels


def update_notification_channel(
    channel_id: str,
    enabled: Optional[bool] = None,
    name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Update settings for a specific notification channel and persist to SQLite settings."""
    channels = get_notification_channels()
    target = None
    for ch in channels:
        if ch.get("id") == channel_id:
            target = ch
            break

    if not target:
        return None

    if enabled is not None:
        target["enabled"] = bool(enabled)
    if name is not None:
        target["name"] = name.strip()
    if config is not None:
        existing_cfg = target.get("config") or {}
        existing_cfg.update(config)
        target["config"] = existing_cfg

    # Clean live status before storing
    clean_channels = []
    for ch in channels:
        clean_channels.append({
            "id": ch["id"],
            "name": ch["name"],
            "type": ch.get("type", ch["id"]),
            "enabled": ch.get("enabled", True),
            "description": ch.get("description", ""),
            "config": ch.get("config", {}),
        })

    db_set_setting(SETTING_KEY_CHANNELS, json.dumps(clean_channels))
    logger.info("[notifications] Updated notification channel '%s' (enabled=%s)", channel_id, target.get("enabled"))

    fresh_channels = get_notification_channels()
    return next((c for c in fresh_channels if c["id"] == channel_id), target)


async def dispatch_notifications(
    message: str,
    source_type: str = "general",
    source_id: Optional[int] = None,
    source_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Dispatch a notification message across all enabled notification channels.
    """
    channels = get_notification_channels()
    enabled_channels = [c for c in channels if c.get("enabled", False)]

    if not enabled_channels:
        logger.info(
            "[NOTIFICATION] Notification requested for %s #%s ('%s'), but no notification channels are enabled.",
            source_type,
            source_id,
            source_name,
        )
        return []

    logger.info(
        "[NOTIFICATION] Dispatching notification for %s #%s ('%s') to %d active channel(s): '%s'",
        source_type,
        source_id,
        source_name,
        len(enabled_channels),
        message,
    )

    loop = asyncio.get_running_loop()
    results = []

    for ch in enabled_channels:
        ch_id = ch["id"]
        ch_type = ch.get("type", ch_id)

        if ch_type == "telegram":
            cfg = ch.get("config") or {}
            custom_token = (cfg.get("bot_token") or "").strip()
            custom_chat = (cfg.get("chat_id") or "").strip()

            env_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            env_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()

            bot_token = custom_token or env_token or None
            chat_id = custom_chat or env_chat or None

            try:
                res = await loop.run_in_executor(
                    None,
                    lambda: send_telegram_message(
                        message=message,
                        chat_id=chat_id,
                        bot_token=bot_token,
                        parse_mode="HTML",
                    ),
                )
                logger.info("[NOTIFICATION] Dispatched to Telegram channel '%s': %s", ch_id, res)
                results.append({
                    "channel_id": ch_id,
                    "channel_type": ch_type,
                    "status": "success" if res.get("success") else ("simulated" if res.get("simulated") else "error"),
                    "result": res,
                })
            except Exception as exc:
                logger.exception("[NOTIFICATION] Error dispatching to Telegram channel '%s': %s", ch_id, exc)
                results.append({
                    "channel_id": ch_id,
                    "channel_type": ch_type,
                    "status": "error",
                    "error": str(exc),
                })
        else:
            logger.warning("[NOTIFICATION] Channel type '%s' is not implemented", ch_type)

    return results


async def send_channel_test_alert(channel_id: str, message: Optional[str] = None) -> Dict[str, Any]:
    """Send a test notification to a specific channel."""
    channels = get_notification_channels()
    target = next((c for c in channels if c["id"] == channel_id), None)
    if not target:
        raise ValueError(f"Notification channel '{channel_id}' not found.")

    test_msg = message or f"🔔 Test Alert from IoT System at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"

    ch_type = target.get("type", channel_id)
    if ch_type == "telegram":
        loop = asyncio.get_running_loop()
        cfg = target.get("config") or {}
        custom_token = (cfg.get("bot_token") or "").strip()
        custom_chat = (cfg.get("chat_id") or "").strip()

        env_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        env_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        bot_token = custom_token or env_token or None
        chat_id = custom_chat or env_chat or None

        res = await loop.run_in_executor(
            None,
            lambda: send_telegram_message(
                message=test_msg,
                chat_id=chat_id,
                bot_token=bot_token,
                parse_mode="HTML",
            ),
        )
        return res
    else:
        raise NotImplementedError(f"Channel type '{ch_type}' testing is not implemented.")
