"""The /projects list: a hand-kept list of live projects, each with a status.

The list lives in projects.json (name, LAN link, optional public link,
optional GitHub repo) and is edited from the page. A project whose `service`
(or, failing that, whose name) matches a cockpit service takes that service's
state; any other project is probed over HTTP on its own link. Projects with a
GitHub repo also get their open PR and issue counts, read with `gh` in one
GraphQL call - only when asked for, which the page does once per load.
"""

import json
import os
import re
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
GITHUB_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")

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
        github = str(item.get("github", "")).strip()
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
        if github:
            m = GITHUB_RE.match(github)
            if not m:
                return None, "%s: GitHub link must look like https://github.com/owner/repo" % name
            github = "https://github.com/%s/%s" % m.groups()
        project = {"name": name, "link": link, "remote": remote}
        if service:
            project["service"] = service[:MAX_NAME]
        if github:
            project["github"] = github
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


def _gh_query(repos):
    """Open PR and issue counts and visibility for each (owner, name), in one GraphQL call."""
    parts = ['r%d: repository(owner: %s, name: %s) '
             '{ isPrivate pullRequests(states: OPEN) { totalCount } issues(states: OPEN) { totalCount } }'
             % (i, json.dumps(o), json.dumps(n)) for i, (o, n) in enumerate(repos)]
    try:
        out = subprocess.run(["gh", "api", "graphql", "-f", "query={ %s }" % " ".join(parts)],
                             capture_output=True, text=True, timeout=15)
        # A missing repo still answers with data for the others, but exits non-zero.
        data = json.loads(out.stdout or "{}").get("data") or {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    counts = {}
    for i, repo in enumerate(repos):
        node = data.get("r%d" % i)
        if node:
            counts[repo] = {"prs": node["pullRequests"]["totalCount"],
                            "issues": node["issues"]["totalCount"],
                            "private": bool(node.get("isPrivate"))}
    return counts


def github_counts(items):
    """{github url: {"prs": n, "issues": n, "private": bool}}; repos gh could not read are left out."""
    repos = tuple(sorted({GITHUB_RE.match(p["github"]).groups()
                          for p in items if GITHUB_RE.match(p.get("github", ""))}))
    if not repos:
        return {}
    return {"https://github.com/%s/%s" % r: c for r, c in _gh_query(repos).items()}


def rows(items=None, payload=None, github=False):
    """Each project with its state, in list order; with github=True also its counts."""
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
    gh = github_counts(items) if github else {}
    out = []
    for p in items:
        row = {**p, "state": known.get(key(p)) or states.get(p["name"], UNKNOWN)}
        if p.get("github") in gh:
            row.update(gh[p["github"]])
        out.append(row)
    return out
