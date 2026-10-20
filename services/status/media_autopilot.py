"""The media autopilot's two lists, edited from the cockpit's Media tab.

A "hopping" show is one watched out of order, so the autopilot must not delete
its watched episodes or guess which episodes come next. A "maintained" movie is
one the autopilot must never delete after it is watched. `autopilot.py` stays the
only thing that knows how the lists are stored: this module shells out to its
`hopping`, `maintained`, `shows` and `movies` commands, the same way
supabase_keepalive.py drives keepalive.py, so the page cannot drift from what
the timer actually reads.

Nothing here builds a command out of client text beyond one argv element: the
title the browser sends is passed as a single argument, never through a shell.
"""

import json
import os
import subprocess
import sys

from cockpit.pages import load_template

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
# `or` rather than a get() default: an empty value in the .env means "default".
AUTOPILOT_DIR = os.environ.get("STATUS_AUTOPILOT_DIR") or os.path.join(
    REPO_ROOT, "services", "media-autopilot"
)
SCRIPT = os.path.join(AUTOPILOT_DIR, "autopilot.py")
TIMEOUT = float(os.environ.get("STATUS_AUTOPILOT_TIMEOUT") or "20")


def _run(*argv):
    """Run autopilot.py. Returns (ok, stdout, message)."""
    if not os.path.exists(SCRIPT):
        return False, "", f"autopilot.py not found at {SCRIPT}"
    try:
        done = subprocess.run(
            [sys.executable, SCRIPT, *argv],
            cwd=AUTOPILOT_DIR, capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"autopilot.py {argv[0]} timed out after {TIMEOUT:.0f}s"
    except OSError as err:
        return False, "", str(err)
    if done.returncode != 0:
        return False, done.stdout, (done.stderr or done.stdout).strip()
    return True, done.stdout, ""


def _json(*argv):
    ok, out, message = _run(*argv)
    if not ok:
        return None, message
    try:
        return json.loads(out), ""
    except json.JSONDecodeError:
        return None, f"autopilot.py {argv[0]} returned nothing usable"


LISTS = ("hopping", "maintained")


def roster():
    """Both lists (each entry carrying `matched` and, when renamed, `current_title`),
    plus every show Sonarr has and every movie Radarr has (the add boxes' picker).
    `shows`/`movies` come back empty with a message when that service is down -
    the caller then disables that list's Add box but leaves Remove alone."""
    hopping, message = _json("hopping", "list")
    if hopping is None:
        return {"ok": False, "hopping": [], "maintained": [], "shows": [], "movies": [], "message": message}
    # Sonarr or Radarr being down must not stop the lists from being shown or edited.
    maintained, _ = _json("maintained", "list")
    shows, shows_message = _json("shows")
    movies, movies_message = _json("movies")
    return {"ok": True, "hopping": hopping.get("hopping", []),
            "maintained": (maintained or {}).get("maintained", []),
            "shows": (shows or {}).get("shows", []),
            "shows_message": "" if shows is not None else (shows_message or "Sonarr is unreachable"),
            "movies": (movies or {}).get("movies", []),
            "movies_message": "" if movies is not None else (movies_message or "Radarr is unreachable")}


def edit(ident, add, kind="hopping"):
    """Add or remove one entry on the `hopping` or `maintained` list.

    `ident` is the id the page picked (an `int`) for add, or for remove either
    that same id or the title of a title-only entry (a `str`). Returns
    {"ok", "message"}."""
    if kind not in LISTS:
        return {"ok": False, "message": f"unknown list {kind!r}"}
    is_id = isinstance(ident, int) and not isinstance(ident, bool)
    if add:
        if not is_id or ident <= 0:
            return {"ok": False, "message": "pick an item from the list"}
        arg = str(ident)
    elif is_id:
        if ident <= 0:
            return {"ok": False, "message": "pick an item from the list"}
        arg = str(ident)
    else:
        title = ident.strip() if isinstance(ident, str) else ""
        if not title or len(title) > 200 or "\n" in title:
            return {"ok": False, "message": "that is not a title"}
        arg = title
    ok, out, message = _run(kind, "add" if add else "remove", arg)
    if not ok:
        return {"ok": False, "message": message}
    return {"ok": True, "message": out.strip()}


MEDIA_PAGE = load_template("media.html")
