#!/usr/bin/env python3
"""Plan (and, eventually, apply) the move of the Obsidian "Project ideas"
vault into a Kandev "Ideas" workspace.

Reuses the parsers in services/status/ideas_manager.py: nothing here
re-implements vault parsing. This module only maps parsed ideas onto Kandev
tasks and prints or (later) applies the resulting plan.
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVICES_STATUS_DIR = os.path.abspath(
    os.path.join(_THIS_DIR, "..", "services", "status")
)
sys.path.insert(0, _SERVICES_STATUS_DIR)

import ideas_manager  # noqa: E402

MONEY_FILE = "Money making.md"
FOSS_FILE = "FOSS projects.md"
REJECTED_FILE = ideas_manager.REJECTED_FILE

COLUMN_FOR_STATUS = {
    "untagged": "Untagged",
    "next": "Next",
    "ongoing": "Ongoing",
    "shelved": "Shelved",
    "rejected": "Rejected",
}
COLUMNS_ORDER = ("Untagged", "Next", "Ongoing", "Shelved", "Rejected")

# Dossier headers carry a dated status marker, e.g. "`[REJECTED 2026-09-26]`",
# which ideas_manager.STATUS_MARKER_RE (built for undated card markers) does
# not strip. Pull it off the title before reusing clean_display_title.
_DOSSIER_STATUS_MARKER_RE = re.compile(
    r"\s*`?\[(?:ONGOING|SHELVED(?: ON CAPITAL)?|REJECTED|PARKED)[^\]]*\]`?\s*$",
    re.IGNORECASE,
)

WORKSPACE_NAME = "Ideas"
DEFAULT_KANDEV_URL = "http://localhost:3040"


class KandevAPIError(Exception):
    """Raised when the Kandev API rejects a request (401) or is unreachable.

    main() turns this into a one-line message and a non-zero exit instead of
    a traceback.
    """


class KandevClient:
    """Minimal stdlib-only client for the Kandev REST API.

    `opener` defaults to urllib.request.urlopen but can be swapped for a
    fake transport in tests, so nothing here ever touches a real socket
    unless a real urlopen is passed in.
    """

    def __init__(self, base_url=None, token=None, opener=None):
        self.base_url = (
            base_url or os.environ.get("KANDEV_URL") or DEFAULT_KANDEV_URL
        ).rstrip("/")
        self.token = (
            token if token is not None else os.environ.get("KANDEV_TOKEN")
        )
        self._opener = opener or urllib.request.urlopen

    def _get(self, path, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self._opener(req, timeout=10) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 401:
                raise KandevAPIError(
                    f"Kandev API rejected the token (401) for GET {path}"
                ) from exc
            detail = exc.read().decode("utf-8", "replace") if hasattr(exc, "read") else ""
            raise KandevAPIError(
                f"Kandev API error {exc.code} for GET {path}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise KandevAPIError(
                f"Kandev API unreachable at {self.base_url}: {exc.reason}"
            ) from exc
        return json.loads(raw.decode("utf-8")) if raw else None

    def list_workspaces(self):
        body = self._get("/api/v1/workspaces")
        return (body or {}).get("workspaces", [])

    def list_workflows(self, workspace_id):
        body = self._get(f"/api/v1/workspaces/{workspace_id}/workflows")
        return (body or {}).get("workflows", [])

    def list_steps(self, workflow_id):
        body = self._get(f"/api/v1/workflows/{workflow_id}/workflow/steps")
        return (body or {}).get("steps", [])

    def get_task_by_external_id(self, workspace_id, ext_id):
        """Returns the task dict, or None when no task holds this id (404)."""
        return self._get(
            f"/api/v1/workspaces/{workspace_id}/tasks/by-external-id",
            params={"external_id": ext_id},
        )


def resolve_dry_run_status(client, items):
    """Read-only: mark each item 'exists' or 'create' against the live
    Kandev workspace. Issues only GET requests. If the Ideas workspace (or
    its workflow) is not there yet, every item is left as 'create'.
    """
    workspace = next(
        (w for w in client.list_workspaces() if w.get("name") == WORKSPACE_NAME),
        None,
    )
    if workspace is None:
        return

    # Resolved for parity with the apply step (S4), which needs the
    # workflow id too; absence here does not change item status.
    client.list_workflows(workspace["id"])

    for item in items:
        existing = client.get_task_by_external_id(workspace["id"], item["external_id"])
        item["status"] = "exists" if existing is not None else "create"


def load_sources(vault):
    """Read the 3 fixed vault files. Exits non-zero when one is missing."""
    missing = [
        f for f in (MONEY_FILE, FOSS_FILE, REJECTED_FILE)
        if not os.path.isfile(os.path.join(vault, f))
    ]
    if missing:
        sys.stderr.write(
            "Missing vault file(s): " + ", ".join(missing) + "\n"
        )
        sys.exit(1)

    return {
        "money": ideas_manager.parse_active_file(vault, MONEY_FILE),
        "foss": ideas_manager.parse_active_file(vault, FOSS_FILE),
        "rejected": ideas_manager.parse_rejected_file(vault, REJECTED_FILE),
        "reinstated_skipped": _count_reinstated(vault),
    }


def _count_reinstated(vault):
    fpath = os.path.join(vault, REJECTED_FILE)
    if not os.path.isfile(fpath):
        return 0
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    count = 0
    for _header, start, end in ideas_manager.dossier_sections(content):
        tags = ideas_manager.extract_labels(content[start:end])
        if ideas_manager.TAG_REINSTATED in tags:
            count += 1
    return count


def _dossier_title(idea):
    raw = idea["raw_title"]
    header = raw[4:] if raw.startswith("### ") else idea["title"]
    header = _DOSSIER_STATUS_MARKER_RE.sub("", header)
    return ideas_manager.clean_display_title(header)


def _description(file_rel, idea, today):
    header = (
        f"> Migrated from Obsidian `Project ideas/{file_rel}` › "
        f"{idea['category']} (line {idea['line_number']}) on {today}. "
        f"Original line:\n"
        f"> `{idea['raw_title']}`"
    )
    notes = idea["notes"]
    if notes:
        return f"{header}\n\n{notes}"
    return header


def _build_item(file_rel, idea, today, add_foss_label=False):
    title = _dossier_title(idea) if idea["is_dossier"] else idea["title"]

    labels = list(idea["tags"])
    if add_foss_label and "foss" not in labels:
        labels.append("foss")

    return {
        "source": file_rel,
        "column": COLUMN_FOR_STATUS[idea["status"]],
        "title": title,
        "labels": labels,
        "external_id": f"obsidian-ideas:{idea['id']}",
        "description": _description(file_rel, idea, today),
        "line": idea["line_number"],
    }


def check_duplicate_external_ids(items):
    """Abort before any write if two items share an external_id."""
    seen = {}
    for item in items:
        ext_id = item["external_id"]
        if ext_id in seen:
            sys.stderr.write(
                f"Duplicate external_id {ext_id}: "
                f"{seen[ext_id]} and {item['source']}:{item['line']}\n"
            )
            sys.exit(1)
        seen[ext_id] = f"{item['source']}:{item['line']}"


def build_plan(vault, today):
    """Return the list of planned items, in vault order."""
    sources = load_sources(vault)

    items = []
    for idea in sources["money"]:
        items.append(_build_item(MONEY_FILE, idea, today))
    for idea in sources["foss"]:
        items.append(_build_item(FOSS_FILE, idea, today, add_foss_label=True))
    for idea in sources["rejected"]:
        items.append(_build_item(REJECTED_FILE, idea, today))

    check_duplicate_external_ids(items)

    for item in items:
        item["status"] = "create"

    return items


def summary_line(items):
    counts = Counter(item["source"] for item in items)
    return (
        f"{MONEY_FILE}: {counts.get(MONEY_FILE, 0)} cards · "
        f"{FOSS_FILE}: {counts.get(FOSS_FILE, 0)} cards · "
        f"{REJECTED_FILE}: {counts.get(REJECTED_FILE, 0)} dossiers · "
        f"total {len(items)}"
    )


def print_report(items, reinstated_skipped):
    counts_by_column = Counter(item["column"] for item in items)

    if reinstated_skipped:
        print(f"Skipped {reinstated_skipped} dossier(s) tagged #reinstated")

    for column in COLUMNS_ORDER:
        print(f"{column}: {counts_by_column.get(column, 0)}")
    print()

    for item in items:
        print(
            f"[{item['column']}] {item['title']} | "
            f"labels={','.join(item['labels'])} | "
            f"external_id={item['external_id']} | "
            f"status={item['status']} | "
            f"description={len(item['description'])} chars"
        )
    print()
    print(summary_line(items))

    status_counts = Counter(item["status"] for item in items)
    print(
        f"create: {status_counts.get('create', 0)} · "
        f"exists: {status_counts.get('exists', 0)}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Plan (and, eventually, apply) the Obsidian Project "
                     "ideas -> Kandev Ideas workspace migration."
    )
    parser.add_argument("--vault", default=ideas_manager.DEFAULT_DIR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--archive-vault", action="store_true")
    args = parser.parse_args(argv)

    if args.apply:
        sys.stderr.write("--apply is not implemented yet\n")
        sys.exit(1)
    if args.archive_vault:
        sys.stderr.write("--archive-vault is not implemented yet\n")
        sys.exit(1)

    today = datetime.date.today().isoformat()

    reinstated_skipped = load_sources(args.vault)["reinstated_skipped"]
    items = build_plan(args.vault, today)

    if os.environ.get("KANDEV_TOKEN"):
        try:
            resolve_dry_run_status(KandevClient(), items)
        except KandevAPIError as exc:
            sys.stderr.write(f"{exc}\n")
            sys.exit(1)

    if args.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
    else:
        print_report(items, reinstated_skipped)

    return 0


if __name__ == "__main__":
    sys.exit(main())
