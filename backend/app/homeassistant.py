import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

FALLBACK_ENTITIES: List[Dict[str, Any]] = [
    {
        "entity_id": "cover.living_room_blind",
        "friendly_name": "Living Room Blind",
        "domain": "cover",
        "state": "open",
        "current_position": 100,
    },
    {
        "entity_id": "cover.bedroom_blind",
        "friendly_name": "Bedroom Window Blind",
        "domain": "cover",
        "state": "closed",
        "current_position": 0,
    },
    {
        "entity_id": "light.living_room_ceiling",
        "friendly_name": "Living Room Ceiling Light",
        "domain": "light",
        "state": "off",
    },
    {
        "entity_id": "light.kitchen_spots",
        "friendly_name": "Kitchen Spotlights",
        "domain": "light",
        "state": "on",
    },
    {
        "entity_id": "light.garden_terrace",
        "friendly_name": "Garden Terrace Light",
        "domain": "light",
        "state": "off",
    },
    {
        "entity_id": "switch.garden_irrigation_zone1",
        "friendly_name": "Garden Irrigation Zone 1",
        "domain": "switch",
        "state": "off",
    },
    {
        "entity_id": "switch.lawn_irrigation_zone2",
        "friendly_name": "Lawn Irrigation Zone 2",
        "domain": "switch",
        "state": "off",
    },
    {
        "entity_id": "sensor.living_room_temperature",
        "friendly_name": "Living Room Temperature",
        "domain": "sensor",
        "state": "21.5",
    },
    {
        "entity_id": "sensor.bedroom_temperature",
        "friendly_name": "Bedroom Temperature",
        "domain": "sensor",
        "state": "19.8",
    },
    {
        "entity_id": "binary_sensor.corridor_movement",
        "friendly_name": "Corridor Movement Sensor",
        "domain": "binary_sensor",
        "state": "off",
    },
    {
        "entity_id": "binary_sensor.front_door_motion",
        "friendly_name": "Front Door Motion Sensor",
        "domain": "binary_sensor",
        "state": "off",
    },
    {
        "entity_id": "binary_sensor.living_room_presence",
        "friendly_name": "Living Room Presence",
        "domain": "binary_sensor",
        "state": "on",
    },
    {
        "entity_id": "device_tracker.owner_phone_presence",
        "friendly_name": "Owner Phone Presence",
        "domain": "device_tracker",
        "state": "home",
    },
]


_last_ha_check_time = 0.0
_last_ha_status = False


def check_homeassistant_connection(max_age_seconds: float = 10.0) -> bool:
    """
    Check if Home Assistant is reachable and authenticated.
    Results are cached for max_age_seconds to avoid excessive requests during health checks.
    """
    global _last_ha_check_time, _last_ha_status
    import time
    now = time.time()
    if now - _last_ha_check_time < max_age_seconds:
        return _last_ha_status

    hass_url = os.getenv("HASS_URL", "http://localhost:8123").rstrip("/")
    hass_token = os.getenv("HASS_TOKEN", "").strip()

    if not hass_token:
        _last_ha_status = False
        _last_ha_check_time = now
        return False

    api_endpoint = f"{hass_url}/api/"
    req = urllib.request.Request(
        api_endpoint,
        headers={
            "Authorization": f"Bearer {hass_token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=2.0) as response:
            _last_ha_status = (response.status == 200)
    except Exception:
        _last_ha_status = False

    _last_ha_check_time = now
    return _last_ha_status


def fetch_homeassistant_entities() -> Dict[str, Any]:
    """
    Fetch all entities from Home Assistant REST API (/api/states).
    Falls back gracefully to fallback entities if Home Assistant is unreachable or token is missing.
    """
    hass_url = os.getenv("HASS_URL", "http://localhost:8123").rstrip("/")
    hass_token = os.getenv("HASS_TOKEN", "").strip()

    if not hass_token:
        logger.info("Home Assistant token (HASS_TOKEN) is not configured. Serving fallback entities.")
        return {
            "connected": False,
            "hass_url": hass_url,
            "entities": FALLBACK_ENTITIES,
            "error": "Home Assistant token not set in backend/.env. Using fallback demo entities.",
        }

    api_endpoint = f"{hass_url}/api/states"
    req = urllib.request.Request(
        api_endpoint,
        headers={
            "Authorization": f"Bearer {hass_token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=4.0) as response:
            if response.status == 200:
                raw_data = json.loads(response.read().decode("utf-8"))
                entities: List[Dict[str, str]] = []

                for item in raw_data:
                    entity_id = item.get("entity_id", "")
                    if not entity_id:
                        continue
                    attributes = item.get("attributes", {})
                    friendly_name = attributes.get("friendly_name") or entity_id
                    domain = entity_id.split(".")[0] if "." in entity_id else "unknown"
                    state = str(item.get("state", ""))

                    ent_dict = {
                        "entity_id": entity_id,
                        "friendly_name": friendly_name,
                        "domain": domain,
                        "state": state,
                    }
                    if "current_position" in attributes:
                        try:
                            ent_dict["current_position"] = int(attributes["current_position"])
                        except (ValueError, TypeError):
                            pass
                    entities.append(ent_dict)

                entities.sort(key=lambda x: x["friendly_name"].lower())
                return {
                    "connected": True,
                    "hass_url": hass_url,
                    "entities": entities,
                    "error": None,
                }
            else:
                err_msg = f"Home Assistant returned status code {response.status}"
                logger.warning(err_msg)
                return {
                    "connected": False,
                    "hass_url": hass_url,
                    "entities": FALLBACK_ENTITIES,
                    "error": err_msg,
                }

    except urllib.error.HTTPError as http_err:
        err_msg = f"Home Assistant HTTP Error {http_err.code}: {http_err.reason}"
        logger.warning(err_msg)
        return {
            "connected": False,
            "hass_url": hass_url,
            "entities": FALLBACK_ENTITIES,
            "error": err_msg,
        }
    except Exception as exc:
        err_msg = f"Could not connect to Home Assistant at {hass_url}: {str(exc)}"
        logger.warning(err_msg)
        return {
            "connected": False,
            "hass_url": hass_url,
            "entities": FALLBACK_ENTITIES,
            "error": err_msg,
        }


def call_homeassistant_service(
    domain: str,
    service: str,
    entity_id: str,
    service_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Call a Home Assistant service (e.g. switch.turn_on, switch.turn_off, cover.set_cover_position).
    """
    hass_url = os.getenv("HASS_URL", "http://localhost:8123").rstrip("/")
    hass_token = os.getenv("HASS_TOKEN", "").strip()

    if not hass_token:
        # In mock mode, update the state of the fallback entity if present
        for ent in FALLBACK_ENTITIES:
            if ent.get("entity_id") == entity_id:
                if service == "set_cover_position" and service_data and "position" in service_data:
                    pos = int(service_data["position"])
                    ent["current_position"] = pos
                    ent["state"] = "closed" if pos == 0 else "open"
                elif service == "open_cover":
                    ent["current_position"] = 100
                    ent["state"] = "open"
                elif service == "close_cover":
                    ent["current_position"] = 0
                    ent["state"] = "closed"
                elif service in ("turn_on", "open_valve"):
                    ent["state"] = "on"
                elif service in ("turn_off", "close_valve"):
                    ent["state"] = "off"

        logger.info(
            "[MOCK HA] Token not configured. Simulated calling %s.%s for '%s' with data=%s",
            domain,
            service,
            entity_id,
            service_data,
        )
        return {
            "success": True,
            "simulated": True,
            "entity_id": entity_id,
            "service": f"{domain}.{service}",
            "service_data": service_data or {},
        }

    api_endpoint = f"{hass_url}/api/services/{domain}/{service}"
    body: Dict[str, Any] = {"entity_id": entity_id}
    if service_data:
        body.update(service_data)
    payload_data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        api_endpoint,
        data=payload_data,
        headers={
            "Authorization": f"Bearer {hass_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5.0) as response:
            if response.status in (200, 201):
                logger.info("Successfully called HA service %s.%s for '%s'", domain, service, entity_id)
                return {"success": True, "status": response.status, "entity_id": entity_id}
            else:
                logger.warning("HA service %s.%s returned status %s for '%s'", domain, service, response.status, entity_id)
                return {"success": False, "status": response.status, "entity_id": entity_id}
    except Exception as exc:
        logger.warning("Error calling HA service %s.%s for '%s': %s", domain, service, entity_id, exc)
        return {"success": False, "error": str(exc), "entity_id": entity_id}
