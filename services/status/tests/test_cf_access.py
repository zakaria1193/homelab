import base64
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import status_server  # noqa: E402
from cockpit import handler  # noqa: E402
from cockpit.handler import StatusHandler  # noqa: E402


class TestCloudflareAccess(unittest.TestCase):
    def test_parse_jwt_payload_valid(self):
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {"email": "user@example.com", "exp": 9999999999, "aud": "test-aud"}
        
        def b64url(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode("utf-8")).decode("utf-8").rstrip("=")
        
        jwt_str = f"{b64url(header)}.{b64url(payload)}.fakesig"
        parsed = status_server.parse_jwt_payload(jwt_str)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.get("email"), "user@example.com")
        self.assertEqual(parsed.get("aud"), "test-aud")

    def test_parse_jwt_payload_invalid(self):
        self.assertIsNone(status_server.parse_jwt_payload("invalid-token"))
        self.assertIsNone(status_server.parse_jwt_payload(""))

    def test_verify_cf_access_jwt_email_header(self):
        # Without restricted allowed emails, any email header passes
        self.assertTrue(status_server.verify_cf_access_jwt("", cf_email="user@example.com"))
        self.assertFalse(status_server.verify_cf_access_jwt("", cf_email=""))

    def test_verify_cf_access_jwt_expired(self):
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {"email": "user@example.com", "exp": 1000000000}  # past timestamp
        
        def b64url(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode("utf-8")).decode("utf-8").rstrip("=")
        
        jwt_str = f"{b64url(header)}.{b64url(payload)}.fakesig"
        self.assertFalse(status_server.verify_cf_access_jwt(jwt_str))


PI = "192.168.1.11"


def make_handler(client_ip, headers):
    h = StatusHandler.__new__(StatusHandler)
    h.client_address = (client_ip, 50000)
    h.headers = headers
    return h


class TestCfAccessTrustedProxies(unittest.TestCase):
    """The Access headers are plain text: they only count from the tunnel."""

    def setUp(self):
        for name, value in {
            "CF_ACCESS_ENABLED": True,
            "CF_ACCESS_TRUSTED_PROXIES": {PI},
            "REQUIRE_CF_ACCESS": False,
            "BASIC_USER": "admin",
            "BASIC_PASSWORD": "pw",
        }.items():
            patcher = mock.patch.object(handler, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_forged_email_header_from_lan_is_ignored(self):
        h = make_handler("192.168.1.50", {"Cf-Access-Authenticated-User-Email": "x@example.com"})
        self.assertFalse(h._authorized())

    def test_email_header_from_tunnel_is_believed(self):
        h = make_handler(PI, {"Cf-Access-Authenticated-User-Email": "x@example.com"})
        self.assertTrue(h._authorized())

    def test_lan_client_with_header_can_still_use_basic_auth(self):
        token = base64.b64encode(b"admin:pw").decode()
        h = make_handler("192.168.1.50", {
            "Cf-Access-Authenticated-User-Email": "x@example.com",
            "Authorization": f"Basic {token}",
        })
        self.assertTrue(h._authorized())

    def test_no_trusted_proxy_configured_believes_nobody(self):
        with mock.patch.object(handler, "CF_ACCESS_TRUSTED_PROXIES", set()):
            h = make_handler(PI, {"Cf-Access-Authenticated-User-Email": "x@example.com"})
            self.assertFalse(h._authorized())


if __name__ == "__main__":
    unittest.main()
