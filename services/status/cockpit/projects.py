"""The /projects list: a hand-kept list of live projects, each with a status.

The list lives in projects.json (name, LAN link, optional public link) and is
edited from the page. A project whose `service` (or, failing that, whose name)
matches a cockpit service takes that service's state; any other project is
probed over HTTP on its own link.
"""

import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

from .config import HERE, REPO_ROOT, UNKNOWN
from .probes import check_http
from .snapshot import snapshot

PROJECTS_PATH = os.environ.get("STATUS_PROJECTS", os.path.join(HERE, "projects.json"))
MAX_PROJECTS = 100
MAX_NAME = 60
MAX_URL = 500

_lock = threading.Lock()


def load():
    try:
        with open(PROJECTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    return [p for p in data if isinstance(p, dict)] if isinstance(data, list) else []


def _url_ok(url):
    # Rendered as a link on the page, so only web addresses and cockpit paths:
    # never `javascript:` or other schemes.
    return url.startswith(("http://", "https://")) or (url.startswith("/") and not url.startswith("//"))


def validate(items):
    """Clean a list sent by the page. Returns (projects, error)."""
    if not isinstance(items, list):
        return None, "expected a list of projects"
    if len(items) > MAX_PROJECTS:
        return None, "at most %d projects" % MAX_PROJECTS
    clean, seen = [], set()
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            return None, "row %d is not a project" % i
        name = str(item.get("name", "")).strip()
        link = str(item.get("link", "")).strip()
        remote = str(item.get("remote", "")).strip()
        service = str(item.get("service", "")).strip()
        if not name:
            return None, "row %d needs a name" % i
        if len(name) > MAX_NAME:
            return None, "%s: name is longer than %d characters" % (name, MAX_NAME)
        if name.lower() in seen:
            return None, "%s is listed twice" % name
        seen.add(name.lower())
        if not link and not remote:
            return None, "%s needs a link" % name
        for url in (link, remote):
            if url and (len(url) > MAX_URL or not _url_ok(url)):
                return None, "%s: links must start with http://, https:// or /" % name
        project = {"name": name, "link": link, "remote": remote}
        if service:
            project["service"] = service[:MAX_NAME]
        clean.append(project)
    return clean, None


def save(items):
    """Validate, write projects.json and commit it. Returns an API result."""
    clean, error = validate(items)
    if error:
        return {"ok": False, "message": error}
    with _lock:
        tmp = PROJECTS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2)
            f.write("\n")
        os.replace(tmp, PROJECTS_PATH)
        _commit()
    return {"ok": True, "projects": clean}


def _commit():
    # Commit only this file, so whatever else is staged in the repo stays put.
    try:
        subprocess.run(["git", "add", PROJECTS_PATH], cwd=REPO_ROOT, check=False,
                       capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "chore(status): update projects list",
                        "--", PROJECTS_PATH], cwd=REPO_ROOT, check=False,
                       capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _probe(project):
    url = project["link"] if project["link"].startswith("http") else project["remote"]
    if not url.startswith("http"):
        return UNKNOWN
    return check_http({"url": url})["state"]


def rows(items=None, payload=None):
    """Each project with its state, in list order."""
    items = load() if items is None else items
    payload = payload or snapshot()
    known = {s["name"].lower(): s["state"] for g in payload["groups"] for s in g["services"]}
    states = {}

    def key(p):
        return (p.get("service") or p["name"]).lower()

    unknown = [p for p in items if key(p) not in known]
    if unknown:
        with ThreadPoolExecutor(max_workers=min(len(unknown), 16)) as pool:
            states = dict(zip((p["name"] for p in unknown), pool.map(_probe, unknown)))
    return [
        {**p, "state": known.get(key(p)) or states.get(p["name"], UNKNOWN)}
        for p in items
    ]
