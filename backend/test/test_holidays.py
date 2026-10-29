import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Add backend directory to sys.path so 'app' can be imported
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.database import db_delete_holiday, db_get_holiday_by_date, db_list_holidays
from app.main import API_KEY, app
from app.scheduler import APP_TIMEZONE, SYSTEM_FUNCTIONS, fn_add_holiday, fn_get_year_holidays


def run_holidays_tests():
    print("--- Starting Holidays & add_holiday Function Tests ---")

    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. Test GET /holidays
        get_res = client.get("/holidays", headers=headers)
        assert get_res.status_code == 200, f"Expected 200, got {get_res.status_code}"
        assert "holidays" in get_res.json()
        print("PASS: GET /holidays returned 200 and list of holidays")

        # 2. Test POST /holidays with invalid date format
        bad_res = client.post("/holidays", json={"date": "invalid-date", "name": "Bad"}, headers=headers)
        assert bad_res.status_code == 400, f"Expected 400, got {bad_res.status_code}"
        print("PASS: POST /holidays rejected invalid date format")

        # 3. Test POST /holidays with valid date
        test_date = "2099-12-31"
        # Clean up in case exists
        existing = db_get_holiday_by_date(test_date)
        if existing:
            db_delete_holiday(existing["id"])

        create_res = client.post("/holidays", json={"date": test_date, "name": "New Year's Eve 2099"}, headers=headers)
        assert create_res.status_code == 201, f"Expected 201, got {create_res.status_code}: {create_res.text}"
        created_data = create_res.json()["holiday"]
        assert created_data["date"] == test_date
        assert created_data["name"] == "New Year's Eve 2099"
        holiday_id = created_data["id"]
        print(f"PASS: Created holiday #{holiday_id} for {test_date}")

        # 4. Test duplicate POST /holidays returns 409
        dup_res = client.post("/holidays", json={"date": test_date, "name": "Duplicate"}, headers=headers)
        assert dup_res.status_code == 409, f"Expected 409 conflict, got {dup_res.status_code}"
        print("PASS: Duplicate holiday creation returned 409 Conflict")

        # 5. Test DELETE /holidays/{id}
        del_res = client.delete(f"/holidays/{holiday_id}", headers=headers)
        assert del_res.status_code == 200, f"Expected 200, got {del_res.status_code}"
        print(f"PASS: Deleted holiday #{holiday_id}")

        # 5b. Verify logging of holiday creation and deletion
        logs_res = client.get("/logs?search=Holiday", headers=headers)
        assert logs_res.status_code == 200
        logs_list = logs_res.json()["logs"]
        messages = [log["message"] for log in logs_list]
        has_create_log = any(f"Holiday created: ID #{holiday_id}" in msg for msg in messages)
        has_delete_log = any(f"Holiday deleted: ID #{holiday_id}" in msg for msg in messages)
        assert has_create_log, f"Expected 'Holiday created: ID #{holiday_id}' in logs: {messages[:5]}"
        assert has_delete_log, f"Expected 'Holiday deleted: ID #{holiday_id}' in logs: {messages[:5]}"
        print(f"PASS: Verified logs for created and deleted holiday #{holiday_id} are visible in backend logs")

        # 6. Test delete non-existent holiday returns 404
        del_404 = client.delete(f"/holidays/{holiday_id}", headers=headers)
        assert del_404.status_code == 404, f"Expected 404, got {del_404.status_code}"
        print("PASS: Delete non-existent holiday returned 404")

        # 7. Test add_holiday in SYSTEM_FUNCTIONS
        assert "add_holiday" in SYSTEM_FUNCTIONS
        assert SYSTEM_FUNCTIONS["add_holiday"]["name"] == "Add Holiday"
        print("PASS: 'add_holiday' is registered in SYSTEM_FUNCTIONS")

        # 8. Test fn_add_holiday with when='today'
        now_local = datetime.now(APP_TIMEZONE)
        today_str = now_local.strftime("%Y-%m-%d")
        existing_today = db_get_holiday_by_date(today_str)
        if existing_today:
            db_delete_holiday(existing_today["id"])

        today_msg = asyncio.run(fn_add_holiday(data=json.dumps({"when": "today", "name": "Today Test Holiday"})))
        assert "Added holiday" in today_msg
        assert today_str in today_msg
        print(f"PASS: fn_add_holiday('today') succeeded: {today_msg}")

        # Test duplicate fn_add_holiday('today') handles gracefully
        today_dup_msg = asyncio.run(fn_add_holiday(data={"when": "today"}))
        assert "already exists" in today_dup_msg
        print(f"PASS: fn_add_holiday duplicate today handled: {today_dup_msg}")

        # 9. Test fn_add_holiday with when='tomorrow'
        tomorrow_str = (now_local + timedelta(days=1)).strftime("%Y-%m-%d")
        existing_tomorrow = db_get_holiday_by_date(tomorrow_str)
        if existing_tomorrow:
            db_delete_holiday(existing_tomorrow["id"])

        tomorrow_msg = asyncio.run(fn_add_holiday(data=json.dumps({"when": "tomorrow"})))
        assert "Added holiday" in tomorrow_msg
        assert tomorrow_str in tomorrow_msg
        print(f"PASS: fn_add_holiday('tomorrow') succeeded: {tomorrow_msg}")

        # Test duplicate fn_add_holiday('tomorrow') handles gracefully
        tomorrow_dup_msg = asyncio.run(fn_add_holiday(data="tomorrow"))
        assert "already exists" in tomorrow_dup_msg
        print(f"PASS: fn_add_holiday duplicate tomorrow handled: {tomorrow_dup_msg}")

        # Clean up test today and tomorrow
        clean_today = db_get_holiday_by_date(today_str)
        if clean_today:
            db_delete_holiday(clean_today["id"])
        clean_tom = db_get_holiday_by_date(tomorrow_str)
        if clean_tom:
            db_delete_holiday(clean_tom["id"])
        print("PASS: Cleaned up temporary today/tomorrow holidays")

        # 10. Test /use-cases list returns add_holiday and get_year_holidays in available_functions
        uc_res = client.get("/use-cases", headers=headers)
        assert uc_res.status_code == 200
        available_fns = [f["id"] for f in uc_res.json()["available_functions"]]
        assert "add_holiday" in available_fns
        assert "get_year_holidays" in available_fns
        print("PASS: 'add_holiday' and 'get_year_holidays' are exposed in available_functions via GET /use-cases")

        # 11. Test get_year_holidays in SYSTEM_FUNCTIONS
        assert "get_year_holidays" in SYSTEM_FUNCTIONS
        assert SYSTEM_FUNCTIONS["get_year_holidays"]["name"] == "Get Year Holidays"
        print("PASS: 'get_year_holidays' is registered in SYSTEM_FUNCTIONS")

        # 12. Test fn_get_year_holidays function execution (first pass imports holidays for ES-CT by default)
        sync_result = asyncio.run(fn_get_year_holidays())
        assert "Imported" in sync_result
        assert "publicholidays" in sync_result
        assert "county: ES-CT" in sync_result
        print(f"PASS: fn_get_year_holidays execution: {sync_result}")

        # 13. Test duplicate check on second pass (all dates already exist)
        second_pass = asyncio.run(fn_get_year_holidays())
        assert "Imported 0 holidays" in second_pass
        assert "skipped" in second_pass
        assert "county: ES-CT" in second_pass
        print(f"PASS: fn_get_year_holidays duplicate prevention verified: {second_pass}")

        # 14. Test fn_get_year_holidays with explicit county in data parameter
        md_result = asyncio.run(fn_get_year_holidays(data={"county": "ES-MD"}))
        assert "county: ES-MD" in md_result
        print(f"PASS: fn_get_year_holidays with explicit county: {md_result}")

        # 15. Test POST /holidays/sync endpoint with default and custom payload
        sync_res = client.post("/holidays/sync", json={"county": "ES-CT"}, headers=headers)
        assert sync_res.status_code == 200
        sync_json = sync_res.json()
        assert sync_json["status"] == "success"
        assert len(sync_json["holidays"]) > 0
        assert "ES-CT" in sync_json["message"]
        print(f"PASS: POST /holidays/sync succeeded: {sync_json['message']}")

        # 16. Test cancelling deferred one-time schedules when a holiday for today is added
        from app.scheduler import fn_move_blind, dispatch_event_triggers, create_and_register_schedule
        from app.database import db_list_schedules, db_create_event_definition, db_delete_event_definition, db_list_event_definitions

        # Clean up any leftover test event definitions
        for ed in db_list_event_definitions():
            if ed.get("type") == "holiday_notify_test":
                db_delete_event_definition(ed["id"])

        # 16a. Create a deferred one-time schedule
        future_time = now_local + timedelta(hours=3)
        future_str = future_time.strftime("%H:%M")
        blind_res = asyncio.run(fn_move_blind(
            name="Test Auto Blind To Be Cancelled",
            use_case="move_blind",
            data={"entity": "cover.test_cancel", "position": 50, "not_before": future_str}
        ))
        assert "deferred until" in blind_res
        all_s = db_list_schedules()
        def_s = next((s for s in all_s if "Test Auto Blind To Be Cancelled" in s["name"] and s["type"] == "one-time"), None)
        assert def_s is not None
        assert "deferred" in def_s["name"]
        print(f"PASS: Created deferred one-time schedule #{def_s['id']}")

        # 16b. Create event definition for holiday today with notify=1
        ev_payload = {
            "name": "Holiday Test Notification",
            "type": "holiday_notify_test",
            "parameter": "today",
            "use_case": "add_holiday",
            "data": json.dumps({"when": "today", "name": "Deferred Cancel Test Holiday"}),
            "holiday": "all_days",
            "notify": 1,
            "is_active": 1,
        }
        ev_resp = client.post("/event-definitions", json=ev_payload, headers=headers)
        assert ev_resp.status_code == 201
        ev_id = ev_resp.json()["event_definition"]["id"]

        # 16c. Trigger the event with standard message: should add holiday, cancel the deferred schedule, and append deferred count
        with patch("app.scheduler.dispatch_notifications") as mock_dispatch:
            trig_res = asyncio.run(dispatch_event_triggers("holiday_notify_test", "today"))
            assert len(trig_res) == 1
            assert trig_res[0]["status"] == "executed"
            mock_dispatch.assert_called_once()
            call_msg = mock_dispatch.call_args[1].get("message", "")
            assert "1 deferred schedule(s) cancelled" in call_msg
            print(f"PASS: Standard message included deferred count: {call_msg}")

        # 16d. Test custom notification message: should NOT append deferred message
        with patch("app.scheduler.dispatch_notifications") as mock_dispatch_custom:
            import app.scheduler as sched_module
            sched_module._last_cancelled_deferred_count = 2

            # Update event definition to have a custom message
            client.put(f"/event-definitions/{ev_id}", json={
                "name": "Holiday Test Notification",
                "type": "holiday_notify_test",
                "parameter": "today",
                "use_case": "add_holiday",
                "notification_message": "Custom holiday announcement text",
                "holiday": "all_days",
                "notify": 1,
                "is_active": 1,
            }, headers=headers)

            asyncio.run(dispatch_event_triggers("holiday_notify_test", "today"))
            mock_dispatch_custom.assert_called_once()
            custom_call_msg = mock_dispatch_custom.call_args[1].get("message", "")
            assert custom_call_msg == "Custom holiday announcement text", f"Expected exact custom message, got: {custom_call_msg}"
            assert "deferred schedule(s) cancelled" not in custom_call_msg
            print(f"PASS: Custom notification message did NOT include deferred message: {custom_call_msg}")

        # Verify the deferred schedule is now deleted
        all_s_after = db_list_schedules()
        cancelled_sched = next((s for s in all_s_after if s["id"] == def_s["id"]), None)
        assert cancelled_sched is None, "Deferred schedule must be cancelled and removed"
        print("PASS: Deferred schedule was successfully cancelled upon today holiday trigger")

        # Clean up test event definition & holiday
        client.delete(f"/event-definitions/{ev_id}", headers=headers)
        test_h = db_get_holiday_by_date(today_str)
        if test_h:
            db_delete_holiday(test_h["id"])
        print("PASS: Cleaned up deferred schedule cancellation test fixtures")

    print("ALL HOLIDAYS TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_holidays_tests()
