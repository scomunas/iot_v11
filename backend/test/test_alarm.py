import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.alarm import (
    clear_memory_events,
    evaluate_alarm_event,
    get_alarm_config,
    get_memory_events,
    render_alarm_message,
    update_alarm_config,
)

API_KEY = os.getenv("API_KEY", "test-api-key")


def mock_get_entity_state(entity_id: str):
    from app.homeassistant import FALLBACK_ENTITIES
    for ent in FALLBACK_ENTITIES:
        if ent.get("entity_id") == entity_id:
            return str(ent.get("state", "off"))
    return None


class TestAlarmSystem(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from app.database import db_get_setting
        from app.homeassistant import FALLBACK_ENTITIES

        cls._saved_alarm_config = db_get_setting("alarm_system")
        cls._saved_fallback_entities = [dict(e) for e in FALLBACK_ENTITIES]

        # Mock out external network calls so tests never arm real HA alarms or send real Telegram notifications
        cls._patch_ha = patch("app.homeassistant.call_homeassistant_service", return_value={"success": True})
        cls._mock_ha = cls._patch_ha.start()

        cls._patch_state = patch("app.homeassistant.get_entity_state", side_effect=mock_get_entity_state)
        cls._mock_state = cls._patch_state.start()

        cls._patch_notif = patch("app.alarm.dispatch_notifications", new_callable=AsyncMock, return_value={"success": True})
        cls._mock_notif = cls._patch_notif.start()

        cls._patch_speak = patch("app.alarm.broadcast_chime_tts", new_callable=AsyncMock, return_value={"success": True})
        cls._mock_speak = cls._patch_speak.start()

    @classmethod
    def tearDownClass(cls):
        from app.database import db_set_setting
        from app.homeassistant import FALLBACK_ENTITIES

        cls._patch_ha.stop()
        cls._patch_state.stop()
        cls._patch_notif.stop()
        cls._patch_speak.stop()

        FALLBACK_ENTITIES.clear()
        FALLBACK_ENTITIES.extend(cls._saved_fallback_entities)

        if cls._saved_alarm_config is not None:
            db_set_setting("alarm_system", cls._saved_alarm_config)
        else:
            db_set_setting("alarm_system", json.dumps({"enabled": False}))

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-API-Key": API_KEY}
        clear_memory_events()
        update_alarm_config(enabled=True, helper_entity="")

    def tearDown(self):
        clear_memory_events()
        update_alarm_config(enabled=True, helper_entity="")

    def test_alarm_config_crud(self):
        cfg = get_alarm_config()
        self.assertIn("enabled", cfg)
        self.assertIn("notification_message", cfg)
        self.assertIn("speak_message", cfg)

        updated = update_alarm_config(
            enabled=True,
            notification_message="Static test alert for {entity}: {count} in {seconds}s (limit {trigger})",
            speak_message="Atencion {entity} activado {count} veces",
            default_trigger=3,
            default_seconds=45,
        )
        self.assertEqual(updated["default_trigger"], 3)
        self.assertEqual(updated["default_seconds"], 45)
        self.assertIn("{entity}", updated["notification_message"])

    def test_render_alarm_message_tags(self):
        template = "Alert {device_name} [{device_type}] ({entity})! Count: {count}, Trigger: {trigger}, Window: {seconds}s at {date} {time}"
        rendered = render_alarm_message(
            template=template,
            entity="binary_sensor.front_door",
            trigger=2,
            seconds=60,
            count=3,
            dt=datetime(2026, 10, 28, 12, 30, 45, tzinfo=timezone.utc),
            device_name="Front Door Sensor",
            device_type="door",
        )
        self.assertIn("Alert Front Door Sensor [door] (binary_sensor.front_door)!", rendered)
        self.assertIn("Count: 3", rendered)
        self.assertIn("Trigger: 2", rendered)
        self.assertIn("Window: 60s", rendered)
        self.assertIn("2026-10-28", rendered)
        self.assertIn("12:30:45", rendered)

    async def test_evaluate_alarm_event_threshold_logic(self):
        clear_memory_events()
        # Trigger threshold = 2, seconds = 10
        # 1st event -> count=1 <= 2 -> No alarm fired
        res1 = await evaluate_alarm_event(
            entity="binary_sensor.garden_gate",
            trigger=2,
            seconds=10,
            notification=True,
            speak=True,
        )
        self.assertFalse(res1["alarm_triggered"])
        self.assertEqual(res1["count"], 1)

        # 2nd event -> count=2 <= 2 -> No alarm fired
        res2 = await evaluate_alarm_event(
            entity="binary_sensor.garden_gate",
            trigger=2,
            seconds=10,
            notification=True,
            speak=True,
        )
        self.assertFalse(res2["alarm_triggered"])
        self.assertEqual(res2["count"], 2)

        # 3rd event -> count=3 > 2 -> Alarm threshold exceeded -> Schedules deferred one-time schedule
        res3 = await evaluate_alarm_event(
            entity="binary_sensor.garden_gate",
            trigger=2,
            seconds=10,
            notification=True,
            speak=False,
        )
        self.assertTrue(res3["alarm_triggered"])
        self.assertEqual(res3["count"], 3)
        self.assertTrue(res3["notification_scheduled"])
        self.assertFalse(res3["speak_scheduled"])
        self.assertIsNotNone(res3.get("schedule_id"))
        self.assertIn("binary_sensor.garden_gate", res3["message"])

        # Test fire_alarm_actions directly
        from app.alarm import fire_alarm_actions
        fire_res = await fire_alarm_actions({
            "entity": "binary_sensor.garden_gate",
            "trigger": 2,
            "seconds": 10,
            "count": 3,
            "notification": True,
            "speak": False,
        })
        self.assertTrue(fire_res["alarm_fired"])
        self.assertTrue(fire_res["notification_sent"])

    def test_alarm_endpoints(self):
        # 1. GET /alarm/config
        resp = self.client.get("/alarm/config", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("config", data)

        # 2. PUT /alarm/config
        update_payload = {
            "enabled": True,
            "default_trigger": 2,
            "default_seconds": 60,
            "notification_message": "Intrusion at {entity}: {count} events ({trigger} allowed in {seconds}s)",
            "speak_message": "Alarma activada en {entity}",
        }
        put_resp = self.client.put("/alarm/config", json=update_payload, headers=self.headers)
        self.assertEqual(put_resp.status_code, 200)
        self.assertEqual(put_resp.json()["config"]["default_trigger"], 2)

        # 3. POST /alarm/test
        test_payload = {
            "entity": "binary_sensor.test_pir",
            "trigger": 1,
            "seconds": 30,
            "notification": False,
            "speak": False,
        }
        # First call: count=1 <= 1 -> not triggered
        t_resp1 = self.client.post("/alarm/test", json=test_payload, headers=self.headers)
        self.assertEqual(t_resp1.status_code, 200)
        self.assertFalse(t_resp1.json()["result"]["alarm_triggered"])

        # Second call: count=2 > 1 -> triggered
        t_resp2 = self.client.post("/alarm/test", json=test_payload, headers=self.headers)
        self.assertEqual(t_resp2.status_code, 200)
        self.assertTrue(t_resp2.json()["result"]["alarm_triggered"])

        # 4. GET /alarm/events-history
        hist_resp = self.client.get("/alarm/events-history", headers=self.headers)
        self.assertEqual(hist_resp.status_code, 200)
        events = hist_resp.json()["events"]
        self.assertGreaterEqual(len(events), 2)

        # 5. DELETE /alarm/events-history
        del_resp = self.client.delete("/alarm/events-history", headers=self.headers)
        self.assertEqual(del_resp.status_code, 200)

        # Verify history is now empty
        hist_empty_resp = self.client.get("/alarm/events-history", headers=self.headers)
        self.assertEqual(len(hist_empty_resp.json()["events"]), 0)

        # 6. GET /alarm/rules
        rules_resp = self.client.get("/alarm/rules", headers=self.headers)
        self.assertEqual(rules_resp.status_code, 200)
        self.assertIn("rules", rules_resp.json())


    async def test_alarm_helper_entity_sync_and_event(self):
        # 1. Configure helper entity
        update_alarm_config(
            enabled=True,
            helper_entity="input_boolean.alarma_seguridad",
        )
        cfg = get_alarm_config()
        self.assertEqual(cfg.get("helper_entity"), "input_boolean.alarma_seguridad")

        # 2. Simulate Home Assistant event turning alarm off
        from app.scheduler import dispatch_event_triggers
        res_off = await dispatch_event_triggers("input_boolean.alarma_seguridad", "off")
        self.assertTrue(any("Home Assistant Alarm Helper" in str(r.get("name")) for r in res_off))
        cfg_after_off = get_alarm_config()
        self.assertFalse(cfg_after_off.get("enabled"))

        # 3. Simulate Home Assistant event turning alarm back on
        res_on = await dispatch_event_triggers("input_boolean.alarma_seguridad", "on")
        self.assertTrue(any("Home Assistant Alarm Helper" in str(r.get("name")) for r in res_on))
        cfg_after_on = get_alarm_config()
        self.assertTrue(cfg_after_on.get("enabled"))


    async def test_evaluate_alarm_event_purges_events_older_than_retention_seconds(self):
        import app.alarm as alarm_module
        from datetime import timedelta

        update_alarm_config(retention_seconds=60)
        now = datetime.now(timezone.utc)
        alarm_module._alarm_memory_events = [
            {"entity": "binary_sensor.old_sensor", "date": now - timedelta(seconds=120)},
            {"entity": "binary_sensor.recent_sensor", "date": now - timedelta(seconds=20)},
        ]

        await evaluate_alarm_event(
            entity="binary_sensor.current_sensor",
            trigger=2,
            seconds=30,
        )

        remaining_entities = [ev["entity"] for ev in alarm_module._alarm_memory_events]
        self.assertNotIn("binary_sensor.old_sensor", remaining_entities)
        self.assertIn("binary_sensor.recent_sensor", remaining_entities)
        self.assertIn("binary_sensor.current_sensor", remaining_entities)

    async def test_disarm_deletes_deferred_alarm_schedules(self):
        from app.database import db_list_schedules

        update_alarm_config(enabled=True, delay_seconds=60)
        # 1. Trigger alarm event twice (trigger threshold = 1) to create deferred schedule
        await evaluate_alarm_event(
            entity="binary_sensor.test_pir",
            trigger=1,
            seconds=30,
            notification=True,
            speak=True,
        )
        res2 = await evaluate_alarm_event(
            entity="binary_sensor.test_pir",
            trigger=1,
            seconds=30,
            notification=True,
            speak=True,
        )
        self.assertTrue(res2["alarm_triggered"])
        sched_id = res2.get("schedule_id")
        self.assertIsNotNone(sched_id)

        # 2. Verify schedule exists and is active
        schedules = [s for s in db_list_schedules() if s["id"] == sched_id]
        self.assertEqual(len(schedules), 1)

        # 3. Disarm alarm -> deletes all deferred alarm one-time schedules
        update_alarm_config(enabled=False)
        remaining = [s for s in db_list_schedules() if s["id"] == sched_id]
        self.assertEqual(len(remaining), 0)

    async def test_fire_alarm_only_launches_if_alarm_still_on(self):
        from app.scheduler import fn_fire_alarm
        from app.alarm import fire_alarm_actions, is_alarm_on

        # 1. When alarm is ON: fire_alarm launches actions
        update_alarm_config(enabled=True)
        self.assertTrue(is_alarm_on())
        res_on = await fn_fire_alarm(
            data={"entity": "binary_sensor.front_door", "notification": True, "speak": False}
        )
        self.assertIn("ALARM FIRED", res_on.upper())

        # 2. When alarm is DISARMED / OFF: fire_alarm suppresses notification & audio
        update_alarm_config(enabled=False)
        self.assertFalse(is_alarm_on())
        res_off = await fn_fire_alarm(
            data={"entity": "binary_sensor.front_door", "notification": True, "speak": True}
        )
        self.assertIn("skipped", res_off.lower())

        # Also direct call to fire_alarm_actions confirms suppression
        action_res = await fire_alarm_actions({
            "entity": "binary_sensor.front_door",
            "notification": True,
            "speak": True,
        })
        self.assertFalse(action_res["alarm_fired"])
        self.assertIn("NOT on/mounted", action_res["message"])


if __name__ == "__main__":
    unittest.main()
