import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
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
    from app.homeassistant import fetch_homeassistant_entities, check_homeassistant_connection
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
    from homeassistant import fetch_homeassistant_entities, check_homeassistant_connection
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
    block: Optional[int] = Field(default=None, ge=0, le=1, description="1 if blocked/protected from changes or deletion, 0 otherwise")


class ScheduleBlockRequest(BaseModel):
    block: int = Field(..., ge=0, le=1, description="1 to block/protect schedule, 0 to unblock")


@app.get("/ping")
@app.get("/health/ping")
def ping():
    """Unauthenticated health ping endpoint for container and orchestrator health checks."""
    return {"status": "ok"}


@app.get("/health")
def health_check(_: str = Security(verify_api_key)):
    """Health check endpoint protected by API Key."""
    ha_connected = check_homeassistant_connection()
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": ENVIRONMENT,
        "database": "connected",
        "scheduler": "running",
        "homeassistant": "connected" if ha_connected else "disconnected",
    }


@app.get("/schedules")
def list_schedules(_: str = Security(verify_api_key)):
    """Retrieve all schedules from the database and current in-memory status."""
    return {
        "schedules": db_list_schedules(),
        "in_memory_jobs": get_memory_jobs_status(),
    }


@app.post("/schedules", status_code=status.HTTP_201_CREATED)
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
            block=payload.block or 0,
        )
        return {
            "message": "Schedule created and registered in memory",
            "schedule": schedule,
        }
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.get("/schedules/{schedule_id}")
def get_single_schedule(schedule_id: int, _: str = Security(verify_api_key)):
    """Retrieve a single schedule by ID."""
    sched = db_get_schedule(schedule_id)
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return {"schedule": sched}


@app.put("/schedules/{schedule_id}")
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


@app.delete("/schedules/{schedule_id}")
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


@app.patch("/schedules/{schedule_id}/block")
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
    section: Optional[str] = Field(None, description="Optional section identifier ('irrigation', 'blinds', 'rain', 'notification', 'heating', 'heating_control', 'heating_recurrent')")


class UseCaseUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Unique use case name used in schedules")
    function_name: str = Field(..., min_length=1, description="Name of the function to execute")
    description: Optional[str] = Field("", description="Description of what this use case does")
    section: Optional[str] = Field(None, description="Optional section identifier ('irrigation', 'blinds', 'rain', 'notification', 'heating', 'heating_control', 'heating_recurrent')")


@app.get("/use-cases")
def list_use_cases(_: str = Security(verify_api_key)):
    """Retrieve all configured use cases and available system functions."""
    available_fn_list = [
        {"id": k, "name": v["name"], "description": v["description"]}
        for k, v in SYSTEM_FUNCTIONS.items()
    ]
    return {
        "use_cases": db_list_use_cases(),
        "available_functions": available_fn_list,
        "available_sections": ["irrigation", "blinds", "rain", "notification", "heating_control", "heating_recurrent"],
    }


@app.post("/use-cases", status_code=status.HTTP_201_CREATED)
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


@app.put("/use-cases/{use_case_id}")
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


@app.delete("/use-cases/{use_case_id}")
def delete_use_case(use_case_id: int, _: str = Security(verify_api_key)):
    """Delete a use case configuration."""
    existing = db_get_use_case(use_case_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Use case not found")

    db_delete_use_case(use_case_id)
    logger.info("Use case deleted: ID #%s ('%s')", use_case_id, existing.get("name"))
    return {"message": f"Use case #{use_case_id} deleted successfully"}


@app.post("/use-cases/{use_case_id}/test")
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

@app.get("/settings")
def get_system_settings(_: str = Security(verify_api_key)):
    """Retrieve all configurable system settings."""
    return {"settings": db_get_all_settings()}


@app.put("/settings")
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
    type: Literal["light", "irrigation", "temperature", "movement", "presence", "blinds", "rain", "heating"]
    entity_id: str = Field(..., min_length=1, max_length=200, description="Home Assistant entity ID")


class DeviceUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Device friendly name")
    type: Literal["light", "irrigation", "temperature", "movement", "presence", "blinds", "rain", "heating"]
    entity_id: str = Field(..., min_length=1, max_length=200, description="Home Assistant entity ID")


@app.get("/homeassistant/entities")
def list_homeassistant_entities(_: str = Security(verify_api_key)):
    """Retrieve all entities from Home Assistant REST API or fallback demo list."""
    return fetch_homeassistant_entities()


@app.get("/devices")
def list_devices(_: str = Security(verify_api_key)):
    """Retrieve all configured devices."""
    return {"devices": db_list_devices()}


@app.post("/devices", status_code=status.HTTP_201_CREATED)
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


@app.put("/devices/{device_id}")
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


@app.delete("/devices/{device_id}")
def delete_device(device_id: int, _: str = Security(verify_api_key)):
    """Delete a configured device."""
    existing = db_get_device(device_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    db_delete_device(device_id)
    logger.info("Device deleted: ID #%s ('%s')", device_id, existing.get("name"))
    return {"message": f"Device #{device_id} deleted successfully"}


# ==========================================
# Logs Endpoints
# ==========================================

@app.get("/logs")
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


@app.delete("/logs")
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


@app.post("/events", status_code=status.HTTP_200_OK)
@app.post("/event", status_code=status.HTTP_200_OK, include_in_schema=False)
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


@app.get("/events")
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
    is_active: Optional[int] = Field(default=1, ge=0, le=1, description="Active status (1=active, 0=paused)")


class EventDefinitionUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Friendly name of the event definition")
    type: str = Field(..., min_length=1, description="Event type name (e.g. 'sunrise', 'sunset')")
    parameter: Optional[str] = Field(default="", description="Event parameter string")
    use_case: str = Field(..., min_length=1, description="Use case identifier configured in Settings")
    data: Optional[Any] = Field(default="{}", description="JSON parameters for task execution")
    holiday: Optional[str] = Field(default="all_days", description="Holiday filter ('all_days', 'holiday', 'not_holiday')")
    notify: Optional[int] = Field(default=None, ge=0, le=1, description="1 to notify when executed, 0 otherwise")
    notification_message: Optional[str] = Field(default=None, description="Optional custom notification message override")
    is_active: Optional[int] = Field(default=1, ge=0, le=1, description="Active status (1=active, 0=paused)")


@app.get("/event-definitions")
def list_event_definitions(_: str = Security(verify_api_key)):
    """Retrieve all configured event definitions."""
    return {"event_definitions": db_list_event_definitions()}


@app.post("/event-definitions", status_code=status.HTTP_201_CREATED)
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
            is_active=payload.is_active if payload.is_active is not None else 1,
        )
        logger.info("Event definition created: ID #%s ('%s', type: %s, use_case: %s)", defn["id"], defn["name"], defn["type"], defn["use_case"])
        return {
            "message": "Event definition created successfully",
            "event_definition": defn,
        }
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.get("/event-definitions/{definition_id}")
def get_event_definition(definition_id: int, _: str = Security(verify_api_key)):
    """Get a single event definition by ID."""
    defn = db_get_event_definition(definition_id)
    if not defn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event definition not found")
    return {"event_definition": defn}


@app.put("/event-definitions/{definition_id}")
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
            is_active=payload.is_active if payload.is_active is not None else 1,
        )
        return {
            "message": f"Event definition #{definition_id} updated successfully",
            "event_definition": updated,
        }
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.delete("/event-definitions/{definition_id}")
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


@app.get("/holidays")
def list_holidays(_: str = Security(verify_api_key)):
    """Retrieve all configured holidays ordered by date."""
    return {"holidays": db_list_holidays()}


@app.post("/holidays", status_code=status.HTTP_201_CREATED)
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


@app.delete("/holidays/{holiday_id}")
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


@app.post("/holidays/sync", status_code=status.HTTP_200_OK)
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


@app.get("/telegram/status")
def get_telegram_integration_status(_: str = Security(verify_api_key)):
    """Retrieve Telegram configuration and connectivity status."""
    try:
        from app.telegram import get_telegram_status
    except ImportError:
        from telegram import get_telegram_status
    return get_telegram_status()


@app.post("/telegram/send")
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


@app.get("/heating/state")
@app.get("/heating/status", include_in_schema=False)
def get_heating_state(_: str = Security(verify_api_key)):
    """Retrieve current heating system status, devices, active map, and pending resume schedules."""
    state_info = db_get_heating_state()
    heating_devices = db_list_devices(device_type="heating")
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
        "state": state_info.get("state", "on"),
        "deactivated_until": state_info.get("deactivated_until"),
        "updated_at": state_info.get("updated_at"),
        "active_map_id": state_info.get("active_map_id"),
        "active_map": state_info.get("active_map"),
        "devices": heating_devices,
        "temperature_devices": temp_devices,
        "pending_resume_schedules": pending_resumes,
    }


@app.post("/heating/state")
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

            # Find or use use case executing start_heating for deferred activation
            all_ucs = db_list_use_cases()
            heating_uc = next(
                (u for u in all_ucs if u.get("function_name") == "start_heating"),
                None
            ) or next(
                (u for u in all_ucs if u.get("section") == "heating_control"),
                None
            )
            uc_name = heating_uc["name"] if heating_uc else "start_heating"

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


@app.get("/heating/maps")
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


@app.get("/heating/maps/{map_id}")
def get_heating_map(map_id: int, _: str = Security(verify_api_key)):
    """Retrieve a single heating map by ID."""
    map_item = db_get_heating_map(map_id)
    if not map_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Heating map #{map_id} not found")
    return {"map": map_item}


@app.post("/heating/maps", status_code=status.HTTP_201_CREATED)
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


@app.put("/heating/maps/{map_id}")
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


@app.delete("/heating/maps/{map_id}")
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


@app.post("/heating/maps/{map_id}/activate")
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


@app.post("/heating/maps/{map_id}/set-default")
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


@app.get("/heating/calendar")
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


@app.put("/heating/calendar/day")
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


@app.put("/heating/calendar")
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


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
