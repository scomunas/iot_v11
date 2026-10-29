import os
import sys
import unittest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import (
    db_create_use_case,
    db_delete_use_case,
    db_create_schedule,
    db_delete_schedule,
    db_create_event_definition,
    db_delete_event_definition,
    db_list_use_cases_by_section,
)
from app.scheduler import dispatch_notifications, execute_schedule_task, dispatch_event_triggers
import asyncio

API_KEY = os.environ.get("API_KEY", "iot_secret_api_key_2026")
client = TestClient(app)
AUTH_HEADERS = {"X-API-Key": API_KEY}

def test_notification_feature():
    from app.database import db_get_setting, db_set_setting
    saved_channels = db_get_setting("notification_channels")
    try:
        _run_notification_feature_tests()
    finally:
        if saved_channels is not None:
            db_set_setting("notification_channels", saved_channels)


def _run_notification_feature_tests():
    print("\n--- Starting Notification Parameter & Dispatch Tests ---")

    # 1. Check sections do NOT include 'notification' (notification is now a dedicated settings channel, not a use case)
    res = client.get("/use-cases", headers=AUTH_HEADERS)
    assert res.status_code == 200, res.text
    sections = res.json().get("available_sections", [])
    assert "notification" not in sections, f"Expected 'notification' to be removed from available_sections: {sections}"
    print("PASS: 'notification' is no longer in use-cases sections")

    # 2. Check notification channels endpoint
    channels_res = client.get("/notifications/channels", headers=AUTH_HEADERS)
    assert channels_res.status_code == 200, channels_res.text
    channels = channels_res.json()["channels"]
    assert any(c["id"] == "telegram" for c in channels)
    print(f"PASS: GET /notifications/channels returned {len(channels)} channel(s)")

    # 2b. Test updating notification channel configuration
    update_res = client.put(
        "/notifications/channels/telegram",
        json={"enabled": True, "config": {"chat_id": "-1003245904342"}},
        headers=AUTH_HEADERS,
    )
    assert update_res.status_code == 200, update_res.text
    assert update_res.json()["channel"]["enabled"] is True
    print("PASS: PUT /notifications/channels/telegram updated channel successfully")

    # 2c. Test sending test notification via channel endpoint
    test_res = client.post(
        "/notifications/test",
        json={"channel_id": "telegram", "message": "Test alert via notifications/test"},
        headers=AUTH_HEADERS,
    )
    assert test_res.status_code == 200, test_res.text
    assert test_res.json()["status"] == "success"
    print("PASS: POST /notifications/test sent alert successfully")

    # 3. Test direct dispatch_notifications
    asyncio.run(
        dispatch_notifications(
            message="Test direct dispatch message",
            source_type="test",
            source_id=999,
            source_name="Test Direct Dispatch"
        )
    )
    print("PASS: dispatch_notifications executed successfully")

    # 4. Create a schedule with notify=1 and custom message
    create_sch_payload = {
        "name": "Test Notification Schedule",
        "type": "recurrent",
        "trigger_spec": "0 12 * * *",
        "use_case": "test_create_file",
        "data": "{}",
        "notify": 1,
        "notification_message": "Custom test schedule message alert"
    }
    sch_res = client.post("/schedules", json=create_sch_payload, headers=AUTH_HEADERS)
    assert sch_res.status_code == 201, sch_res.text
    sch_data = sch_res.json()["schedule"]
    sch_id = sch_data["id"]
    assert sch_data["notify"] == 1
    assert sch_data["notification_message"] == "Custom test schedule message alert"
    print(f"PASS: Created schedule #{sch_id} with notify=1 and custom message")

    # 5. Execute schedule task directly to verify notification dispatch
    asyncio.run(execute_schedule_task(sch_id, "Test Notification Schedule", "recurrent", "test_create_file", "{}"))
    print(f"PASS: execute_schedule_task triggered for schedule #{sch_id}")

    # 6. Create an event definition with notify=1 and custom message
    create_ev_payload = {
        "name": "Test Notification Event",
        "type": "rain_alert_test",
        "parameter": "heavy",
        "use_case": "test_create_file",
        "data": "{}",
        "holiday": "all_days",
        "notify": 1,
        "notification_message": "Custom test event alert: heavy rain"
    }
    ev_res = client.post("/event-definitions", json=create_ev_payload, headers=AUTH_HEADERS)
    assert ev_res.status_code == 201, ev_res.text
    ev_data = ev_res.json()["event_definition"]
    ev_id = ev_data["id"]
    assert ev_data["notify"] == 1
    assert ev_data["notification_message"] == "Custom test event alert: heavy rain"
    print(f"PASS: Created event definition #{ev_id} with notify=1 and custom message")

    # 7. Trigger the event via dispatch_event_triggers
    triggers = asyncio.run(dispatch_event_triggers("rain_alert_test", "heavy"))
    assert len(triggers) == 1, f"Expected 1 triggered definition, got {len(triggers)}"
    assert triggers[0]["definition_id"] == ev_id
    assert triggers[0]["status"] == "executed"
    print(f"PASS: dispatch_event_triggers executed event #{ev_id} and dispatched notifications")

    # 8. Clean up
    del_sch = client.delete(f"/schedules/{sch_id}", headers=AUTH_HEADERS)
    assert del_sch.status_code == 200
    del_ev = client.delete(f"/event-definitions/{ev_id}", headers=AUTH_HEADERS)
    assert del_ev.status_code == 200
    print("PASS: Cleaned up test schedule and event definition")

    print("\nALL NOTIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_notification_feature()
