"""Obsidian Project Ideas Manager.

Parses, updates, reorders, and inserts project ideas into Obsidian markdown vaults,
matching Obsidian CardBoard and sync.sh rules.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

DEFAULT_DIR = os.path.expanduser("~/Documents/notes_perso/Project ideas")

STATUSES = ("untagged", "next", "ongoing", "shelved", "rejected")
REJECTED_FILE = "rejected/rejected.md"
# Used when no file in the vault declares itself a board backend.
DEFAULT_BACKENDS = ["2 - Money making.md", "3 - FOSS projects.md"]
# Files that live next to the backends but are never boards themselves.
NON_BACKEND_FILES = ("1. notes.md",)
BACKEND_TAG = "myjira/backend"

# An Obsidian tag: '#' at a word start, then a letter. '#1' and 'C#' are not tags.
TAG_RE = re.compile(r"(?<!\S)#([A-Za-z][\w/-]*)")
STATUS_MARKER_RE = re.compile(r"`?\[(?:ONGOING|SHELVED ON CAPITAL|REJECTED|PARKED)\]`?")

# Labels with a meaning of their own on the board and in the CEO's instructions.
TAG_OWNED = "owned"
TAG_CHALLENGED = "rejection_challenged"
TAG_ANSWERED = "rejection_answered"
# A dossier whose ticket went back to an active file. It stays in rejected.md
# for the audit trail but is no longer shown as a card.
TAG_REINSTATED = "reinstated"


def is_state_tag(tag):
    """Tags that place a card on the board (#board/next) rather than describe it."""
    t = tag.lower()
    return t == "board" or t.startswith(("board/", "myjira/", "stage/"))


def extract_labels(text):
    """Classification tags in text, lowercased and de-duplicated, without state tags."""
    out = []
    for t in TAG_RE.findall(text or ""):
        t = t.lower()
        if not is_state_tag(t) and t not in out:
            out.append(t)
    return out


def normalize_tags(tags):
    """Accept a list or a comma/space separated string; return clean labels."""
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = re.split(r"[\s,]+", tags)
    out = []
    for t in tags:
        t = str(t).strip().lstrip("#").lower()
        if t and re.match(r"^[a-z][\w/-]*$", t) and not is_state_tag(t) and t not in out:
            out.append(t)
    return out


def strip_tag_tokens(text, tags):
    """Remove the given #tags from text, leaving everything else as written.

    Works line by line so indentation (which carries nesting) is untouched.
    """
    if not tags:
        return text
    out = []
    for line in text.split("\n"):
        indent = line[:len(line) - len(line.lstrip())]
        rest = line[len(indent):]
        for t in tags:
            rest = re.sub(rf"(?:^|[ \t]+)#{re.escape(t)}(?![\w/-])", "", rest, flags=re.IGNORECASE)
        out.append(indent + rest.strip() if rest.strip() else "")
    return "\n".join(out)


def split_frontmatter(content):
    """Return (frontmatter_text or None, body_text)."""
    lines = content.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, content


def frontmatter_tags(fm):
    """Tags declared in YAML frontmatter, as an inline list or a block list."""
    tags = []
    lines = fm.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^tags\s*:\s*(.*)$", line.strip(), re.IGNORECASE)
        if not m:
            continue
        inline = m.group(1).strip()
        if inline:
            tags.extend(re.split(r"[\s,]+", inline.strip("[]")))
        else:
            for item in lines[i + 1:]:
                im = re.match(r"^\s*-\s*(.+)$", item)
                if not im:
                    break
                tags.append(im.group(1))
    return [t.strip().strip("'\"").lstrip("#").lower() for t in tags if t.strip()]


def is_backend_content(content):
    """True when a note declares itself a board backend (myJira/backend)."""
    fm, body = split_frontmatter(content)
    if fm is not None:
        if re.search(r"(?im)^myjira\s*:\s*['\"]?backend['\"]?\s*$", fm):
            return True
        if BACKEND_TAG in frontmatter_tags(fm):
            return True
    return any(t.lower() == BACKEND_TAG for t in TAG_RE.findall(body))


# ---- Board blueprints ---------------------------------------------------- #
# "simple" boards use the ideas columns (untagged/next/ongoing/...). "pipeline"
# boards run every ticket through model stages, one ticket at a time:
#   raw -> planning -> executing -> review -> human_check -> done
# The stage is a #stage/<name> tag on the ticket line; board_worker.py moves it.
BLUEPRINTS = ("simple", "pipeline")
PIPELINE_STAGES = ("raw", "planning", "executing", "review", "human_check", "done")
ACTIVE_STAGES = ("planning", "executing", "review")
STAGE_TAG_RE = re.compile(r"(?<!\S)#stage/([a-z_-]+)(?![\w/-])", re.IGNORECASE)
TAG_RUN_FAILED = "run_failed"

BOARD_DEFAULTS = {
    "blueprint": "simple",
    "executor": "claude",
    "workspace": "",
    "slack_channel": "",
    "plan_model": "claude-opus-5-5",
    "plan_effort": "high",
    "exec_model": "claude-sonnet-5",
    "exec_effort": "medium",
    "exec_permission_mode": "auto",
    "review_model": "claude-opus-5-5",
    "review_effort": "high",
    "max_review_rounds": "2",
}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
EXEC_PERMISSION_MODES = ("auto", "acceptEdits")


def stage_tag(stage):
    return "#stage/" + stage.replace("_", "-")


def stage_of(line):
    m = STAGE_TAG_RE.search(line or "")
    if not m:
        return None
    st = m.group(1).lower().replace("-", "_")
    return st if st in PIPELINE_STAGES else None


def frontmatter_scalars(fm):
    """Flat 'key: value' pairs of a frontmatter block (lists are skipped)."""
    out = {}
    for line in (fm or "").split("\n"):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$", line)
        if m and m.group(2) and not m.group(2).startswith("["):
            out[m.group(1)] = m.group(2).strip("'\"")
    return out


def board_config_from_content(content):
    fm, _ = split_frontmatter(content)
    cfg = dict(BOARD_DEFAULTS)
    cfg.update({k: v for k, v in frontmatter_scalars(fm).items() if k in BOARD_DEFAULTS})
    if cfg["blueprint"] not in BLUEPRINTS:
        cfg["blueprint"] = "simple"
    return cfg


def get_board_config(board_file):
    base_dir = get_ideas_dir()
    rel = resolve_board_path(base_dir, board_file)
    if not rel or not os.path.isfile(os.path.join(base_dir, rel)):
        return None
    with open(os.path.join(base_dir, rel), "r", encoding="utf-8") as f:
        cfg = board_config_from_content(f.read())
    cfg["file"] = rel
    return cfg


def validate_workspace(path):
    """A pipeline board's repo: an existing git work tree inside $HOME."""
    raw = str(path or "").strip()
    if not raw:
        return {"ok": False, "message": "Enter the project's repository path"}
    full = os.path.realpath(os.path.expanduser(raw))
    home = os.path.realpath(os.path.expanduser("~"))
    if not (full == home or full.startswith(home + os.sep)):
        return {"ok": False, "message": f"{full} is outside your home directory"}
    if not os.path.isdir(full):
        return {"ok": False, "message": f"{full} does not exist or is not a directory"}
    if os.path.realpath(get_ideas_dir()).startswith(full + os.sep) or full == os.path.realpath(get_ideas_dir()):
        return {"ok": False, "message": "The workspace cannot contain the ideas vault"}
    try:
        top = subprocess.run(["git", "-C", full, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        branch = subprocess.run(["git", "-C", full, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "message": f"git failed: {e}"}
    if top.returncode != 0:
        return {"ok": False, "message": f"{full} is not a git repository (execution runs on a branch)"}
    return {"ok": True, "path": top.stdout.strip(), "branch": branch.stdout.strip(),
            "message": f"git repo on branch {branch.stdout.strip()}"}


SLACK_CHANNEL_RE = re.compile(r"^(?:[CG][A-Z0-9]{6,}|#?[a-z0-9][a-z0-9_-]{0,79})$")


def set_board_config(board_file, updates):
    """Validate and write board settings into the note's frontmatter."""
    base_dir = get_ideas_dir()
    rel = resolve_board_path(base_dir, board_file)
    fpath = os.path.join(base_dir, rel) if rel else None
    if not fpath or not os.path.isfile(fpath):
        return {"ok": False, "message": f"Board not found: {board_file}"}

    clean = {}
    for key, val in (updates or {}).items():
        if key not in BOARD_DEFAULTS or val is None:
            continue
        val = str(val).strip()
        if key == "blueprint" and val not in BLUEPRINTS:
            return {"ok": False, "message": f"Unknown blueprint: {val}"}
        if key == "executor":
            import executors
            if val not in executors.EXECUTORS:
                return {"ok": False, "message": f"Unknown executor: {val}"}
        if key.endswith("_effort") and val not in EFFORTS:
            return {"ok": False, "message": f"{key} must be one of {', '.join(EFFORTS)}"}
        if key == "exec_permission_mode" and val not in EXEC_PERMISSION_MODES:
            return {"ok": False, "message": f"exec_permission_mode must be one of {', '.join(EXEC_PERMISSION_MODES)}"}
        if key.endswith("_model") and not re.match(r"^[A-Za-z0-9._\[\]-]{1,80}$", val):
            return {"ok": False, "message": f"Invalid model id: {val}"}
        if key == "max_review_rounds" and not re.match(r"^[0-5]$", val):
            return {"ok": False, "message": "max_review_rounds must be 0-5"}
        if key == "slack_channel" and val and not SLACK_CHANNEL_RE.match(val):
            return {"ok": False, "message": "Slack channel must be a channel id (C0123...) or #name"}
        if key == "workspace" and val:
            chk = validate_workspace(val)
            if not chk["ok"]:
                return chk
            val = chk["path"]
        clean[key] = val

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    blueprint = clean.get("blueprint", board_config_from_content(content)["blueprint"])
    workspace = clean.get("workspace", board_config_from_content(content)["workspace"])
    if blueprint == "pipeline" and not workspace:
        return {"ok": False, "message": "A pipeline board needs a validated workspace (repository path)"}

    fm, body = split_frontmatter(content)
    fm_lines = fm.split("\n") if fm is not None else ["tags:", "  - myJira/backend"]
    for key, val in clean.items():
        line = f"{key}: {val}" if val else None
        for i, l in enumerate(fm_lines):
            if re.match(rf"^{re.escape(key)}\s*:", l):
                if line:
                    fm_lines[i] = line
                else:
                    del fm_lines[i]
                break
        else:
            if line:
                fm_lines.append(line)
    _write_file_atomically(fpath, "---\n" + "\n".join(fm_lines) + "\n---\n" + body)
    trigger_obsidian_sync(reason="board_config")
    cfg = get_board_config(rel)
    return {"ok": True, "message": f"Saved settings for {rel}", "config": cfg}


def set_stage(idea_id, stage, label=None, text=None, add_tags=(), remove_tags=()):
    """Move a pipeline ticket to `stage`, optionally logging an audit bullet."""
    if stage not in PIPELINE_STAGES:
        return {"ok": False, "message": f"Unknown stage: {stage}"}
    idea = _find_idea(idea_id)
    if not idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}
    fpath = os.path.join(get_ideas_dir(), idea["file"])
    lines = _read_lines(fpath)
    span = _locate_bullet(lines, idea)
    if not span:
        return {"ok": False, "message": f"Could not find idea in {idea['file']}"}
    idx, end = span
    m = re.search(r"\s+(?:—|--)\s+", lines[idx])
    head, tail = (lines[idx][:m.start()], lines[idx][m.start():]) if m else (lines[idx], "")
    head = STAGE_TAG_RE.sub("", head).rstrip()
    head = re.sub(r"[ \t]{2,}", " ", head) + " " + stage_tag(stage)
    head = _set_line_labels(head + tail, add=add_tags, remove=remove_tags)
    new_lines = [head] + lines[idx + 1:end]
    if label and text:
        new_lines += _child_bullet(label, text, _child_indent(lines[idx:end]))
    lines[idx:end] = new_lines
    _write_file_atomically(fpath, "\n".join(lines))
    trigger_obsidian_sync(reason="stage_change")
    return {"ok": True, "id": make_idea_id(idea["file"], head.strip()), "stage": stage,
            "message": f"'{idea['title']}' -> {stage}"}


def human_check(idea_id, decision, note=""):
    """The human gate: approve (-> done) or send back for changes (-> executing)."""
    idea = _find_idea(idea_id)
    if not idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}
    if idea.get("status") != "human_check":
        return {"ok": False, "message": "Only tickets waiting for a human check can be approved"}
    if decision == "approve":
        return set_stage(idea_id, "done", "Human check", ("Approved. " + note).strip())
    if decision == "changes":
        if not note.strip():
            return {"ok": False, "message": "Say what needs to change"}
        return set_stage(idea_id, "executing", "Human check", "[changes requested] " + note.strip())
    return {"ok": False, "message": "decision must be 'approve' or 'changes'"}


def retry_ticket(idea_id):
    """Clear #run_failed so the worker picks the ticket up again at its stage."""
    idea = _find_idea(idea_id)
    if not idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}
    return set_stage(idea_id, idea["status"] if idea["status"] in PIPELINE_STAGES else "raw",
                     remove_tags=(TAG_RUN_FAILED,))


# Per-project boards live here, one note per project (e.g. PROJECTS/FARAH ERP.md).
PROJECT_BOARDS_DIR = "PROJECTS"
# Folders under the ideas dir that never hold boards.
SKIP_DIRS = ("rejected",)
MAX_BOARD_DEPTH = 2


def _iter_markdown(base_dir):
    """Relative paths of .md notes under base_dir, top level first, then sub-folders."""
    top, nested = [], []
    for root, dirs, files in os.walk(base_dir):
        rel_root = os.path.relpath(root, base_dir)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (depth == 0 and d in SKIP_DIRS)
                         and depth < MAX_BOARD_DEPTH)
        for fname in sorted(files):
            if fname.endswith(".md") and not fname.startswith("."):
                rel = fname if depth == 0 else os.path.join(rel_root, fname)
                (top if depth == 0 else nested).append(rel.replace(os.sep, "/"))
    return top + nested


def discover_backend_files(base_dir=None):
    """Notes in the ideas folder (or its sub-folders) tagged myJira/backend.

    Paths are relative to the ideas folder: '2 - Money making.md',
    'PROJECTS/FARAH ERP.md'. Top-level boards come first. Falls back to
    DEFAULT_BACKENDS (those that exist) when none is tagged, so a fresh vault
    still has a board.
    """
    if base_dir is None:
        base_dir = get_ideas_dir()
    if not os.path.isdir(base_dir):
        return []

    discovered = []
    for rel in _iter_markdown(base_dir):
        if rel in NON_BACKEND_FILES:
            continue
        try:
            with open(os.path.join(base_dir, rel), "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        if is_backend_content(content):
            discovered.append(rel)

    if discovered:
        return discovered
    return [f for f in DEFAULT_BACKENDS if os.path.isfile(os.path.join(base_dir, f))]


def resolve_board_path(base_dir, target_file):
    """Safe relative path for a board file, or None if it escapes the vault."""
    rel = os.path.normpath(str(target_file or "").replace("\\", "/")).replace(os.sep, "/")
    if (not rel.endswith(".md") or rel.startswith("/") or rel.startswith("..")
            or rel.split("/")[0] in SKIP_DIRS or any(p.startswith(".") for p in rel.split("/"))):
        return None
    full = os.path.realpath(os.path.join(base_dir, rel))
    if not full.startswith(os.path.realpath(base_dir) + os.sep):
        return None
    return rel


def board_name_for(title):
    """File-safe board name for a project title ('FARAH ERP' -> 'FARAH ERP')."""
    name = re.sub(r'[\\/:*?"<>|#^\[\]`]', " ", str(title or ""))
    return re.sub(r"\s+", " ", name).strip(" .")


def _add_backend_tag(content):
    """Tag an existing note as a board, keeping its frontmatter and body."""
    fm, body = split_frontmatter(content)
    if fm is None:
        return "---\ntags:\n  - myJira/backend\n  - board\n---\n" + content
    lines = fm.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(tags\s*:\s*)(.*)$", line.strip(), re.IGNORECASE)
        if not m:
            continue
        inline = m.group(2).strip()
        if inline:
            items = [t for t in re.split(r"[\s,]+", inline.strip("[]")) if t]
            lines[i] = "tags: [" + ", ".join(items + ["myJira/backend"]) + "]"
        else:
            lines.insert(i + 1, "  - myJira/backend")
        break
    else:
        lines += ["tags:", "  - myJira/backend"]
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def create_board(name, sections=None, folder=PROJECT_BOARDS_DIR, parent=None, adopt=True):
    """Create a per-project board note (default PROJECTS/<name>.md).

    The note carries `myJira/backend` in its frontmatter, so it shows up as a
    board tab straight away. `sections` become its '##' headings (the
    categories cards are filed under). An existing untagged note of that name
    is adopted (tagged) rather than overwritten when `adopt` is true.
    """
    base_dir = get_ideas_dir()
    name = board_name_for(name)
    if not name:
        return {"ok": False, "message": "The board needs a name"}
    folder = board_name_for(folder) if folder else ""
    rel = resolve_board_path(base_dir, f"{folder}/{name}.md" if folder else f"{name}.md")
    if not rel or rel in NON_BACKEND_FILES:
        return {"ok": False, "message": f"Not a valid board name: {name}"}
    fpath = os.path.join(base_dir, rel)

    if os.path.isfile(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        if is_backend_content(content):
            return {"ok": False, "message": f"Board '{rel}' already exists", "file": rel, "exists": True}
        if not adopt:
            return {"ok": False, "message": f"'{rel}' exists and is not a board", "file": rel}
        _write_file_atomically(fpath, _add_backend_tag(content))
        trigger_obsidian_sync(reason="adopt_board")
        return {"ok": True, "message": f"Existing note '{rel}' is now a board", "file": rel, "adopted": True}

    sections = [board_name_for(x) for x in (sections or ["Backlog"])]
    sections = [x for x in sections if x] or ["Backlog"]
    lines = [
        "---",
        "tags:",
        "  - myJira/backend",
        "  - board",
        f"project: {name}",
        f"created: {_today()}",
        "---",
    ]
    if parent:
        lines += [f"Board for the *{name}* ticket in [[{os.path.splitext(parent)[0]}]].", ""]
    for sec in sections:
        lines += [f"## {sec}", ""]
    _write_file_atomically(fpath, "\n".join(lines))
    trigger_obsidian_sync(reason="create_board")
    return {"ok": True, "message": f"Created board '{rel}'", "file": rel, "sections": sections}


def get_ideas_dir():
    """Resolve the project ideas directory dynamically:
    1. STATUS_PROJECT_IDEAS_DIR or PROJECT_IDEAS_DIR environment variable
    2. Auto-discovery from obsidian.json (Linux, macOS, Windows)
    3. Auto-discovery in user's Documents folder
    4. Fallback to ~/Documents/Project ideas (auto-created)
    """
    for ev in ("STATUS_PROJECT_IDEAS_DIR", "PROJECT_IDEAS_DIR"):
        val = os.environ.get(ev)
        if val:
            expanded = os.path.abspath(os.path.expanduser(val))
            if os.path.isdir(expanded):
                return expanded

    home = os.path.expanduser("~")

    # Inspect obsidian.json across standard OS locations
    obsidian_cfgs = [
        os.path.join(home, ".config", "obsidian", "obsidian.json"),
        os.path.join(home, "Library", "Application Support", "obsidian", "obsidian.json"),
        os.path.expandvars(r"%APPDATA%/obsidian/obsidian.json"),
    ]
    for cfg in obsidian_cfgs:
        if os.path.isfile(cfg):
            try:
                import json
                with open(cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                vaults = data.get("vaults", {})
                for v in vaults.values():
                    vpath = v.get("path")
                    if vpath and os.path.isdir(vpath):
                        for sub in ("Project ideas", "project ideas", "Projects/Project ideas", "Projects"):
                            candidate = os.path.join(vpath, sub)
                            if os.path.isdir(candidate):
                                return os.path.abspath(candidate)
                        # Check if vault itself contains ideas files
                        if os.path.isfile(os.path.join(vpath, "2 - Money making.md")):
                            return os.path.abspath(vpath)
            except Exception:
                pass

    # Search in standard Documents directories
    candidates = [
        os.path.join(home, "Documents", "notes_perso", "Project ideas"),
        os.path.join(home, "documents", "notes_perso", "Project ideas"),
        os.path.join(home, "Documents", "Project ideas"),
        os.path.join(home, "documents", "project ideas"),
        os.path.join(home, "Documents", "notes_perso"),
        os.path.join(home, "documents", "notes_perso"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return os.path.abspath(c)

    # Shallow scan of Documents directory for any Project ideas folder
    for doc_name in ("Documents", "documents"):
        doc_dir = os.path.join(home, doc_name)
        if os.path.isdir(doc_dir):
            try:
                for root, dirs, _ in os.walk(doc_dir):
                    depth = root[len(doc_dir):].count(os.sep)
                    if depth > 2:
                        continue
                    for d in dirs:
                        if d.lower() == "project ideas":
                            return os.path.abspath(os.path.join(root, d))
            except Exception:
                pass

    fallback = os.path.join(home, "Documents", "Project ideas")
    os.makedirs(fallback, exist_ok=True)
    return os.path.abspath(fallback)


def get_display_path():
    """Format resolved ideas path with ~ for compact display."""
    p = get_ideas_dir()
    home = os.path.expanduser("~")
    if p.startswith(home):
        return "~" + p[len(home):]
    return p


def rank(line):
    """Rank logic matching sync.sh: ongoing=0, next=1, other=2."""
    if "#board/ongoing" in line:
        return 0
    if "#board/next" in line:
        return 1
    return 2


def is_heading(line):
    return line.startswith("#")


def is_top_bullet(line):
    return re.match(r"^[ \t]*- ", line) is not None


def is_child(line):
    return line.strip() != "" and re.match(r"^[ \t]+", line) is not None


def reorder_lines(lines):
    """Stable reordering matching sync.sh: ongoing first, next second, other third."""
    out = []
    i = 0
    n = len(lines)

    # Preserve YAML frontmatter at top of file
    if n > 0 and lines[0].strip() == "---":
        out.append(lines[0])
        i = 1
        while i < n and lines[i].strip() != "---":
            out.append(lines[i])
            i += 1
        if i < n and lines[i].strip() == "---":
            out.append(lines[i])
            i += 1

    while i < n:
        if not is_top_bullet(lines[i]):
            out.append(lines[i])
            i += 1
            continue

        blocks = []
        while i < n and not is_heading(lines[i]):
            l = lines[i]
            if is_top_bullet(l):
                block = [l]
                i += 1
                while i < n and is_child(lines[i]):
                    block.append(lines[i])
                    i += 1
                blocks.append(block)
            elif l.strip() == "":
                j = i
                while j < n and lines[j].strip() == "":
                    j += 1
                if j < n and not is_heading(lines[j]) and is_top_bullet(lines[j]):
                    i = j
                else:
                    break
            else:
                break

        blocks.sort(key=lambda b: rank(b[0]))
        for b in blocks:
            out.extend(b)

    return out


def make_idea_id(file_rel, raw_title):
    """Generate a stable deterministic ID for an idea."""
    clean_title = re.sub(r"\s+", " ", raw_title).strip()
    key = f"{file_rel}::{clean_title}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def split_title_and_inline_notes(raw_line):
    """Splits a bullet line into a clean title and inline notes if separated by — or --."""
    m = re.match(r"^[ \t]*- (?:\[[ xX]\]\s*)?(.*)$", raw_line)
    body = m.group(1).strip() if m else raw_line.strip()
    inline_notes = ""
    # Check for em-dash ' — ' or double-dash ' -- '
    m_split = re.search(r"\s+(?:—|--)\s+", body)
    if m_split:
        title_part = body[:m_split.start()].strip()
        inline_notes = body[m_split.end():].strip()
    else:
        title_part = body

    # Clean tags and status from title_part. Tags are returned separately as
    # labels, so they never leak into the display title.
    t = TAG_RE.sub("", title_part)
    t = STATUS_MARKER_RE.sub("", t)
    # Strip surrounding markdown bold / italic
    t = re.sub(r"^\*+|\*+$", "", t.strip())
    t = re.sub(r"^_+|_+$", "", t.strip())
    clean_title = re.sub(r"\s+", " ", t).strip(" —-:")
    return clean_title, inline_notes


def clean_display_title(raw_title):
    """Extract clean title text for display."""
    clean_title, _ = split_title_and_inline_notes(raw_title)
    return clean_title


def detect_status(text, in_rejected_file=False):
    """Detect status: 'ongoing', 'next', 'shelved', 'rejected', or 'untagged'.

    For active files pass the bullet's own line: markers in its notes (a
    challenge that quotes "rejected", an analysis saying "shelved") must not
    move the card.
    """
    if in_rejected_file:
        if "SHELVED" in text.upper():
            return "shelved"
        return "rejected"

    if "#board/ongoing" in text or "[ONGOING]" in text:
        return "ongoing"
    if "#board/next" in text:
        return "next"
    if re.search(r"\[(?:SHELVED|PARKED)[^\]]*\]", text, re.IGNORECASE):
        return "shelved"
    if re.search(r"\[REJECTED[^\]]*\]", text, re.IGNORECASE):
        return "rejected"
    return "untagged"


def parse_active_file(base_dir, filename):
    """Parse ideas from an active markdown file like '2 - Money making.md'."""
    fpath = os.path.join(base_dir, filename)
    if not os.path.isfile(fpath):
        return []

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    lines = content.split("\n")
    ideas = []
    current_cat = "General"
    i = 0
    n = len(lines)
    pipeline = board_config_from_content(content)["blueprint"] == "pipeline"

    # Skip YAML frontmatter if present
    if n > 0 and lines[0].strip() == "---":
        i = 1
        while i < n and lines[i].strip() != "---":
            i += 1
        if i < n and lines[i].strip() == "---":
            i += 1

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if re.match(r"^#{1,6}\s", stripped):
            # Header line ('#tag' on its own line is a tag, not a heading)
            current_cat = stripped.lstrip("#").strip()
            i += 1
            continue

        # Check for bullet
        m = re.match(r"^[ \t]*- (\[[ xX]\] )?(.*)$", line)
        if m:
            checked = bool(m.group(1) and m.group(1).strip().lower() == "[x]")
            raw_title = line.strip()
            line_no = i + 1

            # Collect child lines (notes / sub-bullets)
            children = []
            j = i + 1
            while j < n and is_child(lines[j]):
                children.append(lines[j])
                j += 1

            full_block_text = line + "\n" + "\n".join(children)
            status = (stage_of(line) or "raw") if pipeline else detect_status(line)
            tags = extract_labels(full_block_text)
            clean_title, inline_notes = split_title_and_inline_notes(line)
            idea_id = make_idea_id(filename, raw_title)

            # Format notes for clean display: inline notes first, then child
            # lines with their common indent removed (nesting survives).
            clean_notes = []
            if inline_notes:
                clean_notes.append(inline_notes)
            if children:
                clean_notes.extend(textwrap.dedent("\n".join(children)).split("\n"))

            ideas.append({
                "id": idea_id,
                "file": filename,
                "category": current_cat,
                "title": clean_title,
                "raw_title": line,
                "status": status,
                "tags": tags,
                "state_tags": [t for t in TAG_RE.findall(line) if is_state_tag(t)],
                "notes": "\n".join(clean_notes),
                "rejection_reason": inline_notes if status in ("rejected", "shelved") else "",
                "pipeline": pipeline,
                "checked": checked,
                "line_number": line_no,
                "child_count": len(children) + (1 if inline_notes else 0),
                "is_dossier": False,
            })
            i = j
            continue

        i += 1

    return ideas


def dossier_sections(content):
    """Yield (header, start, end) for each '### ' dossier in rejected.md.

    A dossier runs until the next heading of level 1-3, so its '####'
    sub-sections belong to it and the '## ' group headings do not.
    """
    matches = list(re.finditer(r"^### +(.+?)[ \t]*$", content, re.MULTILINE))
    for m in matches:
        nxt = re.compile(r"^#{1,3} ", re.MULTILINE).search(content, m.end())
        yield m.group(1).strip(), m.start(), nxt.start() if nxt else len(content)


def _rejection_reason(text):
    """The one-line reason a card was rejected, for the challenge dialog."""
    m = re.search(r"\*\*(?:Detailed )?(?:Rejection|Shelving) Rationale:?\*\*:?[ \t]*(.*)", text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r"\*\*Status:?\*\*:?[ \t]*(.*)", text)
    if m:
        return m.group(1).strip()
    return ""


def parse_rejected_file(base_dir, filename=REJECTED_FILE):
    """Parse dossiers from rejected/rejected.md."""
    fpath = os.path.join(base_dir, filename)
    if not os.path.isfile(fpath):
        return []

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    ideas = []
    for header, start, end in dossier_sections(content):
        sec = content[start:end]
        body = sec.split("\n", 1)[1].strip() if "\n" in sec else ""
        tags = extract_labels(sec)
        if TAG_REINSTATED in tags:
            continue

        ideas.append({
            "id": make_idea_id(filename, header),
            "file": filename,
            "category": "Rejected / Shelved",
            "title": header,
            "raw_title": "### " + header,
            "status": "shelved" if "SHELVED" in sec.upper() else "rejected",
            "tags": tags,
            "state_tags": [],
            "notes": body,
            "rejection_reason": _rejection_reason(body),
            "checked": True,
            "line_number": content.count("\n", 0, start) + 1,
            "child_count": body.count("\n") + 1 if body else 0,
            "is_dossier": True,
        })

    return ideas


def list_all_ideas(file_filter=None, status_filter=None, search=None):
    """Retrieve all parsed ideas across vault files."""
    base_dir = get_ideas_dir()
    ideas = []

    backends = discover_backend_files(base_dir)
    for fname in backends:
        ideas.extend(parse_active_file(base_dir, fname))

    # Parse rejected dossiers
    ideas.extend(parse_rejected_file(base_dir, REJECTED_FILE))

    # A card whose project has its own board (PROJECTS/<title>.md) links to it.
    boards = {os.path.splitext(os.path.basename(f))[0].lower(): f
              for f in backends if "/" in f}
    for i in ideas:
        board = boards.get(board_name_for(i["title"]).lower())
        i["board"] = board if board and board != i["file"] else None

    # Apply filters
    if file_filter and file_filter != "all":
        ideas = [i for i in ideas if i["file"] == file_filter]

    if status_filter and status_filter != "all":
        ideas = [i for i in ideas if i["status"] == status_filter]

    if search:
        s = search.lower()
        ideas = [
            i for i in ideas
            if s in i["title"].lower()
            or s in i["category"].lower()
            or s in i["notes"].lower()
            or any(s in tag.lower() for tag in i["tags"])
        ]

    return ideas


def get_categories():
    """Return all known categories organized by backend file."""
    base_dir = get_ideas_dir()
    categories_by_file = {}

    for fname in discover_backend_files(base_dir):
        fpath = os.path.join(base_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        _, body = split_frontmatter(content)
        cats = []
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") and not TAG_RE.match(stripped):
                cat = stripped.lstrip("#").strip()
                if cat and cat not in cats and not cat.lower().startswith("read [["):
                    cats.append(cat)
        categories_by_file[fname] = cats

    return categories_by_file


def get_stats():
    """Return summary statistics of ideas."""
    all_ideas = list_all_ideas()
    stats = {
        "total": len(all_ideas),
        "ongoing": 0,
        "next": 0,
        "untagged": 0,
        "shelved": 0,
        "rejected": 0,
        "by_file": {},
        "by_category": {},
    }
    for i in all_ideas:
        st = i["status"]
        stats[st] = stats.get(st, 0) + 1

        f = i["file"]
        stats["by_file"][f] = stats["by_file"].get(f, 0) + 1

        c = i["category"]
        stats["by_category"][c] = stats["by_category"].get(c, 0) + 1

    return stats


def _write_file_atomically(fpath, content):
    """Write text content to file atomically via a temporary file."""
    dir_name = os.path.dirname(fpath)
    os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
        tf.write(content)
        temp_name = tf.name
    os.replace(temp_name, fpath)


def is_obsidian_running():
    """Check whether the Obsidian desktop application is currently running."""
    try:
        if sys.platform.startswith("linux") and os.path.isdir("/proc"):
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                comm_path = os.path.join("/proc", pid, "comm")
                if os.path.isfile(comm_path):
                    try:
                        with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                            if f.read().strip().lower() == "obsidian":
                                return True
                    except (OSError, IOError):
                        pass
        if shutil.which("pgrep"):
            res = subprocess.run(["pgrep", "-x", "obsidian"], capture_output=True, timeout=2, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return True
        if shutil.which("ps"):
            res = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, timeout=2, check=False)
            if any(line.strip().lower() == "obsidian" for line in res.stdout.splitlines()):
                return True
    except Exception:
        pass
    return False


def get_sync_state_file():
    """Get location of the sync state JSON file."""
    override = os.environ.get("STATUS_OBSIDIAN_SYNC_STATE")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = os.path.expanduser("~")
    return os.path.join(home, ".config", "obsidian", "sync_state.json")


def get_sync_state():
    """Read the current Obsidian sync state."""
    fpath = get_sync_state_file()
    if os.path.isfile(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {
        "last_sync_timestamp": 0.0,
        "last_sync_time": None,
        "last_trigger": "never",
        "status": "idle",
        "detail": "No sync has been recorded yet.",
    }


def record_sync_event(trigger_reason="idea_drop", status="ok", detail=""):
    """Record a sync event to the sync state JSON file."""
    fpath = get_sync_state_file()
    try:
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        now_ts = time.time()
        now_iso = datetime.datetime.now().isoformat()
        state = {
            "last_sync_timestamp": now_ts,
            "last_sync_time": now_iso,
            "last_trigger": trigger_reason,
            "status": status,
            "detail": detail,
        }
        _write_file_atomically(fpath, json.dumps(state, indent=2))
        return state
    except Exception as exc:
        return {"error": str(exc)}


def dispatch_obsidian_sync(reason="manual"):
    """Synchronously dispatch Obsidian Remotely Save sync and record state."""
    uri = "obsidian://remotely-save-sync"
    detail = ""
    status = "ok"

    try:
        time.sleep(0.3)

        if sys.platform == "darwin":
            if shutil.which("open"):
                res = subprocess.run(["open", uri], capture_output=True, text=True, timeout=5, check=False)
                detail = res.stdout.strip() or res.stderr.strip() or "Dispatched via open"
            else:
                status = "error"
                detail = "open command not found"
        elif sys.platform == "win32":
            try:
                os.startfile(uri)  # type: ignore
                detail = "Dispatched via os.startfile"
            except Exception as e:
                res = subprocess.run(["cmd", "/c", "start", "", uri], shell=True, capture_output=True, text=True, timeout=5, check=False)
                detail = res.stdout.strip() or str(e)
        else:
            # Linux / Unix
            env = dict(os.environ)
            try:
                uid = os.getuid()
            except Exception:
                uid = 1000

            if "DISPLAY" not in env:
                env["DISPLAY"] = ":0"
            if "XAUTHORITY" not in env:
                for auth in [
                    f"/run/user/{uid}/gdm/Xauthority",
                    f"/run/user/{uid}/Xauthority",
                    os.path.expanduser("~/.Xauthority"),
                ]:
                    if os.path.isfile(auth):
                        env["XAUTHORITY"] = auth
                        break
            if "DBUS_SESSION_BUS_ADDRESS" not in env:
                bus_path = f"/run/user/{uid}/bus"
                if os.path.exists(bus_path):
                    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus_path}"

            xdg_open = shutil.which("xdg-open")
            if xdg_open:
                try:
                    res = subprocess.run(
                        [xdg_open, uri],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    detail = res.stdout.strip() or res.stderr.strip() or "Dispatched via xdg-open"
                except subprocess.TimeoutExpired:
                    subprocess.Popen(
                        [xdg_open, uri],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    detail = "Dispatched and launched Obsidian in background"
            else:
                status = "error"
                detail = "xdg-open not found"
    except Exception as exc:
        status = "error"
        detail = str(exc)

    record_sync_event(trigger_reason=reason, status=status, detail=detail)
    return {
        "ok": status == "ok",
        "status": status,
        "trigger": reason,
        "detail": detail,
        "timestamp": time.time(),
    }


def trigger_obsidian_sync(reason="idea_drop"):
    """Trigger Obsidian Remotely Save sync asynchronously in a background thread."""
    threading.Thread(target=dispatch_obsidian_sync, args=(reason,), daemon=True).start()


def add_idea(title, category="Next up", target_file="2 - Money making.md", status="untagged", notes="", tags=None):
    """Add a new idea into the specified Obsidian markdown file.

    `tags` are labels (e.g. ["owned"]) appended to the bullet as #tags.
    """
    base_dir = get_ideas_dir()
    clean_target = resolve_board_path(base_dir, target_file)
    if not clean_target:
        return {"ok": False, "message": f"Not a valid board file: {target_file}"}
    fpath = os.path.join(base_dir, clean_target)

    if not title or not title.strip():
        return {"ok": False, "message": "Idea title cannot be empty"}

    title = title.strip()
    notes = (notes or "").strip()
    status = status.lower() if status in ("ongoing", "next", "untagged", "shelved", "rejected") else "untagged"

    # Build bullet line
    tag_part = ""
    prefix_part = ""
    if status == "ongoing":
        tag_part = " #board/ongoing"
        prefix_part = "`[ONGOING]` "
    elif status == "next":
        tag_part = " #board/next"

    in_title = extract_labels(title)
    label_part = "".join(f" #{t}" for t in normalize_tags(tags) if t not in in_title)

    main_bullet = f"- [ ] {prefix_part}{title}{tag_part}{label_part}"
    block_lines = [main_bullet]
    if notes:
        for nl in notes.split("\n"):
            block_lines.append(f"    {nl.rstrip()}")

    # Read existing content or start fresh
    if os.path.isfile(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
    else:
        lines = [f"# {os.path.splitext(os.path.basename(clean_target))[0]}\n"]

    # Locate the category header
    target_cat = category.strip()
    cat_idx = -1
    for idx, l in enumerate(lines):
        stripped = l.strip()
        if stripped.startswith("#"):
            h_text = stripped.lstrip("#").strip()
            if h_text.lower() == target_cat.lower():
                cat_idx = idx
                break

    if cat_idx != -1:
        # Category exists. Insert right after the header line (or after blank lines following it)
        insert_pos = cat_idx + 1
        while insert_pos < len(lines) and lines[insert_pos].strip() == "":
            insert_pos += 1
        lines[insert_pos:insert_pos] = block_lines
    else:
        # Create category section at end of file (before any trailing separator if present)
        # Skip YAML frontmatter: its '---' fences are not the separator.
        body_start = 0
        if lines and lines[0].strip() == "---":
            for idx in range(1, len(lines)):
                if lines[idx].strip() == "---":
                    body_start = idx + 1
                    break
        sep_idx = -1
        for idx in range(body_start, len(lines)):
            if lines[idx].strip() == "---":
                sep_idx = idx
                break

        new_cat_lines = ["", f"## {target_cat}", ""] + block_lines + [""]
        if sep_idx != -1:
            lines[sep_idx:sep_idx] = new_cat_lines
        else:
            lines.extend(new_cat_lines)

    # Reorder according to sync.sh logic
    reordered = reorder_lines(lines)
    _write_file_atomically(fpath, "\n".join(reordered))
    trigger_obsidian_sync(reason="idea_drop")

    new_id = make_idea_id(clean_target, main_bullet)
    return {
        "ok": True,
        "message": f"Idea added to {clean_target} under '{target_cat}'",
        "id": new_id,
        "title": title,
        "file": clean_target,
        "category": target_cat,
        "status": status,
        "tags": extract_labels(main_bullet),
    }


def _today():
    return datetime.date.today().isoformat()


def _find_idea(idea_id):
    for i in list_all_ideas():
        if i["id"] == idea_id:
            return i
    return None


def _read_lines(fpath):
    with open(fpath, "r", encoding="utf-8") as f:
        return f.read().split("\n")


def _locate_bullet(lines, idea):
    """Return (start, end) of an idea's bullet block in lines, or None."""
    idx = -1
    for i, l in enumerate(lines):
        if l.strip() == idea["raw_title"].strip():
            idx = i
            break
    if idx == -1:
        for i, l in enumerate(lines):
            if is_top_bullet(l) and idea["id"] == make_idea_id(idea["file"], l.strip()):
                idx = i
                break
    if idx == -1:
        for i, l in enumerate(lines):
            if is_top_bullet(l) and idea["title"] and idea["title"] in l:
                idx = i
                break
    if idx == -1:
        return None
    end = idx + 1
    while end < len(lines) and is_child(lines[end]):
        end += 1
    return idx, end


def _locate_dossier(content, idea):
    """Return (start, end) of an idea's '### ' dossier in rejected.md, or None."""
    for header, start, end in dossier_sections(content):
        if header == idea["title"] or make_idea_id(REJECTED_FILE, header) == idea["id"]:
            return start, end
    return None


def _append_to_dossier(content, span, new_lines, drop_tags=()):
    """Append lines at the end of a dossier, before its trailing blanks/rule."""
    start, end = span
    sec_lines = content[start:end].split("\n")
    if drop_tags:
        sec_lines = [strip_tag_tokens(l, drop_tags) if TAG_RE.search(l) else l for l in sec_lines]
    cut = len(sec_lines)
    while cut > 1 and sec_lines[cut - 1].strip() in ("", "---"):
        cut -= 1
    sec_lines[cut:cut] = new_lines
    return content[:start] + "\n".join(sec_lines) + content[end:]


def _child_bullet(label, text, indent="  "):
    """An indented audit-trail bullet; extra lines become continuation lines."""
    parts = [p.strip() for p in str(text).strip().split("\n") if p.strip()]
    out = [f"{indent}- **{label} ({_today()})**: {parts[0] if parts else ''}"]
    out.extend(f"{indent}  {p}" for p in parts[1:])
    return out


def _child_indent(block):
    """Indent used by a bullet's existing children, so appended ones line up."""
    for l in block[1:]:
        m = re.match(r"^([ \t]+)", l)
        if m:
            return m.group(1)
    return "  "


def _set_line_labels(line, add=(), remove=()):
    """Add/remove #labels on a bullet's title line, keeping any ' — ' notes."""
    m = re.search(r"\s+(?:—|--)\s+", line)
    head, tail = (line[:m.start()], line[m.start():]) if m else (line, "")
    head = strip_tag_tokens(head, remove)
    present = extract_labels(head)
    for t in add:
        if t not in present:
            head += f" #{t}"
    return head + tail


def _set_line_status(line, status):
    """Rewrite a bullet's status markers (#board/*, `[REJECTED]`...) in place."""
    m = re.search(r"\s+(?:—|--)\s+", line)
    head, tail = (line[:m.start()], line[m.start():]) if m else (line, "")
    head = re.sub(r"(?<!\S)#board/(?:ongoing|next)(?![\w/-])", "", head)
    head = STATUS_MARKER_RE.sub("", head)
    head = re.sub(r"[ \t]{2,}", " ", head).rstrip()
    body = re.sub(r"^[ \t]*- (?:\[[ xX]\] ?)?", "", head).strip()
    checkbox = "- [x] " if re.match(r"^[ \t]*- \[[xX]\]", line) else "- [ ] "
    marker = {
        "ongoing": ("`[ONGOING]` ", " #board/ongoing"),
        "next": ("", " #board/next"),
        "shelved": ("", " `[SHELVED ON CAPITAL]`"),
        "rejected": ("", " `[REJECTED]`"),
    }.get(status, ("", ""))
    return f"{checkbox}{marker[0]}{body}{marker[1]}{tail}"


def _next_category(fpath):
    """Heading to reinstate a card under: the first one mentioning 'next'."""
    try:
        _, body = split_frontmatter("\n".join(_read_lines(fpath)))
    except OSError:
        return "Next up"
    for line in body.split("\n"):
        if re.match(r"^#{1,6}\s", line) and "next" in line.lower():
            return line.lstrip("#").strip()
    return "Next up"


def _reinstate_dossier(idea, new_status, answer_line=None, tags=None):
    """Put a rejected dossier back on the board as an active ticket.

    The dossier stays in rejected.md for the audit trail, tagged #reinstated
    so it stops showing as a card of its own.
    """
    base_dir = get_ideas_dir()
    backends = discover_backend_files(base_dir)
    m = re.search(r"Moved from (.+?\.md)", idea.get("notes", ""))
    target = m.group(1) if m and m.group(1) in backends else (
        DEFAULT_BACKENDS[0] if DEFAULT_BACKENDS[0] in backends or not backends else backends[0])
    tpath = os.path.join(base_dir, target)

    notes = [f"- Reinstated from `{REJECTED_FILE}` on {_today()} (full dossier: *{idea['title']}*)"]
    if answer_line:
        notes.append(answer_line)
    labels = [t for t in (tags if tags is not None else idea.get("tags", [])) if t != TAG_REINSTATED]
    title = re.sub(r"`?\[(?:REJECTED|SHELVED|PARKED)[^\]]*\]`?", "", idea["title"])
    title = re.sub(r"\s+", " ", title).strip()

    res = add_idea(
        title=title,
        category=_next_category(tpath),
        target_file=target,
        status=new_status,
        notes="\n".join(notes),
        tags=labels,
    )
    if not res.get("ok"):
        return res

    rpath = os.path.join(base_dir, REJECTED_FILE)
    content = "\n".join(_read_lines(rpath))
    span = _locate_dossier(content, idea)
    if span:
        content = _append_to_dossier(
            content, span,
            [f"* **Reinstated ({_today()}):** moved back to `{target}` as {new_status} #{TAG_REINSTATED}"])
        _write_file_atomically(rpath, content)
    res["message"] = f"Reinstated '{idea['title']}' to {target} as {new_status}"
    res["new_status"] = new_status
    return res


def update_idea_status(idea_id, new_status, reason=""):
    """Update status of an idea (untagged, next, ongoing, or rejected)."""
    base_dir = get_ideas_dir()
    new_status = new_status.lower().strip()
    if new_status not in STATUSES + PIPELINE_STAGES:
        return {"ok": False, "message": f"Invalid status: {new_status}"}

    # Find the idea
    all_ideas = list_all_ideas()
    target_idea = None
    for i in all_ideas:
        if i["id"] == idea_id:
            target_idea = i
            break

    if not target_idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}

    source_file = target_idea["file"]

    if target_idea.get("pipeline"):
        if new_status not in PIPELINE_STAGES:
            return {"ok": False, "message": f"Pipeline tickets move between stages: {', '.join(PIPELINE_STAGES)}"}
        if target_idea["status"] == new_status:
            return {"ok": True, "message": "Stage unchanged"}
        return set_stage(idea_id, new_status, "Moved", f"by hand to {new_status}")
    if new_status not in STATUSES:
        return {"ok": False, "message": f"'{new_status}' is a pipeline stage; this board uses {', '.join(STATUSES)}"}

    # If already in that status, nothing to do
    if target_idea["status"] == new_status:
        return {"ok": True, "message": "Status unchanged", "idea": target_idea}

    # A dossier is already archived; don't append a second copy of it.
    if new_status in ("rejected", "shelved") and target_idea.get("is_dossier"):
        return {"ok": False, "message": "Already archived in rejected/rejected.md"}

    # Handling move to rejected
    if new_status in ("rejected", "shelved"):
        # Move to rejected/rejected.md
        rejected_fpath = os.path.join(base_dir, "rejected", "rejected.md")
        os.makedirs(os.path.join(base_dir, "rejected"), exist_ok=True)

        today_str = datetime.date.today().isoformat()
        status_label = "REJECTED" if new_status == "rejected" else "SHELVED ON CAPITAL"
        dossier_entry = (
            f"\n### {target_idea['title']}\n"
            f"* **Concept:** {target_idea['title']}\n"
            f"* **Status:** `[{status_label}]` (Moved from {source_file} on {today_str})\n"
            f"* **Rejection Rationale:** {reason or target_idea['notes'] or 'Moved via Idea Bucket'}\n"
        )
        if target_idea.get("tags"):
            dossier_entry += "* **Labels:** " + " ".join("#" + t for t in target_idea["tags"]) + "\n"
        with open(rejected_fpath, "a", encoding="utf-8") as f:
            f.write(dossier_entry)

        # Remove from active source file
        _remove_bullet_block(os.path.join(base_dir, source_file), target_idea["raw_title"])
        trigger_obsidian_sync(reason="reject_idea")
        return {
            "ok": True,
            "message": f"Moved '{target_idea['title']}' to rejected/rejected.md",
            "new_status": new_status,
        }

    # If moving out of rejected dossier into active files:
    if target_idea["file"] == REJECTED_FILE:
        return _reinstate_dossier(target_idea, new_status)

    # Modifying in active file:
    source_fpath = os.path.join(base_dir, source_file)
    if not os.path.isfile(source_fpath):
        return {"ok": False, "message": f"File {source_file} does not exist"}

    with open(source_fpath, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    # Find the bullet line
    idx = -1
    for i, l in enumerate(lines):
        if l.strip() == target_idea["raw_title"].strip():
            idx = i
            break

    if idx == -1:
        # Fallback search by title
        for i, l in enumerate(lines):
            if is_top_bullet(l) and target_idea["title"] in l:
                idx = i
                break

    if idx == -1:
        return {"ok": False, "message": "Could not locate idea in source file"}

    line = lines[idx]

    # Clean existing tags and markers
    line = re.sub(r"#board/(ongoing|next)\b", "", line)
    line = re.sub(r"`\[(ONGOING|SHELVED ON CAPITAL|REJECTED)\]`", "", line)
    line = re.sub(r"\[(ONGOING|SHELVED ON CAPITAL|REJECTED)\]", "", line)
    line = re.sub(r"\s+", " ", line).strip()

    # Reconstruct line with new status
    prefix = ""
    tag = ""
    if new_status == "ongoing":
        prefix = "`[ONGOING]` "
        tag = " #board/ongoing"
    elif new_status == "next":
        tag = " #board/next"

    # Ensure `- [ ]` prefix remains
    if line.startswith("- [ ] "):
        body = line[6:].strip()
    elif line.startswith("- [x] "):
        body = line[6:].strip()
    elif line.startswith("- "):
        body = line[2:].strip()
    else:
        body = line.strip()

    lines[idx] = f"- [ ] {prefix}{body}{tag}"

    reordered = reorder_lines(lines)
    _write_file_atomically(source_fpath, "\n".join(reordered))
    trigger_obsidian_sync(reason="status_change")

    return {
        "ok": True,
        "message": f"Updated '{target_idea['title']}' to {new_status}",
        "new_status": new_status,
        "new_id": make_idea_id(source_file, lines[idx]),
    }


def _notes_to_block(notes, indent="  "):
    """Split edited notes into (inline_note, child_lines) for a bullet.

    A plain first line goes back after ' — ' on the bullet, as the parser read
    it; lists, callouts and everything after it become indented children.
    """
    lines = notes.split("\n") if notes else []
    inline = ""
    if lines and lines[0].strip() and not re.match(r"^\s*(?:[-*+>|]|\d+[.)])\s", lines[0] + " "):
        inline = lines.pop(0).strip()
    return inline, [f"{indent}{l}" if l.strip() else "" for l in lines]


def update_idea(idea_id, title=None, notes=None, category=None, status=None, tags=None):
    """Update title, notes/details, category, status or labels of an idea.

    `tags` replaces the idea's labels (#owned, #saas...) independently of its
    status; None leaves them as they are. Labels removed here are removed from
    the notes too, wherever they were written.
    """
    base_dir = get_ideas_dir()
    target_idea = _find_idea(idea_id)
    if not target_idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}

    source_file = target_idea["file"]
    fpath = os.path.join(base_dir, source_file)
    if not os.path.isfile(fpath):
        return {"ok": False, "message": f"File not found: {source_file}"}

    old_tags = list(target_idea.get("tags", []))

    # Pipeline tickets change stage only through set_stage (worker / human gate).
    if target_idea.get("pipeline") and status and status != target_idea["status"]:
        res = set_stage(idea_id, status)
        if not res.get("ok"):
            return res
        idea_id = res["id"]
        target_idea = _find_idea(idea_id)
        status = None

    # If status change is requested and different from current:
    if status and status != target_idea["status"]:
        res = update_idea_status(idea_id, status)
        if not res.get("ok"):
            return res
        # Re-fetch the idea from wherever it now lives (its id changes with its line).
        moved = None
        for i in list_all_ideas():
            if i["id"] in (idea_id, res.get("id"), res.get("new_id")) or (
                    i["title"] == target_idea["title"] and i["status"] == status):
                moved = i
                break
        if not moved:
            return {"ok": True, "message": res.get("message", "Status updated"), "new_status": status}
        target_idea = moved
        source_file = target_idea["file"]
        fpath = os.path.join(base_dir, source_file)

    new_title = title.strip() if title is not None else target_idea["title"]
    new_notes = notes.strip() if notes is not None else target_idea["notes"]
    new_cat = category.strip() if category is not None else target_idea.get("category", "General")

    # Labels typed into the title field are labels, not title text.
    title_tags = extract_labels(new_title)
    new_title = re.sub(r"\s+", " ", TAG_RE.sub("", new_title)).strip()
    if tags is not None or title_tags:
        wanted = normalize_tags(tags) if tags is not None else list(old_tags)
        wanted += [t for t in title_tags if t not in wanted]
    else:
        wanted = None
    if wanted is not None:
        new_notes = strip_tag_tokens(new_notes, [t for t in old_tags if t not in wanted])

    if not new_title:
        return {"ok": False, "message": "Idea title cannot be empty"}

    # If it is a dossier in rejected/rejected.md
    if target_idea.get("is_dossier") or source_file == REJECTED_FILE:
        try:
            content = "\n".join(_read_lines(fpath))
        except OSError as e:
            return {"ok": False, "message": str(e)}

        span = _locate_dossier(content, target_idea)
        if not span:
            return {"ok": False, "message": f"Dossier section not found for {target_idea['title']}"}
        if wanted is not None:
            missing = [t for t in wanted if t not in extract_labels(new_notes)]
            new_notes = "\n".join(l for l in new_notes.split("\n") if not l.startswith("* **Labels:**"))
            if missing:
                new_notes = new_notes.rstrip() + "\n* **Labels:** " + " ".join("#" + t for t in missing)
        start, end = span
        trailing = content[start:end][len(content[start:end].rstrip()):]
        new_section = f"### {new_title}\n{new_notes}" + (trailing if trailing.strip() else "\n\n")
        content = content[:start] + new_section + content[end:]
        _write_file_atomically(fpath, content)
        trigger_obsidian_sync(reason="edit_dossier")
        return {"ok": True, "message": f"Updated dossier '{new_title}'",
                "id": make_idea_id(REJECTED_FILE, new_title)}

    # Otherwise it is a bullet in an active file
    try:
        lines = _read_lines(fpath)
    except OSError as e:
        return {"ok": False, "message": str(e)}

    span = _locate_bullet(lines, target_idea)
    if not span:
        return {"ok": False, "message": f"Could not find idea in {source_file}"}
    idx, end_idx = span

    # Labels on the title line: kept as they are unless `tags` says otherwise;
    # labels already written in the notes are not repeated on it.
    old_line = lines[idx]
    m = re.search(r"\s+(?:—|--)\s+", old_line)
    line_labels = extract_labels(old_line[:m.start()] if m else old_line)
    if wanted is not None:
        in_notes = extract_labels(new_notes)
        line_labels = [t for t in wanted if t not in in_notes]

    curr_status = target_idea.get("status", "untagged")
    inline, children = _notes_to_block(new_notes, _child_indent(lines[idx:end_idx]))
    first_line = _set_line_status(f"- [ ] {new_title}", curr_status)
    if target_idea.get("pipeline"):
        first_line += " " + stage_tag(curr_status)
    if target_idea.get("checked"):
        first_line = first_line.replace("- [ ] ", "- [x] ", 1)
    first_line += "".join(f" #{t}" for t in line_labels)
    if inline:
        first_line += f" — {inline}"
    new_block_lines = [first_line] + children

    if new_cat and new_cat != target_idea.get("category"):
        del lines[idx:end_idx]
        cat_idx = -1
        for i, l in enumerate(lines):
            if re.match(r"^#{1,6}\s", l.strip()) and l.strip().lstrip("#").strip().lower() == new_cat.lower():
                cat_idx = i
                break
        if cat_idx != -1:
            lines[cat_idx+1:cat_idx+1] = new_block_lines
        else:
            lines.extend(["", f"## {new_cat}"] + new_block_lines)
    else:
        lines[idx:end_idx] = new_block_lines

    _write_file_atomically(fpath, "\n".join(reorder_lines(lines)))
    trigger_obsidian_sync(reason="edit_idea")

    return {
        "ok": True,
        "message": f"Updated idea '{new_title}'",
        "id": make_idea_id(source_file, first_line.strip()),
        "idea": {
            "id": make_idea_id(source_file, first_line.strip()),
            "title": new_title,
            "notes": new_notes,
            "category": new_cat,
            "status": curr_status,
            "tags": extract_labels(first_line + "\n" + new_notes),
        }
    }


def challenge_rejection(idea_id, challenge_text):
    """Appeal a rejected or shelved idea with a counter-argument.

    Adds #rejection_challenged (dropping a previous #rejection_answered) and an
    audit-trail bullet '- **Challenge (YYYY-MM-DD)**: <text>'. The CEO answers
    on its next heartbeat; see answer_challenge.
    """
    challenge_text = (challenge_text or "").strip()
    if not challenge_text:
        return {"ok": False, "message": "The challenge needs a counter-argument"}
    idea = _find_idea(idea_id)
    if not idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}
    if idea["status"] not in ("rejected", "shelved"):
        return {"ok": False, "message": "Only rejected or shelved ideas can be challenged"}

    fpath = os.path.join(get_ideas_dir(), idea["file"])
    try:
        lines = _read_lines(fpath)
    except OSError as e:
        return {"ok": False, "message": str(e)}

    if idea.get("is_dossier"):
        content = "\n".join(lines)
        span = _locate_dossier(content, idea)
        if not span:
            return {"ok": False, "message": f"Dossier section not found for {idea['title']}"}
        entry = _child_bullet("Challenge", challenge_text, indent="")
        entry[0] = "* " + entry[0][2:] + f" #{TAG_CHALLENGED}"
        content = _append_to_dossier(content, span, entry, drop_tags=(TAG_ANSWERED,))
        _write_file_atomically(fpath, content)
        new_id = idea_id
    else:
        span = _locate_bullet(lines, idea)
        if not span:
            return {"ok": False, "message": f"Could not find idea in {idea['file']}"}
        idx, end = span
        indent = _child_indent(lines[idx:end])
        lines[idx:end] = (
            [_set_line_labels(lines[idx], add=(TAG_CHALLENGED,), remove=(TAG_ANSWERED,))]
            + [strip_tag_tokens(l, (TAG_ANSWERED,)) for l in lines[idx + 1:end]]
            + _child_bullet("Challenge", challenge_text, indent)
        )
        _write_file_atomically(fpath, "\n".join(lines))
        new_id = make_idea_id(idea["file"], lines[idx].strip())

    trigger_obsidian_sync(reason="challenge_rejection")
    return {"ok": True, "message": f"Challenge filed on '{idea['title']}'", "id": new_id}


ACCEPT_VERDICTS = ("accepted", "accept", "overturned", "overturn")
UPHOLD_VERDICTS = ("upheld", "uphold", "denied", "deny", "rejected")


def answer_challenge(idea_id, answer_text, verdict, new_status="next"):
    """Record the CEO's ruling on a challenged rejection.

    Swaps #rejection_challenged for #rejection_answered and appends
    '- **CEO Answer (YYYY-MM-DD)**: [accepted|upheld] <text>'. An accepted
    challenge puts the card back on the board as `new_status` (default next);
    a dossier is reinstated into the active file it came from.
    """
    answer_text = (answer_text or "").strip()
    verdict = (verdict or "").strip().lower()
    if verdict in ACCEPT_VERDICTS:
        verdict = "accepted"
    elif verdict in UPHOLD_VERDICTS:
        verdict = "upheld"
    else:
        return {"ok": False, "message": "verdict must be 'accepted' or 'upheld'"}
    if not answer_text:
        return {"ok": False, "message": "The answer needs a rationale"}
    new_status = (new_status or "next").lower()
    if new_status not in ("untagged", "next", "ongoing"):
        return {"ok": False, "message": f"Invalid status for a reinstated idea: {new_status}"}

    idea = _find_idea(idea_id)
    if not idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}

    fpath = os.path.join(get_ideas_dir(), idea["file"])
    try:
        lines = _read_lines(fpath)
    except OSError as e:
        return {"ok": False, "message": str(e)}
    text = f"[{verdict}] {answer_text}"

    if idea.get("is_dossier"):
        entry = _child_bullet("CEO Answer", text, indent="")
        entry[0] = "* " + entry[0][2:] + f" #{TAG_ANSWERED}"
        if verdict == "accepted":
            tags = [t for t in idea.get("tags", []) if t != TAG_CHALLENGED]
            if TAG_ANSWERED not in tags:
                tags.append(TAG_ANSWERED)
            content = "\n".join(lines)
            span = _locate_dossier(content, idea)
            if span:
                content = _append_to_dossier(content, span, entry, drop_tags=(TAG_CHALLENGED,))
                _write_file_atomically(fpath, content)
            answer_line = _child_bullet("CEO Answer", text, indent="")[0]
            res = _reinstate_dossier(idea, new_status, answer_line=answer_line, tags=tags)
            res["verdict"] = verdict
            return res
        content = "\n".join(lines)
        span = _locate_dossier(content, idea)
        if not span:
            return {"ok": False, "message": f"Dossier section not found for {idea['title']}"}
        content = _append_to_dossier(content, span, entry, drop_tags=(TAG_CHALLENGED,))
        _write_file_atomically(fpath, content)
        new_id = idea_id
    else:
        span = _locate_bullet(lines, idea)
        if not span:
            return {"ok": False, "message": f"Could not find idea in {idea['file']}"}
        idx, end = span
        indent = _child_indent(lines[idx:end])
        head = _set_line_labels(lines[idx], add=(TAG_ANSWERED,), remove=(TAG_CHALLENGED,))
        if verdict == "accepted":
            head = _set_line_status(head, new_status)
        lines[idx:end] = (
            [head]
            + [strip_tag_tokens(l, (TAG_CHALLENGED,)) for l in lines[idx + 1:end]]
            + _child_bullet("CEO Answer", text, indent)
        )
        _write_file_atomically(fpath, "\n".join(reorder_lines(lines)))
        new_id = make_idea_id(idea["file"], head.strip())

    trigger_obsidian_sync(reason="answer_challenge")
    return {
        "ok": True,
        "message": f"Challenge on '{idea['title']}' {verdict}",
        "verdict": verdict,
        "id": new_id,
        "new_status": new_status if verdict == "accepted" else idea["status"],
    }


def append_note(idea_id, note, source=""):
    """Append a note bullet to an existing idea (used by the Slack bot)."""
    note = (note or "").strip()
    if not note:
        return {"ok": False, "message": "Nothing to append"}
    idea = _find_idea(idea_id)
    if not idea:
        return {"ok": False, "message": f"Idea not found with id: {idea_id}"}

    fpath = os.path.join(get_ideas_dir(), idea["file"])
    try:
        lines = _read_lines(fpath)
    except OSError as e:
        return {"ok": False, "message": str(e)}
    label = f"Note{' via ' + source if source else ''}"

    if idea.get("is_dossier"):
        content = "\n".join(lines)
        span = _locate_dossier(content, idea)
        if not span:
            return {"ok": False, "message": f"Dossier section not found for {idea['title']}"}
        entry = _child_bullet(label, note, indent="")
        entry[0] = "* " + entry[0][2:]
        _write_file_atomically(fpath, _append_to_dossier(content, span, entry))
    else:
        span = _locate_bullet(lines, idea)
        if not span:
            return {"ok": False, "message": f"Could not find idea in {idea['file']}"}
        idx, end = span
        lines[end:end] = _child_bullet(label, note, _child_indent(lines[idx:end]))
        _write_file_atomically(fpath, "\n".join(lines))

    trigger_obsidian_sync(reason="append_note")
    return {"ok": True, "message": f"Note added to '{idea['title']}'", "id": idea_id,
            "title": idea["title"], "file": idea["file"]}


def find_ideas(query, limit=5):
    """Ideas whose title best matches a free-text query, best first."""
    q = (query or "").strip().lower()
    if not q:
        return []
    words = [w for w in re.split(r"\W+", q) if w]
    scored = []
    for i in list_all_ideas():
        title = i["title"].lower()
        if title == q:
            score = 1000
        elif q in title:
            score = 500 - len(title)
        else:
            hits = sum(1 for w in words if w in title)
            if not hits or hits < max(1, len(words) // 2):
                continue
            score = hits * 10 - len(title) / 100
        if i["status"] not in ("rejected", "shelved"):
            score += 1
        scored.append((score, i))
    scored.sort(key=lambda x: -x[0])
    return [i for _, i in scored[:limit]]


def toggle_idea_check(idea_id):
    """Toggle completed check mark for an idea."""
    base_dir = get_ideas_dir()
    all_ideas = list_all_ideas()
    target_idea = None
    for i in all_ideas:
        if i["id"] == idea_id:
            target_idea = i
            break

    if not target_idea:
        return {"ok": False, "message": "Idea not found"}

    source_fpath = os.path.join(base_dir, target_idea["file"])
    if not os.path.isfile(source_fpath):
        return {"ok": False, "message": "File not found"}

    with open(source_fpath, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    idx = -1
    for i, l in enumerate(lines):
        if l.strip() == target_idea["raw_title"].strip():
            idx = i
            break

    if idx == -1:
        return {"ok": False, "message": "Could not locate idea in source file"}

    line = lines[idx]
    if "- [ ] " in line:
        lines[idx] = line.replace("- [ ] ", "- [x] ", 1)
        new_checked = True
    elif "- [x] " in line:
        lines[idx] = line.replace("- [x] ", "- [ ] ", 1)
        new_checked = False
    else:
        lines[idx] = "- [x] " + line.lstrip("- ")
        new_checked = True

    _write_file_atomically(source_fpath, "\n".join(lines))
    trigger_obsidian_sync(reason="toggle_check")
    return {"ok": True, "checked": new_checked}


def delete_idea(idea_id):
    """Permanently delete an idea block."""
    base_dir = get_ideas_dir()
    all_ideas = list_all_ideas()
    target_idea = None
    for i in all_ideas:
        if i["id"] == idea_id:
            target_idea = i
            break

    if not target_idea:
        return {"ok": False, "message": "Idea not found"}

    source_fpath = os.path.join(base_dir, target_idea["file"])
    _remove_bullet_block(source_fpath, target_idea["raw_title"])
    trigger_obsidian_sync(reason="delete_idea")
    return {"ok": True, "message": "Idea deleted"}


def _remove_bullet_block(fpath, raw_title):
    """Helper to remove a top bullet and its indented children."""
    if not os.path.isfile(fpath):
        return False
    with open(fpath, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    idx = -1
    for i, l in enumerate(lines):
        if l.strip() == raw_title.strip():
            idx = i
            break

    if idx == -1:
        return False

    del_end = idx + 1
    while del_end < len(lines) and is_child(lines[del_end]):
        del_end += 1

    del lines[idx:del_end]
    reordered = reorder_lines(lines)
    _write_file_atomically(fpath, "\n".join(reordered))
    return True


def _cli(argv):
    """Command line for agents (the CEO agent) working the board.

      ideas_manager.py challenged
          List ideas waiting on a ruling (#rejection_challenged), as JSON.
      ideas_manager.py answer <id> <accepted|upheld> <rationale> [--status next|ongoing|untagged]
          Record the ruling; an accepted challenge puts the card back on the board.
      ideas_manager.py new-board <project> [--sections "Features,Bugs"]
          Create PROJECTS/<project>.md as its own board (or tag an existing note).
      ideas_manager.py boards
          List every board file, as JSON.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="ideas_manager.py", description=_cli.__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("challenged", help="list ideas with a pending rejection challenge")
    ans = sub.add_parser("answer", help="answer a rejection challenge")
    ans.add_argument("id")
    ans.add_argument("verdict", choices=("accepted", "upheld"))
    ans.add_argument("rationale")
    ans.add_argument("--status", default="next", choices=("next", "ongoing", "untagged"))
    nb = sub.add_parser("new-board", help="create a per-project board")
    nb.add_argument("project")
    nb.add_argument("--sections", default="Backlog", help="comma-separated section headings")
    nb.add_argument("--parent", default=None, help="board file holding the project's ticket")
    sub.add_parser("boards", help="list board files")
    args = parser.parse_args(argv)

    if args.cmd == "boards":
        print(json.dumps(discover_backend_files(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "new-board":
        res = create_board(args.project, sections=[x.strip() for x in args.sections.split(",")],
                           parent=args.parent)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("ok") else 1

    if args.cmd == "challenged":
        pending = []
        for i in list_all_ideas():
            if TAG_CHALLENGED in i["tags"]:
                challenges = re.findall(r"\*\*Challenge \(([^)]*)\)\*\*:?\s*(.*)", i["notes"])
                pending.append({
                    "id": i["id"], "title": i["title"], "file": i["file"], "status": i["status"],
                    "tags": i["tags"], "rejection_reason": i.get("rejection_reason", ""),
                    "challenge": strip_tag_tokens(challenges[-1][1], (TAG_CHALLENGED,)) if challenges else "",
                    "challenged_on": challenges[-1][0] if challenges else "",
                })
        print(json.dumps(pending, indent=2, ensure_ascii=False))
        return 0

    res = answer_challenge(args.id, args.rationale, args.verdict, new_status=args.status)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
