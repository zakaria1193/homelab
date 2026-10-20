"""Shared lifecycle for the cockpit's Remote Control instances.

Claude and Antigravity Remote Control are both "one process serves one
directory, every extra workspace is another instance": another `.env.<name>`
next to the service's own `.env`, another systemd unit, another section in
`services.conf`. This module holds that one algorithm - inventory, `describe`,
validation, `run`, `create`, `delete`, `register`, `unregister` - and takes a
small `Kind` config object that supplies everything that differs between the
two: directory, unit and section naming, the env file template, the allowed
verbs, how systemd is checked, and the extra fields and checks each kind adds.

`claude_rc.py` and `antigravity_rc.py` each build one `Kind` and re-export
these functions bound to it, under their original public names, so neither the
handler nor the pages need to change.
"""

import os
import re
import subprocess
import time

from . import conf_edit

# The instance name becomes a unit name, a file name and a make variable, so
# keep it to the intersection all three are happy with. Shared by both kinds.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class Kind:
    """Everything one Remote Control flavour configures the shared code with."""

    def __init__(
        self,
        *,
        dir,                      # instance directory (holds .env.<name> files)
        repo_root,
        make_timeout,
        verbs,
        default_label,
        unit_for,                  # name -> unit string, as run by systemd
        config_section_for,        # name -> services.conf section name
        systemd_state,             # unit -> (state, detail, scope)
        env_template,              # str.format template for a new .env
        describe_extra=None,       # (name, values, scope) -> dict, with "workspace"
        display_unit=None,         # unit -> unit string shown on the page
        validate_name_extra=None,  # name -> message or ""
        validate_workspace_extra=None,  # (path, **kwargs) -> message or "" (blocking)
        workspace_note=None,       # (path, **kwargs) -> note or "" (non-blocking)
        build_env_kwargs=None,     # (name, unit, workspace, extra) -> dict
        validate_create_extra=None,  # extra dict -> (ok, message, normalized)
        register_fields=None,      # (name, unit, where) -> (fields, comment_lines)
    ):
        self.dir = dir
        self.repo_root = repo_root
        self.make_timeout = make_timeout
        self.verbs = verbs
        self.default_label = default_label
        self.unit_for = unit_for
        self.config_section_for = config_section_for
        self.systemd_state = systemd_state
        self.env_template = env_template
        self.describe_extra = describe_extra or (
            lambda name, values, scope: {"workspace": ""}
        )
        self.display_unit = display_unit or (lambda unit: unit)
        self.validate_name_extra = validate_name_extra or (lambda name: "")
        self.validate_workspace_extra = validate_workspace_extra or (
            lambda path, **kwargs: ""
        )
        self.workspace_note = workspace_note or (lambda path, **kwargs: "")
        self.build_env_kwargs = build_env_kwargs or (
            lambda name, unit, workspace, extra: {}
        )
        self.validate_create_extra = validate_create_extra or (
            lambda extra: (True, "", extra)
        )
        self.register_fields = register_fields or (
            lambda name, unit, where: ([], [])
        )


def env_file_for(kind, name):
    return os.path.join(kind.dir, ".env.%s" % name if name else ".env")


def read_env(path):
    """Parse the KEY=value lines out of an env file (systemd-style)."""
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


def names(kind):
    """Every instance the directory knows about, default first.

    Both `.env.<name>` and `.env.<name>.example` count: the Makefile seeds the
    former from the latter, so a workspace that only has a template is still an
    instance you can start.
    """
    result = [""]
    for entry in sorted(os.listdir(kind.dir) if os.path.isdir(kind.dir) else []):
        if not entry.startswith(".env.") or entry == ".env.example":
            continue
        name = entry[len(".env."):]
        if name.endswith(".example"):
            name = name[: -len(".example")]
        if name and name not in result and NAME_RE.match(name):
            result.append(name)
    return result


def describe(kind, name=""):
    env_path = env_file_for(kind, name)
    values = read_env(env_path)
    unit = kind.unit_for(name)
    state, detail, scope = kind.systemd_state(unit)
    extra = kind.describe_extra(name, values, scope)
    workspace = extra.pop("workspace")
    result = {
        "name": name,
        "label": name or kind.default_label,
        "unit": kind.display_unit(unit),
        "env_file": os.path.relpath(env_path, kind.repo_root),
        "has_env": os.path.isfile(env_path),
        "workspace": workspace,
        "workspace_exists": os.path.isdir(workspace),
        "state": state,
        "detail": detail,
        "scope": scope,
        # The default instance is this repo's own always-on session: it is
        # configured in git, not from the browser.
        "removable": bool(name),
    }
    result.update(extra)
    return result


def instances(kind):
    return [describe(kind, name) for name in names(kind)]


def known(kind, name):
    return name in names(kind)


def validate_name(kind, name):
    if not NAME_RE.match(name or ""):
        return "Use 1-32 characters: lowercase letters, digits and dashes."
    if name in names(kind):
        return "An instance named %r already exists." % name
    extra = kind.validate_name_extra(name)
    if extra:
        return extra
    return ""


def deduce_name_from_dir(path):
    path = os.path.realpath(os.path.expanduser(str(path or "").strip()))
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if git_root:
            base = os.path.basename(git_root)
            return re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-")
    except Exception:
        pass
    base = os.path.basename(path.rstrip("/"))
    return re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-") or "workspace"


def validate_workspace(kind, raw, **extra_kwargs):
    """Check a workspace path the way `make start` will.

    Returns {ok, path, message, deduced_name}: `path` is what would be written
    to the env file, always absolute so systemd and the daemon agree on one
    identity for the directory.
    """
    raw = (raw or "").strip()
    if not raw:
        return {"ok": False, "path": "", "message": "Give the workspace directory."}

    path = os.path.expanduser(raw)
    if not os.path.isabs(path):
        path = os.path.join(kind.repo_root, path)
    path = os.path.realpath(path)

    if not os.path.exists(path):
        return {"ok": False, "path": path, "message": "%s does not exist." % path}
    if not os.path.isdir(path):
        return {"ok": False, "path": path, "message": "%s is not a directory." % path}
    if not os.access(path, os.R_OK | os.X_OK):
        return {"ok": False, "path": path, "message": "%s is not readable." % path}

    instances_fn = lambda: instances(kind)  # noqa: E731
    problem = kind.validate_workspace_extra(path, instances_fn=instances_fn, **extra_kwargs)
    if problem:
        return {"ok": False, "path": path, "message": problem}

    note = kind.workspace_note(path, instances_fn=instances_fn, **extra_kwargs)
    return {
        "ok": True,
        "path": path,
        "message": note,
        "deduced_name": deduce_name_from_dir(path),
    }


def command_for(kind, verb, name):
    """The exact make invocation for a verb, also shown to the user."""
    suffix = " INSTANCE=%s" % name if name else ""
    return "make -C %s %s%s" % (os.path.relpath(kind.dir, kind.repo_root), verb, suffix)


def run(kind, verb, name=""):
    """Run one Makefile target for one instance and report what it printed."""
    if verb not in kind.verbs:
        return {"ok": False, "output": "unknown action %r" % verb}
    if not known(kind, name):
        return {"ok": False, "output": "unknown instance %r" % name}

    argv = ["make", "-C", kind.dir, verb]
    if name:
        argv.append("INSTANCE=%s" % name)
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=kind.make_timeout
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "%s timed out after %ds" % (verb, kind.make_timeout)}
    except OSError as exc:
        return {"ok": False, "output": "could not run make: %s" % exc}

    output = (done.stdout + done.stderr).strip() or "(no output)"
    return {"ok": done.returncode == 0, "output": output}


def create(kind, name, workspace, config_path=None, **extra):
    """Write a new instance's env files, start it, and put it on the page."""
    name = (name or "").strip()
    if not name and workspace:
        name = deduce_name_from_dir(workspace)
    problem = validate_name(kind, name)
    if problem:
        return {"ok": False, "message": problem, "output": ""}

    ok, message, extra = kind.validate_create_extra(extra)
    if not ok:
        return {"ok": False, "message": message, "output": ""}

    checked = validate_workspace(kind, workspace, **extra.get("workspace_kwargs", {}))
    if not checked["ok"]:
        return {"ok": False, "message": checked["message"], "output": ""}

    unit = kind.unit_for(name)
    env_kwargs = kind.build_env_kwargs(name, unit, checked["path"], extra)
    body = kind.env_template.format(**env_kwargs)
    # The template is what makes the instance reproducible on a fresh machine
    # (the real env file is git-ignored), so both are written.
    for path in (env_file_for(kind, name) + ".example", env_file_for(kind, name)):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)

    result = run(kind, "start", name)
    note = ""
    if result["ok"] and config_path:
        registered = register(kind, name, checked["path"], config_path)
        if not registered["ok"]:
            note = " Not added to services.conf: %s" % registered["message"]
    return {
        "ok": result["ok"],
        "message": (
            "Started %s in %s.%s" % (unit, checked["path"], note)
            if result["ok"]
            else "Wrote the env files, but `make start` failed."
        ),
        "output": result["output"],
    }


def delete(kind, name, config_path=None):
    """Stop an instance, unregister it, and remove the files that define it."""
    if not name or not known(kind, name):
        return {"ok": False, "message": "Unknown instance %r." % name, "output": ""}

    result = run(kind, "stop", name)
    removed = []
    for path in (env_file_for(kind, name), env_file_for(kind, name) + ".example"):
        if os.path.isfile(path):
            os.remove(path)
            removed.append(os.path.basename(path))
    if config_path:
        unregister(kind, name, config_path)
    return {
        "ok": result["ok"],
        "message": "Removed %s%s." % (
            kind.unit_for(name), " and " + ", ".join(removed) if removed else ""
        ),
        "output": result["output"],
    }


# --------------------------------------------------------------------------- #
# services.conf registration
# --------------------------------------------------------------------------- #
# AGENTS.md §6: a unit that exists and is not on the page does not exist.
# `conf_edit` is the only code that writes services.conf.
def register(kind, name, workspace, config_path):
    section = kind.config_section_for(name)
    where = os.path.relpath(workspace, kind.repo_root)
    if where.startswith(".."):
        where = workspace
    fields, comment_lines = kind.register_fields(name, kind.unit_for(name), where)
    return conf_edit.add_section(config_path, section, fields, comment_lines=comment_lines)


def unregister(kind, name, config_path):
    """Drop the instance's section, and the comment block that introduces it."""
    return conf_edit.remove_section(config_path, kind.config_section_for(name))


def systemd_state_both_scopes(unit):
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


def systemd_state_user_scope(unit):
    """(state, detail, scope) for a unit in user scope, with its MainPID."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", unit, "--no-page",
             "--property=LoadState,ActiveState,SubState,UnitFileState,MainPID"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "unknown", "failed to check systemd", "user"

    props = dict(
        line.split("=", 1) for line in out.strip().splitlines() if "=" in line
    )
    if props.get("LoadState") in ("", "not-found", None):
        return "down", "no unit installed", "user"

    active = props.get("ActiveState", "unknown")
    state = {"active": "up", "failed": "down", "activating": "warn"}.get(
        active, "down" if active == "inactive" else "unknown"
    )
    pid = props.get("MainPID", "0")
    pid_str = " · PID %s" % pid if pid and pid != "0" else ""
    detail = "%s (%s)%s" % (active, props.get("SubState", "?"), pid_str)
    return state, detail, "user"


def sudo_cache(ttl=60):
    """A `(check)` closure over a small cache: asked once per instance per page
    load, and the answer only changes when sudoers does."""
    cache = {"at": 0.0, "ok": False}

    def check():
        if time.time() - cache["at"] < ttl:
            return cache["ok"]
        try:
            ok = subprocess.run(
                ["sudo", "-n", "true"], capture_output=True, timeout=5
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        cache.update(at=time.time(), ok=ok)
        return ok

    return check
