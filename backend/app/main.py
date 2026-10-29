import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from dotenv import load_dotenv
from fastapi import APIRouter, Body, FastAPI, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, model_validator
import uvicorn

# Define backend directory and load backend/.env
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

try:
    from app.logger_handler import memory_log_handler, setup_logging
except ImportError:
    from logger_handler import memory_log_handler, setup_logging

setup_logging(BACKEND_DIR)

try:
    from app.database import (
        db_create_device,
        db_create_event,
        db_create_event_definition,
        db_create_heating_map,
        db_create_holiday,
        db_create_use_case,
        db_delete_device,
        db_delete_event_definition,
        db_delete_heating_map,
        db_delete_holiday,
        db_delete_use_case,
        db_get_default_heating_map,
        db_get_device,
        db_get_event_definition,
        db_get_heating_map,
        db_get_heating_map_by_name,
        db_get_heating_state,
        db_get_holiday,
        db_is_holiday,
        db_get_schedule,
        db_get_setting,
        db_get_all_settings,
        db_set_setting,
        db_get_use_case,
        db_list_devices,
        db_list_events,
        db_list_event_definitions,
        db_list_heating_maps,
        db_list_heating_calendar,
        db_set_heating_calendar_day,
        db_set_heating_calendar_bulk,
        db_resolve_current_heating_map,
        db_list_holidays,
        db_list_schedules,
        db_list_use_cases,
        db_set_active_heating_map,
        db_set_default_heating_map,
        db_set_heating_state,
        db_set_schedule_block,
        db_update_device,
        db_update_event_definition,
        db_update_heating_map,
        db_update_use_case,
        init_db,
    )
    from app.homeassistant import (
        fetch_homeassistant_entities,
        check_homeassistant_connection,
        call_homeassistant_service,
    )
    from app.scheduler import (
        APP_TIMEZONE,
        SYSTEM_FUNCTIONS,
        cancel_and_deactivate_schedule,
        create_and_register_schedule,
        delete_and_remove_schedule,
        dispatch_event_triggers,
        execute_use_case_test,
        fn_set_heating_map,
        fn_start_heating,
        get_memory_jobs_status,
        shutdown_scheduler,
        start_scheduler,
        sync_heating_recurrent_schedule,
        update_and_reschedule,
    )
except ImportError:
    from database import (
        db_create_device,
        db_create_event,
        db_create_event_definition,
        db_create_heating_map,
        db_create_holiday,
        db_create_use_case,
        db_delete_device,
        db_delete_event_definition,
        db_delete_heating_map,
        db_delete_holiday,
        db_delete_use_case,
        db_get_default_heating_map,
        db_get_device,
        db_get_event_definition,
        db_get_heating_map,
        db_get_heating_map_by_name,
        db_get_heating_state,
        db_get_holiday,
        db_is_holiday,
        db_get_schedule,
        db_get_setting,
        db_get_all_settings,
        db_set_setting,
        db_get_use_case,
        db_list_devices,
        db_list_events,
        db_list_event_definitions,
        db_list_heating_maps,
        db_list_heating_calendar,
        db_set_heating_calendar_day,
        db_set_heating_calendar_bulk,
        db_resolve_current_heating_map,
        db_list_holidays,
        db_list_schedules,
        db_list_use_cases,
        db_set_active_heating_map,
        db_set_default_heating_map,
        db_set_heating_state,
        db_set_schedule_block,
        db_update_device,
        db_update_event_definition,
        db_update_heating_map,
        db_update_use_case,
        init_db,
    )
    from homeassistant import (
        fetch_homeassistant_entities,
        check_homeassistant_connection,
        call_homeassistant_service,
    )
    from scheduler import (
        APP_TIMEZONE,
        SYSTEM_FUNCTIONS,
        cancel_and_deactivate_schedule,
        create_and_register_schedule,
        delete_and_remove_schedule,
        dispatch_event_triggers,
        execute_use_case_test,
        fn_set_heating_map,
        fn_start_heating,
        get_memory_jobs_status,
        shutdown_scheduler,
        start_scheduler,
        sync_heating_recurrent_schedule,
        update_and_reschedule,
    )

logger = logging.getLogger("iot_backend")

API_KEY = os.getenv("API_KEY")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if not API_KEY:
    raise RuntimeError("API_KEY is not defined in the environment or .env file.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SQLite database and restore schedules into memory
    logger.info("Starting up IoT Backend...")
    init_db()
    start_scheduler()
    try:
        heating_st = db_get_heating_state()
        is_on = heating_st.get("state") == "on"
        sync_heating_recurrent_schedule(is_on)
        logger.info(
            "Heating system state restored from DB: %s (recurrent schedule active: %s)",
            heating_st.get("state"),
            is_on,
        )
    except Exception as exc:
        logger.warning("Could not sync heating recurrent schedule on startup: %s", exc)
    yield
    # Shutdown: Cleanly shut down scheduler
    logger.info("Shutting down IoT Backend...")
    shutdown_scheduler()


app = FastAPI(
    title="IoT Backend Service",
    description="Minimal backend for home IoT automation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    api_key_h: Optional[str] = Security(api_key_header),
    api_key_q: Optional[str] = Query(None, alias="api_key"),
) -> str:
    """Validate that the provided API key matches the configured API_KEY via header or query param."""
    key = api_key_h or api_key_q
    if not key or not secrets.compare_digest(key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return key


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Friendly name of the schedule")
    type: Literal["one-time", "recurrent"] = Field(..., description="Schedule type: 'one-time' or 'recurrent'")
    trigger_spec: str = Field(..., min_length=1, description="ISO-8601 datetime for one-time, or cron expression (e.g. '0 8 * * *') for recurrent")
    use_case: str = Field(..., min_length=1, description="Use case identifier for task execution")
    data: Optional[Any] = Field(default="{}", description="JSON parameters for task execution")
    notify: Optional[int] = Field(default=0, ge=0, le=1, description="1 to notify when executed, 0 otherwise")
    notification_message: Optional[str] = Field(default="", description="Optional custom notification message override")
    speak: Optional[int] = Field(default=0, ge=0, le=1, description="1 to speak announcement through speaker system when executed, 0 otherwise")
    speak_message: Optional[str] = Field(default="", description="Optional custom speech message override")
    block: Optional[int] = Field(default=0, ge=0, le=1, description="1 if blocked/protected from changes or deletion, 0 otherwise")


class ScheduleUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Friendly name of the schedule")
    type: Literal["one-time", "recurrent"] = Field(..., description="Schedule type: 'one-time' or 'recurrent'")
    trigger_spec: str = Field(..., min_length=1, description="ISO-8601 datetime for one-time, or cron expression for recurrent")
    use_case: str = Field(..., min_length=1, description="Use case identifier for task execution")
    is_active: int = Field(1, ge=0, le=1, description="Active status (1 for active, 0 for inactive)")
    data: Optional[Any] = Field(default=None, description="JSON parameters for task execution")
    notify: Optional[int] = Field(default=None, ge=0, le=1, description="1 to notify when executed, 0 otherwise")
    notification_message: Optional[str] = Field(default=None, description="Optional custom notification message override")
    speak: Optional[int] = Field(default=None, ge=0, le=1, description="1 to speak announcement through speaker system when executed, 0 otherwise")
    speak_message: Optional[str] = Field(default=None, description="Optional custom speech message override")
    block: Optional[int] = Field(default=None, ge=0, le=1, description="1 if blocked/protected from changes or deletion, 0 otherwise")


class ScheduleBlockRequest(BaseModel):
    block: int = Field(..., ge=0, le=1, description="1 to block/protect schedule, 0 to unblock")


@app.get("/ping")
@app.get("/health/ping")
@api_v1.get("/ping")
@api_v1.get("/health/ping")
def ping():
    """Unauthenticated health ping endpoint for container and orchestrator health checks."""
    return {"status": "ok"}


@api_v1.get("/health")
def health_check(_: str = Security(verify_api_key)):
    """Health check endpoint protected by API Key."""
    ha_connected = check_homeassistant_connection()
    try:
        from app.notifications import get_notification_channels
    except ImportError:
        try:
            from notifications import get_notification_channels
        except ImportError:
            get_notification_channels = None

    tg_connected = False
    if get_notification_channels:
        try:
            channels = get_notification_channels()
            tg_ch = next((c for c in channels if c.get("id") == "telegram"), None)
            if tg_ch:
                tg_connected = bool(tg_ch.get("status", {}).get("configured", False))
        except Exception as exc:
            logger.warning("[health] Error checking Telegram status: %s", exc)

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": ENVIRONMENT,
        "database": "connected",
        "scheduler": "running",
        "homeassistant": "connected" if ha_connected else "disconnected",
        "telegram": "connected" if tg_connected else "disconnected",
    }


@api_v1.get("/schedules")
def list_schedules(_: str = Security(verify_api_key)):
    """Retrieve all schedules from the database and current in-memory status."""
    return {
        "schedules": db_list_schedules(),
        "in_memory_jobs": get_memory_jobs_status(),
    }


@api_v1.post("/schedules", status_code=status.HTTP_201_CREATED)
def create_schedule(payload: ScheduleCreateRequest, _: str = Security(verify_api_key)):
    """Create a new schedule, save to SQLite, and register into memory."""
    try:
        schedule = create_and_register_schedule(
            name=payload.name,
            schedule_type=payload.type,
            trigger_spec=payload.trigger_spec,
            use_case=payload.use_case,
            data=payload.data,
            notify=payload.notify or 0,
            notification_message=payload.notification_message,
            speak=payload.speak or 0,
            speak_message=payload.speak_message,
            block=payload.block or 0,
        )
        return {
            "message": "Schedule created and registered in memory",
            "schedule": schedule,
        }
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.get("/schedules/{schedule_id}")
def get_single_schedule(schedule_id: int, _: str = Security(verify_api_key)):
    """Retrieve a single schedule by ID."""
    sched = db_get_schedule(schedule_id)
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return {"schedule": sched}


@api_v1.put("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdateRequest,
    _: str = Security(verify_api_key),
):
    """Modify an existing schedule, update in SQLite, and refresh memory."""
    existing = db_get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if existing.get("block") == 1 and payload.block != 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Schedule #{schedule_id} is blocked and protected against changes. Please unblock it first."
        )

    try:
        updated = update_and_reschedule(
            schedule_id=schedule_id,
            name=payload.name,
            schedule_type=payload.type,
            trigger_spec=payload.trigger_spec,
            use_case=payload.use_case,
            is_active=payload.is_active,
            data=payload.data,
            notify=payload.notify,
            notification_message=payload.notification_message,
            speak=payload.speak,
            speak_message=payload.speak_message,
            block=payload.block,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
        return {
            "message": f"Schedule #{schedule_id} updated successfully",
            "schedule": updated,
        }
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, permanent: bool = True, _: str = Security(verify_api_key)):
    """Delete a schedule from memory and database."""
    schedule = db_get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    if schedule.get("block") == 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Schedule #{schedule_id} is blocked and protected against deletion. Please unblock it first."
        )

    if permanent:
        delete_and_remove_schedule(schedule_id)
        return {"message": f"Schedule #{schedule_id} permanently deleted"}
    else:
        cancel_and_deactivate_schedule(schedule_id)
        return {"message": f"Schedule #{schedule_id} cancelled and deactivated"}


@api_v1.patch("/schedules/{schedule_id}/block")
def set_schedule_block_status(
    schedule_id: int,
    payload: ScheduleBlockRequest,
    _: str = Security(verify_api_key),
):
    """Block or unblock a schedule to protect it from being changed or deleted."""
    schedule = db_get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    updated = db_set_schedule_block(schedule_id, payload.block)
    action_str = "blocked" if payload.block == 1 else "unblocked"
    logger.info("Schedule #%s %s", schedule_id, action_str)
    return {
        "message": f"Schedule #{schedule_id} {action_str} successfully",
        "schedule": updated,
    }


# ==========================================
# Use Cases & Settings Endpoints
# ==========================================

class UseCaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Unique use case name used in schedules")
    function_name: str = Field(..., min_length=1, description="Name of the function to execute")
    description: Optional[str] = Field("", description="Description of what this use case does")
    section: Optional[str] = Field(None, description="Optional section identifier ('irrigation', 'blinds', 'rain', 'notification', 'heating', 'alarm', 'general')")


class UseCaseUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Unique use case name used in schedules")
    function_name: str = Field(..., min_length=1, description="Name of the function to execute")
    description: Optional[str] = Field("", description="Description of what this use case does")
    section: Optional[str] = Field(None, description="Optional section identifier ('irrigation', 'blinds', 'rain', 'notification', 'heating', 'alarm', 'general')")


@api_v1.get("/use-cases")
def list_use_cases(_: str = Security(verify_api_key)):
    """Retrieve all configured use cases and available system functions."""
    available_fn_list = [
        {"id": k, "name": v["name"], "description": v["description"]}
        for k, v in SYSTEM_FUNCTIONS.items()
    ]
    return {
        "use_cases": db_list_use_cases(),
        "available_functions": available_fn_list,
        "available_sections": ["irrigation", "blinds", "rain", "heating", "alarm", "general"],
    }


@api_v1.post("/use-cases", status_code=status.HTTP_201_CREATED)
def create_use_case(payload: UseCaseCreateRequest, _: str = Security(verify_api_key)):
    """Configure a new use case linked to an executable function."""
    if payload.function_name not in SYSTEM_FUNCTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Function '{payload.function_name}' is not recognized. Available: {list(SYSTEM_FUNCTIONS.keys())}",
        )
    try:
        new_uc = db_create_use_case(
            name=payload.name.strip(),
            function_name=payload.function_name,
            description=payload.description.strip() if payload.description else "",
            section=payload.section.strip() if payload.section else None,
        )
        logger.info("Use case created: ID #%s ('%s', fn: '%s')", new_uc["id"], new_uc["name"], new_uc["function_name"])
        return {"message": "Use case configured successfully", "use_case": new_uc}
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.put("/use-cases/{use_case_id}")
def update_use_case(use_case_id: int, payload: UseCaseUpdateRequest, _: str = Security(verify_api_key)):
    """Update a use case configuration."""
    if payload.function_name not in SYSTEM_FUNCTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Function '{payload.function_name}' is not recognized. Available: {list(SYSTEM_FUNCTIONS.keys())}",
        )
    existing = db_get_use_case(use_case_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Use case not found")

    try:
        updated = db_update_use_case(
            use_case_id=use_case_id,
            name=payload.name.strip(),
            function_name=payload.function_name,
            description=payload.description.strip() if payload.description else "",
            section=payload.section.strip() if payload.section else None,
        )
        return {"message": f"Use case #{use_case_id} updated successfully", "use_case": updated}
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.delete("/use-cases/{use_case_id}")
def delete_use_case(use_case_id: int, _: str = Security(verify_api_key)):
    """Delete a use case configuration."""
    existing = db_get_use_case(use_case_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Use case not found")

    db_delete_use_case(use_case_id)
    logger.info("Use case deleted: ID #%s ('%s')", use_case_id, existing.get("name"))
    return {"message": f"Use case #{use_case_id} deleted successfully"}


@api_v1.post("/use-cases/{use_case_id}/test")
async def test_use_case(
    use_case_id: int,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    _: str = Security(verify_api_key),
):
    """Immediately trigger the function associated with this use case to test execution with custom parameters."""
    try:
        test_data = None
        if payload is not None:
            if "data" in payload and len(payload) == 1:
                test_data = payload["data"]
            else:
                test_data = payload
        result = await execute_use_case_test(use_case_id, test_data=test_data)
        return result
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


# ==========================================
# System Settings Endpoints
# ==========================================

@api_v1.get("/settings")
def get_system_settings(_: str = Security(verify_api_key)):
    """Retrieve all configurable system settings."""
    return {"settings": db_get_all_settings()}


@api_v1.put("/settings")
def update_system_settings(payload: Dict[str, Any] = Body(...), _: str = Security(verify_api_key)):
    """Update configurable system settings."""
    for k, v in payload.items():
        if k == "heating_interval_minutes":
            try:
                v_int = int(v)
                if v_int < 1:
                    raise ValueError("heating_interval_minutes must be >= 1")
                db_set_setting(k, v_int)
                # Refresh recurrent schedule interval regardless of whether heating is ON or OFF
                heating_st = db_get_heating_state()
                is_on = heating_st.get("state") == "on"
                sync_heating_recurrent_schedule(is_on)
            except (ValueError, TypeError) as err:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        elif k == "heating_heater_entities":
            if isinstance(v, list):
                clean_list = [str(e).strip() for e in v if str(e).strip()]
                db_set_setting(k, json.dumps(clean_list))
            elif isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        db_set_setting(k, json.dumps([str(e).strip() for e in parsed if str(e).strip()]))
                    else:
                        db_set_setting(k, v)
                except Exception:
                    # In case it was passed as Python repr or comma-separated string
                    import ast
                    try:
                        parsed = ast.literal_eval(v)
                        if isinstance(parsed, list):
                            db_set_setting(k, json.dumps([str(e).strip() for e in parsed if str(e).strip()]))
                        else:
                            db_set_setting(k, json.dumps([v.strip()]))
                    except Exception:
                        clean_items = [e.strip() for e in v.split(",") if e.strip()]
                        db_set_setting(k, json.dumps(clean_items))
            else:
                db_set_setting(k, "[]")
        elif isinstance(v, (list, dict)):
            db_set_setting(k, json.dumps(v))
        else:
            db_set_setting(k, str(v))

    return {
        "message": "Settings updated successfully",
        "settings": db_get_all_settings(),
    }


# ==========================================
# Home Assistant & Devices Endpoints
# ==========================================

class DeviceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Device friendly name")
    type: Literal["light", "irrigation", "temperature", "movement", "presence", "blinds", "rain", "door"]
    entity_id: str = Field(..., min_length=1, max_length=200, description="Home Assistant entity ID")


class DeviceActionRequest(BaseModel):
    action: Optional[Literal["on", "off", "toggle", "set_position"]] = Field(
        None,
        description="Action to perform on device: 'on', 'off', 'toggle', or 'set_position'"
    )
    position: Optional[int] = Field(None, ge=0, le=100, description="Target position for blinds/covers (0-100)")


class DeviceUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Device friendly name")
    type: Literal["light", "irrigation", "temperature", "movement", "presence", "blinds", "rain", "door"]
    entity_id: str = Field(..., min_length=1, max_length=200, description="Home Assistant entity ID")


@api_v1.get("/homeassistant/entities")
def list_homeassistant_entities(_: str = Security(verify_api_key)):
    """Retrieve all entities from Home Assistant REST API or fallback demo list."""
    return fetch_homeassistant_entities()


@api_v1.get("/devices")
def list_devices(_: str = Security(verify_api_key)):
    """Retrieve all configured devices."""
    return {"devices": db_list_devices()}


@api_v1.post("/devices", status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreateRequest, _: str = Security(verify_api_key)):
    """Configure a new device mapped to a Home Assistant entity."""
    try:
        device = db_create_device(
            name=payload.name,
            device_type=payload.type,
            entity_id=payload.entity_id,
        )
        logger.info("Device configured: ID #%s ('%s', type: %s, entity: %s)", device["id"], device["name"], device["type"], device["entity_id"])
        return {"message": "Device configured successfully", "device": device}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.put("/devices/{device_id}")
def update_device(device_id: int, payload: DeviceUpdateRequest, _: str = Security(verify_api_key)):
    """Update an existing configured device."""
    existing = db_get_device(device_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    try:
        updated = db_update_device(
            device_id=device_id,
            name=payload.name,
            device_type=payload.type,
            entity_id=payload.entity_id,
        )
        return {"message": f"Device #{device_id} updated successfully", "device": updated}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.delete("/devices/{device_id}")
def delete_device(device_id: int, _: str = Security(verify_api_key)):
    """Delete a configured device."""
    existing = db_get_device(device_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    db_delete_device(device_id)
    logger.info("Device deleted: ID #%s ('%s')", device_id, existing.get("name"))
    return {"message": f"Device #{device_id} deleted successfully"}


@api_v1.post("/devices/{device_id}/action")
def trigger_device_action(
    device_id: int,
    payload: DeviceActionRequest,
    _: str = Security(verify_api_key),
):
    """
    Manually turn on, off, or toggle a configured device in Home Assistant.
    """
    device = db_get_device(device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device #{device_id} not found")

    entity_id = device.get("entity_id")
    if not entity_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Device #{device_id} has no entity_id configured")

    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"

    # Handle blind / cover position setting
    if payload.position is not None or payload.action == "set_position":
        pos = payload.position if payload.position is not None else 0
        pos = max(0, min(100, pos))
        ha_result = call_homeassistant_service(
            domain=domain,
            service="set_cover_position",
            entity_id=entity_id,
            service_data={"position": pos},
        )
        new_state = "closed" if pos == 0 else "open"
        logger.info("Manual blind position set: Device #%s ('%s', %s) -> %s%%", device_id, device.get("name"), entity_id, pos)
        return {
            "status": "success",
            "device_id": device_id,
            "entity_id": entity_id,
            "action": "set_position",
            "position": pos,
            "state": new_state,
            "ha_result": ha_result,
            "message": f"Device '{device.get('name')}' ({entity_id}) moved to {pos}%",
        }

    target_action = payload.action.lower() if payload.action else "toggle"
    if target_action == "toggle":
        ha_res = fetch_homeassistant_entities()
        entities = ha_res.get("entities", [])
        curr_state = "off"
        for ent in entities:
            if ent.get("entity_id") == entity_id:
                curr_state = ent.get("state", "off")
                break
        if domain == "cover":
            target_action = "off" if curr_state == "open" else "on"
        else:
            target_action = "off" if curr_state == "on" else "on"

    if domain == "cover":
        service = "open_cover" if target_action == "on" else "close_cover"
        new_state = "open" if target_action == "on" else "closed"
        pos = 100 if target_action == "on" else 0
    else:
        service = "turn_on" if target_action == "on" else "turn_off"
        new_state = target_action
        pos = None

    ha_result = call_homeassistant_service(domain=domain, service=service, entity_id=entity_id)

    logger.info("Manual device action executed: Device #%s ('%s', %s) -> %s", device_id, device.get("name"), entity_id, target_action.upper())
    res_data = {
        "status": "success",
        "device_id": device_id,
        "entity_id": entity_id,
        "action": target_action,
        "state": new_state,
        "ha_result": ha_result,
        "message": f"Device '{device.get('name')}' ({entity_id}) turned {target_action.upper()}",
    }
    if pos is not None:
        res_data["position"] = pos
    return res_data


# ==========================================
# Logs Endpoints
# ==========================================

@api_v1.get("/logs")
def list_logs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(25, ge=5, le=500, description="Number of log records per page"),
    level: Optional[str] = Query(None, description="Filter by log level (INFO, WARNING, ERROR, DEBUG)"),
    search: Optional[str] = Query(None, description="Search query in log messages"),
    _: str = Security(verify_api_key),
):
    """Retrieve paginated backend system logs."""
    return memory_log_handler.get_paginated(
        page=page,
        page_size=page_size,
        level=level,
        search=search,
    )


@api_v1.delete("/logs")
def clear_logs(_: str = Security(verify_api_key)):
    """Clear in-memory backend logs buffer."""
    memory_log_handler.clear()
    return {"message": "In-memory backend logs cleared"}


# ==========================================
# Events Endpoints
# ==========================================

class EventReceiveRequest(BaseModel):
    type: str = Field(..., min_length=1, description="Event type name, e.g. 'sunrise', 'sunset'")
    parameter: str = Field(default="", description="Event parameter string")


@api_v1.post("/events", status_code=status.HTTP_200_OK)
@api_v1.post("/event", status_code=status.HTTP_200_OK, include_in_schema=False)
async def receive_event(payload: EventReceiveRequest, _: str = Security(verify_api_key)):
    """
    Receive an event via POST JSON body with 'type' and 'parameter' strings.
    Triggers all active event definitions configured for this event type.
    """
    logger.info("Event received: type='%s', parameter='%s'", payload.type, payload.parameter)
    event_record = db_create_event(event_type=payload.type, parameter=payload.parameter)
    triggered_actions = await dispatch_event_triggers(payload.type, payload.parameter)
    return {
        "status": "success",
        "message": f"Event '{payload.type}' received successfully",
        "event": event_record,
        "triggered_definitions": triggered_actions,
    }


@api_v1.get("/events")
def list_events(limit: int = Query(100, ge=1, le=500), _: str = Security(verify_api_key)):
    """Retrieve history of received events."""
    return {"events": db_list_events(limit=limit)}


# ==========================================
# Event Definitions Endpoints
# ==========================================

class EventDefinitionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Friendly name of the event definition")
    type: str = Field(..., min_length=1, description="Event type name (e.g. 'sunrise', 'sunset')")
    parameter: Optional[str] = Field(default="", description="Event parameter string")
    use_case: str = Field(..., min_length=1, description="Use case identifier configured in Settings")
    data: Optional[Any] = Field(default="{}", description="JSON parameters for task execution")
    holiday: Optional[str] = Field(default="all_days", description="Holiday filter ('all_days', 'holiday', 'not_holiday')")
    notify: Optional[int] = Field(default=0, ge=0, le=1, description="1 to notify when executed, 0 otherwise")
    notification_message: Optional[str] = Field(default="", description="Optional custom notification message override")
    speak: Optional[int] = Field(default=0, ge=0, le=1, description="1 to speak announcement through speaker system when executed, 0 otherwise")
    speak_message: Optional[str] = Field(default="", description="Optional custom speech message override")
    is_active: Optional[int] = Field(default=1, ge=0, le=1, description="Active status (1=active, 0=paused)")

    @model_validator(mode="before")
    @classmethod
    def populate_type(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "type" not in values and "event_type" in values:
                values["type"] = values["event_type"]
        return values


class EventDefinitionUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Friendly name of the event definition")
    type: str = Field(..., min_length=1, description="Event type name (e.g. 'sunrise', 'sunset')")
    parameter: Optional[str] = Field(default="", description="Event parameter string")
    use_case: str = Field(..., min_length=1, description="Use case identifier configured in Settings")
    data: Optional[Any] = Field(default="{}", description="JSON parameters for task execution")
    holiday: Optional[str] = Field(default="all_days", description="Holiday filter ('all_days', 'holiday', 'not_holiday')")
    notify: Optional[int] = Field(default=None, ge=0, le=1, description="1 to notify when executed, 0 otherwise")
    notification_message: Optional[str] = Field(default=None, description="Optional custom notification message override")
    speak: Optional[int] = Field(default=None, ge=0, le=1, description="1 to speak announcement through speaker system when executed, 0 otherwise")
    speak_message: Optional[str] = Field(default=None, description="Optional custom speech message override")
    is_active: Optional[int] = Field(default=1, ge=0, le=1, description="Active status (1=active, 0=paused)")

    @model_validator(mode="before")
    @classmethod
    def populate_type(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "type" not in values and "event_type" in values:
                values["type"] = values["event_type"]
        return values


@api_v1.get("/event-definitions")
@api_v1.get("/events/definitions", include_in_schema=False)
def list_event_definitions(_: str = Security(verify_api_key)):
    """Retrieve all configured event definitions."""
    return {"event_definitions": db_list_event_definitions()}


@api_v1.post("/event-definitions", status_code=status.HTTP_201_CREATED)
@api_v1.post("/events/definitions", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_event_definition(payload: EventDefinitionCreateRequest, _: str = Security(verify_api_key)):
    """Create a new event definition."""
    try:
        defn = db_create_event_definition(
            name=payload.name,
            event_type=payload.type,
            parameter=payload.parameter or "",
            use_case=payload.use_case,
            data=payload.data if payload.data is not None else "{}",
            holiday=payload.holiday or "all_days",
            notify=payload.notify or 0,
            notification_message=payload.notification_message,
            speak=payload.speak or 0,
            speak_message=payload.speak_message,
            is_active=payload.is_active if payload.is_active is not None else 1,
        )
        logger.info("Event definition created: ID #%s ('%s', type: %s, use_case: %s)", defn["id"], defn["name"], defn["type"], defn["use_case"])
        return {
            "message": "Event definition created successfully",
            "event_definition": defn,
        }
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.get("/event-definitions/{definition_id}")
@api_v1.get("/events/definitions/{definition_id}", include_in_schema=False)
def get_event_definition(definition_id: int, _: str = Security(verify_api_key)):
    """Get a single event definition by ID."""
    defn = db_get_event_definition(definition_id)
    if not defn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event definition not found")
    return {"event_definition": defn}


@api_v1.put("/event-definitions/{definition_id}")
@api_v1.put("/events/definitions/{definition_id}", include_in_schema=False)
def update_event_definition(
    definition_id: int,
    payload: EventDefinitionUpdateRequest,
    _: str = Security(verify_api_key),
):
    """Update an existing event definition."""
    existing = db_get_event_definition(definition_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event definition not found")

    try:
        updated = db_update_event_definition(
            definition_id=definition_id,
            name=payload.name,
            event_type=payload.type,
            parameter=payload.parameter or "",
            use_case=payload.use_case,
            data=payload.data if payload.data is not None else "{}",
            holiday=payload.holiday or "all_days",
            notify=payload.notify,
            notification_message=payload.notification_message,
            speak=payload.speak,
            speak_message=payload.speak_message,
            is_active=payload.is_active if payload.is_active is not None else 1,
        )
        return {
            "message": f"Event definition #{definition_id} updated successfully",
            "event_definition": updated,
        }
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.delete("/event-definitions/{definition_id}")
@api_v1.delete("/events/definitions/{definition_id}", include_in_schema=False)
def delete_event_definition(definition_id: int, _: str = Security(verify_api_key)):
    """Delete an event definition."""
    existing = db_get_event_definition(definition_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event definition not found")

    db_delete_event_definition(definition_id)
    logger.info("Event definition deleted: ID #%s ('%s')", definition_id, existing.get("name"))
    return {"message": f"Event definition #{definition_id} deleted successfully"}


# ==============================================================================
# Holidays Endpoints
# ==============================================================================

class HolidayPayload(BaseModel):
    date: str = Field(..., description="Date of the holiday in YYYY-MM-DD format", example="2026-12-25")
    name: Optional[str] = Field(None, description="Optional holiday name or description", example="Christmas")


@api_v1.get("/holidays")
def list_holidays(_: str = Security(verify_api_key)):
    """Retrieve all configured holidays ordered by date."""
    return {"holidays": db_list_holidays()}


@api_v1.post("/holidays", status_code=status.HTTP_201_CREATED)
def create_holiday(payload: HolidayPayload, _: str = Security(verify_api_key)):
    """Add a new holiday date to the holidays list."""
    clean_date = payload.date.strip()
    try:
        datetime.strptime(clean_date, "%Y-%m-%d")
    except ValueError:
        logger.warning("Rejected invalid holiday date format: '%s'", payload.date)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format '{payload.date}'. Expected YYYY-MM-DD.",
        )

    try:
        holiday = db_create_holiday(date=clean_date, name=payload.name)
        h_name = holiday.get("name") or "No name"
        logger.info("Holiday created: ID #%s (date: %s, name: '%s')", holiday["id"], clean_date, h_name)
        return {
            "message": f"Holiday for '{clean_date}' created successfully",
            "holiday": holiday,
        }
    except ValueError as err:
        logger.warning("Failed to create holiday for date '%s': %s", clean_date, err)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except Exception as err:
        logger.error("Error creating holiday for date '%s': %s", clean_date, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(err))


@api_v1.delete("/holidays/{holiday_id}")
def delete_holiday(holiday_id: int, _: str = Security(verify_api_key)):
    """Delete a holiday by ID."""
    existing = db_get_holiday(holiday_id)
    if not existing:
        logger.warning("Attempted to delete non-existent holiday ID #%s", holiday_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Holiday #{holiday_id} not found")

    deleted = db_delete_holiday(holiday_id)
    if not deleted:
        logger.warning("Failed to delete holiday ID #%s", holiday_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Holiday #{holiday_id} could not be deleted")

    h_name = existing.get("name") or "No name"
    logger.info("Holiday deleted: ID #%s (date: %s, name: '%s')", holiday_id, existing.get("date"), h_name)
    return {"message": f"Holiday #{holiday_id} deleted successfully", "id": holiday_id}


@api_v1.post("/holidays/sync", status_code=status.HTTP_200_OK)
async def sync_year_holidays(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    _: str = Security(verify_api_key),
):
    """Sync public holidays for the current year from Nager.Date API using get_year_holidays."""
    try:
        from app.scheduler import fn_get_year_holidays
    except ImportError:
        from scheduler import fn_get_year_holidays

    logger.info("Syncing holidays via get_year_holidays (payload: %s)", payload)
    msg = await fn_get_year_holidays(data=payload)
    logger.info("Holidays sync finished: %s", msg)
    return {
        "status": "success",
        "message": msg,
        "holidays": db_list_holidays(),
    }


# ==============================================================================
# Telegram Integration Endpoints
# ==============================================================================

class TelegramSendRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Alert message text to send", example="🚨 Rain detected! Closing blinds.")
    chat_id: Optional[str] = Field(None, description="Optional target Telegram chat ID overriding the default in .env")
    parse_mode: Optional[str] = Field("HTML", description="Parse mode: HTML or Markdown")


@api_v1.get("/telegram/status")
def get_telegram_integration_status(_: str = Security(verify_api_key)):
    """Retrieve Telegram configuration and connectivity status."""
    try:
        from app.telegram import get_telegram_status
    except ImportError:
        from telegram import get_telegram_status
    return get_telegram_status()


@api_v1.post("/telegram/send")
def send_telegram_alert_endpoint(
    payload: TelegramSendRequest,
    _: str = Security(verify_api_key),
):
    """Send an alert message via Telegram Bot API."""
    try:
        from app.telegram import send_telegram_message
    except ImportError:
        from telegram import send_telegram_message

    res = send_telegram_message(
        message=payload.message,
        chat_id=payload.chat_id,
        parse_mode=payload.parse_mode or "HTML",
    )
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=res.get("error", "Failed to deliver Telegram alert"),
        )
    return res


# ==============================================================================
# Notification Channels Endpoints
# ==============================================================================

class NotificationChannelUpdateRequest(BaseModel):
    enabled: Optional[bool] = Field(None, description="Enable or disable this notification channel")
    name: Optional[str] = Field(None, description="Display name for this channel")
    config: Optional[Dict[str, Any]] = Field(None, description="Channel-specific configuration (e.g. chat_id, bot_token)")


class NotificationTestRequest(BaseModel):
    channel_id: Optional[str] = Field("telegram", description="Target notification channel ID")
    message: Optional[str] = Field(None, description="Optional custom test message")


@api_v1.get("/notifications/channels")
def list_notification_channels(_: str = Security(verify_api_key)):
    """Retrieve all configured notification channels with live status."""
    try:
        from app.notifications import get_notification_channels
    except ImportError:
        from notifications import get_notification_channels
    return {"channels": get_notification_channels()}


@api_v1.put("/notifications/channels/{channel_id}")
def update_notification_channel_endpoint(
    channel_id: str,
    payload: NotificationChannelUpdateRequest,
    _: str = Security(verify_api_key),
):
    """Update configuration and enabled state for a notification channel."""
    try:
        from app.notifications import update_notification_channel
    except ImportError:
        from notifications import update_notification_channel
    updated = update_notification_channel(
        channel_id=channel_id,
        enabled=payload.enabled,
        helper_entity=payload.helper_entity,
        name=payload.name,
        config=payload.config,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Notification channel '{channel_id}' not found.")
    return {"status": "success", "channel": updated}


@api_v1.post("/notifications/test")
async def test_notification_channel_endpoint(
    payload: NotificationTestRequest,
    _: str = Security(verify_api_key),
):
    """Send a test notification alert to a specific channel."""
    try:
        from app.notifications import send_channel_test_alert
    except ImportError:
        from notifications import send_channel_test_alert
    try:
        res = await send_channel_test_alert(
            channel_id=payload.channel_id or "telegram",
            message=payload.message,
        )
        return {"status": "success", "result": res}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ==============================================================================
# Speaker System (Chime TTS) Endpoints
# ==============================================================================

class SpeakerConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = Field(None, description="Enable or disable speaker broadcasts")
    speakers: Optional[List[str]] = Field(None, description="List of media_player entity IDs")
    chime_path: Optional[str] = Field(None, description="Chime audio file name or path (e.g. 'bells')")
    tts_platform: Optional[str] = Field(None, description="TTS service platform (e.g. 'tts.google_translate_say')")
    volume_level: Optional[float] = Field(None, ge=0.0, le=1.0, description="Volume level between 0.0 and 1.0")
    default_message: Optional[str] = Field(None, description="Default announcement message")


class SpeakerBroadcastRequest(BaseModel):
    message: Optional[str] = Field(None, description="Speech message text (uses default if omitted)")
    speakers: Optional[List[str]] = Field(None, description="Optional override list of media_player entities")
    chime_path: Optional[str] = Field(None, description="Optional chime audio path override (e.g. 'bells')")
    tts_platform: Optional[str] = Field(None, description="Optional TTS platform override")
    volume_level: Optional[float] = Field(None, ge=0.0, le=1.0, description="Optional volume level override")
    force: Optional[bool] = Field(True, description="Force broadcast even if system is marked disabled (useful for testing)")


@api_v1.get("/speakers/config")
def get_speaker_system_config(_: str = Security(verify_api_key)):
    """Retrieve speaker system configuration."""
    try:
        from app.speakers import get_speaker_config
    except ImportError:
        from speakers import get_speaker_config
    return get_speaker_config()


@api_v1.put("/speakers/config")
def update_speaker_system_config(
    payload: SpeakerConfigUpdateRequest,
    _: str = Security(verify_api_key),
):
    """Update speaker system configuration."""
    try:
        from app.speakers import update_speaker_config
    except ImportError:
        from speakers import update_speaker_config
    updated = update_speaker_config(
        enabled=payload.enabled,
        speakers=payload.speakers,
        chime_path=payload.chime_path,
        tts_platform=payload.tts_platform,
        volume_level=payload.volume_level,
        default_message=payload.default_message,
    )
    return {"status": "success", "config": updated}


@api_v1.post("/speakers/broadcast")
def broadcast_speaker_message(
    payload: SpeakerBroadcastRequest,
    _: str = Security(verify_api_key),
):
    """Broadcast an audio message using Home Assistant chime_tts.say service."""
    try:
        from app.speakers import broadcast_chime_tts
    except ImportError:
        from speakers import broadcast_chime_tts
    try:
        res = broadcast_chime_tts(
            message=payload.message,
            speakers=payload.speakers,
            chime_path=payload.chime_path,
            tts_platform=payload.tts_platform,
            volume_level=payload.volume_level,
            force=payload.force if payload.force is not None else True,
        )
        return {"status": "success", "result": res}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ==============================================================================
# ==============================================================================
# Alarm System Endpoints
# ==============================================================================

class AlarmConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = Field(None, description="Enable or disable alarm system")
    helper_entity: Optional[str] = Field(None, description="Home Assistant helper entity defining alarm on/off state")
    notification_message: Optional[str] = Field(None, description="Static notification template with {entity}, {trigger}, {seconds}, {count} tags")
    speak_message: Optional[str] = Field(None, description="Static speak announcement template with {entity}, {trigger}, {seconds}, {count} tags")
    default_trigger: Optional[int] = Field(None, ge=1, description="Default event count threshold")
    default_seconds: Optional[int] = Field(None, ge=1, description="Default evaluation time window in seconds")
    retention_seconds: Optional[int] = Field(None, ge=5, description="Max memory retention window in seconds to prevent uncontrolled growth")
    delay_seconds: Optional[int] = Field(None, ge=0, description="Global delay between trigger and fire alarm in seconds")


class AlarmTestRequest(BaseModel):
    entity: Optional[str] = Field("binary_sensor.front_door", description="Entity to simulate")
    trigger: Optional[int] = Field(1, ge=1, description="Event count threshold")
    seconds: Optional[int] = Field(60, ge=1, description="Time window in seconds")
    notification: Optional[bool] = Field(True, description="Whether to fire notification")
    speak: Optional[bool] = Field(False, description="Whether to fire speaker announcement")


@api_v1.get("/alarm/config")
def get_alarm_configuration(_: str = Security(verify_api_key)):
    """Retrieve general alarm system configuration."""
    try:
        from app.alarm import get_alarm_config
    except ImportError:
        from alarm import get_alarm_config
    return {"status": "success", "config": get_alarm_config()}


@api_v1.put("/alarm/config")
def update_alarm_configuration(
    payload: AlarmConfigUpdateRequest,
    _: str = Security(verify_api_key),
):
    """Update general alarm system configuration."""
    try:
        from app.alarm import update_alarm_config
    except ImportError:
        from alarm import update_alarm_config
    updated = update_alarm_config(
        enabled=payload.enabled,
        helper_entity=payload.helper_entity,
        notification_message=payload.notification_message,
        speak_message=payload.speak_message,
        default_trigger=payload.default_trigger,
        default_seconds=payload.default_seconds,
        retention_seconds=payload.retention_seconds,
        delay_seconds=payload.delay_seconds,
    )
    return {"status": "success", "message": "Alarm configuration updated successfully", "config": updated}


@api_v1.post("/alarm/test")
async def test_alarm_trigger(
    payload: AlarmTestRequest,
    _: str = Security(verify_api_key),
):
    """Test evaluate alarm trigger with sample parameters."""
    try:
        from app.alarm import evaluate_alarm_event
    except ImportError:
        from alarm import evaluate_alarm_event
    res = await evaluate_alarm_event(
        entity=payload.entity or "binary_sensor.front_door",
        trigger=payload.trigger if payload.trigger is not None else 1,
        seconds=payload.seconds if payload.seconds is not None else 60,
        notification=bool(payload.notification),
        speak=bool(payload.speak),
    )
    return {"status": "success", "result": res}


@api_v1.get("/alarm/events-history")
def get_alarm_events_history(_: str = Security(verify_api_key)):
    """Retrieve recent in-memory recorded sensor events."""
    try:
        from app.alarm import get_memory_events
    except ImportError:
        from alarm import get_memory_events
    return {"status": "success", "events": get_memory_events()}


@api_v1.delete("/alarm/events-history")
def clear_alarm_events_history(_: str = Security(verify_api_key)):
    """Clear all in-memory recorded alarm events."""
    try:
        from app.alarm import clear_memory_events
    except ImportError:
        from alarm import clear_memory_events
    clear_memory_events()
    return {"status": "success", "message": "Alarm memory events cleared successfully"}


@api_v1.get("/alarm/rules")
def list_alarm_rules(_: str = Security(verify_api_key)):
    """Retrieve all event definitions configured as alarm rules."""
    all_defs = db_list_event_definitions()
    alarm_rules = [
        d for d in all_defs
        if d.get("use_case") == "check_alarm" or d.get("use_case") == "alarm" or str(d.get("name", "")).lower().startswith("alarm")
    ]
    return {"status": "success", "rules": alarm_rules}


# Heating System Endpoints
# ==============================================================================

class HeatingStateRequest(BaseModel):
    action: Literal["on", "off"] = Field(..., description="'on' to activate or 'off' to deactivate the heating system")
    mode: Optional[Literal["immediate", "hours", "until"]] = Field(
        default="immediate",
        description="Deactivation mode: 'immediate', 'hours' (deactivate for X hours), or 'until' (deactivate until specific time)"
    )
    hours: Optional[float] = Field(default=None, ge=0.01, le=8760, description="Number of hours to deactivate heating for")
    until: Optional[str] = Field(default=None, description="ISO timestamp (or 'YYYY-MM-DDTHH:MM' or 'HH:MM') to deactivate heating until")


class HeatingSettingsUpdateRequest(BaseModel):
    heating_helper_entity: Optional[str] = Field(default=None, description="Home Assistant helper entity defining heating on/off state")
    heating_interval_minutes: Optional[int] = Field(default=None, ge=1, le=720, description="Recurrent check interval in minutes")
    heating_heater_entities: Optional[List[str]] = Field(default=None, description="List of heater actuator entity IDs to fire when heating map conditions are met")


@api_v1.get("/heating/settings")
def get_heating_settings(_: str = Security(verify_api_key)):
    """Retrieve global heating settings."""
    helper_entity = db_get_setting("heating_helper_entity", "") or ""
    try:
        interval = int(db_get_setting("heating_interval_minutes", "5") or 5)
    except Exception:
        interval = 5
    raw_heaters = db_get_setting("heating_heater_entities", "[]") or "[]"
    try:
        heaters = json.loads(raw_heaters) if isinstance(raw_heaters, str) else list(raw_heaters)
        if not isinstance(heaters, list):
            heaters = []
    except Exception:
        import ast
        try:
            parsed = ast.literal_eval(raw_heaters)
            heaters = [str(e).strip() for e in parsed if str(e).strip()] if isinstance(parsed, list) else []
        except Exception:
            heaters = []
    return {
        "heating_helper_entity": helper_entity,
        "heating_interval_minutes": interval,
        "heating_heater_entities": heaters,
    }


@api_v1.put("/heating/settings")
def update_heating_settings(payload: HeatingSettingsUpdateRequest, _: str = Security(verify_api_key)):
    """Update global heating settings."""
    if payload.heating_helper_entity is not None:
        db_set_setting("heating_helper_entity", payload.heating_helper_entity.strip())

    if payload.heating_interval_minutes is not None:
        db_set_setting("heating_interval_minutes", payload.heating_interval_minutes)
        heating_st = db_get_heating_state()
        is_on = heating_st.get("state") == "on"
        sync_heating_recurrent_schedule(is_on)

    if payload.heating_heater_entities is not None:
        clean_heaters = [str(e).strip() for e in payload.heating_heater_entities if str(e).strip()]
        db_set_setting("heating_heater_entities", json.dumps(clean_heaters))

    raw_heaters = db_get_setting("heating_heater_entities", "[]") or "[]"
    try:
        heaters = json.loads(raw_heaters) if isinstance(raw_heaters, str) else list(raw_heaters)
        if not isinstance(heaters, list):
            heaters = []
    except Exception:
        import ast
        try:
            parsed = ast.literal_eval(raw_heaters)
            heaters = [str(e).strip() for e in parsed if str(e).strip()] if isinstance(parsed, list) else []
        except Exception:
            heaters = []

    return {
        "status": "success",
        "message": "Heating settings updated successfully",
        "settings": {
            "heating_helper_entity": db_get_setting("heating_helper_entity", "") or "",
            "heating_interval_minutes": int(db_get_setting("heating_interval_minutes", "5") or 5),
            "heating_heater_entities": heaters,
        },
    }


@api_v1.get("/heating/state")
@api_v1.get("/heating/status", include_in_schema=False)
def get_heating_state(_: str = Security(verify_api_key)):
    """
    Retrieve current heating system status, helper state, temperature sensors, active map,
    and pending resume schedules.
    """
    state_info = db_get_heating_state()
    helper_entity = db_get_setting("heating_helper_entity", "") or ""
    temp_devices = db_list_devices(device_type="temperature")

    try:
        ha_data = fetch_homeassistant_entities()
        entities = ha_data.get("entities", [])
        entity_states = {e["entity_id"]: e.get("state") for e in entities if "entity_id" in e}
        for d in temp_devices:
            raw_val = entity_states.get(d.get("entity_id"))
            if raw_val is not None:
                try:
                    d["current_temperature"] = float(raw_val)
                except (ValueError, TypeError):
                    d["current_temperature"] = raw_val
            else:
                d["current_temperature"] = None
    except Exception as exc:
        logger.warning("Could not fetch HA states for heating temperature devices: %s", exc)
        for d in temp_devices:
            d["current_temperature"] = None

    # Find pending one-time schedule(s) for heating reactivation
    schedules = db_list_schedules()
    pending_resumes = [
        s for s in schedules
        if s.get("type") == "one-time"
        and s.get("is_active") == 1
        and ("heating" in s.get("name", "").lower() or "heating" in s.get("use_case", "").lower())
    ]

    return {
        "state": state_info.get("state", "off"),
        "helper_entity": helper_entity,
        "helper_state": state_info.get("state", "off"),
        "deactivated_until": state_info.get("deactivated_until"),
        "updated_at": state_info.get("updated_at"),
        "active_map_id": state_info.get("active_map_id"),
        "active_map": state_info.get("active_map"),
        "devices": [],
        "temperature_devices": temp_devices,
        "pending_resume_schedules": pending_resumes,
    }


@api_v1.post("/heating/state")
async def update_heating_state(payload: HeatingStateRequest, _: str = Security(verify_api_key)):
    """
    Activate or deactivate the heating system.
    Supports deactivating immediately or scheduling a one-time activation after X hours or until a target datetime.
    """
    action = payload.action.lower()

    if action == "on":
        # Cancel any pending auto-activation one-time schedules
        schedules = db_list_schedules()
        for s in schedules:
            if s.get("type") == "one-time" and ("heating" in s.get("name", "").lower() or "heating" in s.get("use_case", "").lower()):
                try:
                    delete_and_remove_schedule(s["id"])
                except Exception as exc:
                    logger.warning("Could not delete pending heating resume schedule #%s: %s", s.get("id"), exc)

        res_msg = await fn_start_heating(data={"action": "on"})
        return {
            "status": "success",
            "message": res_msg,
            "state": db_get_heating_state(),
        }

    else:
        # action == "off"
        target_dt = None
        now_local = datetime.now(APP_TIMEZONE)

        if payload.mode == "hours" or payload.hours is not None:
            num_hours = payload.hours if payload.hours is not None else 1.0
            target_dt = now_local + timedelta(hours=num_hours)
        elif payload.mode == "until" or (payload.until and payload.until.strip()):
            until_str = payload.until.strip()
            # Try ISO format
            try:
                parsed = datetime.fromisoformat(until_str)
                if parsed.tzinfo is None:
                    target_dt = parsed.replace(tzinfo=APP_TIMEZONE)
                else:
                    target_dt = parsed.astimezone(APP_TIMEZONE)
            except Exception:
                # Try parsing "HH:MM"
                try:
                    time_parts = [int(p) for p in until_str.split(":") if p.strip()]
                    t_hour = time_parts[0]
                    t_minute = time_parts[1] if len(time_parts) > 1 else 0
                    candidate = now_local.replace(hour=t_hour, minute=t_minute, second=0, microsecond=0)
                    if candidate <= now_local:
                        candidate += timedelta(days=1)
                    target_dt = candidate
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid target time format '{until_str}'. Use ISO format (YYYY-MM-DDTHH:MM) or HH:MM.",
                    )

        created_schedule = None
        deactivated_until_iso = None

        # Always cancel any previous auto-activation one-time schedules when action is 'off'
        schedules = db_list_schedules()
        for s in schedules:
            if s.get("type") == "one-time" and ("auto - heating activate" in s.get("name", "").lower() or "heating" in s.get("use_case", "").lower()):
                try:
                    delete_and_remove_schedule(s["id"])
                except Exception as exc:
                    logger.warning("Could not delete pending heating resume schedule #%s: %s", s.get("id"), exc)

        if target_dt is not None:
            deactivated_until_iso = target_dt.isoformat()

            # Find or use use case executing control_heating / heating section for deferred activation
            all_ucs = db_list_use_cases()
            heating_uc = next(
                (u for u in all_ucs if u.get("function_name") == "control_heating" and u.get("section") == "heating"),
                None
            ) or next(
                (u for u in all_ucs if u.get("section") == "heating"),
                None
            ) or next(
                (u for u in all_ucs if u.get("function_name") == "start_heating"),
                None
            )
            uc_name = heating_uc["name"] if heating_uc else "Heating"

            sched_name = f"Auto - Heating Activate ({target_dt.strftime('%Y-%m-%d %H:%M')})"
            created_schedule = create_and_register_schedule(
                name=sched_name,
                schedule_type="one-time",
                trigger_spec=deactivated_until_iso,
                use_case=uc_name,
                data=json.dumps({"action": "on"}),
                block=1,
            )

        res_msg = await fn_start_heating(data={
            "action": "off",
            "deactivated_until": deactivated_until_iso,
        })

        return {
            "status": "success",
            "message": res_msg,
            "state": db_get_heating_state(),
            "schedule": created_schedule,
        }


# ==============================================================================
# Heating Maps Endpoints
# ==============================================================================

class HeatingMapCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Unique heating map name")
    description: Optional[str] = Field(default="", description="Description of the heating map")
    rules: Dict[str, Optional[float]] = Field(default_factory=dict, description="Device ID or entity minimum temperature mapping")
    is_default: Optional[int] = Field(default=0, ge=0, le=1, description="1 if default heating map, 0 otherwise")


class HeatingMapUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Unique heating map name")
    description: Optional[str] = Field(default="", description="Description of the heating map")
    rules: Dict[str, Optional[float]] = Field(default_factory=dict, description="Device ID or entity minimum temperature mapping")
    is_default: Optional[int] = Field(default=None, ge=0, le=1, description="1 if default heating map, 0 otherwise")


@api_v1.get("/heating/maps")
def list_heating_maps(_: str = Security(verify_api_key)):
    """Retrieve all configured heating maps with active and default map markers."""
    maps = db_list_heating_maps()
    state = db_get_heating_state()
    default_map = db_get_default_heating_map()
    return {
        "maps": maps,
        "active_map_id": state.get("active_map_id"),
        "default_map_id": default_map["id"] if default_map else None,
    }


@api_v1.get("/heating/maps/{map_id}")
def get_heating_map(map_id: int, _: str = Security(verify_api_key)):
    """Retrieve a single heating map by ID."""
    map_item = db_get_heating_map(map_id)
    if not map_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Heating map #{map_id} not found")
    return {"map": map_item}


@api_v1.post("/heating/maps", status_code=status.HTTP_201_CREATED)
def create_heating_map(payload: HeatingMapCreateRequest, _: str = Security(verify_api_key)):
    """Create a new heating map with minimum temperature rules."""
    try:
        created = db_create_heating_map(
            name=payload.name,
            description=payload.description or "",
            rules=payload.rules,
            is_default=payload.is_default or 0,
        )
        return {"message": f"Heating map '{created['name']}' created successfully", "map": created}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.put("/heating/maps/{map_id}")
def update_heating_map(map_id: int, payload: HeatingMapUpdateRequest, _: str = Security(verify_api_key)):
    """Update an existing heating map."""
    existing = db_get_heating_map(map_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Heating map #{map_id} not found")

    try:
        updated = db_update_heating_map(
            map_id=map_id,
            name=payload.name,
            description=payload.description,
            rules=payload.rules,
            is_default=payload.is_default,
        )
        return {"message": f"Heating map #{map_id} updated successfully", "map": updated}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.delete("/heating/maps/{map_id}")
def delete_heating_map(map_id: int, _: str = Security(verify_api_key)):
    """Delete a heating map."""
    existing = db_get_heating_map(map_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Heating map #{map_id} not found")

    all_maps = db_list_heating_maps()
    if len(all_maps) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the only configured heating map in the system.",
        )

    db_delete_heating_map(map_id)
    return {"message": f"Heating map #{map_id} ('{existing.get('name')}') deleted successfully"}


@api_v1.post("/heating/maps/{map_id}/activate")
def activate_heating_map_endpoint(map_id: int, _: str = Security(verify_api_key)):
    """Set a heating map as the currently active heating map."""
    existing = db_get_heating_map(map_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Heating map #{map_id} not found")

    updated_state = db_set_active_heating_map(map_id)
    return {
        "message": f"Heating map '{existing['name']}' is now the active map",
        "state": updated_state,
        "active_map": existing,
    }


@api_v1.post("/heating/maps/{map_id}/set-default")
def set_default_heating_map_endpoint(map_id: int, _: str = Security(verify_api_key)):
    """Set a heating map as the default heating map."""
    existing = db_get_heating_map(map_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Heating map #{map_id} not found")

    updated_map = db_set_default_heating_map(map_id)
    return {
        "message": f"Heating map '{existing['name']}' set as system default",
        "map": updated_map,
    }


# ==============================================================================
# Heating Calendar Endpoints
# ==============================================================================

DAYS_METADATA = [
    {"id": 0, "name": "Monday", "short": "Mon"},
    {"id": 1, "name": "Tuesday", "short": "Tue"},
    {"id": 2, "name": "Wednesday", "short": "Wed"},
    {"id": 3, "name": "Thursday", "short": "Thu"},
    {"id": 4, "name": "Friday", "short": "Fri"},
    {"id": 5, "name": "Saturday", "short": "Sat"},
    {"id": 6, "name": "Sunday", "short": "Sun"},
    {"id": 7, "name": "Holidays", "short": "Hol"},
]


class HeatingCalendarSlotItem(BaseModel):
    start_time: str = Field(..., description="Start time in HH:MM format", example="07:00")
    end_time: str = Field(..., description="End time in HH:MM format (or 24:00)", example="09:00")
    map_id: int = Field(..., description="ID of heating map assigned to this slot")


class HeatingCalendarDayUpdateRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=7, description="0=Mon..6=Sun, 7=Holidays")
    slots: List[HeatingCalendarSlotItem] = Field(..., description="List of parts of day for this weekday")
    copy_to_days: Optional[List[int]] = Field(default=None, description="Optional other day_of_week to replicate to")


class HeatingCalendarBulkUpdateRequest(BaseModel):
    slots: List[Dict[str, Any]] = Field(..., description="List of calendar slots across weekdays")


@api_v1.get("/heating/calendar")
def get_heating_calendar(_: str = Security(verify_api_key)):
    """Retrieve weekly heating calendar slots, metadata, and the heating map active right now."""
    now_local = datetime.now(APP_TIMEZONE)
    date_str = now_local.strftime("%Y-%m-%d")
    is_today_holiday = db_is_holiday(date_str)
    current_dow = 7 if is_today_holiday else now_local.weekday()

    slots = db_list_heating_calendar()
    resolved_map = db_resolve_current_heating_map(now_local)

    return {
        "calendar": slots,
        "resolved_map": resolved_map,
        "current_time": now_local.strftime("%H:%M"),
        "current_date": date_str,
        "current_day_of_week": current_dow,
        "is_today_holiday": is_today_holiday,
        "days": DAYS_METADATA,
    }


@api_v1.put("/heating/calendar/day")
def update_heating_calendar_day_endpoint(
    payload: HeatingCalendarDayUpdateRequest,
    _: str = Security(verify_api_key),
):
    """Update heating calendar parts of the day for a weekday, with optional replication."""
    try:
        slots_data = [s.model_dump() for s in payload.slots]
        if not slots_data:
            # Fallback to full day default if empty
            def_map = db_get_default_heating_map()
            def_id = def_map["id"] if def_map else 1
            slots_data = [{"start_time": "00:00", "end_time": "24:00", "map_id": def_id}]

        db_set_heating_calendar_day(payload.day_of_week, slots_data)

        if payload.copy_to_days:
            for other_day in payload.copy_to_days:
                if 0 <= other_day <= 7 and other_day != payload.day_of_week:
                    db_set_heating_calendar_day(other_day, slots_data)

        now_local = datetime.now(APP_TIMEZONE)
        return {
            "status": "success",
            "message": f"Heating calendar for day #{payload.day_of_week} saved successfully",
            "calendar": db_list_heating_calendar(),
            "resolved_map": db_resolve_current_heating_map(now_local),
        }
    except Exception as err:
        logger.error("Error updating heating calendar day #%s: %s", payload.day_of_week, err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@api_v1.put("/heating/calendar")
def update_heating_calendar_bulk_endpoint(
    payload: HeatingCalendarBulkUpdateRequest,
    _: str = Security(verify_api_key),
):
    """Bulk update all heating calendar slots."""
    try:
        db_set_heating_calendar_bulk(payload.slots)
        now_local = datetime.now(APP_TIMEZONE)
        return {
            "status": "success",
            "message": "Heating calendar updated successfully",
            "calendar": db_list_heating_calendar(),
            "resolved_map": db_resolve_current_heating_map(now_local),
        }
    except Exception as err:
        logger.error("Error updating heating calendar bulk: %s", err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


app.include_router(api_v1, prefix="/api/v1")
app.include_router(api_v1, prefix="", include_in_schema=False)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
