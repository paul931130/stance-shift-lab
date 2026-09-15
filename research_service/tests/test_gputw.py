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


if __name__ == "__main__":
    unittest.main()
