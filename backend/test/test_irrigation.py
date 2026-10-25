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
from app.scheduler import SYSTEM_FUNCTIONS, fn_start_irrigation, execute_schedule_task


def test_start_irrigation_direct():
    """Test start_irrigation directly."""
    print("Testing fn_start_irrigation directly...")
    result = asyncio.run(
        fn_start_irrigation(
            data={"entity_id": "switch.garden_irrigation_zone1", "seconds": 0.05}
        )
    )
    assert "Irrigation completed" in result
    assert "switch.garden_irrigation_zone1" in result
    print("PASS: fn_start_irrigation directly executed:", result)


def test_schedules_with_data_and_irrigation_use_case():
    import time
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. Verify start_irrigation is registered in available_functions and start_irrigatioin is removed
        uc_resp = client.get("/use-cases", headers=headers)
        assert uc_resp.status_code == 200
        available_ids = [f["id"] for f in uc_resp.json()["available_functions"]]
        assert "start_irrigation" in available_ids
        assert "start_irrigatioin" not in available_ids
        print("PASS: 'start_irrigation' is the single irrigation function in system functions")

        # 2. Create use case for irrigation with unique name
        uc_name = f"irrigation_zone_{int(time.time() * 1000)}"
        create_uc_resp = client.post(
            "/use-cases",
            json={
                "name": uc_name,
                "function_name": "start_irrigation",
                "description": "Irrigates zone 1 for given seconds",
            },
            headers=headers,
        )
        assert create_uc_resp.status_code == 201, f"Failed to create use case: {create_uc_resp.text}"
        uc_id = create_uc_resp.json()["use_case"]["id"]
        print("PASS: Created use case with ID:", uc_id)

        # 3. Test execution of the irrigation use case via /use-cases/{id}/test
        test_exec_resp = client.post(
            f"/use-cases/{uc_id}/test",
            json={"data": {"entity_id": "switch.garden_irrigation_zone1", "seconds": 0.05}},
            headers=headers,
        )
        assert test_exec_resp.status_code == 200, f"Failed execution: {test_exec_resp.text}"
        test_res_data = test_exec_resp.json()
        assert "switch.garden_irrigation_zone1" in str(test_res_data.get("result"))
        print("PASS: Tested use case execution:", test_res_data["message"])

        # 4. Create a schedule with data field
        irrigation_data = json.dumps({"entity_id": "switch.garden_irrigation_zone1", "seconds": 300})
        create_sched_resp = client.post(
            "/schedules",
            json={
                "name": f"Daily Morning Irrigation {int(time.time())}",
                "type": "recurrent",
                "trigger_spec": "0 6 * * *",
                "use_case": uc_name,
                "data": irrigation_data,
            },
            headers=headers,
        )
        assert create_sched_resp.status_code == 201, f"Failed to create schedule: {create_sched_resp.text}"
        sched = create_sched_resp.json()["schedule"]
        sched_id = sched["id"]
        assert "data" in sched
        assert "switch.garden_irrigation_zone1" in sched["data"]
        print("PASS: Created schedule with data field, ID:", sched_id)

        # 5. Update schedule data
        updated_data = json.dumps({"entity_id": "switch.garden_irrigation_zone1", "seconds": 600})
        update_sched_resp = client.put(
            f"/schedules/{sched_id}",
            json={
                "name": f"Daily Morning Irrigation (10 min) {int(time.time())}",
                "type": "recurrent",
                "trigger_spec": "0 6 * * *",
                "use_case": uc_name,
                "is_active": 1,
                "data": updated_data,
            },
            headers=headers,
        )
        assert update_sched_resp.status_code == 200, f"Failed to update schedule: {update_sched_resp.text}"
        updated_sched = update_sched_resp.json()["schedule"]
        assert "600" in updated_sched["data"]
        print("PASS: Updated schedule with updated data successfully")

        # 6. Clean up
        del_sched = client.delete(f"/schedules/{sched_id}", headers=headers)
        assert del_sched.status_code == 200
        del_uc = client.delete(f"/use-cases/{uc_id}", headers=headers)
        assert del_uc.status_code == 200
        print("PASS: Cleaned up test schedule and use case")


if __name__ == "__main__":
    test_start_irrigation_direct()
    test_schedules_with_data_and_irrigation_use_case()
    print("All irrigation tests passed successfully!")
