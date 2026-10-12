#!/usr/bin/env python3
"""Keep the media disk at "what you are watching + the next few episodes".

Run every few minutes by media-autopilot.timer. Each run reads watch state from
Jellyfin (every user) and then, for every show Sonarr manages:

  * monitors the next KEEP_AHEAD episodes after the furthest one watched or in
    progress, and searches for the ones it does not have yet;
  * deletes episodes watched more than DELETE_AFTER_DAYS ago and unmonitors them,
    so Sonarr does not fetch them again.

Shows in hopping.json (watched out of order) are left completely alone. Posts
a summary to Slack when it grabs or deletes something. Standard library only.
"""

import json
import os
import re
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
RESEARCH_AFTER_S = 24 * 3600
HEARTBEAT_S = 3600
SLACK_CHANNEL = os.environ.get("AUTOPILOT_SLACK_CHANNEL", "media-server")


HOPPING = Path(os.environ.get("AUTOPILOT_HOPPING", HERE / "hopping.json"))


def hopping_list():
    """Sonarr titles of shows watched out of order. Edited from the cockpit's Media tab."""
    try:
        return sorted({str(t).strip() for t in json.loads(HOPPING.read_text()) if str(t).strip()},
                      key=str.lower)
    except (OSError, ValueError):
        return []


def hopping_shows():
    return {t.lower() for t in hopping_list()}


def hopping_edit(title, add):
    title = (title or "").strip()
    if not title:
        return False, "no show title given"
    current = hopping_list()
    if add and title.lower() not in {t.lower() for t in current}:
        current.append(title)
    elif not add:
        current = [t for t in current if t.lower() != title.lower()]
    before = hopping_list()
    HOPPING.write_text(json.dumps(sorted(current, key=str.lower), indent=2) + "\n")
    if sorted(before) != sorted(current):
        notify("info", "Media autopilot", f"Hopping list: {'added' if add else 'removed'} {title} "
               f"(now: {', '.join(sorted(current, key=str.lower)) or 'none'})")
    return True, f"{'added' if add else 'removed'} {title}"


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


# ------------------------------------------------------------------ planning

def plan_show(eps, watched, now):
    """Decide for one non-hopping show. Returns dict(monitor, search, delete)."""
    eps = sorted((e for e in eps if e["seasonNumber"] > 0),
                 key=lambda e: (e["seasonNumber"], e["episodeNumber"]))
    pivot = max(watched)
    ahead = [e for e in eps if (e["seasonNumber"], e["episodeNumber"]) > pivot][:KEEP_AHEAD]
    out = {"monitor": [e for e in ahead if not e["monitored"]],
           "search": [e for e in ahead if not e.get("hasFile")], "delete": []}
    cutoff = now - timedelta(days=DELETE_AFTER_DAYS)
    for e in eps:
        rec = watched.get((e["seasonNumber"], e["episodeNumber"]))
        if rec and rec["played"] and rec["last"] and rec["last"] <= cutoff and e.get("hasFile"):
            out["delete"].append(e)
    return out


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"searched": {}, "last_ok": 0}


def tag(title, e):
    return f"{title} S{e['seasonNumber']:02d}E{e['episodeNumber']:02d}"


def notify(status, title, message):
    try:
        r = subprocess.run([str(NOTIFY), "-c", SLACK_CHANNEL, "-s", status, "-t", title, message],
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            log(f"Slack notify failed: {(r.stderr or r.stdout).strip()[:200]}")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"Slack notify failed: {e}")


def run(sonarr, jf, now=None, dry=False):
    now = now or datetime.now(timezone.utc)
    t = time.time()
    state = load_state()
    watch = collect_watch(jf)
    skip = hopping_shows()
    grabbed, deleted, monitored, pending_deletes = [], [], [], []

    for s in sonarr.series():
        if s["title"].lower() in skip:
            continue
        watched = watch.get(str(s.get("tvdbId"))) or watch.get(s["title"].lower())
        if not watched:
            continue
        p = plan_show(sonarr.episodes(s["id"]), watched, now)
        if p["monitor"]:
            if not dry:
                sonarr.monitor([e["id"] for e in p["monitor"]], True)
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
        deleted.append(tag(title, e))
    capped = len(pending_deletes) > MAX_DELETES
    if capped:
        log(f"WARN {len(pending_deletes)} deletions due, capped at {MAX_DELETES} this run")

    prefix = "[dry-run] " if dry else ""
    lines = []
    if monitored:
        lines.append(f"Now monitoring: {', '.join(monitored)}")
    if grabbed:
        lines.append(f"Searching next: {', '.join(grabbed)}")
    if deleted:
        lines.append(f"Deleted watched: {', '.join(deleted)}")
    if capped:
        lines.append(f"Safety cap: {len(pending_deletes) - MAX_DELETES} more deletion(s) wait for the next run "
                     f"(max {MAX_DELETES} per run).")
    for line in lines:
        log(prefix + line)
    if lines and not dry:
        notify("warn" if capped else "info", "Media autopilot", "\n".join(lines))
    if state.get("failing") and not dry:
        notify("ok", "Media autopilot recovered", "Runs are succeeding again.")
        state["failing"] = False
    if t - state.get("last_ok", 0) >= HEARTBEAT_S and not dry:
        log(f"[OK] {len(watch)} watched shows checked")
        state["last_ok"] = t
    if not dry:
        STATE.write_text(json.dumps(state))
    return {"grabbed": grabbed, "deleted": deleted}


def sonarr_key():
    key = os.environ.get("SONARR_API_KEY")
    if key:
        return key
    cfg = ROOT / "services" / "media" / "sonarr" / "config.xml"
    m = re.search(r"<ApiKey>([^<]+)", cfg.read_text()) if cfg.exists() else None
    if not m:
        raise RuntimeError("SONARR_API_KEY is not set and sonarr/config.xml has none")
    return m.group(1)


def cli(argv):
    """`hopping list|add|remove` and `shows`, for the cockpit's Media tab (JSON on stdout)."""
    if argv[0] == "hopping" and argv[1:2] == ["list"]:
        print(json.dumps({"hopping": hopping_list()}))
    elif argv[0] == "hopping" and argv[1:2] in (["add"], ["remove"]) and len(argv) == 3:
        ok, msg = hopping_edit(argv[2], argv[1] == "add")
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    elif argv[0] == "shows":
        titles = sorted((x["title"] for x in Sonarr(os.environ.get("SONARR_URL", "http://127.0.0.1:8989"),
                                                    sonarr_key()).series()), key=str.lower)
        print(json.dumps({"shows": titles}))
    else:
        print("usage: autopilot.py [--dry-run | hopping list|add <title>|remove <title> | shows]", file=sys.stderr)
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
            Jellyfin(os.environ.get("JELLYFIN_URL", "http://127.0.0.1:8096"), jkey), dry=dry)
    except Exception as e:  # noqa: BLE001 - one failed run must not kill the timer
        log(f"FAILED: {e}")
        state = load_state()
        if not state.get("failing") and not dry:
            # Once per outage, not every five minutes; run() announces the recovery.
            notify("error", "Media autopilot failed", str(e)[:300])
            state["failing"] = True
            STATE.write_text(json.dumps(state))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
