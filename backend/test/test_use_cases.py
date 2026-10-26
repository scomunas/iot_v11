import os
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app, API_KEY


def test_use_cases_crud_and_execution():
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. List use cases
        list_resp = client.get("/use-cases", headers=headers)
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert "use_cases" in data
        assert "available_functions" in data
        assert "available_sections" in data
        assert "irrigation" in data["available_sections"]
        assert "blinds" in data["available_sections"]
        assert "rain" in data["available_sections"]
        assert "heating_control" in data["available_sections"]
        assert "heating_recurrent" in data["available_sections"]
        assert any(fn["id"] == "create_datetime_file" for fn in data["available_functions"])
        assert any(fn["id"] == "control_heating" for fn in data["available_functions"])
        assert any(fn["id"] == "do_nothing" for fn in data["available_functions"])
        
        # Check that default irrigation, blinds, and heating use cases have their section defined
        for uc in data["use_cases"]:
            if uc.get("function_name") == "start_irrigation" or uc.get("name") == "irrigation":
                assert uc.get("section") == "irrigation", f"Irrigation use case should have section 'irrigation', got {uc.get('section')}"
            elif uc.get("function_name") == "move_blind" or uc.get("name") == "move_blind":
                assert uc.get("section") == "blinds", f"Blinds use case should have section 'blinds', got {uc.get('section')}"
            elif uc.get("function_name") == "control_heating":
                assert uc.get("section") in ("heating_control", "heating_recurrent"), f"control_heating use case should have heating section, got {uc.get('section')}"
        print("PASS: Listed use cases and verified default sections for irrigation and blinds")

        # 2. Create new use case with section
        payload = {
            "name": "generate_backup_log",
            "function_name": "create_datetime_file",
            "description": "Writes datetime timestamp file for backup",
            "section": "irrigation",
        }
        create_resp = client.post("/use-cases", json=payload, headers=headers)
        assert create_resp.status_code == 201
        created_uc = create_resp.json()["use_case"]
        uc_id = created_uc["id"]
        assert created_uc["name"] == "generate_backup_log"
        assert created_uc["section"] == "irrigation"
        print("PASS: Created use case with section #", uc_id)

        # 3. Test execution of the function
        test_resp = client.post(f"/use-cases/{uc_id}/test", headers=headers)
        assert test_resp.status_code == 200
        test_data = test_resp.json()
        assert "result_file" in test_data
        result_path = Path(test_data["result_file"])
        assert result_path.exists(), f"File {result_path} should exist"
        assert result_path.suffix == ".txt", f"File extension should be .txt, got {result_path.suffix}"
        content = result_path.read_text(encoding="utf-8")
        assert "IoT Scheduled Task Execution" in content
        assert "generate_backup_log" in content
        print("PASS: Test function executed successfully and created .txt file:", result_path.name)

        # 3b. Test execution of function with custom parameters passed in request body
        custom_params = {"data": {"note": "testing custom params"}}
        test_resp_params = client.post(f"/use-cases/{uc_id}/test", json=custom_params, headers=headers)
        assert test_resp_params.status_code == 200
        print("PASS: Test function executed successfully with custom parameters")

        # 4. Update use case
        update_payload = {
            "name": "generate_backup_log_v2",
            "function_name": "create_datetime_file",
            "description": "Updated description",
            "section": "blinds",
        }
        update_resp = client.put(f"/use-cases/{uc_id}", json=update_payload, headers=headers)
        assert update_resp.status_code == 200
        assert update_resp.json()["use_case"]["name"] == "generate_backup_log_v2"
        assert update_resp.json()["use_case"]["section"] == "blinds"
        print("PASS: Updated use case successfully with new section")

        # 5. Delete use case
        del_resp = client.delete(f"/use-cases/{uc_id}", headers=headers)
        assert del_resp.status_code == 200
        print("PASS: Deleted use case successfully")

        # 6. Test do_nothing function creation and execution
        dn_payload = {
            "name": "notify_rain_alert",
            "function_name": "do_nothing",
            "description": "Notification-only use case for rain alerts",
            "section": "rain",
        }
        dn_create = client.post("/use-cases", json=dn_payload, headers=headers)
        assert dn_create.status_code == 201
        dn_id = dn_create.json()["use_case"]["id"]

        dn_test = client.post(f"/use-cases/{dn_id}/test", headers=headers)
        assert dn_test.status_code == 200
        assert dn_test.json()["result"] == "OK: No action performed"
        print("PASS: Tested do_nothing use case execution: returned 'OK: No action performed'")

        client.delete(f"/use-cases/{dn_id}", headers=headers)
        print("PASS: Cleaned up do_nothing test use case")


if __name__ == "__main__":
    test_use_cases_crud_and_execution()
    print("All use case tests passed successfully!")
