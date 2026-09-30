import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import status_server  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
