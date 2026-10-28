import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app, API_KEY
from app.database import db_is_holiday


def test_events_endpoint():
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. Test POST /events without API key -> 401
        resp = client.post("/events", json={"type": "sunrise", "parameter": ""})
        assert resp.status_code == 401, f"Expected 401 Unauthorized, got {resp.status_code}"
        print("PASS: 401 Unauthorized when missing API key on /events")

        # 2. Test POST /events with sunrise event
        sunrise_payload = {
            "type": "sunrise",
            "parameter": "06:45",
        }
        resp = client.post("/events", json=sunrise_payload, headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "success"
        assert "sunrise" in data["message"]
        assert data["event"]["type"] == "sunrise"
        assert data["event"]["parameter"] == "06:45"
        assert "id" in data["event"]
        assert "created_at" in data["event"]
        print("PASS: POST /events with sunrise event:", data)

        # 3. Test POST /events with sunset event
        sunset_payload = {
            "type": "sunset",
            "parameter": "20:30",
        }
        resp = client.post("/events", json=sunset_payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["event"]["type"] == "sunset"
        assert data["event"]["parameter"] == "20:30"
        print("PASS: POST /events with sunset event:", data)

        # 4. Test query param authentication (?api_key=...)
        resp = client.post(f"/events?api_key={API_KEY}", json={"type": "sunset", "parameter": "dusk"})
        assert resp.status_code == 200
        print("PASS: POST /events with query param authentication")

        # 5. Test alias /event
        resp = client.post("/event", json={"type": "sunrise", "parameter": "dawn"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["event"]["type"] == "sunrise"
        print("PASS: POST /event alias works")

        # 6. Test GET /events to retrieve history
        resp = client.get("/events", headers=headers)
        assert resp.status_code == 200
        events_list = resp.json()["events"]
        assert len(events_list) >= 4
        assert events_list[0]["type"] in ["sunrise", "sunset"]
        print(f"PASS: GET /events returned {len(events_list)} events")

        # 7. Test invalid payload (missing type) -> 422
        resp = client.post("/events", json={"parameter": "no_type"}, headers=headers)
        assert resp.status_code == 422
        print("PASS: 422 Unprocessable Entity when 'type' parameter is missing")


        # 8. Test Event Definitions CRUD
        # 8a. Create Event Definition for sunrise
        def_payload = {
            "name": "Morning Blinds Opening",
            "type": "sunrise",
            "parameter": "07:00",
            "use_case": "test_create_file",
            "data": "{}",
            "is_active": 1,
        }
        resp = client.post("/event-definitions", json=def_payload, headers=headers)
        assert resp.status_code == 201, f"Expected 201 Created, got {resp.status_code}: {resp.text}"
        created_def = resp.json()["event_definition"]
        def_id = created_def["id"]
        assert created_def["name"] == "Morning Blinds Opening"
        assert created_def["type"] == "sunrise"
        assert created_def["parameter"] == "07:00"
        assert created_def["use_case"] == "test_create_file"
        print("PASS: Created event definition:", created_def)

        # 8b. List Event Definitions
        resp = client.get("/event-definitions", headers=headers)
        assert resp.status_code == 200
        defs = resp.json()["event_definitions"]
        assert any(d["id"] == def_id for d in defs)
        print(f"PASS: Listed {len(defs)} event definitions")

        # 8c. Trigger event and verify matching definition executes
        resp = client.post("/events", json={"type": "sunrise", "parameter": "07:00"}, headers=headers)
        assert resp.status_code == 200
        event_result = resp.json()
        assert "triggered_definitions" in event_result
        assert any(d["definition_id"] == def_id for d in event_result["triggered_definitions"])
        matched_trigger = next(d for d in event_result["triggered_definitions"] if d["definition_id"] == def_id)
        assert matched_trigger["status"] == "executed"
        print("PASS: Event triggered matching event definition successfully:", matched_trigger)

        # 8d. Update Event Definition
        update_payload = {
            "name": "Morning Blinds Opening Updated",
            "type": "sunrise",
            "parameter": "07:15",
            "use_case": "test_create_file",
            "data": "{}",
            "is_active": 0,
        }
        resp = client.put(f"/event-definitions/{def_id}", json=update_payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["event_definition"]["name"] == "Morning Blinds Opening Updated"
        assert resp.json()["event_definition"]["is_active"] == 0
        print("PASS: Updated event definition")

        # 8e. Delete Event Definition
        resp = client.delete(f"/event-definitions/{def_id}", headers=headers)
        assert resp.status_code == 200
        print("PASS: Deleted event definition")

        # 9. Test Holiday Filtering on Event Execution
        # 9a. Event with holiday='holiday' (today is Sunday = holiday -> should execute)
        h_payload = {
            "name": "Holiday Only Event",
            "type": "custom_holiday_test",
            "parameter": "",
            "use_case": "test_create_file",
            "holiday": "holiday",
            "is_active": 1,
        }
        h_def_resp = client.post("/event-definitions", json=h_payload, headers=headers)
        assert h_def_resp.status_code == 201
        h_def_id = h_def_resp.json()["event_definition"]["id"]

        # 9b. Event with holiday='not_holiday' (today is Sunday = holiday -> should be skipped)
        nh_payload = {
            "name": "Workdays Only Event",
            "type": "custom_holiday_test",
            "parameter": "",
            "use_case": "test_create_file",
            "holiday": "not_holiday",
            "is_active": 1,
        }
        nh_def_resp = client.post("/event-definitions", json=nh_payload, headers=headers)
        assert nh_def_resp.status_code == 201
        nh_def_id = nh_def_resp.json()["event_definition"]["id"]

        # Trigger event 'custom_holiday_test'
        trig_resp = client.post("/events", json={"type": "custom_holiday_test"}, headers=headers)
        assert trig_resp.status_code == 200
        trig_defs = trig_resp.json()["triggered_definitions"]

        h_result = next((d for d in trig_defs if d["definition_id"] == h_def_id), None)
        nh_result = next((d for d in trig_defs if d["definition_id"] == nh_def_id), None)

        assert h_result is not None, "Expected holiday event to be in triggered definitions"
        assert nh_result is not None, "Expected workdays event to be in triggered definitions"

        is_holiday_or_weekend = datetime.now().weekday() >= 5 or db_is_holiday(datetime.now().strftime("%Y-%m-%d"))
        if is_holiday_or_weekend:
            assert h_result["status"] == "executed", f"Expected holiday event to execute, got {h_result}"
            assert nh_result["status"] == "skipped", f"Expected workdays event to be skipped on holiday/weekend, got {nh_result}"
            print("PASS: Holiday filter logic verified: holiday event executed, workdays event skipped on weekend/holiday")
        else:
            assert h_result["status"] == "skipped", f"Expected holiday event to be skipped on workday, got {h_result}"
            assert nh_result["status"] == "executed", f"Expected workdays event to execute on workday, got {nh_result}"
            print("PASS: Holiday filter logic verified: holiday event skipped on workday, workdays event executed")

        # Clean up
        client.delete(f"/event-definitions/{h_def_id}", headers=headers)
        client.delete(f"/event-definitions/{nh_def_id}", headers=headers)
        print("PASS: Cleaned up holiday test event definitions")

        # 10. Test Event Parameter Matching (e.g. rain start vs rain stop)
        rain_start_payload = {
            "name": "Rain Start Action",
            "type": "rain_test",
            "parameter": "start",
            "use_case": "test_create_file",
            "is_active": 1,
        }
        resp = client.post("/event-definitions", json=rain_start_payload, headers=headers)
        assert resp.status_code == 201
        rain_start_id = resp.json()["event_definition"]["id"]

        rain_stop_payload = {
            "name": "Rain Stop Action",
            "type": "rain_test",
            "parameter": "stop",
            "use_case": "test_create_file",
            "is_active": 1,
        }
        resp = client.post("/event-definitions", json=rain_stop_payload, headers=headers)
        assert resp.status_code == 201
        rain_stop_id = resp.json()["event_definition"]["id"]

        # Trigger rain_test with parameter "stop"
        resp = client.post("/events", json={"type": "rain_test", "parameter": "stop"}, headers=headers)
        assert resp.status_code == 200
        trig = resp.json()["triggered_definitions"]
        assert any(d["definition_id"] == rain_stop_id and d["status"] == "executed" for d in trig), "Rain stop should execute"
        assert not any(d["definition_id"] == rain_start_id for d in trig), "Rain start must NOT execute on rain stop"
        print("PASS: Rain stop triggered only the rain stop definition; rain start was skipped")

        # Trigger rain_test with parameter "start"
        resp = client.post("/events", json={"type": "rain_test", "parameter": "start"}, headers=headers)
        assert resp.status_code == 200
        trig = resp.json()["triggered_definitions"]
        assert any(d["definition_id"] == rain_start_id and d["status"] == "executed" for d in trig), "Rain start should execute"
        assert not any(d["definition_id"] == rain_stop_id for d in trig), "Rain stop must NOT execute on rain start"
        print("PASS: Rain start triggered only the rain start definition; rain stop was skipped")

        # Clean up rain test definitions
        client.delete(f"/event-definitions/{rain_start_id}", headers=headers)
        client.delete(f"/event-definitions/{rain_stop_id}", headers=headers)
        print("PASS: Cleaned up rain test definitions")


if __name__ == "__main__":
    test_events_endpoint()
    print("All events endpoint tests passed successfully!")
