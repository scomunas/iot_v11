import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend directory to sys.path so 'app' can be imported
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app, API_KEY
from app.scheduler import register_task_handler, restore_schedules_from_db, scheduler

executed_events = []


@register_task_handler("test_action")
async def mock_test_action(schedule_id, name, schedule_type, use_case):
    executed_events.append({"id": schedule_id, "name": name, "use_case": use_case})
    print(f"--> Mock handler triggered for {use_case}!")


def test_schedules_full_flow():
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. Test health check
        health_resp = client.get("/health", headers=headers)
        assert health_resp.status_code == 200
        assert health_resp.json()["scheduler"] == "running"
        print("PASS: Health check reports scheduler running")

        # 2. Create a recurrent schedule (e.g. every minute)
        recurrent_payload = {
            "name": "Check Living Room Sensors",
            "type": "recurrent",
            "trigger_spec": "*/1 * * * *",
            "use_case": "check_sensors",
        }
        rec_resp = client.post("/schedules", json=recurrent_payload, headers=headers)
        assert rec_resp.status_code == 201
        rec_data = rec_resp.json()["schedule"]
        rec_id = rec_data["id"]
        print("PASS: Created recurrent schedule:", rec_id)

        # 3. Create a one-time schedule 1 second in the future to test execution
        future_time = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        one_time_payload = {
            "name": "Turn off heater",
            "type": "one-time",
            "trigger_spec": future_time,
            "use_case": "test_action",
        }
        ot_resp = client.post("/schedules", json=one_time_payload, headers=headers)
        assert ot_resp.status_code == 201
        ot_data = ot_resp.json()["schedule"]
        ot_id = ot_data["id"]
        print("PASS: Created one-time schedule:", ot_id)

        # Wait 2 seconds for execution of one-time task
        time.sleep(2.0)
        assert any(e["use_case"] == "test_action" for e in executed_events), "Task handler should have been executed!"
        print("PASS: Task handler was triggered successfully!")

        # 4. Check list of schedules & memory status
        list_resp = client.get("/schedules", headers=headers)
        assert list_resp.status_code == 200
        jobs = list_resp.json()["in_memory_jobs"]
        job_ids = [j["job_id"] for j in jobs]
        assert f"schedule_{rec_id}" in job_ids
        print("PASS: Recurrent schedule found in memory jobs:", job_ids)

        # Verify that completed one-time schedule was removed from memory and deleted from DB
        db_schedules = list_resp.json()["schedules"]
        assert not any(s["id"] == ot_id for s in db_schedules), "One-time schedule must be removed from DB after completion!"
        assert f"schedule_{ot_id}" not in job_ids, "One-time schedule must be removed from memory after completion!"
        print("PASS: Verified one-time task was removed from memory and deleted from DB!")

        # 5. Simulate backend reboot: clear in-memory scheduler, restore from DB
        scheduler.remove_all_jobs()
        assert len(scheduler.get_jobs()) == 0
        restored = restore_schedules_from_db()
        assert restored >= 1
        restored_job_ids = [j.id for j in scheduler.get_jobs()]
        assert f"schedule_{rec_id}" in restored_job_ids
        print(f"PASS: Simulated reboot restored {restored} schedule(s) from DB into memory:", restored_job_ids)

        # 6. Test modify (update) schedule
        update_payload = {
            "name": "Check Living Room Sensors Updated",
            "type": "recurrent",
            "trigger_spec": "*/5 * * * *",
            "use_case": "check_sensors_v2",
            "is_active": 1,
        }
        put_resp = client.put(f"/schedules/{rec_id}", json=update_payload, headers=headers)
        assert put_resp.status_code == 200
        updated_data = put_resp.json()["schedule"]
        assert updated_data["name"] == "Check Living Room Sensors Updated"
        assert updated_data["trigger_spec"] == "*/5 * * * *"
        print("PASS: Schedule modified successfully via PUT /schedules:", updated_data["name"])

        # 7. Delete recurrent schedule
        del_resp = client.delete(f"/schedules/{rec_id}", headers=headers)
        assert del_resp.status_code == 200
        assert not any(j.id == f"schedule_{rec_id}" for j in scheduler.get_jobs())
        print("PASS: Schedule deleted and cancelled from memory.")

        # 8. Test Schedule Block (Lock / Protection)
        blocked_payload = {
            "name": "Protected System Schedule",
            "type": "recurrent",
            "trigger_spec": "0 0 * * *",
            "use_case": "system_maintenance",
            "block": 1,
        }
        create_blk_resp = client.post("/schedules", json=blocked_payload, headers=headers)
        assert create_blk_resp.status_code == 201
        blk_data = create_blk_resp.json()["schedule"]
        blk_id = blk_data["id"]
        assert blk_data["block"] == 1
        print("PASS: Created blocked schedule:", blk_id)

        # Attempt to modify blocked schedule -> Expect 403 Forbidden
        mod_attempt = client.put(f"/schedules/{blk_id}", json={
            "name": "Hacked Schedule",
            "type": "recurrent",
            "trigger_spec": "*/10 * * * *",
            "use_case": "system_maintenance",
            "is_active": 1,
        }, headers=headers)
        assert mod_attempt.status_code == 403
        assert "is blocked and protected against changes" in mod_attempt.json()["detail"]
        print("PASS: Modifying blocked schedule rejected with 403 Forbidden")

        # Attempt to delete blocked schedule -> Expect 403 Forbidden
        del_attempt = client.delete(f"/schedules/{blk_id}", headers=headers)
        assert del_attempt.status_code == 403
        assert "is blocked and protected against deletion" in del_attempt.json()["detail"]
        print("PASS: Deleting blocked schedule rejected with 403 Forbidden")

        # Unblock schedule via PATCH /schedules/{blk_id}/block
        patch_unblock = client.patch(f"/schedules/{blk_id}/block", json={"block": 0}, headers=headers)
        assert patch_unblock.status_code == 200
        assert patch_unblock.json()["schedule"]["block"] == 0
        print("PASS: Successfully unblocked schedule via PATCH /schedules/{id}/block")

        # Now update should succeed
        mod_success = client.put(f"/schedules/{blk_id}", json={
            "name": "Updated Schedule After Unblock",
            "type": "recurrent",
            "trigger_spec": "0 1 * * *",
            "use_case": "system_maintenance",
            "is_active": 1,
        }, headers=headers)
        assert mod_success.status_code == 200
        print("PASS: Modifying unblocked schedule succeeded")

        # Re-lock schedule via PATCH
        patch_lock = client.patch(f"/schedules/{blk_id}/block", json={"block": 1}, headers=headers)
        assert patch_lock.status_code == 200
        assert patch_lock.json()["schedule"]["block"] == 1

        # Unblock again and delete
        client.patch(f"/schedules/{blk_id}/block", json={"block": 0}, headers=headers)
        del_success = client.delete(f"/schedules/{blk_id}", headers=headers)
        assert del_success.status_code == 200
        print("PASS: Unblocked and deleted schedule successfully")


if __name__ == "__main__":
    test_schedules_full_flow()
    print("All schedule tests passed successfully!")
