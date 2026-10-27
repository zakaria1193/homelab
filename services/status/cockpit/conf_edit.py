"""The one module that writes `services.conf`.

Every edit takes a module-level lock, reads the file fresh, validates the
change, writes a temp file in the same directory, re-parses *that* with
`load_checks()` before replacing the real file, and only then commits and
invalidates the snapshot cache. A value or parse problem refuses the edit
before the real file is touched, so a bad write can never reach it.
"""

import os
import subprocess
import tempfile
import threading

from .config import REPO_ROOT, load_checks

_LOCK = threading.Lock()


def _invalidate():
    # Imported lazily: claude_rc/antigravity_rc import this module, and
    # snapshot imports them back to build the workspaces list, so a top-level
    # import here would be circular.
    from .snapshot import invalidate
    invalidate()


def _escape(value):
    """`%` must survive ConfigParser's interpolation on the next read."""
    return (value or "").replace("%", "%%")


def _bad_value(value):
    if any(c in (value or "") for c in "\r\n"):
        return "values must be a single line"
    return ""


def _bad_name(name):
    if not name or any(c in name for c in "[]\r\n"):
        return "section name must be non-empty and contain no '[', ']', CR or LF"
    return ""


def _commit(path, message, repo_root):
    """Commit `path` alone: the pathspec keeps whatever else is staged in the
    repo out of this commit."""
    try:
        subprocess.run(["git", "add", "--", path], cwd=repo_root, check=False, timeout=30)
        subprocess.run(["git", "commit", "-m", message, "--", path], cwd=repo_root, check=False,
                       timeout=30)
    except Exception:
        pass


def _write_checked(path, new_text):
    """Write `new_text` to a temp file next to `path`, re-parse it, and only
    then replace `path`. Returns (ok, message); on failure the temp file is
    gone and `path` is untouched."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        mode = None

    directory = os.path.dirname(path) or "."
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".services.conf.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_text)
        if mode is not None:
            os.chmod(temp_path, mode)
        try:
            load_checks(path=temp_path)
        except Exception as exc:
            return False, "the edit would break services.conf: %s" % exc
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return True, ""


def add_section(path, name, fields, comment_lines=(), commit_message=None, repo_root=None):
    """Append a new section. `fields` is an ordered iterable of (key, value)
    pairs; each value is escaped and must be a single line. `comment_lines`
    are whole lines (e.g. starting with "#") placed directly above the
    section. Returns {"ok": bool, "message": str}."""
    problem = _bad_name(name)
    if problem:
        return {"ok": False, "message": problem}
    for key, value in fields:
        problem = _bad_value(value)
        if problem:
            return {"ok": False, "message": "%s: %s" % (key, problem)}

    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            return {"ok": False, "message": "services.conf not found or unreadable"}

        if ("[%s]" % name) in text:
            return {"ok": False, "message": "section [%s] already exists" % name}

        block_lines = [line.rstrip("\n") + "\n" for line in comment_lines]
        block_lines.append("[%s]\n" % name)
        block_lines.extend("%s = %s\n" % (key, _escape(value)) for key, value in fields)
        new_text = text + "\n" + "".join(block_lines)

        ok, message = _write_checked(path, new_text)
        if not ok:
            return {"ok": False, "message": message}

        if commit_message:
            _commit(path, commit_message, repo_root or REPO_ROOT)
        _invalidate()
        return {"ok": True, "message": ""}


def remove_section(path, name, commit_message=None, repo_root=None):
    """Remove section `name` and the comment lines directly above it, leaving
    exactly one blank line between the sections around it and none at the end
    of the file. Returns {"ok": bool, "message": str}."""
    problem = _bad_name(name)
    if problem:
        return {"ok": False, "message": problem}
    header = "[%s]" % name

    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.read().splitlines(keepends=True)
        except OSError:
            return {"ok": False, "message": "services.conf not found or unreadable"}

        try:
            start = next(i for i, line in enumerate(lines) if line.strip() == header)
        except StopIteration:
            return {"ok": False, "message": "section [%s] not found" % name}

        # Comments directly above a section belong to it; a blank line ends that.
        head = start
        while head > 0 and lines[head - 1].lstrip().startswith("#"):
            head -= 1
        end = start + 1
        while end < len(lines) and not lines[end].lstrip().startswith("["):
            end += 1
        # Leave exactly one blank line where the section was.
        while end > start and lines[end - 1].strip() == "":
            end -= 1
        while head > 0 and lines[head - 1].strip() == "":
            head -= 1

        tail = lines[end:]
        while tail and not tail[0].strip():
            tail.pop(0)
        new_text = "".join(lines[:head] + (["\n"] if tail else []) + tail)

        ok, message = _write_checked(path, new_text)
        if not ok:
            return {"ok": False, "message": message}

        if commit_message:
            _commit(path, commit_message, repo_root or REPO_ROOT)
        _invalidate()
        return {"ok": True, "message": ""}
