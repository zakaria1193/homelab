#!/usr/bin/env python3
"""Keep free-tier Supabase projects from being paused for inactivity.

Supabase pauses a free project after roughly a week without activity, so this
pings every project once a week from the homelab. Projects are discovered
through the Management API with a personal access token, and any project that
token cannot see can be listed by hand in `.env`.

Only the standard library is used, so `make install` has nothing to install.

    keepalive.py ping                 ping every project now
    keepalive.py ping --if-stale      ping only if the last success is old
    keepalive.py status               what is configured and when it last ran
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
ENV_FILE = HERE / ".env"
STATE_FILE = HERE / "state.json"
LOG_FILE = HERE / "keepalive.log"
NOTIFY = REPO_ROOT / "tools" / "slackbot-notify.sh"

MANAGEMENT_API = "https://api.supabase.com/v1"
# What `.env.example` ships as the token. A copied placeholder is not a token,
# and saying so beats a weekly 401 nobody can read.
PLACEHOLDER_PREFIX = "sbp_xxx"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_AGE_DAYS = 7

# The cockpit card watches the log for these two (services/status/services.conf).
OK_LINE = "supabase-keepalive: all projects reached"
FAIL_LINE = "supabase-keepalive: FAILED"


# --------------------------------------------------------------- plumbing

def load_env() -> None:
    """Read `.env` into the environment. systemd passes it too; this is for CLI."""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def now() -> datetime:
    return datetime.now(timezone.utc)


def log(message: str) -> None:
    stamped = f"[{now():%Y-%m-%d %H:%M:%S%z}] {message}"
    print(stamped, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(stamped + "\n")
    except OSError as err:  # a log we cannot write must not fail the ping
        print(f"[warn] could not write {LOG_FILE}: {err}", file=sys.stderr, flush=True)


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def notify_slack(title: str, status: str, message: str) -> None:
    """Homelab standard: a maintenance job reports to Slack (AGENTS.md §7)."""
    if not NOTIFY.exists():
        return
    try:
        subprocess.run(
            [str(NOTIFY), "--title", title, "--status", status, message],
            check=False, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as err:
        log(f"[warn] Slack notification failed: {err}")


# ------------------------------------------------------------ the projects

class Project:
    def __init__(self, name: str, url: str, key: str, table: str = "", ref: str = ""):
        self.name = name
        self.url = url.rstrip("/")
        self.key = key
        self.table = table
        self.ref = ref or self.url.split("//", 1)[-1].split(".", 1)[0]

    def __repr__(self) -> str:
        return f"<Project {self.name} {self.url}>"


def api_get(path: str, token: str) -> object:
    request = urllib.request.Request(
        f"{MANAGEMENT_API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def discover(token: str, table: str) -> tuple[list[Project], list[str]]:
    """Every project the token can see, with its anon key.

    A paused project is returned as a problem rather than as something to ping:
    a request does not wake it, only a restore does, and that is the operator's
    call, not a weekly job's.
    """
    projects: list[Project] = []
    problems: list[str] = []

    try:
        listing = api_get("/projects", token)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as err:
        problems.append(f"management API unreachable: {err}")
        return projects, problems

    for entry in listing if isinstance(listing, list) else []:
        ref, name = entry.get("id", ""), entry.get("name", "?")
        status = (entry.get("status") or "").upper()
        if not ref:
            continue
        if status in {"INACTIVE", "PAUSED", "PAUSING", "GOING_DOWN"}:
            problems.append(f"{name} ({ref}) is {status} — restore it in the dashboard")
            continue
        if status not in {"ACTIVE_HEALTHY", "COMING_UP", "ACTIVE_UNHEALTHY", ""}:
            problems.append(f"{name} ({ref}) is {status}")
            continue

        try:
            keys = api_get(f"/projects/{ref}/api-keys?reveal=true", token)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as err:
            problems.append(f"{name} ({ref}): could not read its anon key: {err}")
            continue

        anon = next((k.get("api_key") for k in keys if k.get("name") == "anon"), None) \
            if isinstance(keys, list) else None
        if not anon:
            problems.append(f"{name} ({ref}): no anon key returned")
            continue

        projects.append(Project(name, f"https://{ref}.supabase.co", anon, table, ref))

    return projects, problems


def from_env(table: str) -> list[Project]:
    """Projects written out by hand: `name|url|anon_key[|table]`, one per line."""
    raw = os.environ.get("SUPABASE_PROJECTS", "").strip()
    projects: list[Project] = []
    for chunk in raw.replace(";", "\n").splitlines():
        entry = chunk.strip()
        if not entry or entry.startswith("#"):
            continue
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) < 3:
            log(f"[warn] ignoring malformed SUPABASE_PROJECTS entry: {entry}")
            continue
        projects.append(Project(parts[0], parts[1], parts[2],
                                parts[3] if len(parts) > 3 else table))
    return projects


def ping(project: Project) -> tuple[bool, str]:
    """One request at the project's REST API, which is what the database sees.

    A table makes it an unmistakable query. Without one the PostgREST root is
    still a request to the project, which is what inactivity is measured on.
    """
    path = (f"/rest/v1/{project.table}?select=*&limit=1" if project.table else "/rest/v1/")
    request = urllib.request.Request(
        project.url + path,
        headers={"apikey": project.key, "Authorization": f"Bearer {project.key}",
                 "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as err:
        # 4xx means the project answered — row-level security refusing an anon
        # read is still the database being asked a question. 5xx is not.
        if err.code < 500:
            return True, f"HTTP {err.code} (reached)"
        return False, f"HTTP {err.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        return False, str(err)


# -------------------------------------------------------------- the commands

def access_token() -> str:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    return "" if token.startswith(PLACEHOLDER_PREFIX) else token


def collect(table: str) -> tuple[list[Project], list[str]]:
    projects, problems = [], []
    token = access_token()
    if token:
        projects, problems = discover(token, table)
    manual = from_env(table)
    known = {p.url for p in projects}
    projects.extend(p for p in manual if p.url not in known)
    return projects, problems


def command_ping(args: argparse.Namespace) -> int:
    table = os.environ.get("SUPABASE_KEEPALIVE_TABLE", "").strip()
    state = read_state()

    if args.if_stale:
        last = parse_time(state.get("last_ok_run"))
        if last and now() - last < timedelta(days=args.max_age_days):
            age = (now() - last).days
            log(f"last successful ping was {age}d ago (< {args.max_age_days}d) — nothing to do")
            return 0
        log("no successful ping inside the window — pinging now")

    projects, problems = collect(table)
    if not projects and not problems:
        log("[error] no projects configured — set SUPABASE_ACCESS_TOKEN or SUPABASE_PROJECTS in .env")
        log(FAIL_LINE)
        return 2

    per_project = state.setdefault("projects", {})
    failures = list(problems)
    for project in projects:
        ok, detail = ping(project)
        log(f"{'[ok]   ' if ok else '[fail] '}{project.name} ({project.ref}): {detail}")
        record = per_project.setdefault(project.ref, {})
        record["name"] = project.name
        record["last_attempt"] = now().isoformat()
        record["last_detail"] = detail
        if ok:
            record["last_ok"] = now().isoformat()
        else:
            failures.append(f"{project.name} ({project.ref}): {detail}")

    state["last_run"] = now().isoformat()
    if projects and not failures:
        state["last_ok_run"] = now().isoformat()
    write_state(state)

    if failures:
        for problem in problems:
            log(f"[fail] {problem}")
        log(f"{FAIL_LINE}: {len(failures)} of {len(projects) + len(problems)} not reached")
        if args.notify != "never":
            notify_slack("Supabase keepalive", "error",
                         "Projects not reached this week:\n• " + "\n• ".join(failures))
        return 1

    log(f"{OK_LINE} ({len(projects)})")
    if args.notify == "always":
        notify_slack("Supabase keepalive", "ok",
                     f"{len(projects)} Supabase projects pinged: "
                     + ", ".join(p.name for p in projects))
    return 0


def command_status(_args: argparse.Namespace) -> int:
    state = read_state()
    last = parse_time(state.get("last_ok_run"))
    if last:
        age = now() - last
        stale = age > timedelta(days=DEFAULT_MAX_AGE_DAYS)
        print(f"last successful run : {last:%Y-%m-%d %H:%M %Z} "
              f"({age.days}d {age.seconds // 3600}h ago){'  [STALE]' if stale else ''}")
    else:
        print("last successful run : never")

    for ref, record in sorted(state.get("projects", {}).items()):
        ok = parse_time(record.get("last_ok"))
        when = f"{ok:%Y-%m-%d %H:%M}" if ok else "never"
        print(f"  {record.get('name', ref):<28} {ref:<22} last ok {when}"
              f"   ({record.get('last_detail', '-')})")

    print()
    raw = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    token = "set" if access_token() else ("still the .env.example placeholder" if raw else "not set")
    manual = len(from_env(""))
    print(f"SUPABASE_ACCESS_TOKEN: {token}   manual projects: {manual}")
    return 0 if last and now() - last <= timedelta(days=DEFAULT_MAX_AGE_DAYS) else 1


def command_list(_args: argparse.Namespace) -> int:
    projects, problems = collect(os.environ.get("SUPABASE_KEEPALIVE_TABLE", "").strip())
    for project in projects:
        print(f"{project.name:<28} {project.url}")
    for problem in problems:
        print(f"[!] {problem}")
    return 0 if projects else 1


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    ping_parser = sub.add_parser("ping", help="ping every configured project")
    ping_parser.add_argument("--if-stale", action="store_true",
                             help="only ping when the last success is older than the window")
    ping_parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                             help="how old the last success may be (default: 7)")
    ping_parser.add_argument("--notify", choices=("never", "error", "always"),
                             default=os.environ.get("SUPABASE_KEEPALIVE_NOTIFY", "error"),
                             help="when to post to Slack (default: error)")
    ping_parser.set_defaults(func=command_ping)

    sub.add_parser("status", help="when it last ran, and per project").set_defaults(func=command_status)
    sub.add_parser("list", help="the projects that would be pinged").set_defaults(func=command_list)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
