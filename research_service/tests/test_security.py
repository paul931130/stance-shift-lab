import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from research_service.app import create_app
from research_service.security import SessionAuth, client_address
from research_service.storage import Store

KEY = "k" * 32


class SessionTests(unittest.TestCase):
    def test_issued_session_is_valid_until_it_expires(self):
        auth = SessionAuth(KEY, session_ttl=60)
        token = auth.issue_session()
        self.assertTrue(auth.valid_session(token))
        with patch("research_service.security.time.time", return_value=10**12):
            self.assertFalse(auth.valid_session(token))

    def test_tampered_or_malformed_tokens_are_rejected(self):
        auth = SessionAuth(KEY)
        token = auth.issue_session()
        self.assertFalse(auth.valid_session(token[:-1] + ("0" if token[-1] != "0" else "1")))
        for bad in ("", "abc", "1.2", None, 42):
            self.assertFalse(auth.valid_session(bad))

    def test_restart_and_logout_invalidate_sessions(self):
        auth = SessionAuth(KEY)
        token = auth.issue_session()
        self.assertFalse(SessionAuth(KEY).valid_session(token), "a new process must not accept old cookies")
        auth.revoke_session(token)
        self.assertFalse(auth.valid_session(token))
        self.assertTrue(auth.valid_session(auth.issue_session()), "revoking one session keeps others valid")

    def test_bearer_requires_the_exact_key(self):
        auth = SessionAuth(KEY)
        self.assertTrue(auth.bearer_ok(KEY))
        self.assertFalse(auth.bearer_ok(KEY[:-1]))
        self.assertFalse(auth.bearer_ok(""))

    def test_login_failures_are_rate_limited_per_client(self):
        auth = SessionAuth(KEY, login_max_attempts=3)
        for _ in range(3):
            auth.record_login_failure("1.1.1.1")
        self.assertTrue(auth.login_rate_limited("1.1.1.1"))
        self.assertFalse(auth.login_rate_limited("2.2.2.2"))
        auth.clear_login_failures("1.1.1.1")
        self.assertFalse(auth.login_rate_limited("1.1.1.1"))


class ClientAddressTests(unittest.TestCase):
    def test_forwarded_header_is_ignored_from_untrusted_peers(self):
        self.assertEqual(client_address("203.0.113.9", "10.0.0.1", set()), "203.0.113.9")
        self.assertEqual(client_address("203.0.113.9", "10.0.0.1", {"127.0.0.1"}), "203.0.113.9")

    def test_trusted_proxy_uses_the_address_it_observed(self):
        # The client controls everything left of the proxy's own entry.
        self.assertEqual(client_address("127.0.0.1", "6.6.6.6, 198.51.100.7", {"127.0.0.1"}), "198.51.100.7")

    def test_malformed_forwarded_header_falls_back_to_peer(self):
        self.assertEqual(client_address("127.0.0.1", "not-an-ip", {"127.0.0.1"}), "127.0.0.1")
        self.assertEqual(client_address(None, "", set()), "unknown")


class LoginFlowTests(unittest.TestCase):
    def test_logout_revokes_the_cookie(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"RESEARCH_ACCESS_KEY": KEY}):
            with TestClient(create_app(Store(directory), start_worker=False)) as client:
                self.assertEqual(client.post("/api/login", json={"key": KEY}).status_code, 200)
                cookie = client.cookies.get("research_session")
                self.assertEqual(client.get("/api/jobs").status_code, 200)
                self.assertEqual(client.post("/api/logout").status_code, 200)
                # Replaying the old cookie must fail even though it is unexpired.
                client.cookies.set("research_session", cookie)
                self.assertEqual(client.get("/api/jobs").status_code, 401)


if __name__ == "__main__":
    unittest.main()
