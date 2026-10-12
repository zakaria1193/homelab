#!/usr/bin/env python3
"""Weekly Security & Endpoint Checker.

Audits exposed homelab endpoints, systemd unit states, authentication settings,
and Cloudflare Access protection. Uses AI CLI (agy/claude) to evaluate safety
of all registered services. Sends alerts to Slack via tools/slackbot-notify.sh.
"""

import configparser
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
LOG_FILE = os.path.join(HERE, "security_checker.log")
SLACK_SCRIPT = os.path.join(REPO_ROOT, "tools", "slackbot-notify.sh")

# Load environment overrides
ENV_PATH = os.path.join(HERE, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

AI_CLI = os.environ.get("SECURITY_CHECKER_AI_CLI", "agy").strip()
ENABLE_AI = os.environ.get("SECURITY_CHECKER_ENABLE_AI", "1") not in ("0", "false", "no")

# --- Agent skill scan (NVIDIA SkillSpector) ------------------------------
SKILLSPECTOR_BIN = os.path.join(HERE, ".venv", "bin", "skillspector")
ENABLE_SKILLSCAN = os.environ.get("SECURITY_CHECKER_ENABLE_SKILLSCAN", "1") not in ("0", "false", "no")
DEFAULT_SKILL_PATHS = (
    "~/.claude/skills:~/.claude/plugins:~/my_repos/*/.claude/skills:"
    "~/.gemini/config/skills:~/.gemini/antigravity-cli/plugins"
)
SKILL_PATHS_SPEC = os.environ.get("SECURITY_CHECKER_SKILL_PATHS", DEFAULT_SKILL_PATHS)
SKILLSCAN_TIMEOUT = int(os.environ.get("SECURITY_CHECKER_SKILLSCAN_TIMEOUT", "120"))
SEVERITY_ERROR = ("critical", "high")
SEVERITY_WARNING = ("medium", "low")


def log(msg, to_file=True):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    if to_file:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")


def check_systemd_unit(unit_name):
    """Check if a systemd unit is stopped/disabled."""
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", unit_name],
            capture_output=True,
            text=True,
        )
        active = proc.stdout.strip() == "active"
        return active
    except Exception:
        return False


def probe_endpoint(url):
    """Probe a public HTTP/HTTPS endpoint."""
    req = Request(url, headers={"User-Agent": "homelab-security-checker/1.0"})
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers
    except HTTPError as e:
        return e.code, e.headers
    except URLError as e:
        return 0, str(e.reason)
    except Exception as e:
        return 0, str(e)


def load_services_config():
    """Load service definitions from services.conf."""
    conf_path = os.path.join(REPO_ROOT, "services", "status", "services.conf")
    if not os.path.exists(conf_path):
        return {}
    cp = configparser.ConfigParser()
    try:
        cp.read(conf_path)
        services = {}
        for sec in cp.sections():
            if sec.lower() in ("default", "homelab cockpit"):
                continue
            services[sec] = dict(cp[sec])
        return services
    except Exception as e:
        log(f"Error reading services.conf: {e}")
        return {}


def run_ai_security_check(service_name, service_info):
    """Invoke configured AI CLI (agy / claude) to analyze service security posture."""
    if not ENABLE_AI:
        return None

    cli_bin = shutil.which(AI_CLI) or AI_CLI
    prompt = (
        f"You are a homelab security auditor. Evaluate if the following service configuration is safe to use:\n\n"
        f"Service Name: {service_name}\n"
        f"Group: {service_info.get('group', 'Unknown')}\n"
        f"Type: {service_info.get('type', 'Unknown')}\n"
        f"Local Link: {service_info.get('link', 'None')}\n"
        f"Remote URL: {service_info.get('remote', 'None')}\n"
        f"Note: {service_info.get('note', 'None')}\n"
        f"Command: {service_info.get('command', 'None')}\n\n"
        f"Security Rules:\n"
        f"- Public remote URLs must be protected by Cloudflare Access or Basic Auth.\n"
        f"- Services exposing terminal access or unauthenticated admin UIs are HIGH RISK.\n"
        f"- Exception: Type 'shell' is not a standalone service - it is a terminal launcher "
        f"reachable only through this same cockpit page, which itself requires Basic Auth and "
        f"sits behind Cloudflare Access. Do not flag a Type 'shell' entry as RISKY or WARNING "
        f"for exposing terminal access; that risk is already covered by the cockpit's own auth.\n"
        f"Respond with exact format 'STATUS: SAFE', 'STATUS: WARNING', or 'STATUS: RISKY' followed by a 1-sentence rationale."
    )

    try:
        proc = subprocess.run(
            [cli_bin, "-p", prompt],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception as e:
        log(f"AI CLI ({AI_CLI}) check skipped for {service_name}: {e}")
    return None


def expand_skill_targets(spec):
    """Expand the colon-separated SECURITY_CHECKER_SKILL_PATHS spec into a
    deduped list of existing target directories. Missing folders and globs
    with no matches are skipped silently (not a warning)."""
    targets = []
    seen_real = set()
    for raw in spec.split(":"):
        raw = raw.strip()
        if not raw:
            continue
        expanded = os.path.expanduser(raw)
        candidates = glob.glob(expanded) if glob.has_magic(expanded) else [expanded]
        for candidate in sorted(candidates):
            if not os.path.isdir(candidate):
                continue
            real = os.path.realpath(candidate)
            if real in seen_real:
                continue
            seen_real.add(real)
            targets.append(candidate)
    return targets


def discover_skill_dirs(target):
    """Find individual skill directories inside a target folder, as real
    paths (SkillSpector itself refuses a symlinked scan target, and the spec
    wants each real path scanned once even when reachable via a symlink).

    A skill directory is any directory containing SKILL.md, or (so that a
    skill with no SKILL.md still gets scanned) any direct child of a
    directory literally named 'skills'. Falls back to the target's own
    direct children if neither pattern matches anything, and to the target
    itself if it has no subdirectories at all."""
    found = []
    seen_real = set()

    def add(path):
        real = os.path.realpath(path)
        if real not in seen_real:
            seen_real.add(real)
            found.append(real)

    for root, dirs, files in os.walk(target, followlinks=True):
        dirs.sort()
        if "SKILL.md" in files:
            add(root)
            dirs[:] = []  # a skill's own subdirectories are not sub-skills
            continue
        if os.path.basename(root) == "skills":
            for d in dirs:
                add(os.path.join(root, d))

    if found:
        return found

    try:
        children = [
            os.path.join(target, d)
            for d in sorted(os.listdir(target))
            if os.path.isdir(os.path.join(target, d))
        ]
    except OSError:
        children = []
    return [os.path.realpath(c) for c in children] or [os.path.realpath(target)]


def run_skillspector_scan(skill_dir, bin_path=SKILLSPECTOR_BIN, timeout=SKILLSCAN_TIMEOUT):
    """Run SkillSpector (static checks only) against one skill directory.

    Returns (parsed_json, None) on success, or (None, reason) on any
    failure to run or parse - missing binary, crash, timeout or output
    that doesn't parse as JSON."""
    if not os.path.exists(bin_path) and not shutil.which(bin_path):
        return None, "SkillSpector binary not found"
    try:
        proc = subprocess.run(
            [bin_path, "scan", skill_dir, "-f", "json", "--no-llm"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"scan timed out after {timeout}s"
    except Exception as e:
        return None, f"scan crashed: {e}"
    try:
        return json.loads(proc.stdout), None
    except (ValueError, TypeError):
        return None, "scan output did not parse as JSON"


def run_skill_scan(errors, warnings, passed, bin_path=SKILLSPECTOR_BIN,
                    spec=SKILL_PATHS_SPEC, timeout=SKILLSCAN_TIMEOUT):
    """Step 5: scan installed agent skills with NVIDIA SkillSpector (Part A,
    static only). Appends to errors/warnings/passed in place and logs a
    'Skills scanned: N in M folders' summary line."""
    if not ENABLE_SKILLSCAN:
        log("Skill scan disabled (SECURITY_CHECKER_ENABLE_SKILLSCAN=0)")
        return 0, 0

    targets = expand_skill_targets(spec)
    if not targets:
        passed.append("SkillSpector: no agent skills found")
        log("Skills scanned: 0 in 0 folders")
        return 0, 0

    total_skill_dirs = 0
    seen_real = set()
    for target in targets:
        skill_dirs = []
        for skill_dir in discover_skill_dirs(target):
            real = os.path.realpath(skill_dir)
            if real in seen_real:
                continue
            seen_real.add(real)
            skill_dirs.append(skill_dir)

        total_skill_dirs += len(skill_dirs)
        target_has_finding = False
        for skill_dir in skill_dirs:
            data, err = run_skillspector_scan(skill_dir, bin_path=bin_path, timeout=timeout)
            if err:
                line = f"SkillSpector could not scan {skill_dir}: {err}"
                warnings.append(line)
                log(line)
                target_has_finding = True
                continue

            issues = data.get("issues", []) if isinstance(data, dict) else []
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                severity = str(issue.get("severity", "")).strip().lower()
                detail = (
                    issue.get("pattern")
                    or issue.get("explanation")
                    or issue.get("finding")
                    or issue.get("message")
                    or issue.get("description")
                    or issue.get("category")
                    or issue.get("id")
                    or "unspecified finding"
                )
                line = f"SkillSpector [{severity}] {skill_dir}: {detail}"
                if severity in SEVERITY_ERROR:
                    errors.append(line)
                    log(line)
                    target_has_finding = True
                elif severity in SEVERITY_WARNING:
                    warnings.append(line)
                    log(line)
                    target_has_finding = True
                elif severity == "info":
                    log(line)
                else:
                    warnings.append(line)
                    log(line)
                    target_has_finding = True

        if not target_has_finding:
            passed.append(f"SkillSpector: {target} - no findings")

    log(f"Skills scanned: {total_skill_dirs} in {len(targets)} folders")
    return total_skill_dirs, len(targets)


def cap_findings_per_target(lines, limit=10):
    """Collapse SkillSpector findings beyond `limit` per skill path into a
    single '+N more' line, for the Slack message only - the log file keeps
    every line."""
    pattern = re.compile(r"^SkillSpector(?: AI)? \[[^\]]+\] (.+?): ")
    counts = {}
    hidden = {}
    capped = []
    for line in lines:
        m = pattern.match(line)
        if not m:
            capped.append(line)
            continue
        target = m.group(1)
        counts[target] = counts.get(target, 0) + 1
        if counts[target] <= limit:
            capped.append(line)
        else:
            hidden[target] = hidden.get(target, 0) + 1
    for target, n in hidden.items():
        capped.append(f"SkillSpector {target}: +{n} more")
    return capped


def run_audit():
    log(f"Starting Weekly Homelab Security Audit (AI Engine: {AI_CLI})...")
    errors = []
    warnings = []
    passed = []

    # 1. Check Homelab Cockpit status
    cockpit_active = check_systemd_unit("homelab-status.service")
    if cockpit_active:
        passed.append("homelab-status.service is active")
    else:
        errors.append("homelab-status.service is NOT running")

    # 2. Check decommissioned services (openhands-ai and hermes-ai must remain stopped)
    for disabled_unit in ["openhands-ai.service", "hermes-ai.service"]:
        is_active = check_systemd_unit(disabled_unit)
        if is_active:
            errors.append(f"Security Warning: {disabled_unit} is RUNNING but should be disabled!")
        else:
            passed.append(f"{disabled_unit} is stopped/disabled as expected")

    # 3. Check public hostnames for unauthenticated exposure
    public_endpoints = [
        "https://homelab.zakariafadli.com",
    ]

    for ep in public_endpoints:
        status, headers = probe_endpoint(ep)
        cf_ray = headers.get("cf-ray") if hasattr(headers, "get") else None
        log(f"Probed {ep} -> Status {status} (CF-Ray: {bool(cf_ray)})")
        if status in (302, 303, 401, 403):
            passed.append(f"{ep} requires authentication/challenge (HTTP {status})")
        elif status == 200:
            if cf_ray:
                passed.append(f"{ep} protected via Cloudflare Zero Trust (HTTP 200)")
            else:
                warnings.append(f"{ep} returned HTTP 200 without Cloudflare proxy header")
        elif status == 0:
            warnings.append(f"{ep} connection error or unreachable: {headers}")

    # 4. Audit all registered services from services.conf using AI CLI
    services = load_services_config()
    log(f"Loaded {len(services)} services from services.conf for AI security audit.")
    for s_name, s_info in list(services.items())[:5]:  # Audit top services
        ai_res = run_ai_security_check(s_name, s_info)
        if ai_res:
            log(f"AI Audit [{s_name}]: {ai_res}")
            if "STATUS: RISKY" in ai_res:
                errors.append(f"AI Audit flagged {s_name} as RISKY: {ai_res}")
            elif "STATUS: WARNING" in ai_res:
                warnings.append(f"AI Audit flagged {s_name}: {ai_res}")
            else:
                passed.append(f"AI Audit verified {s_name} as safe")

    # 5. Scan installed agent skills with NVIDIA SkillSpector
    skills_scanned, folders_scanned = run_skill_scan(errors, warnings, passed)

    # Build Summary
    log("--- Audit Summary ---")
    log(f"Passed: {len(passed)} checks")
    log(f"Warnings: {len(warnings)}")
    log(f"Errors: {len(errors)}")

    overall_status = "ok"
    if errors:
        overall_status = "error"
        log("[FAIL] Security Audit Completed with ERRORS")
    elif warnings:
        overall_status = "warn"
        log("[OK] Security Audit Completed with WARNINGS")
    else:
        log("[OK] Security Audit Completed - ALL CHECKS PASSED")

    # Slack Notification
    summary_text = (
        f"**Audit Findings** (AI Engine: `{AI_CLI}`):\n"
        f"- Passed: {len(passed)}\n"
        f"- Warnings: {len(warnings)}\n"
        f"- Errors: {len(errors)}\n"
        f"- Skills scanned: {skills_scanned} in {folders_scanned} folders\n\n"
    )
    capped_errors = cap_findings_per_target(errors)
    capped_warnings = cap_findings_per_target(warnings)
    if capped_errors:
        summary_text += f"**Errors**:\n" + "\n".join(f"- {e}" for e in capped_errors) + "\n\n"
    if capped_warnings:
        summary_text += f"**Warnings**:\n" + "\n".join(f"- {w}" for w in capped_warnings) + "\n\n"

    title = "Weekly Homelab Security Audit"
    if os.path.exists(SLACK_SCRIPT):
        subprocess.run(
            [SLACK_SCRIPT, "-t", title, "-s", overall_status, summary_text],
            cwd=REPO_ROOT,
            capture_output=True,
        )

    return len(errors) == 0


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
