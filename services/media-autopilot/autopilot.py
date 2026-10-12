#!/usr/bin/env python3
"""Keep the media disk at "what you are watching + the next few episodes".

Run every few minutes by media-autopilot.timer. Each run reads watch state from
Jellyfin (every user) and then, for every show Sonarr manages:

  * monitors the next KEEP_AHEAD episodes after the furthest one watched or in
    progress, and searches for the ones it does not have yet - except any that
    were deleted or unmonitored by hand since, which are left alone for good;
  * deletes episodes watched more than DELETE_AFTER_DAYS ago and unmonitors them,
    so Sonarr does not fetch them again;

and for Radarr movies: warns on Slack when someone finishes one, then deletes (and
unmonitors) it MOVIE_WARN_DAYS later unless it is on the maintained list.

It is a weak helper: unless the signs are clean it does nothing and leaves the show
to you. Shows in hopping.json and shows unmonitored in Sonarr are left completely alone. Posts
a summary to Slack when it grabs or deletes something. Standard library only.
"""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LOG = Path(os.environ.get("AUTOPILOT_LOG", HERE / "autopilot.log"))
STATE = Path(os.environ.get("AUTOPILOT_STATE", HERE / "state.json"))
NOTIFY = ROOT / "tools" / "slackbot-notify.sh"

KEEP_AHEAD = int(os.environ.get("KEEP_AHEAD", "2"))
DELETE_AFTER_DAYS = float(os.environ.get("DELETE_AFTER_DAYS", "3"))
MAX_DELETES = int(os.environ.get("MAX_DELETES_PER_RUN", "25"))
# Hopping shows are never touched, but they must not quietly eat the disk either.
HOPPING_MAX_DISK_FRACTION = float(os.environ.get("HOPPING_MAX_DISK_FRACTION", "0.5"))
DISK_PATH = os.environ.get("AUTOPILOT_DISK_PATH", str(Path.home() / "content"))
MOVIE_WINDOW_DAYS = float(os.environ.get("MOVIE_WINDOW_DAYS", "30"))
MOVIE_WARN_DAYS = float(os.environ.get("MOVIE_WARN_DAYS", "7"))
ABANDONED_DAYS = float(os.environ.get("ABANDONED_DAYS", "365"))
STALE_DAYS = float(os.environ.get("STALE_DAYS", "30"))
RESEARCH_AFTER_S = 24 * 3600
HEARTBEAT_S = 3600
SLACK_CHANNEL = os.environ.get("AUTOPILOT_SLACK_CHANNEL", "media-server")


HOPPING = Path(os.environ.get("AUTOPILOT_HOPPING", HERE / "hopping.json"))
MAINTAINED = Path(os.environ.get("AUTOPILOT_MAINTAINED", HERE / "maintained_movies.json"))


def _read_list(path):
    """A missing file is an empty list. A broken one raises: these lists
    protect shows and movies from deletion, so a typo must stop the run,
    not switch the protection off."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except ValueError as e:
        raise ValueError(f"{path.name} is not valid JSON ({e}); fix it before the autopilot runs again") from e
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must be a JSON list of titles")
    return sorted({str(t).strip() for t in data if str(t).strip()}, key=str.lower)


def _write_json(path, data, indent=None):
    """Write to a temp file and swap it in, so a reader never sees half a file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=indent) + ("\n" if indent else ""))
    os.replace(tmp, path)


def _edit_list(path, label, title, add):
    title = (title or "").strip()
    if not title:
        return False, "no title given"
    # The cockpit serves requests on threads: two edits at once must not lose one.
    with open(path.with_name(f".{path.name}.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = _read_list(path)
        current = list(before)
        if add and title.lower() not in {t.lower() for t in current}:
            current.append(title)
        elif not add:
            current = [t for t in current if t.lower() != title.lower()]
        _write_json(path, sorted(current, key=str.lower), indent=2)
    if sorted(before) != sorted(current):
        notify("info", "Media autopilot", f"{label}: {'added' if add else 'removed'} {title} "
               f"(now: {', '.join(sorted(current, key=str.lower)) or 'none'})")
    return True, f"{'added' if add else 'removed'} {title}"


def hopping_list():
    """Sonarr titles of shows watched out of order. Edited from the cockpit's Media tab."""
    return _read_list(HOPPING)


def hopping_shows():
    return {t.lower() for t in hopping_list()}


def hopping_edit(title, add):
    return _edit_list(HOPPING, "Hopping list", title, add)


def maintained_list():
    """Radarr movies the autopilot must never delete: 'Title' or 'Title (Year)'."""
    return _read_list(MAINTAINED)


def maintained_edit(title, add):
    return _edit_list(MAINTAINED, "Maintained movies", title, add)


def is_maintained(movie, entries):
    names = {movie["title"].lower(), f"{movie['title']} ({movie.get('year', '')})".lower()}
    return bool(names & {e.lower() for e in entries})


def log(msg):
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} media-autopilot: {msg}\n")
    print(msg)


# ------------------------------------------------------------------ clients

def http(url, key_header, key, method="GET", body=None):
    req = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={key_header: key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


class Sonarr:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/") + "/api/v3/", key

    def _c(self, path, method="GET", body=None):
        return http(self.url + path, "X-Api-Key", self.key, method, body)

    def series(self):
        return self._c("series")

    def episodes(self, series_id):
        return self._c(f"episode?seriesId={series_id}&includeEpisodeFile=true")

    def monitor(self, ids, monitored):
        self._c("episode/monitor", "PUT", {"episodeIds": ids, "monitored": monitored})

    def search(self, ids):
        self._c("command", "POST", {"name": "EpisodeSearch", "episodeIds": ids})

    def delete_file(self, file_id):
        self._c(f"episodefile/{file_id}", "DELETE")


class Radarr:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/") + "/api/v3/", key

    def _c(self, path, method="GET", body=None):
        return http(self.url + path, "X-Api-Key", self.key, method, body)

    def movies(self):
        return self._c("movie") or []

    def unmonitor(self, movie_ids):
        self._c("movie/editor", "PUT", {"movieIds": movie_ids, "monitored": False})

    def delete_file(self, file_id):
        self._c(f"moviefile/{file_id}", "DELETE")


class Jellyfin:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def _c(self, path):
        # This Jellyfin rejects X-Emby-Token for API keys; the Authorization form works.
        return http(self.url + path, "Authorization", f'MediaBrowser Token="{self.key}"') or {}

    def users(self):
        return self._c("/Users") or []

    def series_ids(self):
        """Jellyfin series id -> (title, tvdb id or None)."""
        items = self._c("/Items?IncludeItemTypes=Series&Recursive=true&Fields=ProviderIds&Limit=5000").get("Items", [])
        return {i["Id"]: (i["Name"], (i.get("ProviderIds") or {}).get("Tvdb")) for i in items}

    def movies(self, user_id):
        return self._c(f"/Users/{user_id}/Items?IncludeItemTypes=Movie&Recursive=true&Fields=ProviderIds"
                       "&Limit=10000").get("Items", [])

    def episodes(self, user_id):
        return self._c(f"/Users/{user_id}/Items?IncludeItemTypes=Episode&Recursive=true&Limit=10000").get("Items", [])


# --------------------------------------------------------------- watch state

def parse_when(s):
    if not s:
        return None
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def collect_watch(jf):
    """{tvdb id or lower title: {(season, ep): {"played": bool, "last": dt|None}}}, merged over users.

    An episode counts as watched when ANY user finished it; partial playback only
    counts as "reached" (it moves the pivot but never makes an episode deletable).
    """
    sid = jf.series_ids()
    watch = {}
    for u in jf.users():
        for e in jf.episodes(u["Id"]):
            ud = e.get("UserData") or {}
            played, partial = bool(ud.get("Played")), (ud.get("PlaybackPositionTicks") or 0) > 0
            if not (played or partial) or e.get("ParentIndexNumber") is None or e.get("IndexNumber") is None:
                continue
            title, tvdb = sid.get(e.get("SeriesId"), (e.get("SeriesName"), None))
            show = watch.setdefault(str(tvdb) if tvdb else (title or "").lower(), {})
            rec = show.setdefault((e["ParentIndexNumber"], e["IndexNumber"]), {"played": False, "last": None})
            rec["played"] = rec["played"] or played
            when = parse_when(ud.get("LastPlayedDate"))
            if when and (rec["last"] is None or when > rec["last"]):
                rec["last"] = when
    return watch


def collect_movie_watch(jf):
    """{tmdb id: {"played": bool, "last": dt|None}} merged over users; finished plays only."""
    watch = {}
    for u in jf.users():
        for m in jf.movies(u["Id"]):
            ud = m.get("UserData") or {}
            tmdb = (m.get("ProviderIds") or {}).get("Tmdb")
            if not tmdb or not ud.get("Played"):
                continue
            rec = watch.setdefault(str(tmdb), {"played": True, "last": None})
            when = parse_when(ud.get("LastPlayedDate"))
            if when and (rec["last"] is None or when > rec["last"]):
                rec["last"] = when
    return watch


def plan_movies(movies, watch, maintained, warned, now):
    """Split finished movies into (to_warn, to_delete).

    A movie finished within MOVIE_WINDOW_DAYS is first WARNED about on Slack; it may be
    deleted only MOVIE_WARN_DAYS after that warning (and DELETE_AFTER_DAYS after the last
    play, so a rewatch pushes it back). Maintained and unmonitored movies are never
    touched; older plays are left alone (a library favourite is not "just watched").
    """
    oldest = now - timedelta(days=MOVIE_WINDOW_DAYS)
    to_warn, to_delete = [], []
    for m in movies:
        rec = watch.get(str(m.get("tmdbId")))
        if not (rec and m.get("hasFile") and m.get("monitored") and rec["last"] and oldest <= rec["last"] <= now):
            continue
        if is_maintained(m, maintained):
            warned.pop(str(m["tmdbId"]), None)  # protected now; warn afresh if it is ever un-protected
            continue
        at = parse_when(warned.get(str(m["tmdbId"])))
        if at is None:
            to_warn.append((m, max(now + timedelta(days=MOVIE_WARN_DAYS), rec["last"] + timedelta(days=DELETE_AFTER_DAYS))))
        elif now >= max(at + timedelta(days=MOVIE_WARN_DAYS), rec["last"] + timedelta(days=DELETE_AFTER_DAYS)):
            to_delete.append(m)
    return to_warn, to_delete


# ------------------------------------------------------------------ planning

def plan_show(eps, watched, now):
    """Decide for one non-hopping show. Returns dict(monitor, search, delete)."""
    eps = sorted((e for e in eps if e["seasonNumber"] > 0),
                 key=lambda e: (e["seasonNumber"], e["episodeNumber"]))
    pivot = max(watched)
    ahead = [e for e in eps if (e["seasonNumber"], e["episodeNumber"]) > pivot][:KEEP_AHEAD]
    out = {"ahead": ahead, "monitor": [e for e in ahead if not e["monitored"]],
           "search": [e for e in ahead if not e.get("hasFile")], "delete": []}
    cutoff = now - timedelta(days=DELETE_AFTER_DAYS)
    for e in eps:
        rec = watched.get((e["seasonNumber"], e["episodeNumber"]))
        if rec and rec["played"] and rec["last"] and rec["last"] <= cutoff and e.get("hasFile"):
            out["delete"].append(e)
    return out


def doubt_reason(watched, now):
    """(reason, loud) for a show the autopilot should NOT act on, or None when the signs are clean.

    `loud` is True for genuinely unclear signals (worth one Slack line) and False for a
    show that is simply paused (not watched for STALE_DAYS) - that is normal, so silent.

    It is a weak helper: unless you are plainly watching in order, right now-ish,
    it leaves the show to you and Sonarr's own UI. Clean means the furthest episode
    is also the one played most recently, and that was within STALE_DAYS.
    """
    pivot = max(watched)
    dates = [r["last"] for r in watched.values() if r["last"]]
    if not dates or not watched[pivot]["last"]:
        return "no play dates to go on", True
    if watched[pivot]["last"] < max(dates):
        return "an earlier episode was played more recently than your furthest one (rewatching?)", True
    if now - watched[pivot]["last"] > timedelta(days=STALE_DAYS):
        return f"nothing watched in the last {STALE_DAYS:.0f} days", False
    return None


def disk_total():
    return shutil.disk_usage(DISK_PATH).total


def hopping_hog_warning(series, total):
    """A warning line when the hopping shows hold more than their share of the disk, else None."""
    skip = hopping_shows()
    size = sum((s.get("statistics") or {}).get("sizeOnDisk", 0) for s in series if s["title"].lower() in skip)
    if total and size > HOPPING_MAX_DISK_FRACTION * total:
        gb = 1024 ** 3
        return (f"Hopping shows hold {size / gb:.0f} GB, {100 * size / total:.0f}% of the disk "
                f"(limit {100 * HOPPING_MAX_DISK_FRACTION:.0f}%). The autopilot never touches them: "
                "trim them yourself in Sonarr.")
    return None


def untouched_since(series, watched):
    """Last sign of life for a show: its latest play, else the day it was added to Sonarr."""
    plays = [r["last"] for r in (watched or {}).values() if r["last"]]
    return max(plays) if plays else parse_when(series.get("added"))


def load_state():
    """A missing state file is a fresh start. A broken one raises: it holds the
    episodes turned down by hand, and starting over would grab them again."""
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return {"searched": {}, "last_ok": 0}
    except ValueError as e:
        raise ValueError(f"{STATE.name} is not valid JSON ({e}); fix or remove it") from e


def decline_check(state, ahead):
    """Episodes in the window the user has turned down by hand: returns the new ones.

    Declined = it had a file the autopilot saw and the file is gone without the
    autopilot deleting it, or the autopilot monitored it and someone unmonitored it.
    Declined episodes are never monitored, searched or re-added.
    """
    seen, mine, declined = (set(state.setdefault(k, [])) for k in ("seen", "mine", "declined"))
    fresh = []
    for e in ahead:
        i = e["id"]
        if i in declined:
            continue
        if (i in seen and not e.get("hasFile")) or (i in mine and not e["monitored"]):
            declined.add(i)
            fresh.append(e)
        else:
            if e.get("hasFile"):
                seen.add(i)
            if e["monitored"]:
                mine.add(i)  # seen monitored: turning it off later is the user's call
    state["seen"], state["mine"], state["declined"] = sorted(seen), sorted(mine), sorted(declined)
    return fresh


def tag(title, e):
    return f"{title} S{e['seasonNumber']:02d}E{e['episodeNumber']:02d}"


def notify(status, title, message):
    """Post to Slack. Returns True when the message went out."""
    try:
        r = subprocess.run([str(NOTIFY), "-c", SLACK_CHANNEL, "-s", status, "-t", title, message],
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            log(f"Slack notify failed: {(r.stderr or r.stdout).strip()[:200]}")
            return False
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log(f"Slack notify failed: {e}")
        return False


def run(sonarr, jf, now=None, dry=False, radarr=None):
    now = now or datetime.now(timezone.utc)
    t = time.time()
    state = load_state()
    watch = collect_watch(jf)
    skip = hopping_shows()
    grabbed, deleted, monitored, declined, unsure, abandoned, pending_deletes = [], [], [], [], [], [], []

    all_series = sonarr.series()
    hog = hopping_hog_warning(all_series, disk_total())
    for s in all_series:
        watched = watch.get(str(s.get("tvdbId"))) or watch.get(s["title"].lower())
        size = (s.get("statistics") or {}).get("sizeOnDisk", 0)
        since = untouched_since(s, watched) if size else None
        if since and now - since > timedelta(days=ABANDONED_DAYS):
            if s["title"] not in state.setdefault("abandoned", []):
                state["abandoned"].append(s["title"])
                abandoned.append(f"{s['title']} ({size / 1024 ** 3:.0f} GB, nothing since {since:%Y-%m-%d})")
        elif s["title"] in state.get("abandoned", []):
            state["abandoned"].remove(s["title"])  # touched again: may be reported next time
        if s["title"].lower() in skip or not s.get("monitored", True):
            continue  # hopping list, or unmonitored in Sonarr: hands off entirely
        if not watched:
            continue
        doubt = doubt_reason(watched, now)
        if doubt:
            why, loud = doubt
            if loud and state.setdefault("doubt", {}).get(s["title"]) != why:
                unsure.append(f"{s['title']} ({why})")
                state["doubt"][s["title"]] = why
            continue
        state.get("doubt", {}).pop(s["title"], None)
        p = plan_show(sonarr.episodes(s["id"]), watched, now)
        turned_down = decline_check(state, p["ahead"])
        if turned_down:
            # Unmonitor so Sonarr's own RSS sync cannot grab it behind our back.
            todo = [e["id"] for e in turned_down if e["monitored"]]
            if todo and not dry:
                sonarr.monitor(todo, False)
            declined += [tag(s["title"], e) for e in turned_down]
        skipped = set(state["declined"])
        p["monitor"] = [e for e in p["monitor"] if e["id"] not in skipped]
        p["search"] = [e for e in p["search"] if e["id"] not in skipped]
        if p["monitor"]:
            if not dry:
                sonarr.monitor([e["id"] for e in p["monitor"]], True)
                state["mine"] = sorted(set(state["mine"]) | {e["id"] for e in p["monitor"]})
            monitored += [tag(s["title"], e) for e in p["monitor"]]
        fresh = [e for e in p["search"]
                 if t - state["searched"].get(str(e["id"]), 0) > RESEARCH_AFTER_S
                 and (parse_when(e.get("airDateUtc")) or now) <= now]
        if fresh:
            if not dry:
                sonarr.search([e["id"] for e in fresh])
                for e in fresh:
                    state["searched"][str(e["id"])] = t
            grabbed += [tag(s["title"], e) for e in fresh]
        pending_deletes += [(s["title"], e) for e in p["delete"]]

    for title, e in pending_deletes[:MAX_DELETES]:
        if not dry:
            sonarr.monitor([e["id"]], False)
            sonarr.delete_file(e["episodeFile"]["id"])
            state["seen"] = [i for i in state.get("seen", []) if i != e["id"]]
        deleted.append(tag(title, e))
    episodes_waiting = max(0, len(pending_deletes) - MAX_DELETES)
    if episodes_waiting:
        log(f"WARN {len(pending_deletes)} deletions due, capped at {MAX_DELETES} this run")

    movies_gone, movies_waiting, movie_warnings, new_warned = [], 0, [], {}
    warned = state.setdefault("movie_warned", {})
    if radarr is not None:
        to_warn, due = plan_movies(radarr.movies(), collect_movie_watch(jf), maintained_list(), warned, now)
        for m, when in to_warn:
            # Recorded only once Slack has the warning: no warning, no deletion clock.
            new_warned[str(m["tmdbId"])] = now.isoformat()
            movie_warnings.append(f"{m['title']} ({m.get('sizeOnDisk', 0) / 1024 ** 3:.0f} GB, on {when:%Y-%m-%d})")
        for m in due[:MAX_DELETES]:
            if not dry:
                radarr.unmonitor([m["id"]])  # first, so Radarr cannot fetch it again
                radarr.delete_file(m["movieFile"]["id"])
                warned.pop(str(m["tmdbId"]), None)
            movies_gone.append(f"{m['title']} ({m.get('sizeOnDisk', 0) / 1024 ** 3:.0f} GB)")
        movies_waiting = max(0, len(due) - MAX_DELETES)

    prefix = "[dry-run] " if dry else ""
    lines = []
    if movie_warnings:
        lines.append(f"Watched movies to be deleted in {MOVIE_WARN_DAYS:.0f} days: {'; '.join(movie_warnings)}. "
                     "To keep one, add it to the maintained list (cockpit > Media tab).")
    if movies_gone:
        lines.append(f"Deleted watched movies: {', '.join(movies_gone)}")
    if movies_waiting:
        lines.append(f"Safety cap: {movies_waiting} more movie deletion(s) wait for the next run.")
    if monitored:
        lines.append(f"Now monitoring: {', '.join(monitored)}")
    if grabbed:
        lines.append(f"Searching next: {', '.join(grabbed)}")
    if deleted:
        lines.append(f"Deleted watched: {', '.join(deleted)}")
    if unsure:
        lines.append(f"Not sure, leaving it to you in Sonarr: {'; '.join(unsure)}")
    if abandoned:
        lines.append(f"Untouched for over a year, still on disk: {'; '.join(abandoned)}")
    if declined:
        lines.append(f"Left alone (removed or unmonitored by hand): {', '.join(declined)}")
    if episodes_waiting:
        lines.append(f"Safety cap: {episodes_waiting} more deletion(s) wait for the next run "
                     f"(max {MAX_DELETES} per run).")
    for line in lines:
        log(prefix + line)
    if lines and not dry:
        capped = episodes_waiting or movies_waiting
        if notify("warn" if capped or abandoned or movie_warnings else "info", "Media autopilot", "\n".join(lines)):
            warned.update(new_warned)
        elif new_warned:
            log(f"WARN Slack is down: {len(new_warned)} movie warning(s) will be sent again next run")
    if hog:
        # On purpose every run, not once: this one stays loud until it is fixed.
        log(prefix + "WARN " + hog)
        if not dry:
            notify("warn", "Media autopilot: hopping shows are filling the disk", hog)
    if state.get("failing") and not dry:
        notify("ok", "Media autopilot recovered", "Runs are succeeding again.")
        state["failing"] = False
    if t - state.get("last_ok", 0) >= HEARTBEAT_S and not dry:
        log(f"[OK] {len(watch)} watched shows checked")
        state["last_ok"] = t
    if not dry:
        _write_json(STATE, state)
    return {"grabbed": grabbed, "deleted": deleted}


def arr_key(app):
    """API key for sonarr/radarr: SONARR_API_KEY / RADARR_API_KEY, else the app's config.xml."""
    key = os.environ.get(f"{app.upper()}_API_KEY")
    if key:
        return key
    cfg = ROOT / "services" / "media" / app / "config.xml"
    m = re.search(r"<ApiKey>([^<]+)", cfg.read_text()) if cfg.exists() else None
    if not m:
        raise RuntimeError(f"{app.upper()}_API_KEY is not set and {app}/config.xml has none")
    return m.group(1)


def sonarr_key():
    return arr_key("sonarr")


def cli(argv):
    """`hopping list|add|remove` and `shows`, for the cockpit's Media tab (JSON on stdout)."""
    if argv[0] == "hopping" and argv[1:2] == ["list"]:
        print(json.dumps({"hopping": hopping_list()}))
    elif argv[0] == "hopping" and argv[1:2] in (["add"], ["remove"]) and len(argv) == 3:
        ok, msg = hopping_edit(argv[2], argv[1] == "add")
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    elif argv[0] == "maintained" and argv[1:2] == ["list"]:
        print(json.dumps({"maintained": maintained_list()}))
    elif argv[0] == "maintained" and argv[1:2] in (["add"], ["remove"]) and len(argv) == 3:
        ok, msg = maintained_edit(argv[2], argv[1] == "add")
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    elif argv[0] == "movies":
        movies = Radarr(os.environ.get("RADARR_URL", "http://127.0.0.1:7878"), arr_key("radarr")).movies()
        print(json.dumps({"movies": sorted((f"{m['title']} ({m['year']})" for m in movies), key=str.lower)}))
    elif argv[0] == "shows":
        titles = sorted((x["title"] for x in Sonarr(os.environ.get("SONARR_URL", "http://127.0.0.1:8989"),
                                                    sonarr_key()).series()), key=str.lower)
        print(json.dumps({"shows": titles}))
    else:
        print("usage: autopilot.py [--dry-run | hopping|maintained list|add <title>|remove <title> | shows | movies]", file=sys.stderr)
        return 2
    return 0


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        return cli(sys.argv[1:])
    dry = "--dry-run" in sys.argv
    try:
        jkey = os.environ.get("JELLYFIN_API_KEY", "")
        if not jkey:
            raise RuntimeError("JELLYFIN_API_KEY is not set (see .env.example)")
        run(Sonarr(os.environ.get("SONARR_URL", "http://127.0.0.1:8989"), sonarr_key()),
            Jellyfin(os.environ.get("JELLYFIN_URL", "http://127.0.0.1:8096"), jkey), dry=dry,
            radarr=Radarr(os.environ.get("RADARR_URL", "http://127.0.0.1:7878"), arr_key("radarr")))
    except Exception as e:  # noqa: BLE001 - one failed run must not kill the timer
        log(f"FAILED: {e}")
        try:
            state = load_state()
        except ValueError:
            state = None  # broken state file: alert every run, never overwrite it
        if not dry and (state is None or not state.get("failing")):
            # Once per outage, not every five minutes; run() announces the recovery.
            notify("error", "Media autopilot failed", str(e)[:300])
            if state is not None:
                state["failing"] = True
                _write_json(STATE, state)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
