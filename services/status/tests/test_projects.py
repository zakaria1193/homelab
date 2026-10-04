#!/usr/bin/env python3
"""Tests for the /projects list: validation, saving and status lookup."""

import json
import subprocess
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

    def test_service_field_links_a_renamed_project_to_its_unit(self):
        items = [{"name": "Chloé Jobs Agent", "link": "http://h:8200", "remote": "",
                  "service": "ai-job-search"}]
        with mock.patch.object(projects, "check_http") as probe:
            rows = projects.rows(items, payload(("ai-job-search", DOWN)))
        probe.assert_not_called()
        self.assertEqual(rows[0]["state"], DOWN)

    def test_service_field_is_kept_only_when_set(self):
        clean, _ = projects.validate([{"name": "a", "link": "/a", "service": "x"},
                                      {"name": "b", "link": "/b", "service": ""}])
        self.assertEqual(clean[0]["service"], "x")
        self.assertNotIn("service", clean[1])

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


class GithubTest(unittest.TestCase):
    def test_github_link_is_normalised_and_kept_only_when_set(self):
        clean, err = projects.validate([
            {"name": "a", "link": "/a", "github": " https://github.com/me/a.git/ "},
            {"name": "b", "link": "/b", "github": ""}])
        self.assertIsNone(err)
        self.assertEqual(clean[0]["github"], "https://github.com/me/a")
        self.assertNotIn("github", clean[1])

    def test_non_github_links_are_refused(self):
        for bad in ("https://gitlab.com/me/a", "github.com/me/a", "https://github.com/me",
                    "javascript:alert(1)"):
            self.assertIsNotNone(projects.validate([{"name": "a", "link": "/a", "github": bad}])[1], bad)

    def test_counts_are_added_to_rows(self):
        items = [{"name": "a", "link": "/a", "remote": "", "github": "https://github.com/me/a"},
                 {"name": "b", "link": "/b", "remote": ""}]
        with mock.patch.object(projects, "_gh_query",
                               return_value={("me", "a"): {"prs": 2, "issues": 5}}):
            rows = projects.rows(items, payload(), github=True)
        self.assertEqual((rows[0]["prs"], rows[0]["issues"]), (2, 5))
        self.assertNotIn("prs", rows[1])

    def test_gh_is_not_called_unless_asked(self):
        items = [{"name": "a", "link": "/a", "remote": "", "github": "https://github.com/me/a"}]
        with mock.patch.object(projects, "_gh_query") as query:
            rows = projects.rows(items, payload())
        query.assert_not_called()
        self.assertNotIn("prs", rows[0])

    def test_query_parses_gh_output_and_skips_missing_repos(self):
        out = {"data": {"r0": {"isPrivate": True, "pullRequests": {"totalCount": 1},
                               "issues": {"totalCount": 3}},
                        "r1": None}}
        done = mock.Mock(stdout=json.dumps(out))
        with mock.patch.object(projects.subprocess, "run", return_value=done):
            counts = projects._gh_query((("me", "a"), ("me", "gone")))
        self.assertEqual(counts, {("me", "a"): {"prs": 1, "issues": 3, "private": True}})

    def test_gh_failure_gives_no_counts(self):
        with mock.patch.object(projects.subprocess, "run", side_effect=OSError):
            self.assertEqual(projects._gh_query((("me", "a"),)), {})


class SyncAndPush(unittest.TestCase):
    """Real git repos in a temp dir: a bare origin and a clone that is ahead of it."""

    def git(self, path, *args):
        subprocess.run(["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                       check=True, capture_output=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.clone = root / "repos" / "a"
        self.clone.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.clone)], check=True)
        self.git(self.clone, "remote", "add", "origin", "https://github.com/me/a.git")
        self.git(self.clone, "config", "url.%s.insteadOf" % self.origin, "https://github.com/me/a.git")
        self.git(self.clone, "commit", "-q", "--allow-empty", "-m", "one")
        self.git(self.clone, "push", "-q", "origin", "main")
        patcher = mock.patch.object(projects, "REPOS_DIR", str(root / "repos"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.items = [{"name": "a", "link": "/a", "remote": "", "github": "https://github.com/me/a"}]

    def test_in_sync_shows_zero_and_push_does_nothing(self):
        row = projects.rows(self.items, payload())[0]
        self.assertEqual(row["sync"], {"branch": "main", "ahead": 0, "behind": 0})
        self.assertEqual(projects.push_all(self.items), {"ok": True, "pushed": []})

    def test_unpushed_commit_shows_ahead_and_push_all_clears_it(self):
        self.git(self.clone, "commit", "-q", "--allow-empty", "-m", "two")
        row = projects.rows(self.items, payload())[0]
        self.assertEqual((row["sync"]["ahead"], row["sync"]["behind"]), (1, 0))
        out = projects.push_all(self.items)
        self.assertTrue(out["ok"])
        self.assertEqual([r["name"] for r in out["pushed"]], ["a"])
        self.assertEqual(projects.rows(self.items, payload())[0]["sync"]["ahead"], 0)

    def test_project_without_a_clone_has_no_sync(self):
        items = [{"name": "b", "link": "/b", "remote": "", "github": "https://github.com/me/b"}]
        self.assertNotIn("sync", projects.rows(items, payload())[0])


if __name__ == "__main__":
    unittest.main()
