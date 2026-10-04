#!/usr/bin/env python3
"""Tests for the /projects list: validation, saving and status lookup."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import projects  # noqa: E402
from cockpit.config import DOWN, UNKNOWN, UP  # noqa: E402


def payload(*services):
    return {"groups": [{"name": "G", "services": [{"name": n, "state": s} for n, s in services]}]}


class ValidateTest(unittest.TestCase):
    def test_trims_and_keeps_only_known_fields(self):
        clean, err = projects.validate([{"name": " jellyfin ", "link": "http://h:8096", "x": 1}])
        self.assertIsNone(err)
        self.assertEqual(clean, [{"name": "jellyfin", "link": "http://h:8096", "remote": ""}])

    def test_name_is_required(self):
        self.assertIn("needs a name", projects.validate([{"link": "http://h"}])[1])

    def test_a_link_is_required(self):
        self.assertIn("needs a link", projects.validate([{"name": "a"}])[1])

    def test_public_link_alone_is_enough(self):
        self.assertIsNone(projects.validate([{"name": "a", "remote": "https://a.x"}])[1])

    def test_duplicate_names_are_refused_case_insensitively(self):
        err = projects.validate([{"name": "A", "link": "/a"}, {"name": "a", "link": "/b"}])[1]
        self.assertIn("twice", err)

    def test_script_and_protocol_relative_links_are_refused(self):
        for bad in ("javascript:alert(1)", "//evil.example", "ftp://h"):
            self.assertIsNotNone(projects.validate([{"name": "a", "link": bad}])[1], bad)

    def test_cockpit_paths_are_allowed(self):
        self.assertIsNone(projects.validate([{"name": "ideas", "link": "/idea"}])[1])

    def test_not_a_list_is_refused(self):
        self.assertIsNotNone(projects.validate(None)[1])
        self.assertIsNotNone(projects.validate([1])[1])


class SaveTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = str(Path(tmp.name) / "projects.json")
        path_patch = mock.patch.object(projects, "PROJECTS_PATH", self.path)
        commit_patch = mock.patch.object(projects, "_commit")
        path_patch.start()
        self.commit = commit_patch.start()
        self.addCleanup(path_patch.stop)
        self.addCleanup(commit_patch.stop)

    def test_save_writes_and_commits(self):
        res = projects.save([{"name": "a", "link": "http://a"}])
        self.assertTrue(res["ok"])
        self.assertEqual(json.loads(Path(self.path).read_text())[0]["name"], "a")
        self.commit.assert_called_once()
        self.assertEqual(projects.load(), res["projects"])

    def test_invalid_list_is_not_written(self):
        res = projects.save([{"name": "", "link": "http://a"}])
        self.assertFalse(res["ok"])
        self.assertFalse(Path(self.path).exists())
        self.commit.assert_not_called()

    def test_missing_file_is_an_empty_list(self):
        self.assertEqual(projects.load(), [])


class RowsTest(unittest.TestCase):
    def test_named_like_a_service_takes_its_state(self):
        items = [{"name": "Kandev", "link": "http://h:3040", "remote": ""}]
        with mock.patch.object(projects, "check_http") as probe:
            rows = projects.rows(items, payload(("kandev", DOWN)))
        probe.assert_not_called()
        self.assertEqual(rows[0]["state"], DOWN)

    def test_other_projects_are_probed_on_their_link(self):
        items = [{"name": "blog", "link": "", "remote": "https://blog.x"}]
        with mock.patch.object(projects, "check_http", return_value={"state": UP}) as probe:
            rows = projects.rows(items, payload())
        probe.assert_called_once_with({"url": "https://blog.x"})
        self.assertEqual(rows[0]["state"], UP)

    def test_cockpit_path_without_a_service_is_unknown(self):
        rows = projects.rows([{"name": "notes", "link": "/idea", "remote": ""}], payload())
        self.assertEqual(rows[0]["state"], UNKNOWN)

    def test_list_order_is_kept(self):
        items = [{"name": n, "link": "/x", "remote": ""} for n in ("b", "a")]
        rows = projects.rows(items, payload(("a", UP), ("b", UP)))
        self.assertEqual([r["name"] for r in rows], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
