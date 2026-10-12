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

    def monitor(self, ids, m):
        (self.monitored if m else self.unmonitored).extend(ids)
        for eps in self._e.values():
            for e in eps:
                if e["id"] in ids:
                    e["monitored"] = m


class FakeRadarr:
    def __init__(self, movies, tags=()):
        self._m, self._t = movies, list(tags)
        self.unmonitored, self.deleted = [], []

    def movies(self): return self._m
    def tags(self): return self._t
    def unmonitor(self, ids): self.unmonitored += ids
    def delete_file(self, fid): self.deleted.append(fid)


def movie(i, tmdb, title="Film", file=True, monitored=True, tags=()):
    return {"id": i, "tmdbId": tmdb, "title": title, "hasFile": file, "monitored": monitored,
            "tags": list(tags), "movieFile": {"id": 5000 + i}, "sizeOnDisk": 3 * 1024 ** 3}


def mitem(tmdb, days_ago, played=True):
    when = (NOW - timedelta(days=days_ago)).isoformat()
    return {"Name": "x", "ProviderIds": {"Tmdb": str(tmdb)}, "UserData": {"Played": played, "LastPlayedDate": when}}


class FakeJf:
    movie_items = {}

    def __init__(self, items): self.items = items
    def movies(self, uid): return self.movie_items.get(uid, [])
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
        self.sent = []
        a.notify = lambda *x: self.sent.append(x)
        a.disk_total = lambda: 10 ** 15  # huge disk: the hopping-size warning stays quiet unless a test asks
        a.HOPPING = Path(d.name) / "hopping.json"
        a.HOPPING.write_text('["Modern Family"]')
        self.eps = {1: [ep(1, 1, 1, True), ep(2, 1, 2, True), ep(3, 1, 3, False, file=False),
                        ep(4, 1, 4, False, file=False), ep(5, 1, 5, False, file=False)],
                    2: [ep(10, 1, 1), ep(11, 1, 2)]}
        self.series = [{"id": 1, "title": "Show", "tvdbId": 111, "monitored": True},
                       {"id": 2, "title": "Modern Family", "tvdbId": 222, "monitored": True}]

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

    def test_hopping_list_edit_roundtrip(self):
        self.assertEqual(a.hopping_list(), ["Modern Family"])
        self.assertEqual(a.hopping_edit("  grand designs ", True)[0], True)
        a.hopping_edit("GRAND DESIGNS", True)  # duplicate, any case: ignored
        self.assertEqual(a.hopping_list(), ["grand designs", "Modern Family"])
        a.hopping_edit("modern family", False)
        self.assertEqual(a.hopping_list(), ["grand designs"])
        self.assertFalse(a.hopping_edit("  ", True)[0])

    def test_editing_the_list_changes_what_run_touches(self):
        a.hopping_edit("Modern Family", False)
        self.go({"u1": [item("jf2", 1, 1, days_ago=30)]})
        self.assertEqual(self.sonarr.deleted, [1010])

    def test_every_event_reaches_slack_in_one_message(self):
        self.go({"u1": [item("jf1", 1, 1), item("jf1", 1, 2, days_ago=1)]})
        self.assertEqual(len(self.sent), 1)
        msg = self.sent[0][2]
        self.assertIn("Now monitoring: Show S01E03, Show S01E04", msg)
        self.assertIn("Searching next: Show S01E03, Show S01E04", msg)
        self.assertIn("Deleted watched: Show S01E01", msg)

    def test_quiet_run_sends_nothing(self):
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.sent.clear()
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.assertEqual(self.sent, [])

    def test_cap_is_a_warning(self):
        a.MAX_DELETES = 1
        self.addCleanup(setattr, a, "MAX_DELETES", 25)
        self.eps[1] = [ep(i, 1, i) for i in range(1, 6)]
        self.go({"u1": [item("jf1", 1, n) for n in range(1, 6)]})
        self.assertEqual(self.sent[-1][0], "warn")
        self.assertIn("Safety cap", self.sent[-1][2])

    def test_hopping_edits_are_announced_once_each(self):
        a.hopping_edit("Rooster", True)
        a.hopping_edit("Rooster", True)  # no change, no message
        a.hopping_edit("Rooster", False)
        self.assertEqual([m[2].split(" (")[0] for m in self.sent],
                         ["Hopping list: added Rooster", "Hopping list: removed Rooster"])

    def test_failure_alerts_once_then_recovery(self):
        class Boom:
            def users(self): raise RuntimeError("jellyfin down")
            def series_ids(self): raise RuntimeError("jellyfin down")
        a.os.environ["JELLYFIN_API_KEY"] = "x"
        self.addCleanup(a.os.environ.pop, "JELLYFIN_API_KEY", None)
        a.Jellyfin = lambda *x: Boom()
        a.Sonarr = lambda *x: FakeSonarr(self.series, self.eps)
        a.sonarr_key = lambda: "k"
        self.assertEqual(a.main(), 1)
        self.assertEqual(a.main(), 1)  # still down: no second alert
        self.assertEqual([m[0] for m in self.sent], ["error"])
        a.Jellyfin = lambda *x: FakeJf({})
        self.assertEqual(a.main(), 0)
        self.assertEqual([m[0] for m in self.sent], ["error", "ok"])

    def test_manually_deleted_episode_in_window_is_not_regrabbed(self):
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})  # window: E2 (has file), E3
        self.eps[1][1].update(hasFile=False, episodeFile=None)  # user deletes E2 by hand
        self.sent.clear()
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.assertNotIn(2, self.sonarr.searched + self.sonarr.monitored)
        self.assertIn(2, self.sonarr.unmonitored)  # and Sonarr's RSS can't grab it either
        self.assertIn("Left alone", self.sent[0][2])
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})  # stays left alone, silently
        self.assertEqual(len(self.sent), 1)

    def test_manual_unmonitor_is_respected(self):
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})  # autopilot monitors E3
        self.eps[1][2]["monitored"] = False  # user turns it off
        a.load_state()  # state persisted on disk
        st = a.load_state(); st["searched"] = {}; a.STATE.write_text(__import__("json").dumps(st))
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.assertEqual((self.sonarr.monitored, self.sonarr.searched), ([], []))

    def test_unmonitoring_an_episode_it_found_already_monitored_is_respected(self):
        self.eps[1][2]["monitored"] = True  # E3 monitored before the autopilot ever ran
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.eps[1][2]["monitored"] = False  # user unmonitors it in Sonarr
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.assertNotIn(3, self.sonarr.monitored)

    def test_rewatching_an_old_episode_means_doubt_so_nothing_happens(self):
        # furthest = E3 (played 20 days ago), but E1 was played yesterday
        self.go({"u1": [item("jf1", 1, 3, days_ago=20), item("jf1", 1, 1, days_ago=1)]})
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Not sure", self.sent[0][2])
        self.assertIn("Show (an earlier episode", self.sent[0][2])
        self.go({"u1": [item("jf1", 1, 3, days_ago=20), item("jf1", 1, 1, days_ago=1)]})
        self.assertEqual(len(self.sent), 1)  # same doubt: said once

    def test_hopping_shows_over_half_the_disk_warn_every_run_and_only_warn(self):
        gb = 1024 ** 3
        self.series[1]["statistics"] = {"sizeOnDisk": 600 * gb}  # Modern Family, a hopping show
        a.disk_total = lambda: 1000 * gb
        self.addCleanup(setattr, a, "disk_total", lambda: 10 ** 15)
        for _ in range(3):
            self.go({"u1": [item("jf2", 1, 1, days_ago=30)]})
        warns = [m for m in self.sent if "filling the disk" in m[1]]
        self.assertEqual(len(warns), 3)  # every run
        self.assertEqual(warns[0][0], "warn")
        self.assertIn("60% of the disk", warns[0][2])
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))

    def test_hopping_shows_under_the_limit_say_nothing(self):
        gb = 1024 ** 3
        self.series[1]["statistics"] = {"sizeOnDisk": 400 * gb}
        a.disk_total = lambda: 1000 * gb
        self.addCleanup(setattr, a, "disk_total", lambda: 10 ** 15)
        self.go({"u1": [item("jf2", 1, 1, days_ago=30)]})
        self.assertEqual(self.sent, [])

    def test_show_untouched_for_a_year_is_reported_once_and_left_alone(self):
        gb = 1024 ** 3
        self.series[0].update(statistics={"sizeOnDisk": 12 * gb}, added="2023-01-01T00:00:00Z")
        for _ in range(2):
            self.go({"u1": [item("jf1", 1, 1, days_ago=800)]})
        msgs = [m for m in self.sent if "Untouched for over a year" in m[2]]
        self.assertEqual(len(msgs), 1)  # once, not every run
        self.assertEqual(msgs[0][0], "warn")
        self.assertIn("Show (12 GB", msgs[0][2])
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))

    def test_never_watched_show_is_judged_by_when_it_was_added(self):
        gb = 1024 ** 3
        self.series[0].update(statistics={"sizeOnDisk": 5 * gb}, added="2020-05-05T00:00:00Z")
        self.go({})
        self.assertTrue(any("Show (5 GB, nothing since 2020-05-05)" in m[2] for m in self.sent))
        self.sent.clear()
        self.series[0]["added"] = a.datetime.now(a.timezone.utc).isoformat()  # recently added: fine
        self.go({})
        self.assertEqual(self.sent, [])

    def test_empty_show_is_never_reported_and_a_comeback_resets_it(self):
        gb = 1024 ** 3
        self.series[0].update(statistics={"sizeOnDisk": 0}, added="2020-01-01T00:00:00Z")
        self.go({})
        self.assertEqual(self.sent, [])  # nothing on disk, nothing to warn about
        self.series[0]["statistics"] = {"sizeOnDisk": gb}
        self.go({"u1": [item("jf1", 1, 1, days_ago=800)]})
        self.assertEqual(len(self.sent), 1)
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})  # watched again: flag cleared
        self.assertNotIn("Show", a.load_state()["abandoned"])

    def run_movies(self, films, plays, tags=()):
        self.radarr = FakeRadarr(films, tags)
        FakeJf.movie_items = {"u1": plays}
        self.addCleanup(setattr, FakeJf, "movie_items", {})
        self.sonarr = FakeSonarr([], {})
        return a.run(self.sonarr, FakeJf({}), NOW, False, radarr=self.radarr)

    def test_movie_watched_four_days_ago_is_unmonitored_then_deleted(self):
        self.run_movies([movie(1, 100)], [mitem(100, 4)])
        self.assertEqual((self.radarr.unmonitored, self.radarr.deleted), ([1], [5001]))
        self.assertIn("Deleted watched movies: Film (3 GB)", self.sent[0][2])

    def test_movie_watched_yesterday_waits_the_three_days(self):
        self.run_movies([movie(1, 100)], [mitem(100, 1)])
        self.assertEqual(self.radarr.deleted, [])

    def test_old_play_of_a_library_movie_is_left_alone(self):
        self.run_movies([movie(1, 100)], [mitem(100, 600)])  # last played long ago
        self.assertEqual(self.radarr.deleted, [])

    def test_keep_tag_unmonitored_and_unwatched_movies_stay(self):
        films = [movie(1, 100, tags=[7]), movie(2, 200, monitored=False), movie(3, 300), movie(4, 400, file=False)]
        self.run_movies(films, [mitem(100, 5), mitem(200, 5), mitem(300, 5, played=False), mitem(400, 5)],
                        tags=[{"id": 7, "label": "Keep"}])
        self.assertEqual(self.radarr.deleted, [])

    def test_movie_deletes_are_capped(self):
        a.MAX_DELETES = 1
        self.addCleanup(setattr, a, "MAX_DELETES", 25)
        self.run_movies([movie(1, 100), movie(2, 200)], [mitem(100, 5), mitem(200, 5)])
        self.assertEqual(len(self.radarr.deleted), 1)
        self.assertEqual(self.sent[-1][0], "warn")

    def test_stale_show_is_skipped_silently(self):
        self.go({"u1": [item("jf1", 1, 1, days_ago=40)]})
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))
        self.assertEqual(self.sent, [])  # a paused show is normal: no Slack noise

    def test_partial_play_without_a_date_means_doubt(self):
        it = item("jf1", 1, 1, played=False, partial=True)
        it["UserData"]["LastPlayedDate"] = None
        self.go({"u1": [it]})
        self.assertEqual(self.sonarr.searched, [])

    def test_unmonitored_series_is_left_entirely_alone(self):
        self.series[0]["monitored"] = False
        self.go({"u1": [item("jf1", 1, 1)]})
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))

    def test_autopilots_own_deletes_are_not_mistaken_for_manual_ones(self):
        self.go({"u1": [item("jf1", 1, 1)]})
        self.assertEqual(self.sonarr.deleted, [1001])
        self.eps[1][0].update(hasFile=False, episodeFile=None)
        self.sent.clear()
        self.go({"u1": [item("jf1", 1, 1)]})
        self.assertEqual(self.sent, [])

    def test_never_seen_missing_episode_is_still_fetched(self):
        self.go({"u1": [item("jf1", 1, 1, days_ago=1)]})
        self.assertEqual(self.sonarr.searched, [3])  # E2 has a file, E3 never did

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
