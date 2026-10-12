#!/usr/bin/env python3
"""Autopilot decisions against fake Sonarr/Jellyfin - no network, no real library."""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import autopilot as a  # noqa: E402

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def ep(i, s, n, monitored=False, file=True):
    return {"id": i, "seasonNumber": s, "episodeNumber": n, "monitored": monitored, "hasFile": file,
            "episodeFile": {"id": 1000 + i} if file else None, "airDateUtc": "2020-01-01T00:00:00Z"}


class FakeSonarr:
    def __init__(self, series, eps):
        self._s, self._e = series, eps
        self.monitored, self.unmonitored, self.searched, self.deleted = [], [], [], []

    def series(self): return self._s
    def episodes(self, sid): return self._e[sid]
    def search(self, ids): self.searched += ids
    def delete_file(self, fid): self.deleted.append(fid)

    def monitor(self, ids, m): (self.monitored if m else self.unmonitored).extend(ids)


class FakeJf:
    def __init__(self, items): self.items = items
    def users(self): return [{"Id": "u1"}, {"Id": "u2"}]
    def series_ids(self): return {"jf1": ("Show", "111"), "jf2": ("Modern Family", "222")}
    def episodes(self, uid): return self.items.get(uid, [])


def item(sid, s, n, played=True, days_ago=5, partial=False):
    when = (NOW - timedelta(days=days_ago)).isoformat()
    return {"SeriesId": sid, "ParentIndexNumber": s, "IndexNumber": n,
            "UserData": {"Played": played, "PlaybackPositionTicks": 5 if partial else 0, "LastPlayedDate": when}}


class AutopilotTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        a.LOG, a.STATE = Path(d.name) / "l.log", Path(d.name) / "s.json"
        a.notify = lambda *x: None
        self.eps = {1: [ep(1, 1, 1, True), ep(2, 1, 2, True), ep(3, 1, 3, False, file=False),
                        ep(4, 1, 4, False, file=False), ep(5, 1, 5, False, file=False)],
                    2: [ep(10, 1, 1), ep(11, 1, 2)]}
        self.series = [{"id": 1, "title": "Show", "tvdbId": 111}, {"id": 2, "title": "Modern Family", "tvdbId": 222}]

    def go(self, items, dry=False):
        self.sonarr = FakeSonarr(self.series, self.eps)
        return a.run(self.sonarr, FakeJf(items), NOW, dry)

    def test_monitors_and_searches_next_two_and_deletes_old_watched(self):
        self.go({"u1": [item("jf1", 1, 1), item("jf1", 1, 2, days_ago=1)]})
        self.assertEqual(self.sonarr.monitored, [3, 4])
        self.assertEqual(self.sonarr.searched, [3, 4])
        self.assertEqual(self.sonarr.deleted, [1001])  # E1 is 5 days old, E2 only 1 day
        self.assertEqual(self.sonarr.unmonitored, [1])

    def test_second_users_progress_counts(self):
        self.go({"u1": [item("jf1", 1, 1)], "u2": [item("jf1", 1, 2, days_ago=1)]})
        self.assertEqual(self.sonarr.searched, [3, 4])

    def test_partial_play_moves_pivot_but_never_deletes(self):
        self.go({"u1": [item("jf1", 1, 2, played=False, partial=True, days_ago=9)]})
        self.assertEqual(self.sonarr.searched, [3, 4])
        self.assertEqual(self.sonarr.deleted, [])

    def test_hopping_show_is_untouched(self):
        self.go({"u1": [item("jf2", 1, 1, days_ago=30)]})
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))

    def test_does_not_research_within_a_day(self):
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.assertEqual(self.sonarr.searched, [])

    def test_dry_run_changes_nothing(self):
        r = self.go({"u1": [item("jf1", 1, 1)]}, dry=True)
        self.assertTrue(r["deleted"] and r["grabbed"])
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))

    def test_delete_cap(self):
        a.MAX_DELETES = 1
        self.addCleanup(setattr, a, "MAX_DELETES", 25)
        self.eps[1] = [ep(i, 1, i) for i in range(1, 6)]
        self.go({"u1": [item("jf1", 1, n) for n in range(1, 6)]})
        self.assertEqual(len(self.sonarr.deleted), 1)


if __name__ == "__main__":
    unittest.main()
