import json
import os
import sys
import asyncio
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app, API_KEY
from app.scheduler import fn_move_blind


def test_move_blind_direct():
    """Test fn_move_blind directly."""
    print("Testing fn_move_blind directly...")
    result = asyncio.run(
        fn_move_blind(
            data={"entity": "cover.living_room_blind", "position": 45}
        )
    )
    assert "cover.living_room_blind" in result
    assert "45%" in result
    print("PASS: fn_move_blind directly executed:", result)

    # Test clamping
    result_clamped = asyncio.run(
        fn_move_blind(
            data={"entity_id": "cover.bedroom_blind", "position": 150}
        )
    )
    assert "100%" in result_clamped
    print("PASS: fn_move_blind position clamped to 100%:", result_clamped)

    # Test not_before in the past / equal to now -> moves immediately
    result_past = asyncio.run(
        fn_move_blind(
            data={"entity": "cover.living_room_blind", "position": 20, "not_before": "00:01"}
        )
    )
    assert "Moved blind" in result_past
    print("PASS: fn_move_blind with past not_before executed immediately:", result_past)

    # Test not_before in future -> defers and creates one-time schedule
    from datetime import datetime, timedelta
    from app.scheduler import APP_TIMEZONE
    future_time = datetime.now(APP_TIMEZONE) + timedelta(hours=2)
    future_hour_str = future_time.strftime("%H:%M")

    result_deferred = asyncio.run(
        fn_move_blind(
            name="Test Event Blind Deferred",
            use_case="move_blind",
            data={"entity": "cover.living_room_blind", "position": 75, "not_before": future_hour_str}
        )
    )
    assert "deferred until" in result_deferred
    assert future_hour_str in result_deferred
    print("PASS: fn_move_blind with future not_before deferred:", result_deferred)

    # Verify one-time schedule was created in DB
    from app.database import db_list_schedules, db_delete_schedule
    all_schedules = db_list_schedules()
    deferred_sched = next((s for s in all_schedules if "Test Event Blind Deferred" in s["name"] and s["type"] == "one-time"), None)
    assert deferred_sched is not None, "One-time schedule should be created"
    parsed_sched_data = json.loads(deferred_sched["data"])
    assert parsed_sched_data["entity"] == "cover.living_room_blind"
    assert parsed_sched_data["position"] == 75
    assert parsed_sched_data["not_before"] == ""
    print("PASS: Created one-time schedule verified with not_before blank:", deferred_sched)

    # Clean up the test one-time schedule
    db_delete_schedule(deferred_sched["id"])
    print("PASS: Cleaned up deferred test schedule")


def test_blinds_use_case_and_schedule():
    import time
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. Verify move_blind is registered in available_functions
        uc_resp = client.get("/use-cases", headers=headers)
        assert uc_resp.status_code == 200
        available_ids = [f["id"] for f in uc_resp.json()["available_functions"]]
        assert "move_blind" in available_ids
        print("PASS: 'move_blind' is available in system functions")

        # 2. Create use case for blind
        uc_name = f"living_room_blind_control_{int(time.time() * 1000)}"
        create_uc_resp = client.post(
            "/use-cases",
            json={
                "name": uc_name,
                "function_name": "move_blind",
                "description": "Moves living room blind to set position",
            },
            headers=headers,
        )
        assert create_uc_resp.status_code == 201, f"Failed to create use case: {create_uc_resp.text}"
        uc_id = create_uc_resp.json()["use_case"]["id"]
        print("PASS: Created use case with ID:", uc_id)

        # 3. Test execution of the blind use case via /use-cases/{id}/test
        test_exec_resp = client.post(
            f"/use-cases/{uc_id}/test",
            json={"data": {"entity": "cover.living_room_blind", "position": 80}},
            headers=headers,
        )
        assert test_exec_resp.status_code == 200, f"Failed execution: {test_exec_resp.text}"
        test_res_data = test_exec_resp.json()
        assert "cover.living_room_blind" in str(test_res_data.get("result"))
        assert "80%" in str(test_res_data.get("result"))
        print("PASS: Tested use case execution:", test_res_data["message"])

        # 4. Create a schedule with data field for moving blind
        blind_data = json.dumps({"entity": "cover.living_room_blind", "position": 100})
        create_sched_resp = client.post(
            "/schedules",
            json={
                "name": f"Morning Open Blinds {int(time.time())}",
                "type": "recurrent",
                "trigger_spec": "0 7 * * *",
                "use_case": uc_name,
                "data": blind_data,
            },
            headers=headers,
        )
        assert create_sched_resp.status_code == 201, f"Failed to create schedule: {create_sched_resp.text}"
        sched = create_sched_resp.json()["schedule"]
        sched_id = sched["id"]
        assert "data" in sched
        assert "cover.living_room_blind" in sched["data"]
        print("PASS: Created schedule for blind with data field, ID:", sched_id)

        # 5. Clean up
        del_sched = client.delete(f"/schedules/{sched_id}", headers=headers)
        assert del_sched.status_code == 200
        del_uc = client.delete(f"/use-cases/{uc_id}", headers=headers)
        assert del_uc.status_code == 200
        print("PASS: Cleaned up test schedule and use case")


if __name__ == "__main__":
    test_move_blind_direct()
    test_blinds_use_case_and_schedule()
    print("All blinds executable function tests passed successfully!")
