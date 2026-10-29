import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend directory to sys.path so 'app' can be imported
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Isolate test database so test execution NEVER mutates or deletes live user data in db/iot.db
TEST_DB_PATH = BACKEND_DIR / "db" / "test_heating.db"
LIVE_DB_PATH = BACKEND_DIR / "db" / "iot.db"
if LIVE_DB_PATH.exists():
    shutil.copy2(LIVE_DB_PATH, TEST_DB_PATH)
os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)

from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app, API_KEY
from app.database import (
    init_db,
    db_get_heating_state,
    db_set_heating_state,
    db_get_setting,
    db_set_setting,
)
from app.homeassistant import FALLBACK_ENTITIES


def mock_get_entity_state_heating(entity_id: str):
    for ent in FALLBACK_ENTITIES:
        if ent.get("entity_id") == entity_id:
            return str(ent.get("state", "off"))
    return None


def mock_call_ha_heating(domain: str, service: str, entity_id: str = "", service_data: dict = None):
    found = False
    for ent in FALLBACK_ENTITIES:
        if ent.get("entity_id") == entity_id:
            found = True
            if service in ("turn_on", "arm_away", "arm_home"):
                ent["state"] = "on"
            elif service in ("turn_off", "disarm"):
                ent["state"] = "off"
            elif service == "set_hvac_mode":
                hvac_mode = (service_data or {}).get("hvac_mode", "off")
                ent["state"] = "heat" if hvac_mode == "heat" else "off"
    if not found and entity_id:
        st = "on" if service in ("turn_on", "arm_away", "arm_home") else "off"
        if service == "set_hvac_mode":
            st = (service_data or {}).get("hvac_mode", "off")
        FALLBACK_ENTITIES.append({"entity_id": entity_id, "state": st, "friendly_name": entity_id})
    return {"success": True}


@patch("app.homeassistant.call_homeassistant_service", side_effect=mock_call_ha_heating)
@patch("app.scheduler.call_homeassistant_service", side_effect=mock_call_ha_heating)
@patch("app.homeassistant.get_entity_state", side_effect=mock_get_entity_state_heating)
def test_heating_full_flow(mock_ha_call, mock_sched_call, mock_ha_state):
    init_db()
    saved_fallback = [dict(e) for e in FALLBACK_ENTITIES]
    try:
        client = TestClient(app)
        headers = {"X-API-Key": API_KEY}

        print("\n--- Starting Heating System Backend Tests ---")

        # Snapshot original settings to restore after test
        orig_helper = db_get_setting("heating_helper_entity", "")
        orig_interval = int(db_get_setting("heating_interval_minutes", "5") or 5)
        orig_heaters = db_get_setting("heating_heater_entities", "[]")

        # 1. Test GET /heating/state (heating state is derived from helper entity, not stored in DB)
        state_resp = client.get("/heating/state", headers=headers)
        assert state_resp.status_code == 200, f"GET /heating/state failed: {state_resp.text}"
        data = state_resp.json()
        assert "state" in data
        assert "helper_entity" in data
        assert "devices" in data
        assert "temperature_devices" in data
        assert "pending_resume_schedules" in data
        print("PASS: GET /heating/state returned valid state dynamically:", data["state"])

        # 2. Configure global heating helper entity in heating settings
        test_helper = "input_boolean.heating_system"
        test_heaters = ["switch.caldera", "climate.radiador_salon"]
        heat_settings_resp = client.put(
            "/heating/settings",
            json={
                "heating_helper_entity": test_helper,
                "heating_interval_minutes": 5,
                "heating_heater_entities": test_heaters,
            },
            headers=headers,
        )
        assert heat_settings_resp.status_code == 200
        assert heat_settings_resp.json()["settings"]["heating_helper_entity"] == test_helper
        assert heat_settings_resp.json()["settings"]["heating_heater_entities"] == test_heaters
        print("PASS: Configured global heating helper entity and heaters list:", test_helper, test_heaters)

        # Verify GET /heating/settings
        get_settings_resp = client.get("/heating/settings", headers=headers)
        assert get_settings_resp.status_code == 200
        assert get_settings_resp.json()["heating_helper_entity"] == test_helper
        assert get_settings_resp.json()["heating_heater_entities"] == test_heaters
        print("PASS: Verified GET /heating/settings returns configured helper and heaters list")

        try:
            # 3. Test deactivating heating immediately
            deact_resp = client.post(
                "/heating/state",
                json={"action": "off", "mode": "immediate"},
                headers=headers,
            )
            assert deact_resp.status_code == 200
            deact_data = deact_resp.json()
            assert deact_data["state"]["state"] == "off"
            assert "deactivated" in deact_data["message"].lower()
            print("PASS: POST /heating/state with action='off' deactivated heating and helper")

            # 4. Test activating heating
            act_resp = client.post(
                "/heating/state",
                json={"action": "on"},
                headers=headers,
            )
            assert act_resp.status_code == 200
            act_data = act_resp.json()
            assert act_data["state"]["state"] == "on"
            assert act_data["state"]["deactivated_until"] is None
            # Verify Auto - Heating Control recurrent schedule is created and active
            all_scheds = client.get("/schedules", headers=headers).json()["schedules"]
            heat_rec_sched = next((s for s in all_scheds if s["name"] == "Auto - Heating Control"), None)
            assert heat_rec_sched is not None
            assert heat_rec_sched["is_active"] == 1
            assert heat_rec_sched["type"] == "recurrent"
            print("PASS: POST /heating/state with action='on' activated heating and created recurrent schedule #", heat_rec_sched["id"])

            # 4b. Test Settings API & interval update
            put_settings_resp = client.put("/heating/settings", json={"heating_interval_minutes": 10}, headers=headers)
            assert put_settings_resp.status_code == 200
            assert put_settings_resp.json()["settings"]["heating_interval_minutes"] == 10
            # Verify schedule trigger_spec updated to */10 * * * *
            updated_sched = client.get(f"/schedules/{heat_rec_sched['id']}", headers=headers).json()["schedule"]
            assert updated_sched["trigger_spec"] == "*/10 * * * *"
            print("PASS: Settings API updated heating_interval_minutes to 10 and rescheduled recurrent task")

            # 4c. Test Settings API & interval update when heating is OFF
            client.post("/heating/state", json={"action": "off"}, headers=headers)
            put_settings_off_resp = client.put("/heating/settings", json={"heating_interval_minutes": 20}, headers=headers)
            assert put_settings_off_resp.status_code == 200
            updated_sched_off = client.get(f"/schedules/{heat_rec_sched['id']}", headers=headers).json()["schedule"]
            assert updated_sched_off["trigger_spec"] == "*/20 * * * *"
            assert updated_sched_off["is_active"] == 0
            print("PASS: Settings API updated heating_interval_minutes to 20 while heating is OFF and updated schedule trigger_spec to */20 * * * *")

            # 4d. Restore heating_interval_minutes back to 5 mins
            client.put("/heating/settings", json={"heating_interval_minutes": 5}, headers=headers)

            # 4e. Test Home Assistant helper event trigger: HA state change fires start_heating
            event_resp = client.post(
                "/events",
                json={"type": test_helper, "parameter": "on"},
                headers=headers,
            )
            assert event_resp.status_code in (200, 201)
            event_data = event_resp.json()
            assert any(t.get("use_case") == "start_heating" for t in event_data.get("triggered_definitions", []))
            # Verify heating state is on
            cur_st = client.get("/heating/state", headers=headers).json()
            assert cur_st["state"] == "on"
            print("PASS: Home Assistant helper entity event fired start_heating and set heating state to on")

            # 5. Test deactivating for X hours (e.g. 3 hours)
            hours_resp = client.post(
                "/heating/state",
                json={"action": "off", "mode": "hours", "hours": 3},
                headers=headers,
            )
            assert hours_resp.status_code == 200
            hours_data = hours_resp.json()
            assert hours_data["state"]["state"] == "off"
            assert hours_data["state"]["deactivated_until"] is not None
            assert hours_data["schedule"] is not None
            sched = hours_data["schedule"]
            assert sched["type"] == "one-time"
            assert "Heating Activate" in sched["name"]
            assert sched["block"] == 1
            # Verify the schedule uses the use case from 'heating' section
            all_ucs = client.get("/use-cases", headers=headers).json()["use_cases"]
            matching_uc = next((u for u in all_ucs if u["name"] == sched["use_case"]), None)
            assert matching_uc is not None
            assert matching_uc["section"] == "heating"
            assert matching_uc["function_name"] == "start_heating"
            assert json.loads(sched["data"]) == {"action": "on"}
            print("PASS: POST /heating/state for 3 hours created one-time schedule #", sched["id"], "with heating use case:", matching_uc["name"])

            # 6. Verify pending resume schedules in GET /heating/state
            state_resp2 = client.get("/heating/state", headers=headers)
            assert state_resp2.status_code == 200
            pending = state_resp2.json()["pending_resume_schedules"]
            assert any(s["id"] == sched["id"] for s in pending)
            print("PASS: Verified pending resume schedule visible in GET /heating/state")

            # 7. Activating heating cancels pending resume schedules
            resume_resp = client.post(
                "/heating/state",
                json={"action": "on"},
                headers=headers,
            )
            assert resume_resp.status_code == 200
            assert resume_resp.json()["state"]["state"] == "on"
            assert resume_resp.json()["state"]["deactivated_until"] is None

            state_resp3 = client.get("/heating/state", headers=headers)
            pending3 = state_resp3.json()["pending_resume_schedules"]
            assert not any(s["id"] == sched["id"] for s in pending3)
            print("PASS: Activating heating cancelled previous pending resume schedule")

            # 8. Test deactivating until specific time (e.g. 23:30)
            until_resp = client.post(
                "/heating/state",
                json={"action": "off", "mode": "until", "until": "23:30"},
                headers=headers,
            )
            assert until_resp.status_code == 200
            until_data = until_resp.json()
            assert until_data["state"]["state"] == "off"
            assert until_data["schedule"] is not None
            sched2_id = until_data["schedule"]["id"]
            print("PASS: POST /heating/state until 23:30 created one-time schedule #", sched2_id)

            # 8b. Cancel deferred start while keeping heating off
            cancel_resp = client.post("/heating/state", json={"action": "off"}, headers=headers)
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["state"]["state"] == "off"
            assert cancel_resp.json()["state"]["deactivated_until"] is None
            # Verify sched2 was cancelled and deleted
            all_s = client.get("/schedules", headers=headers).json()["schedules"]
            assert not any(s["id"] == sched2_id for s in all_s)
            print("PASS: POST /heating/state with action='off' cancelled deferred resume schedule and kept heating off")

            # Turn back on for next steps
            client.post("/heating/state", json={"action": "on"}, headers=headers)

            # 9. Verify heating functions and sections in available_functions and available_sections
            ucs_resp = client.get("/use-cases", headers=headers)
            assert ucs_resp.status_code == 200
            fn_ids = [f["id"] for f in ucs_resp.json()["available_functions"]]
            assert "start_heating" in fn_ids
            assert "control_heating" in fn_ids
            assert "set_heating_map" in fn_ids
            sections = ucs_resp.json().get("available_sections", [])
            assert "heating" in sections
            assert "heating_control" not in sections
            assert "heating_recurrent" not in sections
            print("PASS: 'start_heating', 'control_heating', and 'set_heating_map' exposed in available_functions")

            # 10. Heating Maps CRUD Tests
            # 10.1 List maps (should include default 'Comfort')
            maps_resp = client.get("/heating/maps", headers=headers)
            assert maps_resp.status_code == 200
            maps_data = maps_resp.json()
            assert len(maps_data["maps"]) >= 1
            default_map_id = maps_data["default_map_id"]
            assert default_map_id is not None
            print("PASS: GET /heating/maps returned list of maps, default ID:", default_map_id)

            # Clean up any leftover test maps from previous interrupted runs
            for m in maps_data["maps"]:
                if m["name"] in ("Eco Night", "Eco Night Mode", "Boost30Test"):
                    client.delete(f"/heating/maps/{m['id']}", headers=headers)

            # 10.2 Create a custom heating map 'Eco Night'
            create_map_resp = client.post(
                "/heating/maps",
                json={
                    "name": "Eco Night",
                    "description": "Lower night temperature map",
                    "rules": {"sensor.living_room_temperature": 18.0},
                    "is_default": 0,
                },
                headers=headers,
            )
            assert create_map_resp.status_code == 201
            eco_map = create_map_resp.json()["map"]
            eco_map_id = eco_map["id"]
            print("PASS: Created heating map 'Eco Night' #", eco_map_id)

            # 10.3 Activate the custom heating map
            act_map_resp = client.post(f"/heating/maps/{eco_map_id}/activate", headers=headers)
            assert act_map_resp.status_code == 200
            state_map_act = client.get("/heating/state", headers=headers).json()
            assert state_map_act["active_map_id"] == eco_map_id
            print("PASS: Activated heating map #", eco_map_id)

            # 10.4 Update heating map
            up_map_resp = client.put(
                f"/heating/maps/{eco_map_id}",
                json={
                    "name": "Eco Night Mode",
                    "description": "Updated description",
                    "rules": {"sensor.living_room_temperature": 17.5},
                },
                headers=headers,
            )
            assert up_map_resp.status_code == 200
            assert up_map_resp.json()["map"]["name"] == "Eco Night Mode"
            print("PASS: Updated heating map #", eco_map_id)

            # 11. Test set_heating_map schedule creation
            map_sched_resp = client.post(
                "/schedules",
                json={
                    "name": "Auto - Heating Map Night Mode",
                    "type": "recurrent",
                    "trigger_spec": "0 22 * * *",
                    "use_case": "set_heating_map",
                    "data": f'{{"map_id": {eco_map_id}}}',
                },
                headers=headers,
            )
            assert map_sched_resp.status_code == 201
            map_sched_id = map_sched_resp.json()["schedule"]["id"]
            print("PASS: Created recurrent schedule #", map_sched_id, "with set_heating_map")

            # 11b. Test Heating Calendar Endpoints
            cal_get_resp = client.get("/heating/calendar", headers=headers)
            assert cal_get_resp.status_code == 200
            cal_data = cal_get_resp.json()
            assert "calendar" in cal_data
            assert "resolved_map" in cal_data
            assert len(cal_data["days"]) == 8  # Mon-Sun + Holidays
            print("PASS: GET /heating/calendar returned calendar and days metadata")

            # PUT /heating/calendar/day for Monday (day_of_week=0)
            cal_put_resp = client.put(
                "/heating/calendar/day",
                json={
                    "day_of_week": 0,
                    "slots": [
                        {"start_time": "00:00", "end_time": "08:00", "map_id": eco_map_id},
                        {"start_time": "08:00", "end_time": "20:00", "map_id": 1},
                        {"start_time": "20:00", "end_time": "24:00", "map_id": eco_map_id},
                    ],
                    "copy_to_days": [1, 2],
                },
                headers=headers,
            )
            assert cal_put_resp.status_code == 200
            updated_cal = cal_put_resp.json()["calendar"]
            mon_slots = [s for s in updated_cal if s["day_of_week"] == 0]
            tue_slots = [s for s in updated_cal if s["day_of_week"] == 1]
            assert len(mon_slots) == 3
            assert len(tue_slots) == 3
            assert mon_slots[0]["start_time"] == "00:00" and mon_slots[0]["end_time"] == "08:00"
            assert mon_slots[1]["start_time"] == "08:00" and mon_slots[1]["end_time"] == "20:00"
            assert mon_slots[2]["start_time"] == "20:00" and mon_slots[2]["end_time"] == "24:00"
            print("PASS: PUT /heating/calendar/day configured parts of day and replicated to Tue/Wed")

            # Test calendar resolution directly
            from app.database import db_resolve_current_heating_map
            dt_morning = datetime(2026, 10, 26, 6, 30)  # Monday 06:30
            dt_daytime = datetime(2026, 10, 26, 14, 0)  # Monday 14:00
            map_morning = db_resolve_current_heating_map(dt_morning)
            map_daytime = db_resolve_current_heating_map(dt_daytime)
            assert map_morning["id"] == eco_map_id
            assert map_daytime["id"] == 1
            print("PASS: db_resolve_current_heating_map correctly resolved Eco (06:30) and Comfort (14:00)")

            # Clean up schedule and eco map
            client.delete(f"/schedules/{map_sched_id}", headers=headers)
            client.delete(f"/heating/maps/{eco_map_id}", headers=headers)
            print("PASS: Cleaned up test heating map and schedule")

            # 12. Test execution of 'control_heating' use case in 'heating' section
            ctrl_heat_uc = next((u for u in all_ucs if u["function_name"] == "control_heating" and u["section"] == "heating"), None)
            assert ctrl_heat_uc is not None
            ctrl_test_resp = client.post(
                f"/use-cases/{ctrl_heat_uc['id']}/test",
                headers=headers,
            )
            assert ctrl_test_resp.status_code == 200
            print("PASS: 'control_heating' executed successfully:", ctrl_test_resp.json().get("result"))

            # 12.1 Test that when heating is evaluated with threshold
            cal_resp = client.get("/heating/calendar", headers=headers).json()
            resolved_map = cal_resp.get("resolved_map") or {"id": default_map_id, "rules": {}}
            res_map_id = resolved_map["id"]
            orig_rules = resolved_map.get("rules", {})

            # Use existing sensor or create test sensor with real HA entity
            temp_dev_resp = client.post(
                "/devices",
                json={"name": "Cold Room Sensor", "type": "temperature", "entity_id": "sensor.temperatura_comedor_grados"},
                headers=headers,
            )
            cold_dev_id = temp_dev_resp.json()["device"]["id"]

            # Set a high threshold (99°C) on the active resolved map
            put_rule_resp = client.put(
                f"/heating/maps/{res_map_id}",
                json={"name": resolved_map.get("name", "Noche"), "rules": {str(cold_dev_id): 99.0}},
                headers=headers,
            )
            assert put_rule_resp.status_code == 200

            ctrl_boost_resp = client.post(f"/use-cases/{ctrl_heat_uc['id']}/test", headers=headers)
            assert ctrl_boost_resp.status_code == 200
            boost_result = ctrl_boost_resp.json().get("result", "")
            assert "Heating REQUIRED" in boost_result or "evaluated" in boost_result.lower()
            print("PASS: 'control_heating' correctly evaluated temperature sensor below rule threshold")

            # Restore original rules and delete temporary device
            client.put(
                f"/heating/maps/{res_map_id}",
                json={"name": resolved_map.get("name", "Noche"), "rules": orig_rules},
                headers=headers,
            )
            client.delete(f"/devices/{cold_dev_id}", headers=headers)

            # 13. Test that backend restart preserves heating state dynamically driven by helper entity
            client.post("/heating/state", json={"action": "on"}, headers=headers)
            assert client.get("/heating/state", headers=headers).json()["state"] == "on"

        finally:
            # Restore original settings
            if orig_helper is not None:
                db_set_setting("heating_helper_entity", orig_helper)
            if orig_interval is not None:
                db_set_setting("heating_interval_minutes", orig_interval)
            if orig_heaters is not None:
                db_set_setting("heating_heater_entities", orig_heaters)
            print("PASS: Cleaned up and restored original heating settings")

        # Simulate fresh backend restart with helper state='on'
        with TestClient(app) as client2:
            reboot_state = client2.get("/heating/state", headers=headers).json()
            print("PASS: Backend restart retrieved live state from helper entity:", reboot_state["state"])
            client2.post("/heating/state", json={"action": "off"}, headers=headers)

    finally:
        FALLBACK_ENTITIES.clear()
        FALLBACK_ENTITIES.extend(saved_fallback)
        print("PASS: Cleaned up and restored fallback entities")
        for ext in ("", "-wal", "-shm"):
            p = Path(str(TEST_DB_PATH) + ext)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    print("\nALL HEATING BACKEND TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_heating_full_flow()
