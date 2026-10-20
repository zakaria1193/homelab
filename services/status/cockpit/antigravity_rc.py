"""Antigravity Remote Control instances, driven from the cockpit.

Matches the architecture and lifecycle of claude_rc.py: both configure the
shared `rc_instances` module with their own naming, env template and checks.
- Reads instances off disk (.env.<name>)
- Inspects systemd user units (agy-remote-control[-<name>])
- Drives the Makefile targets for start, stop, restart, upgrade, logs
- Creates and deletes instances and registers them in services.conf
"""

import os

from . import rc_instances
from .config import REPO_ROOT

AGY_RC_DIR = os.environ.get("STATUS_AGY_RC_DIR") or os.path.join(
    REPO_ROOT, "services", "AI", "antigravityRcAI"
)
MAKE_TIMEOUT = float(os.environ.get("STATUS_RC_TIMEOUT") or "60")
NAME_RE = rc_instances.NAME_RE
VERBS = ("start", "restart", "stop", "upgrade", "status", "doctor")
DEFAULT_LABEL = "default"

DEFAULTS = {
    "AGY_RC_WORKDIR": REPO_ROOT,
    "AGY_RC_NAME": "homelab",
    "AGY_RC_PORT": "4400",
}


def unit_for(name=""):
    return "agy-remote-control-%s" % name if name else "antigravity-cli-daemon"


def env_file_for(name):
    return rc_instances.env_file_for(_KIND, name)


def config_section_for(name):
    return "antigravity-rc-%s" % name if name else "antigravity-rc"


def _describe_extra(name, values, scope):
    workspace = values.get("AGY_RC_WORKDIR", DEFAULTS["AGY_RC_WORKDIR"])
    instance_name = values.get("AGY_RC_NAME", name or DEFAULTS["AGY_RC_NAME"])
    port = values.get("AGY_RC_PORT", DEFAULTS["AGY_RC_PORT"] if not name else "")
    log_file = os.path.expanduser(
        "~/.antigravity/agy_daemon%s.log" % ("_" + name if name else "")
    )
    return {
        "workspace": workspace,
        "instance_name": instance_name,
        "hub_port": port or "auto",
        "dashboard_url": "https://antigravity.google.com/",
        "log_file": log_file,
    }


def _display_unit(unit):
    return "%s.service" % unit


ENV_TEMPLATE = """\
# ------------------------------------------------------------------------------
# Antigravity Remote Control - `{name}` instance
#
# Created from the homelab cockpit. Started with `make start INSTANCE={name}`,
# which installs the user unit `{unit}`.
# ------------------------------------------------------------------------------

AGY_RC_WORKDIR={workspace}
AGY_RC_NAME={instance_name}
AGY_RC_PORT={port}
"""


def _build_env_kwargs(name, unit, workspace, extra):
    return {
        "name": name,
        "unit": unit,
        "workspace": workspace,
        "instance_name": extra.get("session") or name,
        "port": extra.get("port") or "",
    }


def _register_fields(name, unit, where):
    fields = [
        ("group", "AI"),
        ("type", "systemd-user"),
        ("pinned", "1"),
        ("unit", unit),
        ("icon", "antigravity"),
        ("remote", "https://antigravity.google.com/"),
        ("alt_link", "/antigravity-rc"),
        ("alt_label", "server"),
        ("logs", "file:~/.antigravity/agy_daemon_%s.log" % name),
        ("note", "always-on Antigravity %s workspace session" % name),
        ("dir", where),
    ]
    comment_lines = ["# Created from the cockpit: Antigravity instance for %s" % name]
    return fields, comment_lines


_KIND = rc_instances.Kind(
    dir=AGY_RC_DIR,
    repo_root=REPO_ROOT,
    make_timeout=MAKE_TIMEOUT,
    verbs=VERBS,
    default_label=DEFAULT_LABEL,
    unit_for=unit_for,
    config_section_for=config_section_for,
    systemd_state=rc_instances.systemd_state_user_scope,
    env_template=ENV_TEMPLATE,
    describe_extra=_describe_extra,
    display_unit=_display_unit,
    build_env_kwargs=_build_env_kwargs,
    register_fields=_register_fields,
)


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
def describe(name=""):
    return rc_instances.describe(_KIND, name)


def instances():
    return rc_instances.instances(_KIND)


def known(name):
    return rc_instances.known(_KIND, name)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_name(name):
    return rc_instances.validate_name(_KIND, name)


def deduce_name_from_dir(path):
    return rc_instances.deduce_name_from_dir(path)


def validate_workspace(raw):
    return rc_instances.validate_workspace(_KIND, raw)


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def run(verb, name=""):
    return rc_instances.run(_KIND, verb, name)


def create(name, workspace, port="", session="", config_path=None):
    return rc_instances.create(
        _KIND, name, workspace, config_path=config_path, port=port, session=session,
    )


def delete(name, config_path=None):
    return rc_instances.delete(_KIND, name, config_path=config_path)


def register(name, workspace, config_path):
    return rc_instances.register(_KIND, name, workspace, config_path)


def unregister(name, config_path):
    return rc_instances.unregister(_KIND, name, config_path)
