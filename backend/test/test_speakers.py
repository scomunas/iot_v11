"""
Unit tests for Speaker System (Chime TTS) configuration and broadcasting.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import init_db, db_get_setting, db_set_setting
from app.speakers import (
    DEFAULT_SPEAKER_CONFIG,
    broadcast_chime_tts,
    get_speaker_config,
    update_speaker_config,
)

API_KEY = os.environ.get("API_KEY", "iot_secret_api_key_2026")
AUTH_HEADERS = {"X-API-Key": API_KEY}


class TestSpeakerSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_config = db_get_setting("speaker_system")

    @classmethod
    def tearDownClass(cls):
        if cls._saved_config is not None:
            db_set_setting("speaker_system", cls._saved_config)

    def setUp(self):
        init_db()

    def test_default_config(self):
        cfg = get_speaker_config()
        self.assertIn("enabled", cfg)
        self.assertIn("speakers", cfg)
        self.assertIn("chime_path", cfg)
        self.assertIn("tts_platform", cfg)
        self.assertIn("volume_level", cfg)
        self.assertIn("default_message", cfg)

    def test_update_config(self):
        updated = update_speaker_config(
            enabled=True,
            speakers=["media_player.salon", "media_player.cocina"],
            chime_path="chord",
            tts_platform="tts.google_translate_say",
            volume_level=0.75,
            default_message="Intruder warning test",
        )
        self.assertTrue(updated["enabled"])
        self.assertEqual(updated["speakers"], ["media_player.salon", "media_player.cocina"])
        self.assertEqual(updated["chime_path"], "chord")
        self.assertEqual(updated["tts_platform"], "tts.google_translate_say")
        self.assertEqual(updated["volume_level"], 0.75)
        self.assertEqual(updated["default_message"], "Intruder warning test")

        # Re-fetch to ensure persistence
        stored = get_speaker_config()
        self.assertEqual(stored["speakers"], ["media_player.salon", "media_player.cocina"])
        self.assertEqual(stored["volume_level"], 0.75)

    def test_volume_clamping(self):
        # Above 1.0 clamped to 1.0
        up = update_speaker_config(volume_level=1.5)
        self.assertEqual(up["volume_level"], 1.0)

        # Below 0.0 clamped to 0.0
        down = update_speaker_config(volume_level=-0.5)
        self.assertEqual(down["volume_level"], 0.0)

    @patch("app.speakers.call_homeassistant_service")
    def test_broadcast_chime_tts_service_call(self, mock_ha):
        mock_ha.return_value = {"success": True, "simulated": True}
        update_speaker_config(
            enabled=True,
            speakers=["media_player.todos_los_altavoces"],
            chime_path="bells",
            tts_platform="tts.google_translate_say",
            volume_level=0.8,
            default_message="Standard message",
        )

        res = broadcast_chime_tts(message="Custom alert test")
        self.assertTrue(res["success"])
        self.assertEqual(res["service"], "chime_tts.say")

        mock_ha.assert_called_once_with(
            domain="chime_tts",
            service="say",
            entity_id="media_player.todos_los_altavoces",
            service_data={
                "message": "Custom alert test",
                "chime_path": "bells",
                "tts_platform": "tts.google_translate_say",
                "volume_level": 0.8,
            },
        )

    @patch("app.speakers.call_homeassistant_service")
    def test_broadcast_multi_speaker(self, mock_ha):
        mock_ha.return_value = {"success": True, "simulated": True}
        speakers = ["media_player.salon", "media_player.cocina"]
        update_speaker_config(enabled=True, speakers=speakers, chime_path="bells", volume_level=0.8)

        res = broadcast_chime_tts(message="Multi speaker broadcast", volume_level=0.8)
        self.assertTrue(res["success"])
        mock_ha.assert_called_once_with(
            domain="chime_tts",
            service="say",
            entity_id=speakers,
            service_data={
                "message": "Multi speaker broadcast",
                "chime_path": "bells",
                "tts_platform": "tts.google_translate_say",
                "volume_level": 0.8,
            },
        )

    @patch("app.speakers.call_homeassistant_service")
    def test_disabled_speaker_system_skip(self, mock_ha):
        update_speaker_config(enabled=False)
        res = broadcast_chime_tts(message="Should be skipped", force=False)
        self.assertFalse(res["success"])
        self.assertTrue(res.get("skipped"))
        mock_ha.assert_not_called()

        # Force broadcast should still execute even if disabled
        res_forced = broadcast_chime_tts(message="Forced broadcast", force=True)
        self.assertTrue(res_forced["success"])
        mock_ha.assert_called_once()


class TestSpeakerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved_config = db_get_setting("speaker_system")

    @classmethod
    def tearDownClass(cls):
        if cls._saved_config is not None:
            db_set_setting("speaker_system", cls._saved_config)

    def setUp(self):
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    def test_speaker_config_endpoints(self):
        # 1. GET config
        resp = self.client.get("/api/v1/speakers/config", headers=AUTH_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("speakers", data)

        # 2. PUT config
        put_resp = self.client.put(
            "/api/v1/speakers/config",
            json={
                "enabled": True,
                "speakers": ["media_player.todos_los_altavoces"],
                "chime_path": "bells",
                "tts_platform": "tts.google_translate_say",
                "volume_level": 0.85,
                "default_message": "Presencia detectada",
            },
            headers=AUTH_HEADERS,
        )
        self.assertEqual(put_resp.status_code, 200)
        body = put_resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["config"]["volume_level"], 0.85)

        # 3. POST broadcast
        with patch("app.speakers.call_homeassistant_service") as mock_ha:
            mock_ha.return_value = {"success": True, "simulated": True}
            bcast_resp = self.client.post(
                "/api/v1/speakers/broadcast",
                json={"message": "Test speaker broadcast endpoint"},
                headers=AUTH_HEADERS,
            )
            self.assertEqual(bcast_resp.status_code, 200)
            res_data = bcast_resp.json()
            self.assertEqual(res_data["status"], "success")
            self.assertTrue(res_data["result"]["success"])




class TestScheduleAndEventSpeak(unittest.TestCase):
    def setUp(self):
        import asyncio
        from fastapi.testclient import TestClient
        from app.main import app
        self.client = TestClient(app)

    @patch("app.speakers.broadcast_chime_tts")
    def test_schedule_speak_custom_message(self, mock_speak):
        import asyncio
        from app.scheduler import execute_schedule_task

        asyncio.run(execute_schedule_task(
            schedule_id=999,
            name="Garden Irrigation",
            schedule_type="recurrent",
            use_case="do_nothing",
            speak=1,
            speak_message="Garden watering has finished successfully",
        ))

        mock_speak.assert_called_once_with(
            message="Garden watering has finished successfully",
            force=True,
        )

    @patch("app.speakers.broadcast_chime_tts")
    def test_schedule_speak_standard_message(self, mock_speak):
        import asyncio
        from app.scheduler import execute_schedule_task

        asyncio.run(execute_schedule_task(
            schedule_id=998,
            name="Auto Blinds",
            schedule_type="recurrent",
            use_case="do_nothing",
            speak=1,
            speak_message="",
        ))

        mock_speak.assert_called_once_with(
            message="Schedule 'Auto Blinds' executed successfully (Use case: do_nothing)",
            force=True,
        )

    @patch("app.speakers.broadcast_chime_tts")
    def test_event_trigger_speak(self, mock_speak):
        import asyncio
        from app.database import db_create_event_definition, db_delete_event_definition
        from app.scheduler import dispatch_event_triggers

        # 1. Custom message
        ed = db_create_event_definition(
            name="Rain Alert Event",
            event_type="test_speak_rain",
            parameter="start",
            use_case="do_nothing",
            speak=1,
            speak_message="Attention, rain has started. Closing all blinds.",
        )
        try:
            asyncio.run(dispatch_event_triggers("test_speak_rain", "start"))
            mock_speak.assert_called_once_with(
                message="Attention, rain has started. Closing all blinds.",
                force=True,
            )
        finally:
            db_delete_event_definition(ed["id"])

    @patch("app.speakers.broadcast_chime_tts")
    def test_event_trigger_speak_standard_message(self, mock_speak):
        import asyncio
        from app.database import db_create_event_definition, db_delete_event_definition
        from app.scheduler import dispatch_event_triggers

        # 2. Blank / system-generated message
        ed = db_create_event_definition(
            name="Presence Alarm",
            event_type="test_speak_presence",
            parameter="detected",
            use_case="do_nothing",
            speak=1,
            speak_message="",
        )
        try:
            asyncio.run(dispatch_event_triggers("test_speak_presence", "detected"))
            mock_speak.assert_called_once_with(
                message="Event 'Presence Alarm' triggered [test_speak_presence: detected] -> Use case: do_nothing",
                force=True,
            )
        finally:
            db_delete_event_definition(ed["id"])


if __name__ == "__main__":
    unittest.main()
