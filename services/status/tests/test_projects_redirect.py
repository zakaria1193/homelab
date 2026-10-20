#!/usr/bin/env python3
"""homelab-0012: `/projects` redirects to pjm's Projects page instead of
serving its own pane, and the old `/api/projects*` endpoints are gone."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit import config, handler  # noqa: E402
from cockpit.handler import StatusHandler  # noqa: E402

CONF = """[DEFAULT]
host = 192.168.1.10

[pjm]
group = AI
link = http://%(host)s:8400
remote = https://pjm.zakariafadli.com
"""

CONF_NO_PJM = """[DEFAULT]
host = 192.168.1.10

[other]
group = AI
link = http://%(host)s:9000
"""


def make_handler(host_header):
    h = StatusHandler.__new__(StatusHandler)
    h.headers = {"Host": host_header}
    return h


class RedirectTargetTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conf_path = str(Path(tmp.name) / "services.conf")

    def _write(self, text):
        Path(self.conf_path).write_text(text)
        return mock.patch.object(config, "CONFIG_PATH", self.conf_path)

    def test_ip_host_uses_lan_link(self):
        with self._write(CONF):
            h = make_handler("192.168.1.10:8300")
            self.assertEqual(h._pjm_target(), "http://192.168.1.10:8400")

    def test_public_hostname_uses_remote(self):
        with self._write(CONF):
            h = make_handler("homelab.zakariafadli.com")
            self.assertEqual(h._pjm_target(), "https://pjm.zakariafadli.com")

    def test_x_forwarded_host_wins_over_host(self):
        with self._write(CONF):
            h = make_handler("192.168.1.10:8300")
            h.headers["X-Forwarded-Host"] = "homelab.zakariafadli.com"
            self.assertEqual(h._pjm_target(), "https://pjm.zakariafadli.com")

    def test_missing_pjm_section_falls_back_to_link_host(self):
        with self._write(CONF_NO_PJM):
            h = make_handler("192.168.1.10:8300")
            with mock.patch.object(handler, "LINK_HOST", "192.168.1.10"):
                self.assertEqual(h._pjm_target(), "http://192.168.1.10:8400")


class ProjectsRouteTest(unittest.TestCase):
    def _get(self, path, host="192.168.1.10:8300"):
        h = StatusHandler.__new__(StatusHandler)
        h.headers = {"Host": host}
        h.path = path
        sent = {}
        h._send = lambda code, body, ctype, extra_headers=(): sent.update(
            code=code, body=body, headers=dict(extra_headers)
        )
        with mock.patch.object(StatusHandler, "_authorized", return_value=True):
            h.do_GET()
        return sent

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conf_path = str(Path(tmp.name) / "services.conf")
        Path(self.conf_path).write_text(CONF)
        patcher = mock.patch.object(config, "CONFIG_PATH", self.conf_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_projects_redirects_to_pjm_on_lan(self):
        sent = self._get("/projects")
        self.assertEqual(sent["code"], 302)
        self.assertEqual(sent["headers"]["Location"], "http://192.168.1.10:8400/#/projects")

    def test_projects_redirects_to_pjm_on_public_host(self):
        sent = self._get("/projects", host="homelab.zakariafadli.com")
        self.assertEqual(sent["code"], 302)
        self.assertEqual(sent["headers"]["Location"], "https://pjm.zakariafadli.com/#/projects")

    def test_projects_embedded_param_still_redirects(self):
        sent = self._get("/projects?embedded=1")
        self.assertEqual(sent["code"], 302)
        self.assertEqual(sent["headers"]["Location"], "http://192.168.1.10:8400/#/projects")

    def test_old_api_projects_endpoints_are_gone(self):
        self.assertEqual(self._get("/api/projects")["code"], 404)

    def _post(self, path):
        h = StatusHandler.__new__(StatusHandler)
        h.headers = {"Host": "192.168.1.10:8300", "Content-Length": "0"}
        h.path = path
        sent = {}
        h._send = lambda code, body, ctype, extra_headers=(): sent.update(code=code)
        with mock.patch.object(StatusHandler, "_authorized", return_value=True):
            h.do_POST()
        return sent

    def test_old_api_projects_save_is_gone(self):
        self.assertEqual(self._post("/api/projects/save")["code"], 404)

    def test_old_api_projects_push_all_is_gone(self):
        self.assertEqual(self._post("/api/projects/push-all")["code"], 404)


if __name__ == "__main__":
    unittest.main()
