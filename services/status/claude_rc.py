"""Claude Remote Control instances, driven from the cockpit.

One `claude remote-control` process serves exactly one directory, so every extra
workspace is another instance: another `.env.<name>` next to
`services/AI/claudeRcAI/.env`, and another `claude-rc-ai-<name>` unit. This
module is the cockpit's side of that. It reads the instances off disk, reports
what systemd is doing with them, drives their Makefile for start/stop/restart,
and writes the two files a brand new instance needs.

Nothing here builds a command out of client text: the browser sends an instance
name and a verb, both of which are checked against this module's own inventory
before anything is executed.
"""

import os
import re
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
# `or` rather than a get() default: systemd hands us the key with an empty
# value when the .env leaves it blank, and empty means "use the default".
RC_DIR = os.environ.get("STATUS_RC_DIR") or os.path.join(
    REPO_ROOT, "services", "AI", "claudeRcAI"
)
# `make start` installs a unit, reloads systemd and waits for it: slower than a
# probe, and worth waiting for rather than reporting a false failure.
MAKE_TIMEOUT = float(os.environ.get("STATUS_RC_TIMEOUT") or "180")

# The instance name becomes a unit name, a file name and a make variable, so
# keep it to the intersection all three are happy with.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
# The verbs the cockpit is allowed to hand to the Makefile. `status` changes
# nothing, so it is also the safe one to prove the plumbing with.
VERBS = ("start", "restart", "stop", "upgrade", "status")
SPAWN_MODES = ("worktree", "same-dir", "session")
PERMISSION_MODES = (
    "default",
    "acceptEdits",
    "auto",
    "plan",
    "dontAsk",
    "bypassPermissions",
)
DEFAULT_LABEL = "default"

# Defaults the Makefile applies when a key is missing from the env file; the
# cockpit shows the same values so the page matches what would actually run.
DEFAULTS = {
    "RC_WORKDIR": REPO_ROOT,
    "RC_SPAWN_MODE": "worktree",
    "RC_CAPACITY": "32",
    "RC_PERMISSION_MODE": "auto",
    "RC_SESSION_PREFIX": "homelab",
    "RC_SESSION_NAME": "homelab",
}


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
def unit_for(name):
    return "claude-rc-ai-%s" % name if name else "claude-rc-ai"


def env_file_for(name):
    return os.path.join(RC_DIR, ".env.%s" % name if name else ".env")


def config_section_for(name):
    """Section the cockpit registers this instance under in services.conf."""
    return "claude-rc-%s" % name if name else "claude-rc-ai"


def _read_env(path):
    """Parse the RC_* keys out of an env file (systemd-style KEY=value)."""
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return values


def _systemd_state(unit):
    """(state, detail, scope) for a unit, looking in both systemd scopes."""
    for scope, prefix in (("user", ["systemctl", "--user"]), ("system", ["systemctl"])):
        try:
            out = subprocess.run(
                prefix + ["show", unit, "--no-page",
                          "--property=LoadState,ActiveState,SubState,UnitFileState"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        props = dict(
            line.split("=", 1) for line in out.strip().splitlines() if "=" in line
        )
        if props.get("LoadState") in ("", "not-found", None):
            continue
        active = props.get("ActiveState", "unknown")
        state = {"active": "up", "failed": "down", "activating": "warn"}.get(
            active, "down" if active == "inactive" else "unknown"
        )
        detail = "%s (%s)" % (active, props.get("SubState", "?"))
        if props.get("UnitFileState"):
            detail += " · %s" % props["UnitFileState"]
        return state, detail, scope
    return "unknown", "no unit installed", ""


_sudo_cache = {"at": 0.0, "ok": False}


def _privileged():
    """Whether this process can touch system units without a password prompt.

    Cached: this is asked once per instance per page load and the answer only
    changes when sudoers does.
    """
    if time.time() - _sudo_cache["at"] < 60:
        return _sudo_cache["ok"]
    try:
        ok = subprocess.run(
            ["sudo", "-n", "true"], capture_output=True, timeout=5
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    _sudo_cache.update(at=time.time(), ok=ok)
    return ok


def _names():
    """Every instance the directory knows about, default first.

    Both `.env.<name>` and `.env.<name>.example` count: the Makefile seeds the
    former from the latter, so a workspace that only has a template is still an
    instance you can start.
    """
    names = [""]
    for entry in sorted(os.listdir(RC_DIR) if os.path.isdir(RC_DIR) else []):
        if not entry.startswith(".env.") or entry == ".env.example":
            continue
        name = entry[len(".env."):]
        if name.endswith(".example"):
            name = name[: -len(".example")]
        if name and name not in names and NAME_RE.match(name):
            names.append(name)
    return names


def describe(name):
    env_path = env_file_for(name)
    values = _read_env(env_path)
    unit = unit_for(name)
    state, detail, scope = _systemd_state(unit)
    workspace = values.get("RC_WORKDIR", DEFAULTS["RC_WORKDIR"])
    return {
        "name": name,
        "label": name or DEFAULT_LABEL,
        "unit": unit,
        "env_file": os.path.relpath(env_path, REPO_ROOT),
        "has_env": os.path.isfile(env_path),
        "workspace": workspace,
        "workspace_exists": os.path.isdir(workspace),
        "spawn": values.get("RC_SPAWN_MODE", DEFAULTS["RC_SPAWN_MODE"]),
        "capacity": values.get("RC_CAPACITY", DEFAULTS["RC_CAPACITY"]),
        "permission": values.get("RC_PERMISSION_MODE", DEFAULTS["RC_PERMISSION_MODE"]),
        "session": values.get("RC_SESSION_NAME", DEFAULTS["RC_SESSION_NAME"]),
        "prefix": values.get("RC_SESSION_PREFIX", DEFAULTS["RC_SESSION_PREFIX"]),
        "state": state,
        "detail": detail,
        "scope": scope,
        # A system unit needs root to start or stop. Without passwordless sudo
        # the API cannot do it, but the terminal can - it can ask for the
        # password - so the page offers that route instead of failing silently.
        "needs_sudo": scope == "system" and not _privileged(),
        # The default instance is this repo's own always-on session: it is
        # configured in git, not from the browser.
        "removable": bool(name),
    }


def instances():
    return [describe(name) for name in _names()]


def known(name):
    return name in _names()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_name(name):
    if not NAME_RE.match(name or ""):
        return "Use 1-32 characters: lowercase letters, digits and dashes."
    if name in _names():
        return "An instance named %r already exists." % name
    return ""


def validate_workspace(raw, spawn="worktree"):
    """Check a workspace path the way `make start` will.

    Returns {ok, path, message}: `path` is what would be written to
    RC_WORKDIR, which is always absolute so systemd and Claude agree on one
    identity for the directory.
    """
    raw = (raw or "").strip()
    if not raw:
        return {"ok": False, "path": "", "message": "Give the workspace directory."}

    path = os.path.expanduser(raw)
    if not os.path.isabs(path):
        path = os.path.join(REPO_ROOT, path)
    path = os.path.realpath(path)

    if not os.path.exists(path):
        return {"ok": False, "path": path, "message": "%s does not exist." % path}
    if not os.path.isdir(path):
        return {"ok": False, "path": path, "message": "%s is not a directory." % path}
    if not os.access(path, os.R_OK | os.X_OK):
        return {"ok": False, "path": path, "message": "%s is not readable." % path}
    if spawn == "worktree" and not os.path.isdir(os.path.join(path, ".git")):
        return {
            "ok": False,
            "path": path,
            "message": "%s is not a git repository, so spawn mode 'worktree' cannot "
                       "branch it. Use 'same-dir' instead." % path,
        }

    taken = [i["label"] for i in instances() if os.path.realpath(i["workspace"]) == path]
    note = ""
    if taken:
        note = "Already served by: %s. A second server on one directory is " \
               "allowed but rarely what you want." % ", ".join(taken)
    return {"ok": True, "path": path, "message": note}


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def command_for(verb, name):
    """The exact make invocation for a verb, also shown to the user."""
    suffix = " INSTANCE=%s" % name if name else ""
    return "make -C %s %s%s" % (os.path.relpath(RC_DIR, REPO_ROOT), verb, suffix)


def run(verb, name):
    """Run one Makefile target for one instance and report what it printed."""
    if verb not in VERBS:
        return {"ok": False, "output": "unknown action %r" % verb}
    if not known(name):
        return {"ok": False, "output": "unknown instance %r" % name}

    argv = ["make", "-C", RC_DIR, verb]
    if name:
        argv.append("INSTANCE=%s" % name)
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=MAKE_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "%s timed out after %ds" % (verb, MAKE_TIMEOUT)}
    except OSError as exc:
        return {"ok": False, "output": "could not run make: %s" % exc}

    output = (done.stdout + done.stderr).strip() or "(no output)"
    return {"ok": done.returncode == 0, "output": output}


ENV_TEMPLATE = """\
# ------------------------------------------------------------------------------
# Claude Remote Control - `{name}` instance
#
# Created from the homelab cockpit. Started with `make start INSTANCE={name}`,
# which installs the unit `{unit}` alongside the
# default `claude-rc-ai`. One Remote Control process serves exactly one
# directory, which is the only reason this instance exists.
#
# Same rules as .env.example: RC_* keys only, no secrets - Remote Control
# authenticates with the credentials already in ~/.claude.
# ------------------------------------------------------------------------------

# The directory this server hosts sessions in.
RC_WORKDIR={workspace}

# worktree - each on-demand session gets its own git worktree
# same-dir - every session shares RC_WORKDIR
# session  - one session per connection
RC_SPAWN_MODE={spawn}

# Max concurrent sessions hosted by this server.
RC_CAPACITY={capacity}

RC_PERMISSION_MODE={permission}
RC_SESSION_PREFIX={prefix}
RC_SESSION_NAME={session}
"""


def create(name, workspace, spawn, capacity, permission, session, config_path=None):
    """Write a new instance's env files, start it, and put it on the page."""
    problem = validate_name(name)
    if problem:
        return {"ok": False, "message": problem, "output": ""}
    if spawn not in SPAWN_MODES:
        return {"ok": False, "message": "Unknown spawn mode %r." % spawn, "output": ""}
    if permission not in PERMISSION_MODES:
        return {"ok": False, "message": "Unknown permission mode %r." % permission,
                "output": ""}
    try:
        capacity = str(int(capacity))
    except (TypeError, ValueError):
        return {"ok": False, "message": "Capacity must be a number.", "output": ""}

    checked = validate_workspace(workspace, spawn)
    if not checked["ok"]:
        return {"ok": False, "message": checked["message"], "output": ""}

    body = ENV_TEMPLATE.format(
        name=name,
        unit=unit_for(name),
        workspace=checked["path"],
        spawn=spawn,
        capacity=capacity,
        permission=permission,
        prefix=session or name,
        session=session or name,
    )
    # The template is what makes the instance reproducible on a fresh machine
    # (the real env file is git-ignored), so both are written.
    for path in (env_file_for(name) + ".example", env_file_for(name)):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)

    result = run("start", name)
    if result["ok"] and config_path:
        register(name, checked["path"], config_path)
    return {
        "ok": result["ok"],
        "message": "Started %s in %s." % (unit_for(name), checked["path"])
        if result["ok"] else "Wrote the env files, but `make start` failed.",
        "output": result["output"],
    }


def delete(name, config_path=None):
    """Stop an instance, unregister it, and remove the files that define it."""
    if not name or not known(name):
        return {"ok": False, "message": "Unknown instance %r." % name, "output": ""}

    result = run("stop", name)
    removed = []
    for path in (env_file_for(name), env_file_for(name) + ".example"):
        if os.path.isfile(path):
            os.remove(path)
            removed.append(os.path.basename(path))
    if config_path:
        unregister(name, config_path)
    return {
        "ok": result["ok"],
        "message": "Removed %s%s." % (
            unit_for(name), " and " + ", ".join(removed) if removed else ""
        ),
        "output": result["output"],
    }


# --------------------------------------------------------------------------- #
# services.conf registration
# --------------------------------------------------------------------------- #
# AGENTS.md §6: a unit that exists and is not on the page does not exist. The
# cockpit therefore edits the inventory as plain text - configparser would
# rewrite the file and take every comment in it with it.
def register(name, workspace, config_path):
    section = config_section_for(name)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    if ("[%s]" % section) in text:
        return False

    where = os.path.relpath(workspace, REPO_ROOT)
    if where.startswith(".."):
        where = workspace
    block = (
        "\n# Created from the cockpit: one Remote Control process per workspace.\n"
        "[%s]\n"
        "group = AI\n"
        "type = systemd\n"
        "pinned = 1\n"
        "unit = %s\n"
        "icon = claude\n"
        "remote = https://claude.ai/code\n"
        "note = always-on %s workspace session\n"
        "dir = %s\n" % (section, unit_for(name), name, where)
    )
    with open(config_path, "a", encoding="utf-8") as handle:
        handle.write(block)
    return True


def unregister(name, config_path):
    """Drop the instance's section, and the comment block that introduces it."""
    section = "[%s]" % config_section_for(name)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines(keepends=True)
    except OSError:
        return False

    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == section)
    except StopIteration:
        return False

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

    # Exactly one blank line where the section was - and none at all when it
    # was the last thing in the file.
    tail = lines[end:]
    while tail and not tail[0].strip():
        tail.pop(0)
    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines[:head] + (["\n"] if tail else []) + tail))
    return True
