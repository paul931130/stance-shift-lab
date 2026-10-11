import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from research_service.app import create_app
from research_service import gputw
from research_service.storage import Store


def response_for(payload):
    response = MagicMock()
    response.__enter__.return_value = io.BytesIO(json.dumps(payload).encode("utf-8"))
    response.__exit__.return_value = False
    return response


class GpuTwTests(unittest.TestCase):
    def test_missing_key_is_explicitly_not_configured(self):
        with patch.dict(os.environ, {"GPUTW_API_KEY": "", "GPUTW_INSTANCE_ID": ""}, clear=False):
            result = gputw.status()
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["configured"])

    def test_active_status_accepts_wrapped_payload_and_uses_bearer_key(self):
        with patch.dict(os.environ, {"GPUTW_API_KEY": "gputw_test_key", "GPUTW_INSTANCE_ID": ""}, clear=False), \
             patch("research_service.gputw.urlopen", return_value=response_for({"data": {"instances": [{"id": "i-1", "status": "RUNNING"}]}})) as opener:
            result = gputw.status()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["active_instances"][0]["id"], "i-1")
        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer gputw_test_key")
        self.assertNotIn("gputw_test_key", json.dumps(result))

    def test_http_403_is_reported_as_forbidden_and_retryable_is_false(self):
        from urllib.error import HTTPError

        error = HTTPError("https://gputw.ai/api/instances/active", 403, "forbidden", {}, io.BytesIO())
        with patch.dict(os.environ, {"GPUTW_API_KEY": "gputw_test_key", "GPUTW_INSTANCE_ID": ""}, clear=False), \
             patch("research_service.gputw.urlopen", side_effect=error):
            result = gputw.status()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], "forbidden")
        self.assertFalse(result["retryable"])

    def test_resources_without_instance_explains_required_setting(self):
        with patch.dict(os.environ, {"GPUTW_API_KEY": "gputw_test_key", "GPUTW_INSTANCE_ID": ""}, clear=False):
            result = gputw.resources()
        self.assertEqual(result["status"], "needs_instance")

    def test_app_exposes_read_only_routes_without_network_when_unconfigured(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {"GPUTW_API_KEY": "", "GPUTW_INSTANCE_ID": ""}, clear=False):
            store = Store(Path(directory))
            with TestClient(create_app(store, start_worker=False)) as client:
                config = client.get("/api/config")
                status = client.get("/api/gputw/status")
                resources = client.get("/api/gputw/resources")
        self.assertFalse(config.json()["gputw"]["configured"])
        self.assertEqual(status.json()["status"], "not_configured")
        self.assertEqual(resources.json()["status"], "not_configured")

    def test_stop_uses_the_separate_manage_key_and_never_the_read_key(self):
        env = {"GPUTW_API_KEY": "read_key", "GPUTW_MANAGE_API_KEY": "manage_key", "GPUTW_INSTANCE_ID": "i-1"}
        with patch.dict(os.environ, env, clear=False), \
             patch("research_service.gputw.urlopen", return_value=response_for({"data": {"status": "STOPPED"}})) as opener:
            result = gputw.stop_instance()
        request = opener.call_args.args[0]
        self.assertEqual((request.get_method(), request.full_url), ("POST", "https://gputw.ai/api/instances/stop"))
        self.assertEqual(json.loads(request.data), {"instanceId": "i-1"})
        self.assertEqual(request.get_header("Authorization"), "Bearer manage_key")
        self.assertEqual(result["status"], "stopped")
        self.assertNotIn("manage_key", json.dumps(result))

    def test_stop_falls_back_to_the_main_key_and_explains_a_missing_scope(self):
        from urllib.error import HTTPError
        env = {"GPUTW_API_KEY": "main_key", "GPUTW_MANAGE_API_KEY": "", "GPUTW_INSTANCE_ID": "i-1"}
        error = HTTPError("https://gputw.ai/api/instances/stop", 403, "forbidden", {}, io.BytesIO())
        with patch.dict(os.environ, env, clear=False), \
             patch("research_service.gputw.urlopen", side_effect=error) as opener:
            result = gputw.stop_instance()
        self.assertEqual(opener.call_args.args[0].get_header("Authorization"), "Bearer main_key")
        self.assertEqual(result["code"], "forbidden")
        self.assertIn("instances:manage", result["message"])
        self.assertNotIn("main_key", json.dumps(result))

    def test_stop_without_any_key_does_not_call_the_api(self):
        env = {"GPUTW_API_KEY": "", "GPUTW_MANAGE_API_KEY": "", "GPUTW_INSTANCE_ID": "i-1"}
        with patch.dict(os.environ, env, clear=False), patch("research_service.gputw.urlopen") as opener:
            result = gputw.stop_instance()
        opener.assert_not_called()
        self.assertEqual(result["status"], "not_configured")


class AutoStopTests(unittest.TestCase):
    ENV = {"GPUTW_MANAGE_API_KEY": "manage_key", "GPUTW_INSTANCE_ID": "i-1", "RESEARCH_GPUTW_AUTOSTOP_MINUTES": "15"}

    def watchdog(self, jobs, state="RUNNING"):
        from research_service.autostop import AutoStop
        self.now, self.stops = 0.0, []
        return AutoStop(lambda: jobs[0], clock=lambda: self.now, state=lambda: state,
                        stop=lambda: self.stops.append(1) or {"status": "stopped"})

    def test_stops_only_after_the_queue_is_idle_for_the_whole_period(self):
        jobs = [3]
        with patch.dict(os.environ, self.ENV, clear=False):
            dog = self.watchdog(jobs)
            for minute in range(0, 60, 1):  # an hour of work: never stop while jobs remain
                self.now = minute * 60
                dog.tick()
            jobs[0] = 0
            self.now = 3600
            dog.tick()                      # queue just emptied: start the idle clock
            self.now = 3600 + 14 * 60
            dog.tick()
            self.assertEqual(self.stops, [])
            self.now = 3600 + 15 * 60
            self.assertEqual(dog.tick(), {"status": "stopped"})
        self.assertEqual(self.stops, [1])

    def test_new_work_resets_the_idle_clock(self):
        jobs = [0]
        with patch.dict(os.environ, self.ENV, clear=False):
            dog = self.watchdog(jobs)
            dog.tick()
            self.now = 10 * 60
            jobs[0] = 1
            dog.tick()
            jobs[0] = 0
            self.now = 16 * 60
            dog.tick()
            self.now = 20 * 60
            dog.tick()
        self.assertEqual(self.stops, [])

    def test_an_already_stopped_instance_is_left_alone(self):
        with patch.dict(os.environ, self.ENV, clear=False):
            dog = self.watchdog([0], state="STOPPED")
            dog.tick()
            self.now = 16 * 60
            dog.tick()
        self.assertEqual(self.stops, [])

    def test_a_freshly_started_gpu_gets_the_whole_period_to_warm_up(self):
        from research_service.autostop import AutoStop
        status, stops = ["STOPPED"], []
        self.now = 0.0
        with patch.dict(os.environ, self.ENV, clear=False):
            dog = AutoStop(lambda: 0, clock=lambda: self.now, state=lambda: status[0],
                           stop=lambda: stops.append(1) or {"status": "stopped"})
            for minute in range(0, 180):          # service idle for three hours, GPU off
                self.now = minute * 60
                dog.tick()
            status[0] = "RUNNING"                 # the user starts the GPU; the model loads for ~10 min
            for minute in range(180, 194):
                self.now = minute * 60
                dog.tick()
            self.assertEqual(stops, [])
            self.now = 196 * 60
            dog.tick()
        self.assertEqual(stops, [1])

    def test_a_key_without_manage_scope_is_tried_once(self):
        from research_service.autostop import AutoStop
        calls = []
        self.now = 0.0
        with patch.dict(os.environ, self.ENV, clear=False):
            dog = AutoStop(lambda: 0, clock=lambda: self.now, state=lambda: "RUNNING",
                           stop=lambda: calls.append(1) or {"status": "error", "code": "forbidden", "message": "no scope"})
            for minute in range(0, 120):
                self.now = minute * 60
                dog.tick()
            self.assertFalse(dog.public()["enabled"])
            self.assertEqual(dog.public()["last_action"]["code"], "forbidden")
        self.assertEqual(calls, [1])

    def test_inert_without_a_manage_key_or_when_disabled(self):
        for env in ({**self.ENV, "GPUTW_MANAGE_API_KEY": "", "GPUTW_API_KEY": ""},
                    {**self.ENV, "RESEARCH_GPUTW_AUTOSTOP_MINUTES": "0"}):
            with patch.dict(os.environ, env, clear=False):
                dog = self.watchdog([0])
                dog.tick()
                self.now = 99 * 60
                dog.tick()
                self.assertFalse(dog.public()["enabled"])
        self.assertEqual(self.stops, [])


if __name__ == "__main__":
    unittest.main()
