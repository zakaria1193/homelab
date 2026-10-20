"""Claude Remote Control instances, driven from the cockpit.

One `claude remote-control` process serves exactly one directory, so every extra
workspace is another instance: another `.env.<name>` next to
`services/AI/claudeRcAI/.env`, and another `claude-rc-ai-<name>` unit. This
module configures `rc_instances` (the shared lifecycle both RC kinds use) with
Claude's own naming, env template and extra checks.

Nothing here builds a command out of client text: the browser sends an instance
name and a verb, both of which are checked against this module's own inventory
before anything is executed.
"""

import functools
import os

from . import rc_instances
from .config import REPO_ROOT

# `or` rather than a get() default: systemd hands us the key with an empty
# value when the .env leaves it blank, and empty means "use the default".
RC_DIR = os.environ.get("STATUS_RC_DIR") or os.path.join(
    REPO_ROOT, "services", "AI", "claudeRcAI"
)
# `make start` installs a unit, reloads systemd and waits for it: slower than a
# probe, and worth waiting for rather than reporting a false failure.
MAKE_TIMEOUT = float(os.environ.get("STATUS_RC_TIMEOUT") or "180")

NAME_RE = rc_instances.NAME_RE
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
# The unnamed instance is this repo's own always-on server, so the page names it
# after the workspace rather than calling it "default" - every other card is
# named after its workspace too.
DEFAULT_LABEL = "homelab"

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


def unit_for(name):
    return "claude-rc-ai-%s" % name if name else "claude-rc-ai"


def env_file_for(name):
    return rc_instances.env_file_for(_KIND, name)


def config_section_for(name):
    """Section the cockpit registers this instance under in services.conf."""
    return "claude-rc-%s" % name if name else "claude-rc-ai"


_sudo_privileged = rc_instances.sudo_cache()


def _describe_extra(name, values, scope):
    workspace = values.get("RC_WORKDIR", DEFAULTS["RC_WORKDIR"])
    return {
        "workspace": workspace,
        "spawn": values.get("RC_SPAWN_MODE", DEFAULTS["RC_SPAWN_MODE"]),
        "capacity": values.get("RC_CAPACITY", DEFAULTS["RC_CAPACITY"]),
        "permission": values.get("RC_PERMISSION_MODE", DEFAULTS["RC_PERMISSION_MODE"]),
        "session": values.get("RC_SESSION_NAME", DEFAULTS["RC_SESSION_NAME"]),
        "prefix": values.get("RC_SESSION_PREFIX", DEFAULTS["RC_SESSION_PREFIX"]),
        # A system unit needs root to start or stop. Without passwordless sudo
        # the API cannot do it, but the terminal can - it can ask for the
        # password - so the page offers that route instead of failing silently.
        "needs_sudo": scope == "system" and not _sudo_privileged(),
    }


def _validate_name_extra(name):
    if name == DEFAULT_LABEL:
        return "%r is the name the default instance goes by." % DEFAULT_LABEL
    return ""


def _validate_workspace_extra(path, spawn="worktree", **_kwargs):
    if spawn == "worktree" and not os.path.isdir(os.path.join(path, ".git")):
        return (
            "%s is not a git repository, so spawn mode 'worktree' cannot "
            "branch it. Use 'same-dir' instead." % path
        )
    return ""


def _workspace_note(path, instances_fn, **_kwargs):
    taken = [i["label"] for i in instances_fn() if os.path.realpath(i["workspace"]) == path]
    if not taken:
        return ""
    return (
        "Already served by: %s. A second server on one directory is "
        "allowed but rarely what you want." % ", ".join(taken)
    )


def _validate_create_extra(extra):
    spawn = extra.get("spawn", "worktree")
    permission = extra.get("permission", "auto")
    if spawn not in SPAWN_MODES:
        return False, "Unknown spawn mode %r." % spawn, extra
    if permission not in PERMISSION_MODES:
        return False, "Unknown permission mode %r." % permission, extra
    try:
        extra["capacity"] = str(int(extra.get("capacity", DEFAULTS["RC_CAPACITY"])))
    except (TypeError, ValueError):
        return False, "Capacity must be a number.", extra
    extra["workspace_kwargs"] = {"spawn": spawn}
    return True, "", extra


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


def _build_env_kwargs(name, unit, workspace, extra):
    session = extra.get("session") or name
    return {
        "name": name,
        "unit": unit,
        "workspace": workspace,
        "spawn": extra.get("spawn", "worktree"),
        "capacity": extra.get("capacity", DEFAULTS["RC_CAPACITY"]),
        "permission": extra.get("permission", "auto"),
        "prefix": session,
        "session": session,
    }


def _register_fields(name, unit, where):
    fields = [
        ("group", "AI"),
        ("type", "systemd"),
        ("pinned", "1"),
        ("unit", unit),
        ("icon", "claude"),
        ("remote", "https://claude.ai/code"),
        ("note", "always-on %s workspace session" % name),
        ("dir", where),
    ]
    comment_lines = ["# Created from the cockpit: one Remote Control process per workspace."]
    return fields, comment_lines


_KIND = rc_instances.Kind(
    dir=RC_DIR,
    repo_root=REPO_ROOT,
    make_timeout=MAKE_TIMEOUT,
    verbs=VERBS,
    default_label=DEFAULT_LABEL,
    unit_for=unit_for,
    config_section_for=config_section_for,
    systemd_state=rc_instances.systemd_state_both_scopes,
    env_template=ENV_TEMPLATE,
    describe_extra=_describe_extra,
    validate_name_extra=_validate_name_extra,
    validate_workspace_extra=_validate_workspace_extra,
    workspace_note=_workspace_note,
    build_env_kwargs=_build_env_kwargs,
    validate_create_extra=_validate_create_extra,
    register_fields=_register_fields,
)


# Thin re-exports, bound to Claude's `_KIND`, under the names the handler and
# the pages already import. `create` and `validate_workspace` stay as defs:
# their extra fields (spawn, capacity, permission, session) are Claude-only.
describe = functools.partial(rc_instances.describe, _KIND)
instances = functools.partial(rc_instances.instances, _KIND)
known = functools.partial(rc_instances.known, _KIND)
validate_name = functools.partial(rc_instances.validate_name, _KIND)
deduce_name_from_dir = rc_instances.deduce_name_from_dir
command_for = functools.partial(rc_instances.command_for, _KIND)
run = functools.partial(rc_instances.run, _KIND)
delete = functools.partial(rc_instances.delete, _KIND)
# AGENTS.md §6: a unit that exists and is not on the page does not exist.
# `conf_edit` is the only code that writes services.conf.
register = functools.partial(rc_instances.register, _KIND)
unregister = functools.partial(rc_instances.unregister, _KIND)


def validate_workspace(raw, spawn="worktree"):
    return rc_instances.validate_workspace(_KIND, raw, spawn=spawn)


def create(name, workspace, spawn, capacity, permission, session, config_path=None):
    """Write a new instance's env files, start it, and put it on the page."""
    return rc_instances.create(
        _KIND, name, workspace,
        config_path=config_path,
        spawn=spawn, capacity=capacity, permission=permission, session=session,
    )
