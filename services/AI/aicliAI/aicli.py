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
from datetime import datetime, timezone
from pathlib import Path

TOOLS = ("claude", "agy")
TIERS = ("low", "default", "deep")
EFFORTS = ("low", "medium", "high")
DEFAULT_USAGE_LOG = Path("~/.local/state/aicli/usage.jsonl").expanduser()
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
    if extra and (extra[0] in TOOLS or os.path.basename(extra[0]) in TOOLS):
        extra = extra[1:]

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


# ---- routing layer ---------------------------------------------------------

DEFAULT_CLASSES = {
    "maintenance": {
        "description": "Repository maintenance, CI fixes, security dependency updates",
        "frequency": "Daily/Weekly background batch",
        "tool": "agy",
        "tier": "low",
    },
    "deep-spec": {
        "description": "Complex architecture, multi-file specs, and deep PR reviews",
        "frequency": "Moderate (ticket creation & review)",
        "tool": "claude",
        "tier": "deep",
    },
    "standard-dev": {
        "description": "Standard code implementation, ticket subtask execution",
        "frequency": "High burst during active work",
        "tool": "claude",
        "tier": "default",
    },
    "managerial-audit": {
        "description": "Cross-project status auditing, watchdog, and scheduled scrum reports",
        "frequency": "4 times / day (07:30, 12:00, 17:00, 22:00)",
        "tool": "agy",
        "tier": "low",
    },
    "lightweight-task": {
        "description": "High-throughput data extraction, job scraping, metadata tagging",
        "frequency": "Continuous / On-demand",
        "tool": "agy",
        "tier": "low",
    },
    "interactive-shell": {
        "description": "Direct interactive human terminal sessions",
        "frequency": "On-demand by user",
        "tool": "claude",
        "tier": "default",
    },
}


def default_routes_path(config=None):
    if os.environ.get("AICLI_ROUTES"):
        return Path(os.environ["AICLI_ROUTES"])
    if config and "routes_file" in config:
        return Path(os.path.expanduser(config["routes_file"]))
    config_file = Path(os.environ.get("AICLI_CONFIG") or default_config_path())
    return config_file.with_name("routes.json")


def load_routes(config=None, routes_path=None):
    routes_file = Path(routes_path) if routes_path else default_routes_path(config)
    classes = {k: dict(v) for k, v in DEFAULT_CLASSES.items()}
    if config and "classes" in config and isinstance(config["classes"], dict):
        for name, d in config["classes"].items():
            if isinstance(d, dict):
                classes.setdefault(name, {}).update(d)
    clients = {}
    if config and "routes" in config and isinstance(config["routes"], dict):
        for name, d in config["routes"].items():
            if isinstance(d, dict):
                clients[name] = dict(d)

    if routes_file.is_file():
        try:
            with open(routes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("classes"), dict):
                for name, d in data["classes"].items():
                    if isinstance(d, dict):
                        classes.setdefault(name, {}).update(d)
            if isinstance(data.get("clients"), dict):
                for name, d in data["clients"].items():
                    if isinstance(d, dict):
                        clients.setdefault(name, {}).update(d)
        except (OSError, json.JSONDecodeError) as e:
            print(f"aicli: warning: could not read {routes_file}: {e}", file=sys.stderr)

    return {"classes": classes, "clients": clients}


def save_routes(routes, config=None, routes_path=None):
    routes_file = Path(routes_path) if routes_path else default_routes_path(config)
    routes_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = routes_file.with_suffix(f".tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(routes, f, indent=2)
        f.write("\n")
    os.replace(tmp, routes_file)


def resolve_route(config, client=None, workload_class=None, requested_tool=None,
                  requested_tier=None, requested_effort=None, routes=None):
    if routes is None:
        routes = load_routes(config)
    classes = routes.get("classes") or {}
    clients = routes.get("clients") or {}

    resolved_class = workload_class
    target_tool = None
    target_tier = None
    target_effort = None

    client_entry = clients.get(client) if client else None
    if client_entry:
        if not resolved_class and "class" in client_entry:
            resolved_class = client_entry["class"]
        target_tool = client_entry.get("tool")
        target_tier = client_entry.get("tier")
        target_effort = client_entry.get("effort")

    if resolved_class:
        if resolved_class not in classes:
            known = ", ".join(sorted(classes.keys()))
            raise ValueError(f"unknown workload class {resolved_class!r} (known: {known})")
        cls_def = classes[resolved_class]
        if not target_tool:
            target_tool = cls_def.get("tool")
        if not target_tier:
            target_tier = cls_def.get("tier", "default")
        if not target_effort:
            target_effort = cls_def.get("effort")

    if requested_tool:
        target_tool = requested_tool
    if requested_tier:
        target_tier = requested_tier
    if requested_effort:
        target_effort = requested_effort

    if not target_tool:
        raise ValueError("either --tool, --class, or a known --client is required")

    if target_tool not in TOOLS:
        raise ValueError(f"unknown tool {target_tool!r} (known: {', '.join(TOOLS)})")

    target_tier = target_tier or "default"
    if target_tier not in TIERS:
        raise ValueError(f"unknown tier {target_tier!r} (known: {', '.join(TIERS)})")

    if target_effort and target_effort not in EFFORTS:
        raise ValueError(f"unknown effort {target_effort!r} (known: {', '.join(EFFORTS)})")

    return target_tool, target_tier, target_effort, resolved_class



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


def get_tool_quota(config, tool, timeout=3.0):
    try:
        fn = _claude_usage if tool == "claude" else _agy_usage
        return fn(config, timeout)
    except Exception:
        return {"state": UNKNOWN, "bars": {}}


# ---- command line ----------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="aicli")
    parser.add_argument("--config", help="path to aicli.toml (default: $AICLI_CONFIG or the repo one)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_which = sub.add_parser("which")
    p_which.add_argument("tool", choices=TOOLS)

    def add_tool_args(p):
        p.add_argument("--tool", choices=TOOLS)
        p.add_argument("--tier", choices=TIERS)
        p.add_argument("--effort", choices=EFFORTS)
        p.add_argument("--client", help="client identifier (e.g. pjm:maintainer, ai-job-search)")
        p.add_argument("--class", dest="workload_class", help="workload class (e.g. maintenance, standard-dev)")
        p.add_argument("--json", action="store_true")
        p.add_argument("args", nargs=argparse.REMAINDER)

    add_tool_args(sub.add_parser("argv"))
    p_run = sub.add_parser("run")
    add_tool_args(p_run)
    p_run.add_argument("--meta-out", help="write execution metadata (model, quota, timestamp) to path before exec")

    p_resolve = sub.add_parser("resolve")
    add_tool_args(p_resolve)
    p_resolve.add_argument("--quota", action="store_true", help="include live quota metadata")

    p_usage = sub.add_parser("usage")
    p_usage.add_argument("--json", action="store_true")

    p_routes = sub.add_parser("routes")
    p_routes.add_argument("--json", action="store_true")

    p_route = sub.add_parser("route")
    route_sub = p_route.add_subparsers(dest="route_command", required=True)
    p_set_cls = route_sub.add_parser("set-class")
    p_set_cls.add_argument("name")
    p_set_cls.add_argument("--tool", required=True, choices=TOOLS)
    p_set_cls.add_argument("--tier", default="default", choices=TIERS)

    p_set_cli = route_sub.add_parser("set-client")
    p_set_cli.add_argument("name")
    p_set_cli.add_argument("--class", dest="workload_class")
    p_set_cli.add_argument("--tool", choices=TOOLS)
    p_set_cli.add_argument("--tier", choices=TIERS)

    p_del_cli = route_sub.add_parser("remove-client")
    p_del_cli.add_argument("name")

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
    try:
        tool, tier, effort, _ = resolve_route(
            config,
            client=args.client,
            workload_class=args.workload_class,
            requested_tool=args.tool,
            requested_tier=args.tier,
            requested_effort=args.effort,
        )
    except ValueError as e:
        print(f"aicli: {e}", file=sys.stderr)
        return 2

    argv = build_argv(config, tool, tier, effort, extra)
    if argv is None:
        print(f"{tool} CLI not found", file=sys.stderr)
        return 1
    print(json.dumps(argv) if args.json else shlex.join(argv))
    return 0


def cmd_resolve(args, config):
    try:
        tool, tier, effort, resolved_class = resolve_route(
            config,
            client=args.client,
            workload_class=args.workload_class,
            requested_tool=args.tool,
            requested_tier=args.tier,
            requested_effort=args.effort,
        )
    except ValueError as e:
        print(f"aicli: {e}", file=sys.stderr)
        return 2

    model = config.get(tool, {}).get("tiers", {}).get(tier, "unknown")
    res = {
        "client": args.client,
        "class": resolved_class,
        "tool": tool,
        "tier": tier,
        "model": model,
        "effort": effort,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if args.quota or args.json:
        res["quota"] = get_tool_quota(config, tool)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        q_str = ""
        if "quota" in res and res["quota"].get("bars"):
            bars = [f"{k}={v['pct']}%" for k, v in res["quota"]["bars"].items()]
            q_str = f" [quota: {', '.join(bars)}]"
        print(f"{resolved_class or 'unclassified'}: {tool}/{tier} ({model}){q_str}")
    return 0


def cmd_run(args, config):
    extra = _strip_dashdash(args.args)
    try:
        tool, tier, effort, resolved_class = resolve_route(
            config,
            client=args.client,
            workload_class=args.workload_class,
            requested_tool=args.tool,
            requested_tier=args.tier,
            requested_effort=args.effort,
        )
    except ValueError as e:
        print(f"aicli: {e}", file=sys.stderr)
        return 2

    model = config.get(tool, {}).get("tiers", {}).get(tier, "unknown")
    quota = get_tool_quota(config, tool)

    if getattr(args, "meta_out", None):
        meta = {
            "client": args.client,
            "class": resolved_class,
            "tool": tool,
            "tier": tier,
            "model": model,
            "effort": effort,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "quota": quota,
        }
        meta_path = Path(args.meta_out)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = meta_path.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, meta_path)

    try:
        usage_log = Path(os.environ.get("AICLI_USAGE_LOG", DEFAULT_USAGE_LOG)).expanduser()
        usage_log.parent.mkdir(parents=True, exist_ok=True)
        with open(usage_log, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(),
                "client": args.client,
                "class": resolved_class,
                "tool": tool,
                "tier": tier,
                "model": model,
                "quota": quota,
            }) + "\n")
    except OSError:
        pass

    argv = build_argv(config, tool, tier, effort, extra)
    if argv is None:
        print(f"{tool} CLI not found", file=sys.stderr)
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


def cmd_routes(args, config):
    routes = load_routes(config)
    classes = routes["classes"]
    clients = routes["clients"]
    if args.json:
        out = {"classes": {}, "clients": {}}
        for name, c in classes.items():
            tool = c.get("tool", "claude")
            tier = c.get("tier", "default")
            model = config.get(tool, {}).get("tiers", {}).get(tier, "")
            out["classes"][name] = {**c, "model": model}
        for name, c in clients.items():
            tool = c.get("tool")
            tier = c.get("tier")
            model = config.get(tool, {}).get("tiers", {}).get(tier, "") if tool and tier else ""
            out["clients"][name] = {**c, "model": model}
        print(json.dumps(out, indent=2))
        return 0

    print("WORKLOAD CLASSES:")
    for name, c in sorted(classes.items()):
        tool = c.get("tool", "claude")
        tier = c.get("tier", "default")
        model = config.get(tool, {}).get("tiers", {}).get(tier, "")
        print(f"  {name:20} -> {tool:6} (tier: {tier:7}, model: {model})")
        if c.get("description"):
            print(f"    {c['description']} [{c.get('frequency', '')}]")
    if clients:
        print("\nCLIENT OVERRIDES:")
        for name, c in sorted(clients.items()):
            route_str = f"class: {c.get('class', 'none')}"
            if c.get("tool"):
                route_str += f", tool: {c['tool']}"
            if c.get("tier"):
                route_str += f", tier: {c['tier']}"
            print(f"  {name:20} -> {route_str}")
    return 0


def cmd_route(args, config):
    routes = load_routes(config)
    if args.route_command == "set-class":
        if args.name not in routes["classes"]:
            routes["classes"][args.name] = {"description": "", "frequency": ""}
        routes["classes"][args.name]["tool"] = args.tool
        routes["classes"][args.name]["tier"] = args.tier
        save_routes(routes, config)
        print(f"route updated: class {args.name} -> {args.tool}/{args.tier}")
        return 0
    elif args.route_command == "set-client":
        entry = routes["clients"].setdefault(args.name, {})
        if args.workload_class:
            entry["class"] = args.workload_class
        if args.tool:
            entry["tool"] = args.tool
        if args.tier:
            entry["tier"] = args.tier
        save_routes(routes, config)
        print(f"route updated: client {args.name} -> {entry}")
        return 0
    elif args.route_command == "remove-client":
        if args.name in routes["clients"]:
            del routes["clients"][args.name]
            save_routes(routes, config)
            print(f"client {args.name} removed from routes")
        else:
            print(f"client {args.name} not in routes", file=sys.stderr)
            return 1
        return 0
    return 1


def main(argv=None):
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    handler = {
        "which": cmd_which, "argv": cmd_argv, "run": cmd_run, "resolve": cmd_resolve,
        "usage": cmd_usage, "routes": cmd_routes, "route": cmd_route,
    }[args.command]
    return handler(args, config)


if __name__ == "__main__":
    sys.exit(main())

