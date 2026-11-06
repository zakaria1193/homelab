#!/usr/bin/env python3
"""Tests for github_limits against a fake GitHub API.

Nothing here touches the network: `_api` is replaced with a table of answers,
and `now` is passed in so the month arithmetic does not depend on the clock.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cockpit import github_limits  # noqa: E402
from cockpit.pages.github_limits import GITHUB_LIMITS_PAGE  # noqa: E402

NOW = datetime(2026, 11, 11, 0, 0, 0, tzinfo=timezone.utc)


def job(seconds, labels=("ubuntu-latest",)):
    end = f"2026-11-02T00:{seconds // 60:02d}:{seconds % 60:02d}Z"
    return {"started_at": "2026-11-02T00:00:00Z", "completed_at": end, "labels": list(labels)}


def run(run_id, name="Nightly", status="completed", day="2026-11-02"):
    return {"id": run_id, "name": name, "status": status, "created_at": day + "T00:00:00Z"}


class FakeGitHub:
    """Answers by path; counts calls, so tests can assert what was not asked again."""

    def __init__(self):
        self.calls = []
        self.repos = [
            {"name": "big", "full_name": "me/big", "private": True},
            {"name": "small", "full_name": "me/small", "private": True},
            {"name": "open", "full_name": "me/open", "private": False},
        ]
        self.runs = {
            ("me/big", "2026-11"): [run(1), run(2, name="CI", day="2026-11-03")],
            ("me/big", "2026-10"): [run(9, day="2026-10-05")],
            ("me/small", "2026-11"): [run(3, status="in_progress")],
        }
        self.jobs = {1: [job(90), job(30)], 2: [job(61)], 3: [job(60)], 9: [job(300)]}
        self.broken = set()

    def __call__(self, path):
        self.calls.append(path)
        bare = path.split("?")[0]
        if bare == "/user/repos":
            return self.repos
        parts = bare.strip("/").split("/")
        full = "/".join(parts[1:3])
        if full in self.broken:
            raise github_limits.GitHubError(f"HTTP 403 on {bare}")
        if bare.endswith("/actions/runs"):
            month = path.split("created=")[1][:7]
            return {"workflow_runs": self.runs.get((full, month), [])}
        if bare.endswith("/jobs"):
            return {"jobs": self.jobs[int(parts[-2])]}
        if bare.endswith("/actions/artifacts"):
            if full != "me/big":
                return {"artifacts": []}
            return {"artifacts": [
                {"name": "pkg", "size_in_bytes": 300, "expired": False},
                {"name": "pkg", "size_in_bytes": 300, "expired": False},
                {"name": "report", "size_in_bytes": 0, "expired": False},
                {"name": "old", "size_in_bytes": 9999, "expired": True},
            ]}
        if bare.endswith("/actions/cache/usage"):
            return {"active_caches_size_in_bytes": 50 if full == "me/big" else 0,
                    "active_caches_count": 2 if full == "me/big" else 0}
        raise AssertionError("unexpected call " + path)


class Base(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub()
        old = github_limits._api
        github_limits._api = self.gh
        self.addCleanup(setattr, github_limits, "_api", old)


class JobMinutesTests(unittest.TestCase):
    def test_rounds_up_per_job(self):
        self.assertEqual(github_limits.job_minutes(job(61)), 2)
        self.assertEqual(github_limits.job_minutes(job(60)), 1)

    def test_weights_by_runner_os(self):
        self.assertEqual(github_limits.job_minutes(job(60, ["windows-latest"])), 2)
        self.assertEqual(github_limits.job_minutes(job(60, ["macos-14"])), 10)

    def test_self_hosted_is_free(self):
        self.assertEqual(github_limits.job_minutes(job(600, ["self-hosted", "linux"])), 0)

    def test_unstarted_job_costs_nothing(self):
        self.assertEqual(github_limits.job_minutes({"started_at": None, "completed_at": None}), 0)


class CollectTests(Base):
    def test_counts_private_repos_and_names_the_top_consumer(self):
        minutes = github_limits.collect(now=NOW)["snapshot"]["minutes"]
        # big: 2 + 1 + 2 = 5, small: 1.
        self.assertEqual(minutes["used"], 6)
        self.assertEqual([r["name"] for r in minutes["repos"]], ["big", "small"])
        self.assertEqual(minutes["repos"][0]["workflows"][0],
                         {"name": "Nightly", "minutes": 3, "runs": 1})

    def test_public_repos_are_never_asked_about(self):
        github_limits.collect(now=NOW)
        self.assertFalse([c for c in self.gh.calls if "me/open" in c])

    def test_projects_the_month_from_the_pace_so_far(self):
        # 10 of 30 days gone with 6 used.
        self.assertEqual(github_limits.collect(now=NOW)["snapshot"]["minutes"]["projected"], 18)

    def test_no_projection_in_the_first_day(self):
        early = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)
        self.assertIsNone(github_limits.collect(now=early)["snapshot"]["minutes"]["projected"])

    def test_previous_month_total_and_per_repo(self):
        minutes = github_limits.collect(now=NOW)["snapshot"]["minutes"]
        self.assertEqual((minutes["previous_month"], minutes["previous"]), ("2026-10", 5))
        self.assertEqual(minutes["repos"][0]["previous"], 5)

    def test_days_cover_the_whole_month(self):
        days = github_limits.collect(now=NOW)["snapshot"]["minutes"]["days"]
        self.assertEqual(len(days), 30)
        self.assertEqual(days[1], {"day": "2026-11-02", "minutes": 4})  # runs 1 and 3

    def test_storage_skips_expired_artifacts_and_groups_by_name(self):
        storage = github_limits.collect(now=NOW)["snapshot"]["storage"]
        self.assertEqual(storage["artifact_bytes"], 600)
        self.assertEqual(storage["cache_bytes"], 50)
        self.assertEqual(storage["repos"][0]["top_artifacts"],
                         [{"name": "pkg", "bytes": 600, "count": 2}])


class CostTests(Base):
    def test_a_finished_run_is_never_fetched_twice(self):
        state = github_limits.collect(now=NOW)
        self.gh.calls.clear()
        github_limits.collect(now=NOW, state=state)
        jobs = [c for c in self.gh.calls if "/jobs" in c]
        self.assertEqual(len(jobs), 1, jobs)  # only the run still in progress
        self.assertIn("/runs/3/", jobs[0])

    def test_previous_month_is_counted_only_once(self):
        state = github_limits.collect(now=NOW)
        self.gh.calls.clear()
        github_limits.collect(now=NOW, state=state)
        self.assertFalse([c for c in self.gh.calls if "created=2026-10" in c])

    def test_a_new_month_drops_the_old_runs(self):
        state = github_limits.collect(now=NOW)
        later = datetime(2026, 12, 2, tzinfo=timezone.utc)
        self.assertEqual(github_limits.collect(now=later, state=state)["runs"], {})


class FailureTests(Base):
    def test_one_bad_repo_is_reported_and_the_rest_still_count(self):
        self.gh.broken.add("me/small")
        snap = github_limits.collect(now=NOW)["snapshot"]
        self.assertEqual(snap["minutes"]["used"], 5)
        self.assertEqual(len(snap["problems"]), 1)
        self.assertIn("small", snap["problems"][0])

    def test_a_failed_sweep_does_not_freeze_a_partial_previous_month(self):
        self.gh.broken.add("me/small")
        state = github_limits.collect(now=NOW)
        self.assertIsNone(state["snapshot"]["minutes"]["previous"])
        self.assertEqual(state["closed"], {})


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for attr, value in (("STATE_FILE", os.path.join(self.tmp.name, "s.json")),
                            ("_kick", lambda: None), ("_state", None),
                            ("_token", lambda: "t")):
            self.addCleanup(setattr, github_limits, attr, getattr(github_limits, attr))
            setattr(github_limits, attr, value)

    def test_answers_at_once_with_nothing_collected_yet(self):
        data = github_limits.snapshot()
        self.assertFalse(data["ok"])
        self.assertEqual(data["rate"], [])

    def test_serves_the_saved_state_after_a_restart(self):
        github_limits._save_state({"snapshot": {"ok": True, "month": "2026-11"}})
        self.assertTrue(github_limits.snapshot()["ok"])

    def test_without_a_token_it_says_what_to_do(self):
        github_limits._token = lambda: ""
        self.assertIn("GH_TOKEN", github_limits.snapshot()["message"])

    def test_stale_means_old_or_from_another_month(self):
        fresh = datetime.now(timezone.utc)
        self.assertFalse(github_limits._is_stale(
            {"updated_at": fresh.isoformat(), "month": f"{fresh:%Y-%m}"}))
        self.assertTrue(github_limits._is_stale(
            {"updated_at": fresh.isoformat(), "month": "2001-01"}))
        self.assertTrue(github_limits._is_stale({}))


class PageTests(unittest.TestCase):
    def test_page_has_a_section_for_each_limit(self):
        for piece in ('id="tiles"', 'id="days"', 'id="repos"', 'id="storage"', 'id="rate"'):
            self.assertIn(piece, GITHUB_LIMITS_PAGE)

    def test_the_cockpit_has_a_tab_for_it(self):
        main = Path(github_limits.__file__).parent / "templates" / "main.html"
        self.assertIn('data-tab="github-limits"', main.read_text())
        self.assertIn('data-src="/github-limits?embedded=1"', main.read_text())


if __name__ == "__main__":
    unittest.main()
