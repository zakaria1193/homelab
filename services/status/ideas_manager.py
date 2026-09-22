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
import threading
import time

DEFAULT_DIR = os.path.expanduser("~/Documents/notes_perso/Project ideas")


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


def clean_display_title(raw_title):
    """Extract clean title text for display."""
    t = raw_title
    # Strip markdown checkbox
    t = re.sub(r"^- \[[ xX]\]\s*", "", t)
    t = re.sub(r"^- \s*", "", t)
    # Strip tags like #board/ongoing, #board/next
    t = re.sub(r"#board/(ongoing|next)\b", "", t)
    # Strip status markers
    t = re.sub(r"`\[(ONGOING|SHELVED ON CAPITAL|REJECTED|PARKED)\]`", "", t)
    t = re.sub(r"\[(ONGOING|SHELVED ON CAPITAL|REJECTED|PARKED)\]", "", t)
    return re.sub(r"\s+", " ", t).strip(" —-:")


def detect_status(text, in_rejected_file=False):
    """Detect status: 'ongoing', 'next', 'shelved', 'rejected', or 'untagged'."""
    if in_rejected_file:
        if "SHELVED" in text.upper():
            return "shelved"
        return "rejected"

    if "#board/ongoing" in text or "[ONGOING]" in text:
        return "ongoing"
    if "#board/next" in text:
        return "next"
    if "SHELVED" in text.upper():
        return "shelved"
    if "REJECTED" in text.upper():
        return "rejected"
    return "untagged"


def extract_tags(text):
    """Extract all hashtag tags from text (e.g. #board/ongoing, #easy, #tag)."""
    return re.findall(r"(?<!\S)#([a-zA-Z0-9_\-\/]+)", text)


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

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("#"):
            # Header line
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
            status = detect_status(full_block_text)
            tags = extract_tags(full_block_text)
            clean_title = clean_display_title(line)
            idea_id = make_idea_id(filename, raw_title)

            # Format notes for clean display (strip leading 2 or 4 spaces)
            clean_notes = []
            for c in children:
                clean_notes.append(re.sub(r"^[ \t]{2,4}", "", c))

            ideas.append({
                "id": idea_id,
                "file": filename,
                "category": current_cat,
                "title": clean_title,
                "raw_title": line,
                "status": status,
                "tags": tags,
                "notes": "\n".join(clean_notes),
                "checked": checked,
                "line_number": line_no,
                "child_count": len(children),
                "is_dossier": False,
            })
            i = j
            continue

        i += 1

    return ideas


def parse_rejected_file(base_dir, filename="rejected/rejected.md"):
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
    # Split by ### headers
    sections = re.split(r"\n(?=### )", content)
    for sec in sections:
        if not sec.startswith("### "):
            continue
        lines = sec.strip().split("\n")
        header = lines[0].lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()

        status = "shelved" if "SHELVED" in sec.upper() else "rejected"
        tags = extract_tags(sec)
        idea_id = make_idea_id(filename, header)

        ideas.append({
            "id": idea_id,
            "file": filename,
            "category": "Rejected / Shelved",
            "title": header,
            "raw_title": lines[0],
            "status": status,
            "tags": tags,
            "notes": body,
            "checked": True,
            "line_number": 1,
            "child_count": len(lines) - 1,
            "is_dossier": True,
        })

    return ideas


def list_all_ideas(file_filter=None, status_filter=None, search=None):
    """Retrieve all parsed ideas across vault files."""
    base_dir = get_ideas_dir()
    ideas = []

    # Priority active files
    active_files = ["2 - Money making.md", "3 - FOSS projects.md"]

    # Also scan for other .md files in the folder (excluding rejected directory)
    for entry in sorted(os.listdir(base_dir)):
        if entry.endswith(".md") and entry not in active_files and entry != "1. notes.md":
            active_files.append(entry)

    for fname in active_files:
        ideas.extend(parse_active_file(base_dir, fname))

    # Parse rejected dossiers
    ideas.extend(parse_rejected_file(base_dir, "rejected/rejected.md"))

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
    """Return all known categories organized by file."""
    base_dir = get_ideas_dir()
    categories_by_file = {}
    active_files = ["2 - Money making.md", "3 - FOSS projects.md"]

    for fname in active_files:
        fpath = os.path.join(base_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        cats = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
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


def add_idea(title, category="Next up", target_file="2 - Money making.md", status="untagged", notes=""):
    """Add a new idea into the specified Obsidian markdown file."""
    base_dir = get_ideas_dir()
    clean_target = os.path.basename(target_file)
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

    main_bullet = f"- [ ] {prefix_part}{title}{tag_part}"
    block_lines = [main_bullet]
    if notes:
        for nl in notes.split("\n"):
            block_lines.append(f"    {nl.rstrip()}")

    # Read existing content or start fresh
    if os.path.isfile(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
    else:
        lines = [f"# {clean_target.replace('.md', '')}\n"]

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
        sep_idx = -1
        for idx, l in enumerate(lines):
            if l.strip().startswith("---"):
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
    }


def update_idea_status(idea_id, new_status, reason=""):
    """Update status of an idea (untagged, next, ongoing, or rejected)."""
    base_dir = get_ideas_dir()
    new_status = new_status.lower().strip()
    if new_status not in ("untagged", "next", "ongoing", "rejected", "shelved"):
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

    # If already in that status, nothing to do
    if target_idea["status"] == new_status:
        return {"ok": True, "message": "Status unchanged", "idea": target_idea}

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
    if target_idea["file"] == "rejected/rejected.md":
        # Add to 2 - Money making.md
        return add_idea(
            title=target_idea["title"],
            category="Next up",
            target_file="2 - Money making.md",
            status=new_status,
            notes=target_idea["notes"],
        )

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
