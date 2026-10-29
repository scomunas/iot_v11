import os
import shutil
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Isolate test database so test execution NEVER mutates live db/iot.db
TEST_DB_PATH = BACKEND_DIR / "db" / "test_devices.db"
LIVE_DB_PATH = BACKEND_DIR / "db" / "iot.db"
if "DATABASE_PATH" not in os.environ:
    if LIVE_DB_PATH.exists():
        shutil.copy2(LIVE_DB_PATH, TEST_DB_PATH)
    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)

from fastapi.testclient import TestClient
from app.main import app, API_KEY


def test_homeassistant_and_devices_flow():
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. Test GET /homeassistant/entities
        ha_resp = client.get("/homeassistant/entities", headers=headers)
        assert ha_resp.status_code == 200, f"Expected 200, got {ha_resp.status_code}"
        ha_data = ha_resp.json()
        assert "entities" in ha_data
        assert isinstance(ha_data["entities"], list)
        assert len(ha_data["entities"]) > 0
        first_entity = ha_data["entities"][0]
        assert "entity_id" in first_entity
        assert "friendly_name" in first_entity
        print(f"PASS: Listed {len(ha_data['entities'])} Home Assistant entities (connected: {ha_data['connected']})")

        # 2. Test GET /devices initially
        dev_resp = client.get("/devices", headers=headers)
        assert dev_resp.status_code == 200
        initial_devices = dev_resp.json()["devices"]
        print(f"PASS: Retrieved devices, count={len(initial_devices)}")

        # 3. Test POST /devices for each valid device type (heating removed!)
        types = ["light", "irrigation", "blinds", "temperature", "movement", "presence", "rain", "door"]
        created_ids = []

        for d_type in types:
            payload = {
                "name": f"Test Device {d_type.capitalize()}",
                "type": d_type,
                "entity_id": f"{d_type}.test_entity_1",
            }
            create_resp = client.post("/devices", json=payload, headers=headers)
            assert create_resp.status_code == 201, f"Failed creating device: {create_resp.text}"
            dev_data = create_resp.json()["device"]
            assert dev_data["name"] == payload["name"]
            assert dev_data["type"] == d_type
            assert dev_data["entity_id"] == payload["entity_id"]
            created_ids.append(dev_data["id"])
            print(f"PASS: Created device #{dev_data['id']} of type '{d_type}'")

        # 4. Test invalid device type rejection (including 'heating')
        bad_payload = {
            "name": "Invalid Device",
            "type": "invalid_type_abc",
            "entity_id": "sensor.invalid",
        }
        bad_resp = client.post("/devices", json=bad_payload, headers=headers)
        assert bad_resp.status_code in (422, 400)
        print("PASS: Rejected invalid device type properly")

        heating_dev_payload = {
            "name": "Heating Device",
            "type": "heating",
            "entity_id": "climate.heating",
        }
        heating_resp = client.post("/devices", json=heating_dev_payload, headers=headers)
        assert heating_resp.status_code in (422, 400)
        print("PASS: Rejected 'heating' device type properly (heating is now global configuration)")

        # 5. Test PUT /devices/{device_id}
        update_id = created_ids[0]
        update_payload = {
            "name": "Updated Living Room Light",
            "type": "light",
            "entity_id": "light.living_room_ceiling",
        }
        up_resp = client.put(f"/devices/{update_id}", json=update_payload, headers=headers)
        assert up_resp.status_code == 200
        assert up_resp.json()["device"]["name"] == "Updated Living Room Light"
        print(f"PASS: Updated device #{update_id} successfully")

        # 5b. Test POST /devices/{device_id}/action (Manual on/off/toggle)
        irrig_id = created_ids[1]
        action_on_resp = client.post(f"/devices/{irrig_id}/action", json={"action": "on"}, headers=headers)
        assert action_on_resp.status_code == 200, f"Expected 200, got {action_on_resp.status_code}: {action_on_resp.text}"
        assert action_on_resp.json()["action"] == "on"
        assert action_on_resp.json()["state"] == "on"
        print(f"PASS: Turned ON device #{irrig_id} manually")

        action_off_resp = client.post(f"/devices/{irrig_id}/action", json={"action": "off"}, headers=headers)
        assert action_off_resp.status_code == 200
        assert action_off_resp.json()["action"] == "off"
        assert action_off_resp.json()["state"] == "off"
        print(f"PASS: Turned OFF device #{irrig_id} manually")

        action_toggle_resp = client.post(f"/devices/{irrig_id}/action", json={"action": "toggle"}, headers=headers)
        assert action_toggle_resp.status_code == 200
        print(f"PASS: Toggled device #{irrig_id} manually (result: {action_toggle_resp.json()['action']})")

        # 5c. Test POST /devices/{device_id}/action with blind position slider
        blind_id = created_ids[2]
        action_pos_resp = client.post(f"/devices/{blind_id}/action", json={"action": "set_position", "position": 65}, headers=headers)
        assert action_pos_resp.status_code == 200, f"Expected 200, got {action_pos_resp.status_code}: {action_pos_resp.text}"
        assert action_pos_resp.json()["action"] == "set_position"
        assert action_pos_resp.json()["position"] == 65
        print(f"PASS: Set blind position for device #{blind_id} to 65% manually")

        # 6. Clean up: Delete created test devices
        for d_id in created_ids:
            del_resp = client.delete(f"/devices/{d_id}", headers=headers)
            assert del_resp.status_code == 200
            print(f"PASS: Cleaned up test device #{d_id}")

        # 7. Final GET /devices verification
        final_resp = client.get("/devices", headers=headers)
        assert final_resp.status_code == 200
        assert len(final_resp.json()["devices"]) == len(initial_devices)
        print(f"PASS: All test devices cleaned up, count returned to {len(initial_devices)}")


if __name__ == "__main__":
    try:
        test_homeassistant_and_devices_flow()
    finally:
        for ext in ("", "-wal", "-shm"):
            p = Path(str(TEST_DB_PATH) + ext)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
