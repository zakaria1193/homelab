"""The Supabase keepalive roster, driven from the cockpit.

A project that is not worth keeping awake - an archived side project, a demo
whose free tier can lapse - should not make the weekly run look like it failed.
This module is the cockpit's side of that switch: it reads the roster, and it
pauses and resumes one project at a time.

`keepalive.py` stays the only thing that knows what a project is. This module
shells out to it rather than re-reading `.env`, so the page cannot drift from
what the timer actually does, and the anon keys never enter this process: the
`list --json` it parses does not carry them.

Nothing here builds a command out of client text. The browser sends a project
ref, which is looked up in this module's own inventory before `pause` or
`resume` is run with it - the same rule claude_rc.py follows.
"""

import json
import os
import subprocess
import sys

from .config import REPO_ROOT
from .pages import load_template

# `or` rather than a get() default: systemd hands the key over with an empty
# value when the .env leaves it blank, and empty means "use the default".
KEEPALIVE_DIR = os.environ.get("STATUS_SUPABASE_DIR") or os.path.join(
    REPO_ROOT, "services", "supabase-keepalive"
)
SCRIPT = os.path.join(KEEPALIVE_DIR, "keepalive.py")
# Listing is local when the projects are listed by hand in .env, but a
# SUPABASE_ACCESS_TOKEN makes it a Management API round trip, so allow for one.
TIMEOUT = float(os.environ.get("STATUS_SUPABASE_TIMEOUT") or "45")


def _run(*argv):
    """Run keepalive.py. Returns (ok, stdout, message)."""
    if not os.path.exists(SCRIPT):
        return False, "", f"keepalive.py not found at {SCRIPT}"
    try:
        done = subprocess.run(
            [sys.executable, SCRIPT, *argv],
            cwd=KEEPALIVE_DIR, capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"keepalive.py {' '.join(argv)} timed out after {TIMEOUT:.0f}s"
    except OSError as err:
        return False, "", str(err)
    if done.returncode != 0:
        # `list` exits non-zero when nothing is configured, which is a real
        # answer rather than a crash, so hand the stderr back either way.
        return False, done.stdout, (done.stderr or done.stdout).strip()
    return True, done.stdout, ""


def roster():
    """Every configured project, each flagged paused or not."""
    ok, out, message = _run("list", "--json")
    if not ok and not out:
        return {"ok": False, "projects": [], "problems": [], "message": message}
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return {"ok": False, "projects": [], "problems": [],
                "message": message or "keepalive.py list --json returned nothing usable"}
    payload.setdefault("projects", [])
    payload.setdefault("problems", [])
    payload["ok"] = True
    return payload


def known(ref):
    return any(p.get("ref") == ref for p in roster().get("projects", []))


def set_paused(ref, paused):
    """Pause or resume one project, by the ref the page was rendered with."""
    ref = (ref or "").strip()
    if not known(ref):
        # Covers both a stale page and anything the browser made up.
        return {"ok": False, "message": f"no configured project with ref {ref!r}"}
    ok, out, message = _run("pause" if paused else "resume", ref)
    if not ok:
        return {"ok": False, "message": message}
    return {"ok": True, "ref": ref, "paused": paused, "message": out.strip()}


SUPABASE_PAGE = load_template("supabase.html")
