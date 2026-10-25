import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import API_KEY, app
from app.scheduler import SYSTEM_FUNCTIONS, fn_send_telegram_alert
from app.telegram import get_telegram_status, send_telegram_message


def test_telegram_integration_flow():
    print("--- Starting Telegram Integration Tests ---")

    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # 1. Test 401 without API Key
        unauth_resp = client.get("/telegram/status")
        assert unauth_resp.status_code == 401
        print("PASS: 401 Unauthorized when missing API key on /telegram/status")

        # 2. Test GET /telegram/status
        status_resp = client.get("/telegram/status", headers=headers)
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert "configured" in status_data
        assert "bot_token_configured" in status_data
        assert "chat_id_configured" in status_data
        assert "message" in status_data
        print(f"PASS: GET /telegram/status returned valid status: configured={status_data['configured']}")

        # 3. Test POST /telegram/send with message (simulated when no live token)
        send_resp = client.post(
            "/telegram/send",
            json={"message": "[Test Alert] automated test suite"},
            headers=headers,
        )
        assert send_resp.status_code == 200, f"Expected 200, got {send_resp.status_code}: {send_resp.text}"
        send_data = send_resp.json()
        assert send_data["success"] is True
        print(f"PASS: POST /telegram/send succeeded (simulated={send_data.get('simulated')})")

        # 4. Test POST /telegram/send with custom chat_id
        send_custom = client.post(
            "/telegram/send",
            json={
                "message": "[Rain Alert] Heavy rainfall detected",
                "chat_id": "987654321",
                "parse_mode": "HTML",
            },
            headers=headers,
        )
        if send_custom.status_code == 200:
            custom_data = send_custom.json()
            assert custom_data["chat_id"] == "987654321"
        else:
            # In live bot environment, non-existent chat ID triggers Telegram 400 Bad Request
            assert send_custom.status_code == 502
            assert "chat not found" in send_custom.text.lower() or "error" in send_custom.text.lower()
        print("PASS: POST /telegram/send with custom chat_id handled correctly")

        # 5. Test 422 Unprocessable Entity when message is empty
        bad_resp = client.post("/telegram/send", json={"message": ""}, headers=headers)
        assert bad_resp.status_code == 422
        print("PASS: 422 rejected empty message payload")

        # 6. Test function registered in SYSTEM_FUNCTIONS
        assert "send_telegram_alert" in SYSTEM_FUNCTIONS
        assert SYSTEM_FUNCTIONS["send_telegram_alert"]["name"] == "Send Telegram Alert"
        print("PASS: 'send_telegram_alert' is registered in SYSTEM_FUNCTIONS")

        # 7. Test fn_send_telegram_alert directly
        alert_msg = asyncio.run(fn_send_telegram_alert(data="[System Alert] Reboot Notification"))
        assert "alert" in alert_msg.lower() or "delivered" in alert_msg.lower()
        print(f"PASS: fn_send_telegram_alert direct execution succeeded")

        # 8. Test fn_send_telegram_alert with JSON payload
        alert_json_msg = asyncio.run(
            fn_send_telegram_alert(data='{"message": "Sunrise event triggered blinds", "chat_id": "112233"}')
        )
        assert "delivered" in alert_json_msg.lower() or "alert" in alert_json_msg.lower()
        print(f"PASS: fn_send_telegram_alert with JSON data succeeded")

        # 9. Test GET /use-cases includes send_telegram_alert
        uc_resp = client.get("/use-cases", headers=headers)
        assert uc_resp.status_code == 200
        available_ids = [f["id"] for f in uc_resp.json()["available_functions"]]
        assert "send_telegram_alert" in available_ids
        print("PASS: 'send_telegram_alert' exposed in available_functions via GET /use-cases")

    print("ALL TELEGRAM INTEGRATION TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_telegram_integration_flow()
