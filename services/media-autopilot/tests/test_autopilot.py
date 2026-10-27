#!/usr/bin/env python3
"""Autopilot decisions against fake Sonarr/Jellyfin - no network, no real library."""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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
    def __init__(self, movies):
        self._m = movies
        self.unmonitored, self.deleted = [], []

    def movies(self): return self._m
    def unmonitor(self, ids): self.unmonitored += ids
    def delete_file(self, fid): self.deleted.append(fid)


def movie(i, tmdb, title="Film", file=True, monitored=True):
    return {"id": i, "tmdbId": tmdb, "title": title, "year": 2020, "hasFile": file, "monitored": monitored,
            "movieFile": {"id": 5000 + i}, "sizeOnDisk": 3 * 1024 ** 3}


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
        a.notify = lambda *x: self.sent.append(x) or True
        a.disk_total = lambda: 10 ** 15  # huge disk: the hopping-size warning stays quiet unless a test asks
        a.MAINTAINED = Path(d.name) / "maintained.json"
        a.MAINTAINED.write_text("[]")
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
        self.assertEqual([e["title"] for e in a.hopping_list()], ["Modern Family"])
        self.assertEqual(a.hopping_edit("  grand designs ", True)[0], True)
        a.hopping_edit("GRAND DESIGNS", True)  # duplicate, any case: ignored
        self.assertEqual([e["title"] for e in a.hopping_list()], ["grand designs", "Modern Family"])
        a.hopping_edit("modern family", False)
        self.assertEqual([e["title"] for e in a.hopping_list()], ["grand designs"])
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
        for name in ("Jellyfin", "Sonarr", "Radarr", "arr_key", "sonarr_key"):
            self.addCleanup(setattr, a, name, getattr(a, name))
        a.Jellyfin = lambda *x: Boom()
        a.Sonarr = lambda *x: FakeSonarr(self.series, self.eps)
        a.Radarr = lambda *x: FakeRadarr([])  # never the real Radarr on 127.0.0.1:7878
        a.arr_key = lambda app: "k"
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

    def run_movies(self, films, plays, at=NOW):
        self.radarr = FakeRadarr(films)
        FakeJf.movie_items = {"u1": plays}
        self.addCleanup(setattr, FakeJf, "movie_items", {})
        self.sonarr = FakeSonarr([], {})
        return a.run(self.sonarr, FakeJf({}), at, False, radarr=self.radarr)

    def test_finished_movie_is_warned_about_first_never_deleted_at_once(self):
        self.run_movies([movie(1, 100)], [mitem(100, 4)])
        self.assertEqual((self.radarr.unmonitored, self.radarr.deleted), ([], []))
        self.assertEqual(self.sent[0][0], "warn")
        self.assertIn("to be deleted in 7 days: Film (3 GB, on 2026-10-19)", self.sent[0][2])
        self.assertIn("maintained list", self.sent[0][2])

    def test_deleted_a_week_after_the_warning_and_warned_only_once(self):
        play = [mitem(100, 4)]  # played 4 days before NOW
        self.run_movies([movie(1, 100)], play)
        self.sent.clear()
        self.run_movies([movie(1, 100)], play, at=NOW + timedelta(days=6))
        self.assertEqual((self.radarr.deleted, self.sent), ([], []))  # still waiting, no second warning
        self.run_movies([movie(1, 100)], play, at=NOW + timedelta(days=8))
        self.assertEqual((self.radarr.unmonitored, self.radarr.deleted), ([1], [5001]))
        self.assertIn("Deleted watched movies: Film (3 GB)", self.sent[0][2])

    def test_maintained_movie_is_never_warned_or_deleted(self):
        a.maintained_edit("Film (2020)", True)  # 'Title (Year)' form
        self.run_movies([movie(1, 100)], [mitem(100, 4)])
        self.assertEqual((self.radarr.deleted, [m for m in self.sent if "Film" in m[2] and "deleted" in m[2]]), ([], []))
        a.maintained_edit("film", True)  # plain title works too

    def test_adding_to_maintained_after_the_warning_cancels_the_deletion(self):
        play = [mitem(100, 4)]
        self.run_movies([movie(1, 100)], play)
        a.maintained_edit("Film", True)
        self.run_movies([movie(1, 100)], play, at=NOW + timedelta(days=9))
        self.assertEqual(self.radarr.deleted, [])
        a.maintained_edit("Film", False)  # protection lifted: a fresh warning, not an instant delete
        self.sent.clear()
        self.run_movies([movie(1, 100)], play, at=NOW + timedelta(days=10))
        self.assertEqual(self.radarr.deleted, [])
        self.assertIn("to be deleted", self.sent[0][2])

    def test_rewatching_during_the_week_pushes_the_deletion_back(self):
        self.run_movies([movie(1, 100)], [mitem(100, 4)])
        again = [mitem(100, 0)]
        again[0]["UserData"]["LastPlayedDate"] = (NOW + timedelta(days=7)).isoformat()
        self.run_movies([movie(1, 100)], again, at=NOW + timedelta(days=8))  # played 1 day ago
        self.assertEqual(self.radarr.deleted, [])

    def test_old_play_of_a_library_movie_is_left_alone(self):
        self.run_movies([movie(1, 100)], [mitem(100, 600)])
        self.assertEqual((self.radarr.deleted, self.sent), ([], []))

    def test_unmonitored_unwatched_and_fileless_movies_stay(self):
        films = [movie(2, 200, monitored=False), movie(3, 300), movie(4, 400, file=False)]
        self.run_movies(films, [mitem(200, 5), mitem(300, 5, played=False), mitem(400, 5)])
        self.run_movies(films, [mitem(200, 5), mitem(300, 5, played=False), mitem(400, 5)], at=NOW + timedelta(days=9))
        self.assertEqual((self.radarr.deleted, self.sent), ([], []))

    def test_movie_deletes_are_capped(self):
        a.MAX_DELETES = 1
        self.addCleanup(setattr, a, "MAX_DELETES", 25)
        films, plays = [movie(1, 100), movie(2, 200, "Two")], [mitem(100, 5), mitem(200, 5)]
        self.run_movies(films, plays)
        self.run_movies(films, plays, at=NOW + timedelta(days=8))
        self.assertEqual(len(self.radarr.deleted), 1)
        self.assertEqual(self.sent[-1][0], "warn")

    def test_maintained_list_roundtrip_is_announced(self):
        a.maintained_edit("Adele One Night Only (2011)", True)
        a.maintained_edit("Adele One Night Only (2011)", True)  # duplicate: no change
        self.assertEqual([e["title"] for e in a.maintained_list()], ["Adele One Night Only (2011)"])
        a.maintained_edit("adele one night only (2011)", False)
        self.assertEqual(a.maintained_list(), [])
        self.assertEqual([m[2].split(" (now")[0] for m in self.sent],
                         ["Maintained movies: added Adele One Night Only (2011)",
                          "Maintained movies: removed adele one night only (2011)"])

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

    # The lists and the state file guard against deletion: broken means stop.

    def test_broken_hopping_list_stops_the_run_instead_of_deleting(self):
        a.HOPPING.write_text('["Modern Family",]')  # trailing comma
        with self.assertRaises(ValueError):
            self.go({"u1": [item("jf2", 1, 1, days_ago=30)]})
        self.assertEqual(self.sonarr.deleted, [])

    def test_missing_list_is_empty(self):
        a.HOPPING.unlink()
        self.assertEqual(a.hopping_list(), [])

    def test_editing_a_broken_list_does_not_overwrite_it(self):
        a.HOPPING.write_text("{oops")
        with self.assertRaises(ValueError):
            a.hopping_edit("Rooster", True)
        self.assertEqual(a.HOPPING.read_text(), "{oops")

    def test_list_writes_leave_no_temp_file(self):
        a.maintained_edit("Film", True)
        self.assertEqual(sorted(p.name for p in a.MAINTAINED.parent.glob(".maintained.json.tmp")), [])
        self.assertEqual([e["title"] for e in a.maintained_list()], ["Film"])

    def test_broken_state_stops_the_run_and_is_kept(self):
        a.STATE.write_text("{half")
        with self.assertRaises(ValueError):
            self.go({"u1": [item("jf1", 1, 1)]})
        self.assertEqual(a.STATE.read_text(), "{half")

    def test_slack_down_means_no_deletion_clock(self):
        a.notify = lambda *x: self.sent.append(x) and False  # every post fails
        self.run_movies([movie(1, 100)], [mitem(100, 4)])
        self.assertEqual(a.load_state()["movie_warned"], {})
        a.notify = lambda *x: self.sent.append(x) or True  # Slack back: warned now, deleted a week later
        self.run_movies([movie(1, 100)], [mitem(100, 4)], at=NOW + timedelta(days=8))
        self.assertEqual(self.radarr.deleted, [])
        self.assertIn("to be deleted", self.sent[-1][2])

    # Matching by id, not title (homelab-0010): a rename in Sonarr/Radarr must not
    # lift protection, and an entry nothing matches must be reported, not ignored.

    def test_renamed_hopping_show_stays_protected_and_still_counts_as_a_hog(self):
        a.HOPPING.write_text('[{"title": "Modern Family", "tvdbId": 222}]')
        gb = 1024 ** 3
        self.series[1]["title"] = "Modern Family (2026 re-release)"  # Sonarr renamed it
        self.series[1]["statistics"] = {"sizeOnDisk": 600 * gb}
        a.disk_total = lambda: 1000 * gb
        self.addCleanup(setattr, a, "disk_total", lambda: 10 ** 15)
        self.go({"u1": [item("jf2", 1, 1, days_ago=30)]})
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))
        self.assertTrue(any("filling the disk" in m[1] for m in self.sent))

    def test_renamed_maintained_movie_stays_protected_past_the_warning_window(self):
        a.MAINTAINED.write_text('[{"title": "Film", "tmdbId": 100}]')
        films = [movie(1, 100, title="Film (director's cut)")]  # Radarr renamed it
        play = [mitem(100, 4)]
        self.run_movies(films, play)
        self.run_movies(films, play, at=NOW + timedelta(days=9))
        self.assertEqual((self.radarr.deleted, [m for m in self.sent if "Film" in m[2] and "deleted" in m[2]]),
                          ([], []))

    def test_unmatched_entry_warns_every_run_and_slacks_once_each_way(self):
        a.MAINTAINED.write_text('[{"title": "Ghost Movie", "tmdbId": 999}]')
        films = [movie(1, 100)]
        play = [mitem(100, 4)]
        self.run_movies(films, play)
        self.assertIn("WARN Maintained movies entry matches nothing in Sonarr/Radarr: Ghost Movie", a.LOG.read_text())
        self.assertEqual(len([m for m in self.sent if "Ghost Movie" in m[2]]), 1)
        self.sent.clear()
        self.run_movies(films, play, at=NOW + timedelta(days=1))  # still unmatched: logged, not re-slacked
        self.assertIn("WARN Maintained movies entry matches nothing in Sonarr/Radarr: Ghost Movie", a.LOG.read_text())
        self.assertEqual([m for m in self.sent if "Ghost Movie" in m[2]], [])
        films.append(movie(2, 999, title="Ghost Movie"))  # it reappears in Radarr
        self.run_movies(films, play, at=NOW + timedelta(days=2))
        self.assertTrue(any("Ghost Movie" in m[2] and "matches again" in m[2] for m in self.sent))
        # Other movies are still warned about and deleted as usual.
        self.run_movies(films, play, at=NOW + timedelta(days=10))
        self.assertEqual(self.radarr.deleted, [5001])

    def test_unmatched_entry_removed_from_list_reports_removed_not_matches_again(self):
        a.MAINTAINED.write_text('[{"title": "Ghost Movie", "tmdbId": 999}]')
        films = [movie(1, 100)]
        play = [mitem(100, 4)]
        self.run_movies(films, play)
        self.assertEqual(len([m for m in self.sent if "Ghost Movie" in m[2]]), 1)
        self.sent.clear()
        a.MAINTAINED.write_text("[]")  # entry removed from the list entirely, not re-matched
        self.run_movies(films, play, at=NOW + timedelta(days=1))
        self.assertTrue(any("Ghost Movie" in m[2] and "removed from the list" in m[2] for m in self.sent))
        self.assertFalse(any("matches again" in m[2] for m in self.sent))

    def test_unmatched_check_skipped_on_an_empty_radarr_list(self):
        a.MAINTAINED.write_text('[{"title": "Ghost Movie", "tmdbId": 999}]')
        self.run_movies([], [])
        self.assertNotIn("Ghost Movie", a.LOG.read_text())
        self.assertEqual(self.sent, [])

    def test_unmatched_entry_logs_but_sends_nothing_in_dry_run(self):
        a.MAINTAINED.write_text('[{"title": "Ghost Movie", "tmdbId": 999}]')
        self.sonarr = FakeSonarr([], {})
        self.radarr = FakeRadarr([movie(1, 100)])
        a.run(self.sonarr, FakeJf({}), NOW, dry=True, radarr=self.radarr)
        self.assertIn("WARN Maintained movies entry matches nothing in Sonarr/Radarr: Ghost Movie", a.LOG.read_text())
        self.assertEqual(self.sent, [])
        self.assertEqual(a.load_state().get("unmatched", {}), {})

    def test_legacy_plain_string_lists_still_protect_by_title(self):
        a.HOPPING.write_text('["Modern Family"]')
        entries = a.hopping_list()
        self.assertEqual(entries, [{"title": "Modern Family"}])
        a.MAINTAINED.write_text('["Film"]')
        self.assertEqual(a.maintained_list(), [{"title": "Film"}])
        self.go({"u1": [item("jf2", 1, 1, days_ago=30)]})
        self.assertEqual((self.sonarr.deleted, self.sonarr.searched, self.sonarr.monitored), ([], [], []))
        self.run_movies([movie(1, 100, title="Film")], [mitem(100, 4)])
        self.assertEqual((self.radarr.deleted, [m for m in self.sent if "Film" in m[2] and "deleted" in m[2]]),
                          ([], []))

    # CLI add/remove by id, list with `matched`, and `migrate` (homelab-0010, plan item 2).

    def test_add_stores_id_with_live_title_and_refuses_unknown_or_unreachable(self):
        sonarr = FakeSonarr(self.series, self.eps)  # tvdbId 222 is "Modern Family"
        ok, _ = a.hopping_add(sonarr, 111)
        self.assertTrue(ok)
        self.assertIn("Show", [e["title"] for e in a.hopping_list()])
        ok, _ = a.hopping_add(sonarr, 404)  # not a real series
        self.assertFalse(ok)
        self.assertIn("Show", [e["title"] for e in a.hopping_list()])  # nothing extra written
        self.assertNotIn("404", str(a.hopping_list()))

        class Boom:
            def movies(self): raise RuntimeError("radarr down")
        with self.assertRaises(RuntimeError):
            a.maintained_add(Boom(), 100)
        self.assertEqual(a.maintained_list(), [])  # nothing written

    def test_add_an_id_already_on_the_list_changes_nothing(self):
        sonarr = FakeSonarr(self.series, self.eps)
        a.hopping_add(sonarr, 111)
        self.sent.clear()
        a.hopping_add(sonarr, 111)
        self.assertEqual(len(a.hopping_list()), 2)  # Modern Family (legacy) + Show
        self.assertEqual(self.sent, [])  # no duplicate Slack line

    def test_remove_works_by_id_and_by_title_without_sonarr_radarr(self):
        a.HOPPING.write_text('[{"title": "Modern Family", "tvdbId": 222}, {"title": "Rooster"}]')
        ok, _ = a.hopping_remove(222)
        self.assertTrue(ok)
        self.assertEqual([e["title"] for e in a.hopping_list()], ["Rooster"])
        ok, _ = a.hopping_remove("rooster")  # title-only entry, by title
        self.assertTrue(ok)
        self.assertEqual(a.hopping_list(), [])
        ok, _ = a.hopping_remove(999)
        self.assertFalse(ok)

    def test_list_reports_matched_and_renamed_titles(self):
        a.HOPPING.write_text('[{"title": "Modern Family", "tvdbId": 222}, {"title": "Ghost", "tvdbId": 9}]')
        series = [{"title": "Modern Family (2026 re-release)", "tvdbId": 222}]
        rows = {e["title"]: e for e in a._annotate(a.hopping_list(), series, "tvdbId", False)}
        self.assertTrue(rows["Modern Family"]["matched"])
        self.assertEqual(rows["Modern Family"]["current_title"], "Modern Family (2026 re-release)")
        self.assertFalse(rows["Ghost"]["matched"])
        self.assertNotIn("current_title", rows["Ghost"])
        null_rows = a._annotate(a.hopping_list(), None, "tvdbId", False)
        self.assertTrue(all(r["matched"] is None for r in null_rows))

    def test_migrate_resolves_ids_keeps_ambiguous_title_only_and_is_idempotent(self):
        a.HOPPING.write_text('["Modern Family", "Nonexistent Show"]')
        a.MAINTAINED.write_text('["Film"]')
        sonarr = FakeSonarr([{"id": 2, "title": "Modern Family", "tvdbId": 222, "monitored": True}], {})
        radarr = FakeRadarr([movie(1, 100, title="Film"), movie(2, 200, title="Film")])  # ambiguous title
        left_h, left_m = a.migrate(sonarr, radarr)
        self.assertEqual(left_h, ["Nonexistent Show"])
        self.assertEqual(left_m, ["Film"])
        self.assertEqual(a.hopping_list(), [{"title": "Modern Family", "tvdbId": 222},
                                             {"title": "Nonexistent Show"}])
        self.assertEqual(a.maintained_list(), [{"title": "Film"}])
        before_h, before_m = a.HOPPING.read_text(), a.MAINTAINED.read_text()
        left_h2, left_m2 = a.migrate(sonarr, radarr)  # running again changes nothing
        self.assertEqual((left_h2, left_m2), (left_h, left_m))
        self.assertEqual((a.HOPPING.read_text(), a.MAINTAINED.read_text()), (before_h, before_m))

    def test_migrate_writes_nothing_when_sonarr_or_radarr_is_unreachable(self):
        a.HOPPING.write_text('["Modern Family"]')
        before = a.HOPPING.read_text()

        class Boom:
            def series(self): raise RuntimeError("sonarr down")
        with self.assertRaises(RuntimeError):
            a.migrate(Boom(), FakeRadarr([]))
        self.assertEqual(a.HOPPING.read_text(), before)

    def test_movie_cap_message_never_negative(self):
        a.MAX_DELETES = 1
        self.addCleanup(setattr, a, "MAX_DELETES", 25)
        films, plays = [movie(1, 100), movie(2, 200, "Two")], [mitem(100, 5), mitem(200, 5)]
        self.run_movies(films, plays)
        self.run_movies(films, plays, at=NOW + timedelta(days=8))
        msg = self.sent[-1][2]
        self.assertIn("1 more movie deletion(s)", msg)
        self.assertNotIn("-1", msg)


class TestArrKey(unittest.TestCase):
    def setUp(self):
        self._orig_env = dict(a.os.environ)

    def tearDown(self):
        a.os.environ.clear()
        a.os.environ.update(self._orig_env)

    def test_arr_key_from_env(self):
        a.os.environ["SONARR_API_KEY"] = "my_sonarr_key"
        self.assertEqual(a.arr_key("sonarr"), "my_sonarr_key")

    def test_arr_key_from_config_xml(self):
        a.os.environ.pop("SONARR_API_KEY", None)
        orig_root = a.ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Path(tmp) / "services" / "media" / "sonarr" / "config.xml"
                cfg.parent.mkdir(parents=True)
                cfg.write_text("<Config><ApiKey>xml_sonarr_key</ApiKey></Config>")
                a.ROOT = Path(tmp)
                self.assertEqual(a.arr_key("sonarr"), "xml_sonarr_key")
        finally:
            a.ROOT = orig_root

    def test_arr_key_missing_raises_runtime_error(self):
        a.os.environ.pop("SONARR_API_KEY", None)
        orig_root = a.ROOT
        try:
            a.ROOT = Path("/nonexistent/path/for/test")
            with tempfile.TemporaryDirectory() as tmp:
                with patch("pathlib.Path.home", return_value=Path(tmp)):
                    with self.assertRaises(RuntimeError) as cm:
                        a.arr_key("sonarr")
                    self.assertIn("SONARR_API_KEY is not set", str(cm.exception))
        finally:
            a.ROOT = orig_root


if __name__ == "__main__":
    unittest.main()
