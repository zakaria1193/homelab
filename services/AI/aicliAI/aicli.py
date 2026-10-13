#!/usr/bin/env python3
"""aicli - the one place every homelab caller reaches `claude` and `agy`.

It only builds an argv and execs the real, unmodified CLI under the user's
own login. It never reads, stores or forwards OAuth tokens, and it never
calls a vendor backend itself. See ticket homelab-0013 for the why.

`AICLI_CONFIG` points this module at a different `aicli.toml` (tests use it).
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = ("claude", "agy")
TIERS = ("low", "default", "deep")
EFFORTS = ("low", "medium", "high")
# The tmux wrapper (tools/optiplex-ai-tmux.sh) symlinks `claude`/`agy` here, so
# a PATH search that walked into them would just exec itself in a loop.
SKIP_DIRS = {"/usr/local/bin", "/usr/local/sbin"}

UNKNOWN = "unknown"
OK = "ok"


def default_config_path():
    # __file__ is the symlink path when run via the ~/.local/bin/aicli link
    # `make install` creates, so resolve it before finding aicli.toml next to
    # the real aicli.py in this repo.
    return Path(__file__).resolve().with_name("aicli.toml")


def load_config(path=None):
    path = Path(path) if path else Path(os.environ.get("AICLI_CONFIG") or default_config_path())
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"aicli: invalid config {path}: {e}", file=sys.stderr)
        raise SystemExit(2)


def resolve_bin(config, tool):
    """The real binary for `tool`: the configured `bin` if executable, else
    the first PATH match that isn't the tmux-wrapper symlink directory."""
    cfg = config[tool]
    configured = os.path.expanduser(cfg.get("bin", ""))
    if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
        return configured
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or d in SKIP_DIRS:
            continue
        candidate = os.path.join(d, tool)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def build_argv(config, tool, tier="default", effort=None, extra=None):
    """The argv `run` would exec, or None if the binary can't be found."""
    cfg = config[tool]
    bin_path = resolve_bin(config, tool)
    if bin_path is None:
        return None
    extra = list(extra or [])
    argv = [bin_path, *cfg.get("args", [])]

    model_flag = cfg.get("model_flag", "")
    model = cfg.get("tiers", {}).get(tier)
    if model and model_flag and model_flag not in extra:
        argv += [model_flag, model]

    effort_flag = cfg.get("effort_flag", "")
    if effort and effort_flag and effort_flag not in extra:
        argv += [effort_flag, effort]

    argv += extra
    return argv


def _strip_dashdash(args):
    return args[1:] if args[:1] == ["--"] else args


# ---- /usage, moved from services/status/usage.py -------------------------

# "Current session: 76% used · resets Aug 25, 1:09am (Europe/Paris)"
_CLAUDE_SESSION_RE = re.compile(
    r"(?im)^Current session:\s*(\d+)%\s*used.*?resets\s+(.+?)\s*$"
)
# "Current week (all models): 6% used · resets Aug 31, 6:59pm (Europe/Paris)"
_CLAUDE_WEEK_RE = re.compile(
    r"(?im)^Current week[^:\n]*:\s*(\d+)%\s*used.*?resets\s+(.+?)\s*$"
)


def _run_usage(bin_path, timeout):
    try:
        return subprocess.run(
            [bin_path, "-p", "/usage"], capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _claude_usage(config, timeout):
    bin_path = resolve_bin(config, "claude")
    if bin_path is None:
        return {"state": UNKNOWN, "detail": "claude CLI not found", "bars": {}}

    result = _run_usage(bin_path, timeout)
    if result is None:
        return {"state": UNKNOWN, "detail": "claude -p /usage timed out", "bars": {}}
    if result.returncode != 0:
        return {"state": UNKNOWN, "detail": "claude -p /usage failed", "bars": {}}

    text = result.stdout
    bars = {}
    session = _CLAUDE_SESSION_RE.search(text)
    if session:
        bars["five_hour"] = {"pct": int(session.group(1)), "reset": session.group(2)}
    week = _CLAUDE_WEEK_RE.search(text)
    if week:
        bars["weekly"] = {"pct": int(week.group(1)), "reset": week.group(2)}

    if not bars:
        return {"state": UNKNOWN, "detail": "could not parse /usage output", "bars": {}}
    return {"state": OK, "detail": "", "bars": bars}


# `agy -p "/usage"` prints one tab-separated line per (model group, period):
#   Gemini Models\tWeekly Limit Remaining\t0%\t2026-08-24T21:11:51Z
#   Gemini Models\tFive Hour Limit Remaining\tdisabled\t
# A plan can carry more than one model group - Gemini (the one Antigravity
# actually drives you with) and "Claude and GPT models" (an ancillary,
# separately-metered allowance for picking a different model). They are not
# on the same billing cycle, so Gemini leads when it has a reading for the
# period; the other group only fills in when Gemini doesn't report one.
_AGY_PERIODS = {"Weekly": "weekly", "Five Hour": "five_hour"}
_AGY_PRIMARY_GROUP = "Gemini"


def _agy_usage(config, timeout):
    bin_path = resolve_bin(config, "agy")
    if bin_path is None:
        return {"state": UNKNOWN, "detail": "agy CLI not found", "bars": {}}

    result = _run_usage(bin_path, timeout)
    if result is None:
        return {"state": UNKNOWN, "detail": "agy -p /usage timed out", "bars": {}}
    if result.returncode != 0:
        return {"state": UNKNOWN, "detail": "agy -p /usage failed", "bars": {}}

    bars = {}
    for line in result.stdout.splitlines():
        cols = [c.strip() for c in line.split("\t")]
        if len(cols) < 3:
            continue
        group, label, value = cols[0], cols[1], cols[2]
        reset = cols[3] if len(cols) > 3 else ""
        period = next(
            (key for prefix, key in _AGY_PERIODS.items() if label.startswith(prefix)),
            None,
        )
        if period is None or not value.endswith("%"):
            continue  # "disabled" - no limit to bar for this group/period
        try:
            remaining = int(value.rstrip("%"))
        except ValueError:
            continue
        used = 100 - remaining
        current = bars.get(period)
        is_primary = group.startswith(_AGY_PRIMARY_GROUP)
        was_primary = current is not None and current["group"].startswith(_AGY_PRIMARY_GROUP)
        if current is None or (is_primary and not was_primary):
            bars[period] = {"pct": used, "reset": reset, "group": group}

    if not bars:
        return {"state": UNKNOWN, "detail": "no active limits reported", "bars": {}}
    return {"state": OK, "detail": "", "bars": bars}


def compute_usage(config):
    timeout = config.get("usage_timeout", 30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claude_result, agy_result = pool.map(
            lambda fn: fn(config, timeout), (_claude_usage, _agy_usage)
        )
    return {"claude": claude_result, "agy": agy_result}


# ---- command line ----------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="aicli")
    parser.add_argument("--config", help="path to aicli.toml (default: $AICLI_CONFIG or the repo one)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_which = sub.add_parser("which")
    p_which.add_argument("tool", choices=TOOLS)

    def add_tool_args(p):
        p.add_argument("--tool", required=True, choices=TOOLS)
        p.add_argument("--tier", default="default", choices=TIERS)
        p.add_argument("--effort", choices=EFFORTS)
        p.add_argument("--json", action="store_true")
        p.add_argument("args", nargs=argparse.REMAINDER)

    add_tool_args(sub.add_parser("argv"))
    add_tool_args(sub.add_parser("run"))

    p_usage = sub.add_parser("usage")
    p_usage.add_argument("--json", action="store_true")

    return parser


def cmd_which(args, config):
    bin_path = resolve_bin(config, args.tool)
    if bin_path is None:
        print(f"{args.tool} CLI not found", file=sys.stderr)
        return 1
    print(bin_path)
    return 0


def cmd_argv(args, config):
    extra = _strip_dashdash(args.args)
    argv = build_argv(config, args.tool, args.tier, args.effort, extra)
    if argv is None:
        print(f"{args.tool} CLI not found", file=sys.stderr)
        return 1
    print(json.dumps(argv) if args.json else shlex.join(argv))
    return 0


def cmd_run(args, config):
    extra = _strip_dashdash(args.args)
    argv = build_argv(config, args.tool, args.tier, args.effort, extra)
    if argv is None:
        print(f"{args.tool} CLI not found", file=sys.stderr)
        return 1
    os.execv(argv[0], argv)  # never returns


def cmd_usage(args, config):
    data = compute_usage(config)
    if args.json:
        print(json.dumps(data))
        return 0
    for tool, result in data.items():
        line = f"{tool}: {result['state']}"
        if result["detail"]:
            line += f" ({result['detail']})"
        for period, bar in result["bars"].items():
            line += f" {period}={bar['pct']}% resets {bar['reset']}"
        print(line)
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    handler = {
        "which": cmd_which, "argv": cmd_argv, "run": cmd_run, "usage": cmd_usage,
    }[args.command]
    return handler(args, config)


if __name__ == "__main__":
    sys.exit(main())
