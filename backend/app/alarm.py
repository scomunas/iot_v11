import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from app.database import db_get_setting, db_set_setting, db_list_devices
    from app.notifications import dispatch_notifications
    from app.speakers import broadcast_chime_tts
except ImportError:
    from database import db_get_setting, db_set_setting, db_list_devices
    from notifications import dispatch_notifications
    from speakers import broadcast_chime_tts

logger = logging.getLogger(__name__)

SETTING_KEY_ALARM = "alarm_system"

DEFAULT_ALARM_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "helper_entity": "",
    "notification_message": "🚨 ALARM: Excessive activity detected on {device_name} ({device_type})! {count} events occurred within {seconds}s (Threshold: {trigger}).",
    "speak_message": "Atención: Alarma de seguridad activada en {device_name}. Se han detectado {count} eventos en {seconds} segundos.",
    "default_trigger": 2,
    "default_seconds": 60,
    "retention_seconds": 300,
    "delay_seconds": 30,
}

# In-memory storage for sensor events: list of {"entity": str, "date": datetime}
_alarm_memory_events: List[Dict[str, Any]] = []


def get_alarm_config() -> Dict[str, Any]:
    """Retrieve general alarm system configuration from SQLite settings."""
    raw = db_get_setting(SETTING_KEY_ALARM)
    config = dict(DEFAULT_ALARM_CONFIG)
    if raw:
        try:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                config.update(stored)
        except Exception as exc:
            logger.warning("[alarm] Error parsing stored alarm config: %s", exc)

    # Check live state from helper entity if configured
    helper = (config.get("helper_entity") or "").strip()
    if helper:
        try:
            from app.homeassistant import get_entity_state
        except ImportError:
            from homeassistant import get_entity_state
        try:
            st = get_entity_state(helper)
            if st is not None:
                new_enabled = st.strip().lower() in ("on", "armed", "armed_home", "armed_away", "true", "1")
                if config.get("enabled") and not new_enabled:
                    delete_deferred_alarm_schedules()
                config["enabled"] = new_enabled
        except Exception as exc:
            logger.warning("[alarm] Could not query helper entity '%s': %s", helper, exc)

    return config


def update_alarm_config(
    enabled: Optional[bool] = None,
    helper_entity: Optional[str] = None,
    notification_message: Optional[str] = None,
    speak_message: Optional[str] = None,
    default_trigger: Optional[int] = None,
    default_seconds: Optional[int] = None,
    retention_seconds: Optional[int] = None,
    delay_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Update general alarm system configuration and persist to SQLite settings."""
    current = get_alarm_config()

    if helper_entity is not None:
        current["helper_entity"] = helper_entity.strip()

    if enabled is not None:
        was_enabled = current.get("enabled", True)
        current["enabled"] = bool(enabled)
        if was_enabled and not current["enabled"]:
            delete_deferred_alarm_schedules()

        # Sync state to Home Assistant helper entity if configured
        target_helper = current.get("helper_entity", "").strip()
        if target_helper:
            try:
                from app.homeassistant import call_homeassistant_service, FALLBACK_ENTITIES
                for ent in FALLBACK_ENTITIES:
                    if ent.get("entity_id") == target_helper:
                        ent["state"] = "on" if current["enabled"] else "off"
            except ImportError:
                try:
                    from homeassistant import call_homeassistant_service, FALLBACK_ENTITIES
                    for ent in FALLBACK_ENTITIES:
                        if ent.get("entity_id") == target_helper:
                            ent["state"] = "on" if current["enabled"] else "off"
                except ImportError:
                    pass
            domain = target_helper.split(".")[0] if "." in target_helper else "homeassistant"
            service = "turn_on" if current["enabled"] else "turn_off"
            try:
                call_homeassistant_service(
                    domain=domain,
                    service=service,
                    entity_id=target_helper,
                )
            except Exception as exc:
                logger.warning("[alarm] Could not sync helper entity '%s' to %s: %s", target_helper, service, exc)
    if notification_message is not None:
        current["notification_message"] = notification_message.strip()
    if speak_message is not None:
        current["speak_message"] = speak_message.strip()
    if default_trigger is not None:
        try:
            current["default_trigger"] = max(1, int(default_trigger))
        except (ValueError, TypeError):
            pass
    if default_seconds is not None:
        try:
            current["default_seconds"] = max(1, int(default_seconds))
        except (ValueError, TypeError):
            pass
    if retention_seconds is not None:
        try:
            current["retention_seconds"] = max(5, int(retention_seconds))
        except (ValueError, TypeError):
            pass
    if delay_seconds is not None:
        try:
            current["delay_seconds"] = max(0, int(delay_seconds))
        except (ValueError, TypeError):
            pass

    db_set_setting(SETTING_KEY_ALARM, json.dumps(current))
    logger.info(
        "[alarm] Updated alarm configuration: enabled=%s, trigger=%s, seconds=%s, retention=%s, delay=%s",
        current.get("enabled"),
        current.get("default_trigger"),
        current.get("default_seconds"),
        current.get("retention_seconds"),
        current.get("delay_seconds"),
    )
    return current


def get_memory_events() -> List[Dict[str, Any]]:
    """Retrieve in-memory recorded events formatted for inspection."""
    results = []
    for ev in _alarm_memory_events:
        dt = ev.get("date")
        iso_str = dt.isoformat() if isinstance(dt, datetime) else str(dt)
        results.append({
            "entity": ev.get("entity"),
            "date": iso_str,
        })
    return results


def clear_memory_events() -> None:
    """Clear all in-memory recorded sensor events."""
    global _alarm_memory_events
    _alarm_memory_events.clear()
    logger.info("[alarm] Cleared all in-memory alarm events.")


def render_alarm_message(
    template: str,
    entity: str,
    trigger: int,
    seconds: int,
    count: int,
    dt: Optional[datetime] = None,
    device_name: Optional[str] = None,
    device_type: Optional[str] = None,
) -> str:
    """
    Safely replace template tags in static notification and speak messages.
    Supported tags:
      {device_name} - Configured friendly name of the device (or entity if not found)
      {device}      - Alias for {device_name}
      {device_type} - Configured device type (e.g. movement, door, presence)
      {type}        - Alias for {device_type}
      {entity}      - Target sensor or device entity ID / friendly name
      {trigger}     - Configured threshold count
      {seconds}     - Configured evaluation window in seconds
      {count}       - Actual number of events recorded in the window
      {date}        - Date in YYYY-MM-DD
      {time}        - Time in HH:MM:SS
      {timestamp}   - Combined datetime timestamp
    """
    resolved_device_name = device_name
    resolved_device_type = device_type
    if not resolved_device_name or not resolved_device_type:
        try:
            for d in db_list_devices():
                if d.get("entity_id") == entity or d.get("name") == entity:
                    if not resolved_device_name:
                        resolved_device_name = d.get("name")
                    if not resolved_device_type:
                        resolved_device_type = d.get("type")
                    break
        except Exception as exc:
            logger.warning("[alarm] Could not look up device info for %s: %s", entity, exc)

    if not resolved_device_name:
        resolved_device_name = str(entity)
    if not resolved_device_type:
        resolved_device_type = entity.split(".")[0] if "." in str(entity) else "sensor"

    eval_dt = dt or datetime.now()
    date_str = eval_dt.strftime("%Y-%m-%d")
    time_str = eval_dt.strftime("%H:%M:%S")
    timestamp_str = f"{date_str} {time_str}"

    replacements = {
        "{device_name}": str(resolved_device_name),
        "{device}": str(resolved_device_name),
        "{device_type}": str(resolved_device_type),
        "{type}": str(resolved_device_type),
        "{entity}": str(entity),
        "{trigger}": str(trigger),
        "{seconds}": str(seconds),
        "{count}": str(count),
        "{date}": date_str,
        "{time}": time_str,
        "{timestamp}": timestamp_str,
    }

    result = template or ""
    for tag, val in replacements.items():
        result = result.replace(tag, val)
    return result


def is_truthy(val: Any) -> bool:
    """Check if a parameter value represents True."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "on")
    return bool(val)


async def evaluate_alarm_event(
    entity: str,
    trigger: int,
    seconds: int,
    notification: Any = True,
    speak: Any = False,
) -> Dict[str, Any]:
    """
    Core function for 'check_alarm':
      1. Records (entity, date) in the on-memory event list.
      2. Cleans up old events outside the time window.
      3. If count <= trigger: only stores event in memory, no alarm fired.
      4. If count > trigger: threshold exceeded! Schedules a deferred one-time schedule
         to execute 'fire_alarm' (which uses global notification/speak templates from Settings).
    """
    global _alarm_memory_events

    clean_entity = str(entity).strip()
    try:
        clean_trigger = max(1, int(trigger))
    except (ValueError, TypeError):
        clean_trigger = 2

    try:
        clean_seconds = max(1, int(seconds))
    except (ValueError, TypeError):
        clean_seconds = 60

    cfg = get_alarm_config()
    try:
        configured_retention = max(5, int(cfg.get("retention_seconds", 300)))
    except (ValueError, TypeError):
        configured_retention = 300

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=clean_seconds)
    effective_retention = max(configured_retention, clean_seconds)
    retention_cutoff = now - timedelta(seconds=effective_retention)

    # 1. Prune events older than configured retention_seconds to prevent memory list from growing uncontrolled
    _alarm_memory_events = [
        ev for ev in _alarm_memory_events
        if ev.get("date") and ev["date"] >= retention_cutoff
    ]

    # 2. Append new event to in-memory list
    _alarm_memory_events.append({
        "entity": clean_entity,
        "date": now,
    })

    # 3. Count events for this entity within the window
    entity_events = [
        ev for ev in _alarm_memory_events
        if ev.get("entity") == clean_entity and ev["date"] >= cutoff
    ]
    count = len(entity_events)

    logger.info(
        "[check_alarm] Entity '%s' has %d event(s) in the last %ds (Trigger threshold: %d)",
        clean_entity,
        count,
        clean_seconds,
        clean_trigger,
    )

    # 4. Check threshold condition
    # If no events or events are less or equal to trigger: only store in memory
    if count <= clean_trigger:
        msg = (
            f"Alarm check: Entity '{clean_entity}' event recorded ({count}/{clean_trigger} in {clean_seconds}s). "
            f"Threshold not exceeded; alarm silent."
        )
        return {
            "alarm_triggered": False,
            "entity": clean_entity,
            "count": count,
            "trigger": clean_trigger,
            "seconds": clean_seconds,
            "notification_sent": False,
            "speak_sent": False,
            "message": msg,
        }

    # Else: count > trigger -> Threshold exceeded! Create deferred one-time schedule with fire_alarm
    cfg = get_alarm_config()
    system_enabled = cfg.get("enabled", True)

    notif_requested = is_truthy(notification)
    speak_requested = is_truthy(speak)

    notif_sent = False
    speak_sent = False
    action_notes = []

    if not system_enabled:
        msg = (
            f"ALARM THRESHOLD EXCEEDED for '{clean_entity}' ({count} > {clean_trigger} in {clean_seconds}s), "
            f"but Alarm System is globally DISABLED in configuration. Actions suppressed."
        )
        logger.warning("[check_alarm] %s", msg)
        return {
            "alarm_triggered": True,
            "entity": clean_entity,
            "count": count,
            "trigger": clean_trigger,
            "seconds": clean_seconds,
            "delay_seconds": 0,
            "schedule_id": None,
            "notification_scheduled": False,
            "speak_scheduled": False,
            "system_enabled": False,
            "message": msg,
        }

    # Resolve device details
    resolved_device_name = None
    resolved_device_type = None
    try:
        for d in db_list_devices():
            if d.get("entity_id") == clean_entity or d.get("name") == clean_entity:
                resolved_device_name = d.get("name")
                resolved_device_type = d.get("type")
                break
    except Exception as exc:
        logger.warning("[check_alarm] Could not look up device info for %s: %s", clean_entity, exc)

    if not resolved_device_name:
        resolved_device_name = clean_entity
    if not resolved_device_type:
        resolved_device_type = clean_entity.split(".")[0] if "." in clean_entity else "sensor"

    delay_seconds = max(0, int(cfg.get("delay_seconds", 30)))

    # Schedule deferred one-time schedule with executable function 'fire_alarm'
    schedule_info = schedule_deferred_fire_alarm(
        entity=clean_entity,
        device_name=resolved_device_name,
        device_type=resolved_device_type,
        trigger=clean_trigger,
        seconds=clean_seconds,
        count=count,
        notification=notif_requested,
        speak=speak_requested,
        delay_seconds=delay_seconds,
    )

    sched_id = schedule_info.get("id")
    msg = (
        f"ALARM THRESHOLD EXCEEDED for '{clean_entity}' ({count} > {clean_trigger} in {clean_seconds}s). "
        f"Deferred one-time schedule #{sched_id or 'N/A'} created with {delay_seconds}s delay to execute 'fire_alarm'."
    )
    logger.info("[check_alarm] %s", msg)

    return {
        "alarm_triggered": True,
        "entity": clean_entity,
        "count": count,
        "trigger": clean_trigger,
        "seconds": clean_seconds,
        "delay_seconds": delay_seconds,
        "schedule_id": sched_id,
        "notification_scheduled": notif_requested,
        "speak_scheduled": speak_requested,
        "system_enabled": True,
        "message": msg,
    }


def schedule_deferred_fire_alarm(
    entity: str,
    device_name: str,
    device_type: str,
    trigger: int,
    seconds: int,
    count: int,
    notification: bool,
    speak: bool,
    delay_seconds: int,
) -> Dict[str, Any]:
    """
    Creates a deferred one-time schedule to run executable function 'fire_alarm' after delay_seconds.
    One-time schedule never has notification and speak configured itself; they are passed in data.
    """
    try:
        from app.scheduler import create_and_register_schedule, APP_TIMEZONE
    except ImportError:
        try:
            from scheduler import create_and_register_schedule, APP_TIMEZONE
        except ImportError:
            from zoneinfo import ZoneInfo
            APP_TIMEZONE = ZoneInfo("Europe/Madrid")
            create_and_register_schedule = None

    now_local = datetime.now(APP_TIMEZONE) if 'APP_TIMEZONE' in locals() and APP_TIMEZONE else datetime.now()
    target_dt = now_local + timedelta(seconds=max(0, delay_seconds))
    sched_name = f"Fire Alarm - {device_name} (deferred)"

    deferred_data = {
        "type": "alarm",
        "deferred": True,
        "entity": entity,
        "device_name": device_name,
        "device_type": device_type,
        "trigger": trigger,
        "seconds": seconds,
        "count": count,
        "notification": bool(notification),
        "speak": bool(speak),
    }

    if create_and_register_schedule is None:
        logger.warning("[alarm] create_and_register_schedule not available; skipping schedule creation.")
        return {"id": None}

    try:
        new_schedule = create_and_register_schedule(
            name=sched_name,
            schedule_type="one-time",
            trigger_spec=target_dt.isoformat(),
            use_case="fire_alarm",
            data=json.dumps(deferred_data),
            notify=0,
            notification_message="",
            speak=0,
            speak_message="",
        )
        logger.info(
            "[alarm] Created deferred one-time schedule #%s ('%s') at %s (delay: %ss)",
            new_schedule.get("id"),
            sched_name,
            target_dt.strftime("%Y-%m-%d %H:%M:%S"),
            delay_seconds,
        )
        return new_schedule
    except Exception as exc:
        logger.error("[alarm] Failed to create deferred fire_alarm schedule for '%s': %s", entity, exc)
        return {"id": None, "error": str(exc)}


def delete_deferred_alarm_schedules() -> int:
    """
    Delete all scheduled one-times of type alarm and deferred.
    Removes them from APScheduler memory and SQLite database.
    Returns the number of deleted schedules.
    """
    try:
        from app.database import db_list_schedules
        from app.scheduler import delete_and_remove_schedule
    except ImportError:
        try:
            from database import db_list_schedules
            from scheduler import delete_and_remove_schedule
        except ImportError:
            return 0

    deleted_count = 0
    try:
        schedules = db_list_schedules()
    except Exception as exc:
        logger.warning("[alarm] Could not list schedules to delete deferred: %s", exc)
        return 0

    for s in schedules:
        if s.get("type") == "one-time" and s.get("is_active") == 1:
            is_alarm = False
            is_deferred = False

            use_case = (s.get("use_case") or "").lower()
            name = (s.get("name") or "").lower()

            if use_case in ("fire_alarm", "check_alarm", "alarm") or "alarm" in name:
                is_alarm = True

            if "(deferred)" in name:
                is_deferred = True

            raw_data = s.get("data")
            if raw_data:
                try:
                    d = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                    if isinstance(d, dict):
                        if d.get("deferred"):
                            is_deferred = True
                        if d.get("type") == "alarm" or d.get("source") == "alarm":
                            is_alarm = True
                except Exception:
                    pass

            if is_alarm and is_deferred:
                try:
                    delete_and_remove_schedule(s["id"])
                    deleted_count += 1
                    logger.info("[alarm] Disarm: deleted deferred alarm schedule #%s ('%s')", s["id"], s.get("name"))
                except Exception as exc:
                    logger.warning("[alarm] Failed to delete deferred schedule #%s: %s", s["id"], exc)

    return deleted_count


def is_alarm_on() -> bool:
    """
    Check if the alarm system is currently on / mounted (armed).
    Evaluates both the stored configuration and live Home Assistant helper entity state if configured.
    """
    cfg = get_alarm_config()
    is_on = bool(cfg.get("enabled", False))
    helper = (cfg.get("helper_entity") or "").strip()
    if helper:
        try:
            from app.homeassistant import get_entity_state
        except ImportError:
            from homeassistant import get_entity_state
        try:
            st = get_entity_state(helper)
            if st is not None:
                is_on = st.strip().lower() in ("on", "armed", "armed_home", "armed_away", "true", "1")
        except Exception as exc:
            logger.warning("[alarm] Could not query helper entity '%s': %s", helper, exc)
    return is_on


async def fire_alarm_actions(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executable function handler logic for 'fire_alarm'.
    Fires notification and/or speaker announcement as configured in data parameters.
    Suppresses actions if alarm system was disarmed/disabled during delay or is not on/mounted.
    """
    clean_entity = str(params.get("entity") or "sensor").strip()
    resolved_device_name = params.get("device_name") or clean_entity
    resolved_device_type = params.get("device_type") or (clean_entity.split(".")[0] if "." in clean_entity else "sensor")
    trigger = params.get("trigger", 2)
    seconds = params.get("seconds", 60)
    count = params.get("count", 1)
    notif_requested = is_truthy(params.get("notification", True))
    speak_requested = is_truthy(params.get("speak", False))

    if not is_alarm_on():
        msg = (
            f"ALARM SUPPRESSED for '{clean_entity}': Alarm is NOT on/mounted (disarmed/off). "
            f"Notification and audio skipped."
        )
        logger.warning("[fire_alarm] %s", msg)
        delete_deferred_alarm_schedules()
        return {
            "alarm_fired": False,
            "system_enabled": False,
            "entity": clean_entity,
            "message": msg,
        }

    cfg = get_alarm_config()

    # Render static message templates with dynamic tags (defined in settings section)
    notif_template = cfg.get("notification_message") or DEFAULT_ALARM_CONFIG["notification_message"]
    speak_template = cfg.get("speak_message") or DEFAULT_ALARM_CONFIG["speak_message"]

    now = datetime.now()
    rendered_notif = render_alarm_message(
        template=notif_template,
        entity=clean_entity,
        trigger=trigger,
        seconds=seconds,
        count=count,
        dt=now,
        device_name=resolved_device_name,
        device_type=resolved_device_type,
    )

    rendered_speak = render_alarm_message(
        template=speak_template,
        entity=clean_entity,
        trigger=trigger,
        seconds=seconds,
        count=count,
        dt=now,
        device_name=resolved_device_name,
        device_type=resolved_device_type,
    )

    notif_sent = False
    speak_sent = False
    action_notes = []

    # Dispatch notification if requested
    if notif_requested:
        try:
            await dispatch_notifications(
                message=rendered_notif,
                source_type="alarm",
                source_id=None,
                source_name=f"Alarm: {resolved_device_name}",
            )
            notif_sent = True
            action_notes.append("Notification sent")
            logger.info("[fire_alarm] Notification dispatched: '%s'", rendered_notif)
        except Exception as n_err:
            logger.error("[fire_alarm] Failed to dispatch notification: %s", n_err)
            action_notes.append(f"Notification error: {n_err}")

    # Dispatch speaker broadcast if requested
    if speak_requested:
        try:
            broadcast_chime_tts(message=rendered_speak, force=True)
            speak_sent = True
            action_notes.append("Speaker broadcast sent")
            logger.info("[fire_alarm] Speaker broadcast dispatched: '%s'", rendered_speak)
        except Exception as s_err:
            logger.error("[fire_alarm] Failed to broadcast to speaker: %s", s_err)
            action_notes.append(f"Speaker error: {s_err}")

    actions_summary = "; ".join(action_notes) if action_notes else "No actions requested in parameters"
    msg = (
        f"🚨 ALARM FIRED for '{clean_entity}': {count} events in {seconds}s (Threshold: {trigger}). "
        f"[{actions_summary}]"
    )

    return {
        "alarm_fired": True,
        "entity": clean_entity,
        "count": count,
        "trigger": trigger,
        "seconds": seconds,
        "notification_sent": notif_sent,
        "speak_sent": speak_sent,
        "system_enabled": True,
        "notification_message": rendered_notif if notif_sent else None,
        "speak_message": rendered_speak if speak_sent else None,
        "message": msg,
    }
