import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend directory to sys.path so 'app' can be imported
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app, API_KEY
from app.database import db_get_heating_state, db_set_heating_state


def test_heating_full_flow():
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        print("\n--- Starting Heating System Backend Tests ---")

        # 1. Test GET /heating/state (heating state is preserved from database)
        state_resp = client.get("/heating/state", headers=headers)
        assert state_resp.status_code == 200, f"GET /heating/state failed: {state_resp.text}"
        data = state_resp.json()
        assert "state" in data
        assert "devices" in data
        assert "pending_resume_schedules" in data
        print("PASS: GET /heating/state returned valid state from DB:", data["state"])

        # 2. Configure a heating test device
        dev_resp = client.post(
            "/devices",
            json={
                "name": "Living Room Radiator",
                "type": "heating",
                "entity_id": "climate.living_room_thermostat",
            },
            headers=headers,
        )
        assert dev_resp.status_code == 201
        test_device = dev_resp.json()["device"]
        test_device_id = test_device["id"]
        print("PASS: Configured test heating device #", test_device_id)

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
            print("PASS: POST /heating/state with action='off' deactivated heating")

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
            settings_resp = client.get("/settings", headers=headers)
            assert settings_resp.status_code == 200
            assert "heating_interval_minutes" in settings_resp.json()["settings"]
            orig_interval = int(settings_resp.json()["settings"].get("heating_interval_minutes", 5))
            put_settings_resp = client.put("/settings", json={"heating_interval_minutes": 10}, headers=headers)
            assert put_settings_resp.status_code == 200
            assert put_settings_resp.json()["settings"]["heating_interval_minutes"] == 10
            # Verify schedule trigger_spec updated to */10 * * * *
            updated_sched = client.get(f"/schedules/{heat_rec_sched['id']}", headers=headers).json()["schedule"]
            assert updated_sched["trigger_spec"] == "*/10 * * * *"
            print("PASS: Settings API updated heating_interval_minutes to 10 and rescheduled recurrent task")

            # 4c. Test Settings API & interval update when heating is OFF
            client.post("/heating/state", json={"action": "off"}, headers=headers)
            put_settings_off_resp = client.put("/settings", json={"heating_interval_minutes": 20}, headers=headers)
            assert put_settings_off_resp.status_code == 200
            updated_sched_off = client.get(f"/schedules/{heat_rec_sched['id']}", headers=headers).json()["schedule"]
            assert updated_sched_off["trigger_spec"] == "*/20 * * * *"
            assert updated_sched_off["is_active"] == 0
            print("PASS: Settings API updated heating_interval_minutes to 20 while heating is OFF and updated schedule trigger_spec to */20 * * * *")

            # 4d. Restore heating_interval_minutes back to default (5 mins)
            put_restore_resp = client.put("/settings", json={"heating_interval_minutes": orig_interval}, headers=headers)
            assert put_restore_resp.status_code == 200
            print(f"PASS: Restored heating_interval_minutes back to default: {orig_interval} mins")

            # Turn heating back on before next step
            client.post("/heating/state", json={"action": "on"}, headers=headers)

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
            # Verify the schedule uses the use case from 'heating_control' section
            all_ucs = client.get("/use-cases", headers=headers).json()["use_cases"]
            matching_uc = next((u for u in all_ucs if u["name"] == sched["use_case"]), None)
            assert matching_uc is not None
            assert matching_uc["section"] == "heating_control"
            print("PASS: POST /heating/state for 3 hours created one-time schedule #", sched["id"], "with heating_control use case:", matching_uc["name"])

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
            assert "heating" not in sections
            assert "heating_control" in sections
            assert "heating_recurrent" in sections
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

            # 10.2 Create a new Heating Map (e.g. 'Eco Night')
            create_map_resp = client.post(
                "/heating/maps",
                json={
                    "name": "Eco Night",
                    "description": "Lower nighttime temperature rules",
                    "rules": {"104": 18.0},
                    "is_default": 0,
                },
                headers=headers,
            )
            assert create_map_resp.status_code == 201
            eco_map = create_map_resp.json()["map"]
            eco_map_id = eco_map["id"]
            assert eco_map["name"] == "Eco Night"
            assert eco_map["rules"] == {"104": 18.0}
            print("PASS: POST /heating/maps created map #", eco_map_id)

            # 10.3 Update heating map
            update_map_resp = client.put(
                f"/heating/maps/{eco_map_id}",
                json={
                    "name": "Eco Night Mode",
                    "description": "Updated description",
                    "rules": {"104": 17.5},
                },
                headers=headers,
            )
            assert update_map_resp.status_code == 200
            assert update_map_resp.json()["map"]["rules"] == {"104": 17.5}
            print("PASS: PUT /heating/maps updated rules successfully")

            # 10.4 Activate heating map
            act_map_resp = client.post(f"/heating/maps/{eco_map_id}/activate", headers=headers)
            assert act_map_resp.status_code == 200
            assert act_map_resp.json()["state"]["active_map_id"] == eco_map_id
            print("PASS: Activated 'Eco Night Mode' map")

            # 10.5 Verify state returns active map
            state_chk = client.get("/heating/state", headers=headers)
            assert state_chk.status_code == 200
            assert state_chk.json()["active_map_id"] == eco_map_id
            assert state_chk.json()["active_map"]["name"] == "Eco Night Mode"
            print("PASS: GET /heating/state reflects newly active heating map")

            # 10.6 Test changing heating map via executable function fn_set_heating_map
            # Create a schedule that calls set_heating_map
            map_sched_resp = client.post(
                "/schedules",
                json={
                    "name": "Auto - Heating Map - Comfort at 07:00",
                    "type": "recurrent",
                    "trigger_spec": "0 7 * * *",
                    "use_case": "set_heating_map",
                    "data": {"map_name": "Comfort"},
                },
                headers=headers,
            )
            assert map_sched_resp.status_code == 201
            map_sched_id = map_sched_resp.json()["schedule"]["id"]
            print("PASS: Created heating map schedule #", map_sched_id)

            # Test use case execution for set_heating_map
            set_map_payload = {
                "name": "test_set_heating_map",
                "function_name": "set_heating_map",
                "description": "Switches active heating map",
            }
            create_uc_resp = client.post("/use-cases", json=set_map_payload, headers=headers)
            assert create_uc_resp.status_code == 201
            set_map_uc_id = create_uc_resp.json()["use_case"]["id"]

            test_uc_resp = client.post(
                f"/use-cases/{set_map_uc_id}/test",
                json={"map_name": "Comfort"},
                headers=headers,
            )
            assert test_uc_resp.status_code == 200
            # Verify active map switched back to Comfort
            state_chk2 = client.get("/heating/state", headers=headers)
            assert state_chk2.json()["active_map"]["name"] == "Comfort"
            print("PASS: 'set_heating_map' function successfully switched active map to 'Comfort'")
            client.delete(f"/use-cases/{set_map_uc_id}", headers=headers)

            # 14. Test Weekly Heating Calendar API & resolution
            cal_get_resp = client.get("/heating/calendar", headers=headers)
            assert cal_get_resp.status_code == 200
            cal_data = cal_get_resp.json()
            assert "calendar" in cal_data
            assert "days" in cal_data
            assert len(cal_data["days"]) == 8
            assert "resolved_map" in cal_data
            print("PASS: GET /heating/calendar returned slots and resolved map:", cal_data["resolved_map"]["name"])

            # Configure Monday (0) into 3 parts of the day:
            # 00:00 - 08:00 (Eco map), 08:00 - 20:00 (Comfort map), 20:00 - 24:00 (Eco map)
            # And copy to Tuesday (1) and Wednesday (2)
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

            # 12. Test execution of 'control_heating' use case in 'heating_control' section
            ctrl_heat_uc = next((u for u in all_ucs if u["function_name"] == "control_heating" and u["section"] in ("heating_control", "heating_recurrent")), None)
            assert ctrl_heat_uc is not None
            ctrl_test_resp = client.post(
                f"/use-cases/{ctrl_heat_uc['id']}/test",
                headers=headers,
            )
            assert ctrl_test_resp.status_code == 200
            print("PASS: 'control_heating' executed successfully:", ctrl_test_resp.json().get("result"))

            # 12.1 Test that when heating is required, setpoint is 30.0°C
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
            assert "30.0°C" in boost_result or "30°C" in boost_result, f"Expected 30.0°C in result: {boost_result}"
            print("PASS: 'control_heating' correctly activated heating devices at 30.0°C setpoint")

            # Restore original rules and delete temporary device
            client.put(
                f"/heating/maps/{res_map_id}",
                json={"name": resolved_map.get("name", "Noche"), "rules": orig_rules},
                headers=headers,
            )
            client.delete(f"/devices/{cold_dev_id}", headers=headers)

            # 13. Test that backend restart preserves heating state stored in DB
            client.post("/heating/state", json={"action": "on"}, headers=headers)
            assert client.get("/heating/state", headers=headers).json()["state"] == "on"

        finally:
            # Clean up test device and ensure heating_interval_minutes is 5
            client.delete(f"/devices/{test_device_id}", headers=headers)
            client.put("/settings", json={"heating_interval_minutes": 5}, headers=headers)
            print("PASS: Cleaned up test device and ensured heating_interval_minutes is 5")

    # Simulate fresh backend restart with state='on' in DB
    with TestClient(app) as client2:
        reboot_state = client2.get("/heating/state", headers=headers).json()
        assert reboot_state["state"] == "on", f"Expected state to remain 'on' across backend reboot, got {reboot_state['state']}"
        print("PASS: Backend restart preserved heating state 'on' from database")

        # Now test that if state was 'off', reboot also preserves 'off'
        client2.post("/heating/state", json={"action": "off"}, headers=headers)
        assert client2.get("/heating/state", headers=headers).json()["state"] == "off"

    # Simulate second backend restart with state='off' in DB
    with TestClient(app) as client3:
        reboot_state_off = client3.get("/heating/state", headers=headers).json()
        assert reboot_state_off["state"] == "off", f"Expected state to remain 'off' across backend reboot, got {reboot_state_off['state']}"
        print("PASS: Backend restart preserved heating state 'off' from database")

    print("\nALL HEATING BACKEND TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_heating_full_flow()
