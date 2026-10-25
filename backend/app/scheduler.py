import asyncio
import inspect
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

try:
    from app.database import (
        db_create_holiday,
        db_create_schedule,
        db_deactivate_schedule,
        db_delete_schedule,
        db_get_active_schedules,
        db_get_active_event_definitions_by_type,
        db_get_default_heating_map,
        db_get_heating_map,
        db_get_heating_map_by_name,
        db_get_heating_state,
        db_get_holiday_by_date,
        db_get_schedule,
        db_get_use_case,
        db_get_use_case_by_name,
        db_is_holiday,
        db_list_devices,
        db_list_heating_maps,
        db_list_schedules,
        db_list_use_cases,
        db_list_use_cases_by_section,
        db_set_active_heating_map,
        db_set_heating_state,
        db_set_schedule_block,
        db_update_schedule,
        db_get_setting,
        db_list_heating_calendar,
        db_resolve_current_heating_map,
    )
    from app.homeassistant import call_homeassistant_service
except ImportError:
    from database import (
        db_create_holiday,
        db_create_schedule,
        db_deactivate_schedule,
        db_delete_schedule,
        db_get_active_schedules,
        db_get_active_event_definitions_by_type,
        db_get_default_heating_map,
        db_get_heating_map,
        db_get_heating_map_by_name,
        db_get_heating_state,
        db_get_holiday_by_date,
        db_get_schedule,
        db_get_use_case,
        db_get_use_case_by_name,
        db_is_holiday,
        db_list_devices,
        db_list_heating_maps,
        db_list_schedules,
        db_list_use_cases,
        db_list_use_cases_by_section,
        db_set_active_heating_map,
        db_set_heating_state,
        db_set_schedule_block,
        db_update_schedule,
        db_get_setting,
        db_list_heating_calendar,
        db_resolve_current_heating_map,
    )
    from homeassistant import call_homeassistant_service

logger = logging.getLogger(__name__)

# System / Local timezone configuration (Europe/Madrid - CET/CEST)
TIMEZONE_NAME = os.getenv("TIMEZONE", "Europe/Madrid")
try:
    APP_TIMEZONE = ZoneInfo(TIMEZONE_NAME)
except Exception:
    APP_TIMEZONE = ZoneInfo("Europe/Madrid")

# Global in-memory scheduler instance configured in local timezone
scheduler = AsyncIOScheduler(timezone=APP_TIMEZONE)

# Task handlers registry: maps use_case string -> callable handler
TASK_HANDLERS: Dict[str, Callable] = {}


def fn_create_datetime_file(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
) -> str:
    """Create a text file with current local datetime as filename."""
    output_dir = Path(__file__).resolve().parent.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    now_local = datetime.now(APP_TIMEZONE)
    # File name format: YYYY-MM-DD_HH-mm-ss.txt (safe across Windows/Linux)
    filename = now_local.strftime("%Y-%m-%d_%H-%M-%S.txt")
    file_path = output_dir / filename

    content = (
        f"IoT Scheduled Task Execution\n"
        f"============================\n"
        f"File Created: {now_local.strftime('%d-%m-%Y %H:%M:%S')} (Europe/Madrid)\n"
        f"Schedule ID: {schedule_id if schedule_id is not None else 'Manual Test'}\n"
        f"Schedule Name: {name or 'Manual Trigger'}\n"
        f"Schedule Type: {schedule_type or 'Manual'}\n"
        f"Use Case: {use_case or 'test'}\n"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Created datetime text file: %s", file_path)
    return str(file_path)


async def fn_start_irrigation(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: start_irrigation
    Receives in data: entity_id and seconds.
    Puts on the entity_id in HA, sleeps for seconds, and then puts off the entity_id.
    """
    import json
    params = {}
    if isinstance(data, str) and data.strip():
        try:
            params = json.loads(data)
        except Exception:
            params = {}
    elif isinstance(data, dict):
        params = data

    entity_id = params.get("entity_id") or params.get("device_id")
    try:
        seconds = float(params.get("seconds", 0))
    except (TypeError, ValueError):
        seconds = 0.0

    if not entity_id:
        entity_id = "switch.garden_irrigation_zone1"
        logger.warning("[start_irrigation] No entity_id in data, using default '%s'", entity_id)

    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"

    logger.info("[start_irrigation] Turning ON entity '%s'", entity_id)
    call_homeassistant_service(domain=domain, service="turn_on", entity_id=entity_id)

    if seconds > 0:
        logger.info("[start_irrigation] Sleeping for %s seconds before turning OFF...", seconds)
        await asyncio.sleep(seconds)

    logger.info("[start_irrigation] Turning OFF entity '%s'", entity_id)
    call_homeassistant_service(domain=domain, service="turn_off", entity_id=entity_id)

    msg = f"Irrigation completed for '{entity_id}' (duration: {seconds}s)"
    logger.info("[start_irrigation] %s", msg)
    return msg


async def fn_move_blind(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: move_blind
    Receives in data parameters: entity (or entity_id), position, and optional not_before ("HH:MM").
    If not_before is provided and its hour is after current local time, defers execution by
    creating a one-time schedule for today at the indicated hour (with not_before blank).
    Otherwise, moves blind to target position (0-100%) immediately.
    """
    import json
    params = {}
    if isinstance(data, str) and data.strip():
        try:
            params = json.loads(data)
        except Exception:
            params = {}
    elif isinstance(data, dict):
        params = data

    entity_id = params.get("entity_id") or params.get("entity") or params.get("device_id")
    try:
        position = int(params.get("position", 0))
    except (TypeError, ValueError):
        position = 0

    # Clamp position to valid range [0, 100]
    position = max(0, min(100, position))

    if not entity_id:
        entity_id = "cover.living_room_blind"
        logger.warning("[move_blind] No entity in data, using default '%s'", entity_id)

    # Check for not_before constraint
    not_before_raw = params.get("not_before")
    not_before_str = str(not_before_raw).strip() if not_before_raw is not None else ""

    if not_before_str:
        try:
            parts = [int(p.strip()) for p in not_before_str.split(":") if p.strip()]
            if parts:
                nb_hour = parts[0]
                nb_minute = parts[1] if len(parts) > 1 else 0
                nb_second = parts[2] if len(parts) > 2 else 0

                now_local = datetime.now(APP_TIMEZONE)
                target_dt = now_local.replace(
                    hour=nb_hour,
                    minute=nb_minute,
                    second=nb_second,
                    microsecond=0,
                )

                if target_dt > now_local:
                    # Target time is later today -> defer by creating a one-time schedule
                    target_use_case = use_case
                    if not target_use_case:
                        try:
                            all_ucs = db_list_use_cases()
                            blind_uc = next((u for u in all_ucs if u.get("function_name") == "move_blind"), None)
                            target_use_case = blind_uc["name"] if blind_uc else "move_blind"
                        except Exception:
                            target_use_case = "move_blind"

                    deferred_data = {
                        "entity": entity_id,
                        "entity_id": entity_id,
                        "position": position,
                        "not_before": "",
                    }

                    sched_name = name or f"Auto - Blinds (not_before {not_before_str})"
                    new_schedule = create_and_register_schedule(
                        name=sched_name,
                        schedule_type="one-time",
                        trigger_spec=target_dt.isoformat(),
                        use_case=target_use_case,
                        data=json.dumps(deferred_data),
                    )

                    msg = (
                        f"Blind '{entity_id}' movement deferred until {not_before_str} "
                        f"(one-time schedule #{new_schedule['id']} created for {target_dt.strftime('%H:%M:%S')})"
                    )
                    logger.info("[move_blind] %s", msg)
                    return msg
        except Exception as exc:
            logger.warning("[move_blind] Error checking not_before='%s': %s. Moving blind now.", not_before_str, exc)

    domain = entity_id.split(".")[0] if "." in entity_id else "cover"

    logger.info("[move_blind] Moving blind '%s' to position %s%%", entity_id, position)
    call_homeassistant_service(
        domain=domain,
        service="set_cover_position",
        entity_id=entity_id,
        service_data={"position": position},
    )

    msg = f"Moved blind '{entity_id}' to position {position}%"
    logger.info("[move_blind] %s", msg)
    return msg


async def fn_add_holiday(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: add_holiday
    Receives in data parameter 'when' with 2 possible values: 'today' or 'tomorrow'.
    Adds the indicated date to the holidays list in SQLite.
    """
    import json
    from datetime import timedelta

    params = {}
    if isinstance(data, str) and data.strip():
        try:
            params = json.loads(data)
        except Exception:
            raw_val = data.strip().lower()
            if raw_val in ("today", "tomorrow"):
                params = {"when": raw_val}
            else:
                params = {}
    elif isinstance(data, dict):
        params = data

    when_val = str(params.get("when", "today")).strip().lower()
    now_local = datetime.now(APP_TIMEZONE)

    if when_val == "tomorrow":
        target_date = (now_local + timedelta(days=1)).strftime("%Y-%m-%d")
        default_name = "Holiday (Tomorrow)"
    else:
        when_val = "today"
        target_date = now_local.strftime("%Y-%m-%d")
        default_name = "Holiday (Today)"

    holiday_name = params.get("name") or default_name

    # Check if holiday already exists
    existing = db_get_holiday_by_date(target_date)
    if existing:
        msg = f"Holiday for {target_date} ({when_val}) already exists in holidays list (ID #{existing['id']})"
        logger.info("[add_holiday] %s", msg)
        return msg

    try:
        created = db_create_holiday(date=target_date, name=holiday_name)
        msg = f"Added holiday for {target_date} ({when_val}) with ID #{created['id']}"
        logger.info("[add_holiday] %s", msg)
        return msg
    except Exception as exc:
        msg = f"Error adding holiday for {target_date} ({when_val}): {exc}"
        logger.error("[add_holiday] %s", msg)
        return msg


async def fn_get_year_holidays(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: get_year_holidays
    Calls the Nager.Date API URL: https://date.nager.at/api/v3/publicholidays/{year}/ES
    where year defaults to current year ($today.year).
    Accepts only results of the county specified as parameter in data, by default 'ES-CT'.
    Adds public holidays of the year for that county directly into the holidays table.
    Checks every register to prevent duplicate dates.
    """
    import json
    import urllib.request
    import urllib.error

    now_local = datetime.now(APP_TIMEZONE)
    target_year = now_local.year
    target_county = "ES-CT"

    if data:
        params = {}
        if isinstance(data, str) and data.strip():
            try:
                params = json.loads(data)
            except Exception:
                stripped = data.strip()
                if stripped.isdigit():
                    params = {"year": int(stripped)}
                else:
                    params = {"county": stripped}
        elif isinstance(data, dict):
            params = data

        if "year" in params and str(params["year"]).isdigit():
            target_year = int(params["year"])

        if "county" in params and params["county"] is not None:
            c_str = str(params["county"]).strip()
            if c_str:
                target_county = c_str

    url = f"https://date.nager.at/api/v3/publicholidays/{target_year}/ES"
    logger.info("[get_year_holidays] Calling API: %s (county: %s)", url, target_county)

    try:
        def _fetch():
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "IoT-App/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                return json.loads(resp.read().decode("utf-8"))

        loop = asyncio.get_running_loop()
        holidays_list = await loop.run_in_executor(None, _fetch)
    except Exception as exc:
        msg = f"Error fetching public holidays for year {target_year} from {url}: {exc}"
        logger.error("[get_year_holidays] %s", msg)
        return msg

    if not isinstance(holidays_list, list):
        msg = f"Unexpected response from {url}: expected list, got {type(holidays_list).__name__}"
        logger.error("[get_year_holidays] %s", msg)
        return msg

    added_count = 0
    skipped_count = 0
    filtered_out_count = 0
    seen_in_payload = set()

    norm_county = target_county.strip().upper()

    for item in holidays_list:
        if not isinstance(item, dict):
            continue
        date_str = item.get("date")
        if not date_str:
            continue
        date_str = str(date_str).strip()

        # Check county filter: national holidays (global or no counties) apply to all counties
        is_global = bool(item.get("global")) or not item.get("counties")
        item_counties = [str(c).strip().upper() for c in (item.get("counties") or [])]

        county_matches = False
        if norm_county in ("ALL", "*"):
            county_matches = True
        elif is_global:
            county_matches = True
        elif norm_county in item_counties or (not norm_county.startswith("ES-") and f"ES-{norm_county}" in item_counties):
            county_matches = True

        if not county_matches:
            filtered_out_count += 1
            continue

        # Prevent duplicate dates within the same API payload
        if date_str in seen_in_payload:
            skipped_count += 1
            continue
        seen_in_payload.add(date_str)

        # Prevent duplicate dates in the database
        existing = db_get_holiday_by_date(date_str)
        if existing:
            skipped_count += 1
            continue

        holiday_name = item.get("localName") or item.get("name") or "Public Holiday"
        try:
            db_create_holiday(date=date_str, name=holiday_name)
            added_count += 1
        except Exception as exc:
            logger.warning("[get_year_holidays] Could not insert holiday for %s: %s", date_str, exc)
            skipped_count += 1

    msg = (
        f"Imported {added_count} holidays for year {target_year} (county: {target_county}) "
        f"from {url} ({skipped_count} skipped/duplicates, {filtered_out_count} other counties filtered)."
    )
    logger.info("[get_year_holidays] %s", msg)
    return msg


async def fn_send_telegram_alert(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: send_telegram_alert
    Dispatches an alert notification message to Telegram.
    Accepts string or JSON object with 'message', optional 'chat_id' and 'parse_mode'.
    """
    import json
    try:
        from app.telegram import send_telegram_message
    except ImportError:
        from telegram import send_telegram_message

    msg_text = "🚨 IoT System Alert"
    target_chat = None
    parse_mode = "HTML"

    if data:
        if isinstance(data, str):
            clean_data = data.strip()
            if clean_data.startswith("{") and clean_data.endswith("}"):
                try:
                    payload = json.loads(clean_data)
                    msg_text = payload.get("message") or payload.get("text") or msg_text
                    target_chat = payload.get("chat_id")
                    parse_mode = payload.get("parse_mode", "HTML")
                except Exception:
                    msg_text = clean_data
            else:
                msg_text = clean_data
        elif isinstance(data, dict):
            msg_text = data.get("message") or data.get("text") or msg_text
            target_chat = data.get("chat_id")
            parse_mode = data.get("parse_mode", "HTML")

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(
        None,
        lambda: send_telegram_message(
            message=msg_text,
            chat_id=target_chat,
            parse_mode=parse_mode,
        ),
    )

    if res.get("success"):
        return res.get("message", f"Telegram alert delivered: {msg_text}")
    else:
        return f"Failed to deliver Telegram alert: {res.get('error')}"


async def fn_start_heating(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: start_heating
    Receives in data the 'action' parameter ('on' or 'off').
    Activates or deactivates the heating system and stores heating state in SQLite.
    When deactivated ('off'): turns off all configured devices marked as 'heating'.
    When activated ('on'): does nothing to devices for the moment.
    """
    import json

    params = {}
    if isinstance(data, str) and data.strip():
        try:
            params = json.loads(data)
        except Exception:
            clean_str = data.strip().lower()
            if clean_str in ("on", "off"):
                params = {"action": clean_str}
            else:
                params = {}
    elif isinstance(data, dict):
        params = data

    action = str(params.get("action", "on")).strip().lower()
    deactivated_until = params.get("deactivated_until")

    if action == "off":
        db_set_heating_state(state="off", deactivated_until=deactivated_until)
        sync_heating_recurrent_schedule(False)
        heating_devices = db_list_devices(device_type="heating")
        switched_off = []
        for dev in heating_devices:
            entity_id = dev.get("entity_id")
            if not entity_id:
                continue
            domain = entity_id.split(".")[0] if "." in entity_id else "switch"
            if domain == "climate":
                call_homeassistant_service(
                    domain="climate",
                    service="set_hvac_mode",
                    entity_id=entity_id,
                    service_data={"hvac_mode": "off"},
                )
            else:
                call_homeassistant_service(
                    domain=domain,
                    service="turn_off",
                    entity_id=entity_id,
                )
            switched_off.append(entity_id)

        msg = f"Heating system deactivated (state: off). Switched off {len(switched_off)} heating device(s)."
        if deactivated_until:
            msg += f" Deactivated until {deactivated_until}."
        logger.info("[start_heating] %s", msg)
        return msg
    else:
        # action == "on"
        db_set_heating_state(state="on", deactivated_until=None)
        sync_heating_recurrent_schedule(True)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(fn_control_heating())
        except Exception:
            pass
        msg = "Heating system activated (state: on). Recurrent heating schedule activated."
        logger.info("[start_heating] %s", msg)
        return msg


async def fn_set_heating_map(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: set_heating_map
    Receives in data the target map identifier:
    e.g. {'map_id': 1} or {'map_name': 'Comfort'} or {'heating_map': 'Eco'} or string 'Comfort'.
    Sets the active heating map in the database.
    """
    import json

    params = {}
    if isinstance(data, str) and data.strip():
        try:
            params = json.loads(data)
        except Exception:
            clean_str = data.strip()
            if clean_str.isdigit():
                params = {"map_id": int(clean_str)}
            else:
                params = {"map_name": clean_str}
    elif isinstance(data, dict):
        params = data

    map_id = params.get("map_id")
    map_name = params.get("map_name") or params.get("heating_map") or params.get("name")

    target_map = None
    if map_id is not None:
        try:
            target_map = db_get_heating_map(int(map_id))
        except (ValueError, TypeError):
            pass

    if not target_map and map_name:
        target_map = db_get_heating_map_by_name(str(map_name).strip())

    if not target_map:
        target_map = db_get_default_heating_map()
        if not target_map:
            msg = "No heating maps available in database to activate"
            logger.warning("[set_heating_map] %s", msg)
            return msg

    db_set_active_heating_map(target_map["id"])
    msg = f"Active heating map changed to '{target_map['name']}' (ID #{target_map['id']})"
    logger.info("[set_heating_map] %s", msg)
    return msg


async def fn_control_heating(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> str:
    """
    Executable function: control_heating
    Evaluates temperature sensors against the active heating map minimum temperature rules.
    If heating is turned off, skips control.
    If heating is turned on, checks all temperature sensors with configured minimum thresholds.
    Turns on heating devices if any sensor is below minimum threshold, turns off if all satisfied.
    """
    import json

    # 1. Check heating system state
    state_info = db_get_heating_state()
    if state_info.get("state") != "on":
        msg = "Heating system is currently deactivated (state: off). Control heating skipped."
        logger.info("[control_heating] %s", msg)
        return msg

    # 2. Review Weekly Heating Calendar to determine the current heating map!
    now_local = datetime.now(APP_TIMEZONE)
    active_map = db_resolve_current_heating_map(now_local)
    if not active_map:
        active_map = state_info.get("active_map") or db_get_default_heating_map()

    if not active_map:
        msg = "No heating map found in database. Control heating skipped."
        logger.warning("[control_heating] %s", msg)
        return msg

    # Reflect resolved map in heating_state if different
    if state_info.get("active_map_id") != active_map.get("id"):
        try:
            db_set_active_heating_map(active_map["id"])
        except Exception:
            pass

    map_name = active_map.get("name", "Unknown")
    rules = active_map.get("rules", {})
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except Exception:
            rules = {}

    # 3. Get temperature sensors and heating devices
    temp_devices = db_list_devices(device_type="temperature")
    heating_devices = db_list_devices(device_type="heating")

    if not heating_devices:
        msg = f"Heating map '{map_name}' active, but no heating devices are configured in the system."
        logger.warning("[control_heating] %s", msg)
        return msg

    # 4. Fetch Home Assistant entities
    loop = asyncio.get_running_loop()
    try:
        from app.homeassistant import fetch_homeassistant_entities, call_homeassistant_service
    except ImportError:
        from homeassistant import fetch_homeassistant_entities, call_homeassistant_service

    ha_data = await loop.run_in_executor(None, fetch_homeassistant_entities)
    entities = ha_data.get("entities", [])
    entity_states: Dict[str, str] = {e["entity_id"]: str(e.get("state", "")) for e in entities if "entity_id" in e}

    # 5. Evaluate temperature sensors with configured rules
    below_threshold = []
    satisfied = []
    skipped = []
    target_temperatures = []

    for dev in temp_devices:
        dev_id = str(dev.get("id"))
        entity_id = dev.get("entity_id", "")
        dev_name = dev.get("name") or entity_id

        rule_val = rules.get(dev_id)
        if rule_val is None and entity_id:
            rule_val = rules.get(entity_id)

        # If no temperature defined, ignore the device
        if rule_val is None or str(rule_val).strip() == "":
            skipped.append(dev_name)
            continue

        try:
            min_temp = float(rule_val)
        except (ValueError, TypeError):
            continue

        raw_state = entity_states.get(entity_id)
        if raw_state is None:
            logger.warning("[control_heating] Sensor '%s' (%s) not found in Home Assistant states", dev_name, entity_id)
            continue

        try:
            current_temp = float(raw_state)
        except (ValueError, TypeError):
            logger.warning("[control_heating] Sensor '%s' (%s) state '%s' cannot be parsed as float", dev_name, entity_id, raw_state)
            continue

        if current_temp < min_temp:
            below_threshold.append(f"{dev_name}: {current_temp}°C < {min_temp}°C")
            target_temperatures.append(min_temp)
        else:
            satisfied.append(f"{dev_name}: {current_temp}°C >= {min_temp}°C")

    # 6. Apply heating actions
    if below_threshold:
        # At least one sensor below rule: start all devices marked as heating at full power (30.0°C)
        # to ensure all target temperatures across all rooms are effectively reached
        heating_setpoint = 30.0
        for dev in heating_devices:
            entity_id = dev.get("entity_id")
            if not entity_id:
                continue
            domain = entity_id.split(".")[0] if "." in entity_id else "switch"
            if domain == "climate":
                call_homeassistant_service(domain="climate", service="set_hvac_mode", entity_id=entity_id, service_data={"hvac_mode": "heat"})
                call_homeassistant_service(domain="climate", service="set_temperature", entity_id=entity_id, service_data={"temperature": heating_setpoint})
            else:
                call_homeassistant_service(domain=domain, service="turn_on", entity_id=entity_id, service_data={"temperature": heating_setpoint})

        msg = (
            f"Heating control evaluated (Map: '{map_name}'). "
            f"Heating REQUIRED by: [{', '.join(below_threshold)}]. "
            f"Started {len(heating_devices)} heating device(s) with temperature {heating_setpoint}°C."
        )
    elif satisfied:
        # If temperature is greater or equal: stop all devices marked as heating
        for dev in heating_devices:
            entity_id = dev.get("entity_id")
            if not entity_id:
                continue
            domain = entity_id.split(".")[0] if "." in entity_id else "switch"
            if domain == "climate":
                call_homeassistant_service(domain="climate", service="set_hvac_mode", entity_id=entity_id, service_data={"hvac_mode": "off"})
            else:
                call_homeassistant_service(domain=domain, service="turn_off", entity_id=entity_id)

        msg = (
            f"Heating control evaluated (Map: '{map_name}'). "
            f"All {len(satisfied)} sensor(s) satisfied. "
            f"Stopped {len(heating_devices)} heating device(s)."
        )
    else:
        # No rules matched any active sensors
        msg = (
            f"Heating control evaluated (Map: '{map_name}'). "
            f"No active temperature rules defined for available sensors. Heating devices untouched."
        )

    logger.info("[control_heating] %s", msg)
    return msg


SYSTEM_FUNCTIONS: Dict[str, Dict[str, Any]] = {
    "create_datetime_file": {
        "id": "create_datetime_file",
        "name": "Create Datetime Text File",
        "description": "Creates a text file named with the current local datetime (.txt) in the backend output folder",
        "handler": fn_create_datetime_file,
    },
    "start_irrigation": {
        "id": "start_irrigation",
        "name": "Start Irrigation",
        "description": "Turns ON entity_id, waits for seconds, and turns OFF entity_id",
        "handler": fn_start_irrigation,
    },
    "move_blind": {
        "id": "move_blind",
        "name": "Move Blind",
        "description": "Moves blind/cover entity to target position (0-100%)",
        "handler": fn_move_blind,
    },
    "add_holiday": {
        "id": "add_holiday",
        "name": "Add Holiday",
        "description": "Adds today or tomorrow to the holiday list (parameter 'when': 'today' | 'tomorrow')",
        "handler": fn_add_holiday,
    },
    "get_year_holidays": {
        "id": "get_year_holidays",
        "name": "Get Year Holidays",
        "description": "Calls Nager.Date API for Spain public holidays of the year filtered by county (defaults to 'ES-CT', parameter 'county' in data)",
        "handler": fn_get_year_holidays,
    },
    "send_telegram_alert": {
        "id": "send_telegram_alert",
        "name": "Send Telegram Alert",
        "description": "Dispatches an alert notification message to Telegram bot or configured chat",
        "handler": fn_send_telegram_alert,
    },
    "start_heating": {
        "id": "start_heating",
        "name": "Start Heating",
        "description": "Activates or deactivates the heating system (action parameter: 'on' or 'off')",
        "handler": fn_start_heating,
    },
    "control_heating": {
        "id": "control_heating",
        "name": "Control Heating",
        "description": "Evaluates temperature sensors against active heating map and regulates heating devices",
        "handler": fn_control_heating,
    },
    "set_heating_map": {
        "id": "set_heating_map",
        "name": "Set Heating Map",
        "description": "Changes the active heating map rule set",
        "handler": fn_set_heating_map,
    },
}


def register_task_handler(use_case: str):
    """Decorator to register a custom task handler for a given use_case."""
    def decorator(func: Callable):
        TASK_HANDLERS[use_case] = func
        logger.info("Registered task handler for use_case: '%s'", use_case)
        return func
    return decorator


async def default_task_handler(
    schedule_id: Optional[int] = None,
    name: Optional[str] = None,
    schedule_type: Optional[str] = None,
    use_case: Optional[str] = None,
    data: Optional[Any] = None,
) -> None:
    """Default fallback task handler when no specific use_case handler is registered."""
    logger.info(
        "[TASK EXECUTION] Schedule #%s ('%s') triggered! Type: %s | Use case: '%s' | Data: %s",
        schedule_id,
        name,
        schedule_type,
        use_case,
        data,
    )


async def dispatch_notifications(
    message: str,
    source_type: str,
    source_id: Optional[int] = None,
    source_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Finds all use cases with section='notification' and executes them with the notification message.
    """
    notification_use_cases = db_list_use_cases_by_section("notification")
    if not notification_use_cases:
        logger.info(
            "[NOTIFICATION] Notification requested for %s #%s ('%s'), but no use cases are marked with section='notification'",
            source_type,
            source_id,
            source_name,
        )
        return []

    logger.info(
        "[NOTIFICATION] Dispatching notification for %s #%s ('%s') to %d use case(s) with message: '%s'",
        source_type,
        source_id,
        source_name,
        len(notification_use_cases),
        message,
    )

    results = []
    for uc in notification_use_cases:
        fn_name = uc.get("function_name")
        fn_info = SYSTEM_FUNCTIONS.get(fn_name)
        if not fn_info:
            logger.warning("[NOTIFICATION] Function '%s' for use case '%s' not found", fn_name, uc.get("name"))
            continue

        handler = fn_info["handler"]
        try:
            sig = inspect.signature(handler)
            kwargs_to_pass = {
                "schedule_id": source_id,
                "name": f"Notification: {source_name}",
                "schedule_type": "notification",
                "use_case": uc.get("name"),
            }
            notif_data = {"message": message}
            if "data" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                kwargs_to_pass["data"] = notif_data

            if inspect.iscoroutinefunction(handler):
                res = await handler(**kwargs_to_pass)
            else:
                res = handler(**kwargs_to_pass)

            logger.info("[NOTIFICATION] Notification use case '%s' (%s) executed: %s", uc.get("name"), fn_name, res)
            results.append({"use_case": uc.get("name"), "status": "success", "result": str(res)})
        except Exception as exc:
            logger.exception("[NOTIFICATION] Error executing notification use case '%s': %s", uc.get("name"), exc)
            results.append({"use_case": uc.get("name"), "status": "error", "error": str(exc)})

    return results


async def execute_schedule_task(
    schedule_id: int,
    name: str,
    schedule_type: str,
    use_case: str,
    data: Optional[Any] = None,
    notify: int = 0,
    notification_message: Optional[str] = None,
) -> None:
    """
    Dispatcher triggered by the scheduler.
    Executes the appropriate task handler (from registry or DB-configured use case) and updates DB if one-time.
    If notify is enabled, dispatches notifications to all use cases in the 'notification' section.
    """
    logger.info("Dispatching task for schedule #%s ('%s') - Type: %s (notify: %s)", schedule_id, name, schedule_type, notify)
    
    # 1. Check code-registered handlers
    handler = TASK_HANDLERS.get(use_case)

    # 2. If not registered in code, check DB use_cases table
    if not handler:
        uc_record = db_get_use_case_by_name(use_case)
        if uc_record and uc_record.get("function_name") in SYSTEM_FUNCTIONS:
            handler = SYSTEM_FUNCTIONS[uc_record["function_name"]]["handler"]
        else:
            handler = default_task_handler

    try:
        sig = inspect.signature(handler)
        kwargs_to_pass = {
            "schedule_id": schedule_id,
            "name": name,
            "schedule_type": schedule_type,
            "use_case": use_case,
        }
        if "data" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            kwargs_to_pass["data"] = data

        if inspect.iscoroutinefunction(handler):
            await handler(**kwargs_to_pass)
        else:
            handler(**kwargs_to_pass)

        # 3. If notify is enabled, dispatch notification
        if notify:
            standard_msg = f"Schedule '{name}' executed successfully (Use case: {use_case})"
            override_msg = (notification_message or "").strip()
            final_msg = override_msg if override_msg else standard_msg
            await dispatch_notifications(
                message=final_msg,
                source_type="schedule",
                source_id=schedule_id,
                source_name=name,
            )
    except Exception as exc:
        logger.exception("Error executing task handler for schedule #%s: %s", schedule_id, exc)
    finally:
        # If it was a one-time schedule, remove it from memory and permanently delete from DB
        if schedule_type == "one-time":
            delete_and_remove_schedule(schedule_id)
            logger.info("One-time schedule #%s completed, removed from memory and deleted from DB.", schedule_id)


async def execute_use_case_test(use_case_id: int, test_data: Optional[Any] = None) -> Dict[str, Any]:
    """Manually test-execute the function linked to a use case."""
    uc = db_get_use_case(use_case_id)
    if not uc:
        raise ValueError(f"Use case #{use_case_id} not found")
    fn_name = uc.get("function_name")
    if fn_name not in SYSTEM_FUNCTIONS:
        raise ValueError(f"Function '{fn_name}' is not registered in system functions")

    handler = SYSTEM_FUNCTIONS[fn_name]["handler"]
    sig = inspect.signature(handler)
    kwargs_to_pass = {
        "schedule_id": None,
        "name": f"Manual Test ({uc['name']})",
        "schedule_type": "manual-test",
        "use_case": uc["name"],
    }
    if "data" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        kwargs_to_pass["data"] = test_data

    if inspect.iscoroutinefunction(handler):
        result = await handler(**kwargs_to_pass)
    else:
        result = handler(**kwargs_to_pass)

    return {
        "message": f"Successfully executed function '{fn_name}' for use case '{uc['name']}'",
        "result_file": result if isinstance(result, str) else str(result),
        "result": result,
    }


def is_holiday_or_weekend(dt: Optional[datetime] = None) -> bool:
    """
    Check if a datetime (defaulting to current local time in APP_TIMEZONE) is considered a holiday.
    Saturday (5) and Sunday (6) are always considered holidays.
    Any date registered in the holidays table is also considered a holiday.
    """
    if dt is None:
        dt = datetime.now(APP_TIMEZONE)
    # Weekday: Monday is 0, Saturday is 5, Sunday is 6
    if dt.weekday() in (5, 6):
        return True
    date_str = dt.strftime("%Y-%m-%d")
    return db_is_holiday(date_str)


async def dispatch_event_triggers(event_type: str, parameter: str = "") -> List[Dict[str, Any]]:
    """
    Find active event definitions matching event_type and execute their configured use cases.
    Respects the 'holiday' filter: 'all_days', 'holiday', or 'not_holiday'.
    """
    matching_definitions = db_get_active_event_definitions_by_type(event_type)
    triggered = []

    for defn in matching_definitions:
        def_id = defn["id"]
        name = defn["name"]
        use_case = defn["use_case"]
        data = defn.get("data", "{}")
        holiday_setting = defn.get("holiday") or "all_days"

        # Check holiday / weekend filter
        is_today_holiday = is_holiday_or_weekend()
        if holiday_setting == "holiday" and not is_today_holiday:
            logger.info(
                "[EVENT TRIGGER] Skipping event definition #%s ('%s'): filter is 'holiday' but today is not a holiday/weekend",
                def_id,
                name,
            )
            triggered.append({
                "definition_id": def_id,
                "name": name,
                "use_case": use_case,
                "status": "skipped",
                "result": "Skipped: only runs on holidays or weekends",
            })
            continue

        if holiday_setting == "not_holiday" and is_today_holiday:
            logger.info(
                "[EVENT TRIGGER] Skipping event definition #%s ('%s'): filter is 'not_holiday' but today is a holiday/weekend",
                def_id,
                name,
            )
            triggered.append({
                "definition_id": def_id,
                "name": name,
                "use_case": use_case,
                "status": "skipped",
                "result": "Skipped: only runs on working days (not holidays/weekends)",
            })
            continue

        logger.info(
            "[EVENT TRIGGER] Executing event definition #%s ('%s') for event '%s' (use_case: '%s', holiday: '%s')",
            def_id,
            name,
            event_type,
            use_case,
            holiday_setting,
        )

        handler = TASK_HANDLERS.get(use_case)
        if not handler:
            uc_record = db_get_use_case_by_name(use_case)
            if uc_record and uc_record.get("function_name") in SYSTEM_FUNCTIONS:
                handler = SYSTEM_FUNCTIONS[uc_record["function_name"]]["handler"]
            else:
                handler = default_task_handler

        try:
            sig = inspect.signature(handler)
            kwargs_to_pass = {
                "schedule_id": None,
                "name": name,
                "schedule_type": "event",
                "use_case": use_case,
            }
            if "data" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                kwargs_to_pass["data"] = data

            if inspect.iscoroutinefunction(handler):
                result = await handler(**kwargs_to_pass)
            else:
                result = handler(**kwargs_to_pass)

            # If notify is enabled for this event definition, dispatch notifications
            def_notify = defn.get("notify", 0)
            def_notif_msg = defn.get("notification_message", "")
            if def_notify:
                param_str = f": {parameter}" if parameter else ""
                standard_msg = f"Event '{name}' triggered [{event_type}{param_str}] -> Use case: {use_case}"
                override_msg = (def_notif_msg or "").strip()
                final_msg = override_msg if override_msg else standard_msg
                await dispatch_notifications(
                    message=final_msg,
                    source_type="event",
                    source_id=def_id,
                    source_name=name,
                )

            triggered.append({
                "definition_id": def_id,
                "name": name,
                "use_case": use_case,
                "status": "executed",
                "result": str(result) if result is not None else "OK",
            })
        except Exception as exc:
            logger.exception("Error executing event definition #%s: %s", def_id, exc)
            triggered.append({
                "definition_id": def_id,
                "name": name,
                "use_case": use_case,
                "status": "error",
                "error": str(exc),
            })

    return triggered


def parse_trigger(schedule_type: str, trigger_spec: str):
    """Parse trigger_spec into an APScheduler trigger based on schedule type in local timezone."""
    if schedule_type == "one-time":
        clean_spec = trigger_spec.replace("Z", "+00:00")
        run_date = datetime.fromisoformat(clean_spec)
        if run_date.tzinfo is None:
            run_date = run_date.replace(tzinfo=APP_TIMEZONE)
        else:
            run_date = run_date.astimezone(APP_TIMEZONE)
        return DateTrigger(run_date=run_date, timezone=APP_TIMEZONE)
    elif schedule_type == "recurrent":
        return CronTrigger.from_crontab(trigger_spec, timezone=APP_TIMEZONE)
    else:
        raise ValueError(f"Unsupported schedule type: '{schedule_type}'. Must be 'one-time' or 'recurrent'.")


def add_job_to_memory(schedule_data: Dict[str, Any]) -> Optional[str]:
    """Add or replace a schedule job in APScheduler memory."""
    schedule_id = schedule_data["id"]
    job_id = f"schedule_{schedule_id}"
    name = schedule_data["name"]
    schedule_type = schedule_data["type"]
    trigger_spec = schedule_data["trigger_spec"]
    use_case = schedule_data["use_case"]

    try:
        trigger = parse_trigger(schedule_type, trigger_spec)
    except Exception as exc:
        logger.error("Failed to parse trigger for schedule #%s ('%s'): %s", schedule_id, trigger_spec, exc)
        return None

    # Check if a one-time schedule is already in the past
    if schedule_type == "one-time":
        now_dt = datetime.now(APP_TIMEZONE)
        target_dt = trigger.run_date
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=APP_TIMEZONE)
        else:
            target_dt = target_dt.astimezone(APP_TIMEZONE)
        if target_dt < now_dt:
            logger.warning(
                "One-time schedule #%s ('%s') is in the past (%s < %s). Removing from DB.",
                schedule_id,
                name,
                target_dt,
                now_dt,
            )
            delete_and_remove_schedule(schedule_id)
            return None

    data = schedule_data.get("data", "{}")
    notify = schedule_data.get("notify", 0)
    notification_message = schedule_data.get("notification_message", "")

    scheduler.add_job(
        execute_schedule_task,
        trigger=trigger,
        id=job_id,
        name=name,
        replace_existing=True,
        kwargs={
            "schedule_id": schedule_id,
            "name": name,
            "schedule_type": schedule_type,
            "use_case": use_case,
            "data": data,
            "notify": notify,
            "notification_message": notification_message,
        },
    )
    logger.info("Loaded schedule #%s ('%s') into memory [%s - %s]", schedule_id, name, schedule_type, trigger_spec)
    return job_id


def restore_schedules_from_db() -> int:
    """Restore all active schedules from the database into in-memory scheduler."""
    active_schedules = db_get_active_schedules()
    restored_count = 0
    for schedule_item in active_schedules:
        job_id = add_job_to_memory(schedule_item)
        if job_id:
            restored_count += 1
    logger.info("Restored %d active schedule(s) from database into memory.", restored_count)
    return restored_count


def create_and_register_schedule(
    name: str,
    schedule_type: str,
    trigger_spec: str,
    use_case: str,
    data: Optional[Any] = "{}",
    notify: int = 0,
    notification_message: Optional[str] = None,
    block: int = 0,
) -> Dict[str, Any]:
    """Validate trigger, save to SQLite, and register into the in-memory scheduler."""
    parse_trigger(schedule_type, trigger_spec)
    schedule_data = db_create_schedule(
        name=name,
        schedule_type=schedule_type,
        trigger_spec=trigger_spec,
        use_case=use_case,
        data=data,
        notify=notify,
        notification_message=notification_message,
        block=block,
    )
    add_job_to_memory(schedule_data)
    return schedule_data


def cancel_and_deactivate_schedule(schedule_id: int) -> bool:
    """Remove a schedule from memory and mark inactive in DB."""
    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Removed job '%s' from in-memory scheduler.", job_id)
    return db_deactivate_schedule(schedule_id)


def update_and_reschedule(
    schedule_id: int,
    name: str,
    schedule_type: str,
    trigger_spec: str,
    use_case: str,
    is_active: int = 1,
    data: Optional[Any] = None,
    notify: Optional[int] = None,
    notification_message: Optional[str] = None,
    block: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Validate trigger, update SQLite record, and refresh in-memory job."""
    if is_active == 1:
        parse_trigger(schedule_type, trigger_spec)

    updated = db_update_schedule(
        schedule_id=schedule_id,
        name=name,
        schedule_type=schedule_type,
        trigger_spec=trigger_spec,
        use_case=use_case,
        is_active=is_active,
        data=data,
        notify=notify,
        notification_message=notification_message,
        block=block,
    )

    if not updated:
        return None

    job_id = f"schedule_{schedule_id}"
    if is_active == 1:
        add_job_to_memory(updated)
    else:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("Removed inactive job '%s' from memory after update.", job_id)

    return updated


def delete_and_remove_schedule(schedule_id: int) -> bool:
    """Permanently delete from database and remove from memory."""
    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Removed job '%s' from in-memory scheduler.", job_id)
    return db_delete_schedule(schedule_id)


def sync_heating_recurrent_schedule(heating_on: bool) -> Optional[Dict[str, Any]]:
    """
    Synchronizes the recurrent schedule for heating control:
    - Calculates the cron trigger_spec from 'heating_interval_minutes' setting.
    - When heating is ON: creates or activates the recurrent schedule in DB and APScheduler.
    - When heating is OFF: updates trigger_spec in DB to match settings, ensures is_active=0,
      and removes from memory if active.
    """
    sched_name = "Auto - Heating Control"
    all_schedules = db_list_schedules()
    existing_sched = next(
        (s for s in all_schedules if s.get("name") == sched_name),
        None
    )

    # 1. Retrieve interval minutes from settings (defaults to 5)
    try:
        interval_str = db_get_setting("heating_interval_minutes", "5")
        interval_mins = int(interval_str)
        if interval_mins < 1:
            interval_mins = 1
    except Exception:
        interval_mins = 5

    trigger_spec = f"*/{interval_mins} * * * *" if interval_mins < 60 else f"0 */{interval_mins // 60} * * *"

    # 2. Find use case: prioritize use case linked to control_heating
    all_ucs = db_list_use_cases()
    ctrl_uc = next(
        (u for u in all_ucs if u.get("function_name") == "control_heating" and u.get("section") == "heating_control"),
        None
    ) or next(
        (u for u in all_ucs if u.get("function_name") == "control_heating"),
        None
    )
    uc_name = ctrl_uc["name"] if ctrl_uc else "Heating Control"

    if heating_on:
        if existing_sched:
            sched_id = existing_sched["id"]
            updated = update_and_reschedule(
                schedule_id=sched_id,
                name=sched_name,
                schedule_type="recurrent",
                trigger_spec=trigger_spec,
                use_case=uc_name,
                is_active=1,
                data=existing_sched.get("data", "{}"),
                notify=existing_sched.get("notify", 0),
                notification_message=existing_sched.get("notification_message"),
                block=1,
            )
            logger.info("Activated/updated recurrent heating schedule #%s ('%s', spec: %s)", sched_id, sched_name, trigger_spec)
            return updated
        else:
            created = create_and_register_schedule(
                name=sched_name,
                schedule_type="recurrent",
                trigger_spec=trigger_spec,
                use_case=uc_name,
                data="{}",
                block=1,
            )
            logger.info("Created new recurrent heating schedule #%s ('%s', spec: %s)", created["id"], sched_name, trigger_spec)
            return created
    else:
        # Heating is OFF:
        # Always update trigger_spec with current interval setting, and keep is_active=0
        if existing_sched:
            sched_id = existing_sched["id"]
            updated = update_and_reschedule(
                schedule_id=sched_id,
                name=sched_name,
                schedule_type="recurrent",
                trigger_spec=trigger_spec,
                use_case=uc_name,
                is_active=0,
                data=existing_sched.get("data", "{}"),
                notify=existing_sched.get("notify", 0),
                notification_message=existing_sched.get("notification_message"),
                block=1,
            )
            logger.info("Deactivated/updated recurrent heating schedule #%s ('%s', spec: %s)", sched_id, sched_name, trigger_spec)
            return updated
        else:
            # Create inactive schedule in database so it is immediately visible in schedules
            created = db_create_schedule(
                name=sched_name,
                schedule_type="recurrent",
                trigger_spec=trigger_spec,
                use_case=uc_name,
                data="{}",
                notify=0,
                notification_message=None,
                block=1,
            )
            db_deactivate_schedule(created["id"])
            created["is_active"] = 0
            logger.info("Created inactive recurrent heating schedule #%s ('%s', spec: %s)", created["id"], sched_name, trigger_spec)
            return created


def get_memory_jobs_status() -> List[Dict[str, Any]]:
    """Get status of all currently active in-memory scheduled jobs in local timezone."""
    jobs_info = []
    for job in scheduler.get_jobs():
        next_run_iso = None
        if job.next_run_time:
            next_run_iso = job.next_run_time.astimezone(APP_TIMEZONE).isoformat()
        jobs_info.append({
            "job_id": job.id,
            "name": job.name,
            "next_run_time": next_run_iso,
        })
    return jobs_info


def start_scheduler():
    """Start the scheduler and restore schedules from DB."""
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")
    restore_schedules_from_db()


def shutdown_scheduler():
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down.")
