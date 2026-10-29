import json
import logging
from typing import Any, Dict, List, Optional

try:
    from app.database import db_get_setting, db_set_setting
    from app.homeassistant import call_homeassistant_service
except ImportError:
    from database import db_get_setting, db_set_setting
    from homeassistant import call_homeassistant_service

logger = logging.getLogger(__name__)

SETTING_KEY_SPEAKER = "speaker_system"

DEFAULT_SPEAKER_CONFIG = {
    "enabled": True,
    "speakers": ["media_player.todos_los_altavoces"],
    "chime_path": "bells",
    "tts_platform": "tts.google_translate_say",
    "volume_level": 0.8,
    "default_message": "Se ha detectado su presencia de forma indebida y se está comunicando a la policía.",
}


def get_speaker_config() -> Dict[str, Any]:
    """Retrieve speaker system configuration from SQLite settings."""
    raw = db_get_setting(SETTING_KEY_SPEAKER)
    if raw:
        try:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                merged = dict(DEFAULT_SPEAKER_CONFIG)
                merged.update(stored)
                return merged
        except Exception as exc:
            logger.warning("[speakers] Error parsing stored speaker config: %s", exc)

    return dict(DEFAULT_SPEAKER_CONFIG)


def update_speaker_config(
    enabled: Optional[bool] = None,
    speakers: Optional[List[str]] = None,
    chime_path: Optional[str] = None,
    tts_platform: Optional[str] = None,
    volume_level: Optional[float] = None,
    default_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Update speaker system configuration and persist to SQLite settings."""
    current = get_speaker_config()

    if enabled is not None:
        current["enabled"] = bool(enabled)
    else:
        current["enabled"] = True
    if speakers is not None:
        clean_speakers = [str(s).strip() for s in speakers if str(s).strip()]
        current["speakers"] = clean_speakers
    if chime_path is not None:
        current["chime_path"] = chime_path.strip()
    if tts_platform is not None:
        current["tts_platform"] = tts_platform.strip()
    if volume_level is not None:
        # Clamp between 0.0 and 1.0
        try:
            vol = float(volume_level)
            current["volume_level"] = max(0.0, min(1.0, round(vol, 2)))
        except (ValueError, TypeError):
            pass
    if default_message is not None:
        current["default_message"] = default_message.strip()

    db_set_setting(SETTING_KEY_SPEAKER, json.dumps(current))
    logger.info(
        "[speakers] Updated speaker configuration: enabled=%s, %d speaker(s)",
        current.get("enabled"),
        len(current.get("speakers", [])),
    )
    return current


def broadcast_chime_tts(
    message: Optional[str] = None,
    speakers: Optional[List[str]] = None,
    chime_path: Optional[str] = None,
    tts_platform: Optional[str] = None,
    volume_level: Optional[float] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Dispatch an audio announcement through Home Assistant using the chime_tts.say service.
    Follows the chime_tts call schema:
      - Domain: chime_tts
      - Service: say
      - entity_id: target speaker(s) (e.g. media_player.todos_los_altavoces)
      - chime_path: audio chime to play prior to TTS (e.g. 'bells')
      - tts_platform: speech engine (e.g. 'tts.google_translate_say')
      - volume_level: playback volume (e.g. 0.8)
      - message: speech text content
    """
    cfg = get_speaker_config()

    if not cfg.get("enabled", True) and not force:
        logger.info("[speakers] Speaker system is disabled; broadcast skipped.")
        return {
            "success": False,
            "skipped": True,
            "reason": "Speaker system is disabled in settings.",
        }

    effective_msg = (message or cfg.get("default_message") or "").strip()
    if not effective_msg:
        raise ValueError("Broadcast message cannot be empty.")

    target_speakers = speakers if speakers is not None else cfg.get("speakers", [])
    if not target_speakers:
        target_speakers = ["media_player.todos_los_altavoces"]

    effective_entity_id = (
        target_speakers if len(target_speakers) > 1 else target_speakers[0]
    )

    effective_chime = (chime_path if chime_path is not None else cfg.get("chime_path", "bells")).strip()
    effective_platform = (tts_platform if tts_platform is not None else cfg.get("tts_platform", "tts.google_translate_say")).strip()

    if volume_level is not None:
        try:
            effective_volume = max(0.0, min(1.0, round(float(volume_level), 2)))
        except (ValueError, TypeError):
            effective_volume = cfg.get("volume_level", 0.8)
    else:
        effective_volume = cfg.get("volume_level", 0.8)

    service_data = {
        "message": effective_msg,
        "chime_path": effective_chime,
        "tts_platform": effective_platform,
        "volume_level": effective_volume,
    }

    logger.info(
        "[speakers] Broadcasting Chime TTS to '%s': '%s' (chime=%s, vol=%s)",
        effective_entity_id,
        effective_msg,
        effective_chime,
        effective_volume,
    )

    ha_res = call_homeassistant_service(
        domain="chime_tts",
        service="say",
        entity_id=effective_entity_id,
        service_data=service_data,
    )

    return {
        "success": ha_res.get("success", False),
        "simulated": ha_res.get("simulated", False),
        "speakers": target_speakers,
        "service": "chime_tts.say",
        "service_data": service_data,
        "response": ha_res,
    }
