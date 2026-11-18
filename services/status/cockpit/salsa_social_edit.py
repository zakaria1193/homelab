"""Edits one existing salsa-social community (homelab-0024, plan item 2),
against the local git clone `communities.SALSA_SOCIAL_DIR`, following
`cockpit/conf_edit.py`'s lock-validate-write-commit shape but against a git
clone with a remote instead of a bare config file:

1. take the module lock, so only one save runs at a time;
2. refuse before touching anything if the clone is missing, not on `main`,
   dirty in the file this edit touches, or `git pull --ff-only` fails;
3. refuse before touching anything on an unknown field, an out-of-range
   status/ingestion/feature value, a bad name, or a request that, once
   compared against the file `git pull` just gave us, changes nothing;
4. refuse if the values Zak's page saw ("expected_old") no longer match the
   file - someone else pushed since he loaded the page;
5. rewrite only the changed literal values in
   `src/server/communities/<slug>.ts`, run salsa-social's checks, and on any
   failure restore the file and report why - nothing is pushed;
6. on success, commit only that file with a message naming each
   `field: old -> new` and push to `origin main`; if the push is refused,
   drop the local commit and restore the file, and report why.

Every attempt (good or refused) gets one line in `salsa_social_edit.log`.
"""

import os
import re
import subprocess
import threading
import time

from .communities import FEATURE_KEYS, SALSA_SOCIAL_DIR, _communities_dir, _features_field, _string_field

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "salsa_social_edit.log")
LOG_MAX_LINES = 500

ALLOWED_STATUS = ("live", "hidden")
ALLOWED_INGESTION = ("faurax", "manual")
STRING_FIELDS = ("name", "status", "ingestion")
ALLOWED_FIELDS = STRING_FIELDS + FEATURE_KEYS
CHECK_TIMEOUT = float(os.environ.get("STATUS_SALSA_SOCIAL_CHECK_TIMEOUT") or "300")
GIT_TIMEOUT = float(os.environ.get("STATUS_SALSA_SOCIAL_GIT_TIMEOUT") or "30")

_LOCK = threading.Lock()


def append_log(line, path=None, max_lines=LOG_MAX_LINES):
    path = path or LOG_PATH
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = "%s %s" % (stamp, line)
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    lines.append(entry)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines[-max_lines:]) + "\n")


def _community_path(salsa_dir, slug):
    return os.path.join(_communities_dir(salsa_dir), slug + ".ts")


def _escape_ts_string(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _validate_changes(changes):
    """Everything that can be checked with no file or git access. Returns an
    error message, or "" if `changes` is well-formed."""
    if not isinstance(changes, dict) or not changes:
        return "no changes given"
    unknown = sorted(set(changes) - set(ALLOWED_FIELDS))
    if unknown:
        return "unknown field(s): %s" % ", ".join(unknown)

    if "name" in changes:
        name = changes["name"]
        if not isinstance(name, str) or not name:
            return "name must be a non-empty string"
        if len(name) > 80:
            return "name must be at most 80 characters"
        if "\n" in name or "\r" in name:
            return "name must be a single line"

    if "status" in changes and changes["status"] not in ALLOWED_STATUS:
        return "status must be one of: %s" % ", ".join(ALLOWED_STATUS)

    if "ingestion" in changes and changes["ingestion"] not in ALLOWED_INGESTION:
        return "ingestion must be one of: %s" % ", ".join(ALLOWED_INGESTION)

    for key in FEATURE_KEYS:
        if key in changes and not isinstance(changes[key], bool):
            return "%s must be true or false" % key

    return ""


def _parse_current(text):
    """The same flat shape as `changes`/`expected_old`: name/status/ingestion
    plus one key per feature flag."""
    current = {field: _string_field(text, field) for field in STRING_FIELDS}
    current.update(_features_field(text))
    return current


def _replace_string_field(text, name, new_value):
    pattern = r"(%s:\s*')((?:[^'\\]|\\.)*)(')" % re.escape(name)
    new_text, count = re.subn(pattern, lambda m: m.group(1) + _escape_ts_string(new_value) + m.group(3), text,
                               count=1)
    if count != 1:
        raise ValueError("could not find a single `%s` field to rewrite" % name)
    return new_text


def _replace_bool_field(text, name, new_value):
    pattern = r"(%s\s*:\s*)(true|false)" % re.escape(name)
    literal = "true" if new_value else "false"
    new_text, count = re.subn(pattern, lambda m: m.group(1) + literal, text, count=1)
    if count != 1:
        raise ValueError("could not find a single `%s` field to rewrite" % name)
    return new_text


def _apply_diff(text, diff):
    for field, (_old, new_value) in diff.items():
        if field in STRING_FIELDS:
            text = _replace_string_field(text, field, new_value)
        else:
            text = _replace_bool_field(text, field, new_value)
    return text


def _format_diff(diff):
    def fmt(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    return ", ".join("%s: %s -> %s" % (field, fmt(old), fmt(new)) for field, (old, new) in sorted(diff.items()))


def _run_git(args, repo_root, timeout=GIT_TIMEOUT):
    try:
        done = subprocess.run(["git"] + args, cwd=repo_root, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "git %s timed out after %.0fs" % (" ".join(args), timeout)
    except OSError as exc:
        return False, str(exc)
    if done.returncode != 0:
        return False, (done.stderr or done.stdout).strip()
    return True, (done.stdout or "").strip()


def _check_clone(repo_root, file_path):
    """Everything the spec requires before any file is touched. Returns an
    error message, or "" when the clone is ready."""
    if not os.path.isdir(os.path.join(repo_root, ".git")):
        return "no salsa-social clone at %s" % repo_root
    if not os.path.isfile(file_path):
        return "no such community file: %s" % os.path.relpath(file_path, repo_root)

    ok, out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if not ok:
        return "could not read the current branch: %s" % out
    if out != "main":
        return "the clone is on `%s`, not `main`" % out

    ok, out = _run_git(["status", "--porcelain", "--", file_path], repo_root)
    if not ok:
        return "could not check the clone's status: %s" % out
    if out.strip():
        return "the clone has uncommitted changes to %s" % os.path.relpath(file_path, repo_root)

    ok, out = _run_git(["pull", "--ff-only"], repo_root)
    if not ok:
        return "git pull --ff-only failed: %s" % out

    return ""


def default_run_checks(repo_root, timeout=CHECK_TIMEOUT):
    """salsa-social's own checks, run with no build arguments (so
    `check-launch-checklist` only checks the checklist text, never a dist
    directory). Returns (ok, failed_command, output)."""
    commands = [
        ["npx", "astro", "check"],
        ["npm", "test"],
        ["npm", "run", "check-launch-checklist"],
    ]
    for command in commands:
        name = " ".join(command)
        try:
            done = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, name, "%s timed out after %.0fs" % (name, timeout)
        except OSError as exc:
            return False, name, str(exc)
        if done.returncode != 0:
            return False, name, (done.stdout + "\n" + done.stderr).strip()
    return True, "", ""


def edit_community(slug, changes, expected_old, salsa_dir=None, repo_root=None, run_checks=None,
                    timeout=CHECK_TIMEOUT, log_path=None):
    """Edits `slug`'s config file with `changes` (a flat dict: any of
    name/status/ingestion/the six feature keys). `expected_old` carries every
    editable value Zak's page showed him, so a push by someone else - to a
    field he is changing or not - since the page loaded is caught rather than
    overwritten or silently combined with his edit.
    Returns {"ok": bool, "message": str, "commit": str, "diff": {...}}."""
    salsa_dir = salsa_dir or SALSA_SOCIAL_DIR
    repo_root = repo_root or salsa_dir
    run_checks = run_checks or default_run_checks

    problem = _validate_changes(changes)
    if problem:
        append_log("refused %s: %s" % (slug, problem), path=log_path)
        return {"ok": False, "message": problem}

    with _LOCK:
        file_path = _community_path(salsa_dir, slug)
        problem = _check_clone(repo_root, file_path)
        if problem:
            append_log("refused %s: %s" % (slug, problem), path=log_path)
            return {"ok": False, "message": problem}

        with open(file_path, encoding="utf-8") as handle:
            original_text = handle.read()
        current = _parse_current(original_text)

        stale = sorted(
            field for field, old in (expected_old or {}).items()
            if current.get(field) != old
        )
        if stale:
            message = "someone else changed %s on main since this page loaded; reload and try again" % (
                ", ".join(stale)
            )
            append_log("refused %s: %s" % (slug, message), path=log_path)
            return {"ok": False, "message": message}

        diff = {field: (current.get(field), new) for field, new in changes.items() if current.get(field) != new}
        if not diff:
            append_log("refused %s: nothing changed" % slug, path=log_path)
            return {"ok": False, "message": "nothing changed"}

        try:
            new_text = _apply_diff(original_text, diff)
        except ValueError as exc:
            append_log("refused %s: %s" % (slug, exc), path=log_path)
            return {"ok": False, "message": str(exc)}

        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(new_text)

        ok, failed_command, output = run_checks(repo_root, timeout)
        if not ok:
            _run_git(["checkout", "--", file_path], repo_root)
            message = "%s failed:\n%s" % (failed_command, output)
            append_log("refused %s: %s failed" % (slug, failed_command), path=log_path)
            return {"ok": False, "message": message}

        description = _format_diff(diff)
        commit_message = "%s: %s" % (slug, description)
        ok, out = _run_git(["add", "--", file_path], repo_root)
        if ok:
            ok, out = _run_git(["commit", "-m", commit_message, "--", file_path], repo_root)
        if not ok:
            _run_git(["checkout", "--", file_path], repo_root)
            append_log("refused %s: commit failed: %s" % (slug, out), path=log_path)
            return {"ok": False, "message": "commit failed: %s" % out}

        ok, out = _run_git(["push", "origin", "main"], repo_root)
        if not ok:
            _run_git(["reset", "--hard", "HEAD~1"], repo_root)
            append_log("refused %s: push failed: %s" % (slug, out), path=log_path)
            return {"ok": False, "message": "push failed, nothing kept: %s" % out}

        ok, commit_hash = _run_git(["rev-parse", "--short", "HEAD"], repo_root)
        commit_hash = commit_hash if ok else ""
        new_values = dict(current)
        new_values.update(changes)
        append_log("saved %s: %s (%s)" % (slug, description, commit_hash), path=log_path)
        return {"ok": True, "message": "", "commit": commit_hash, "diff": diff, "new_values": new_values}
