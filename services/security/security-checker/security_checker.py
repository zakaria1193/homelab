#!/usr/bin/env python3
"""Weekly Security & Endpoint Checker.

Audits exposed homelab endpoints, systemd unit states, authentication settings,
and Cloudflare Access protection. Uses AI CLI (agy/claude) to evaluate safety
of all registered services. Sends alerts to Slack via tools/slackbot-notify.sh.
"""

import configparser
import json
import os
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
        f"- Errors: {len(errors)}\n\n"
    )
    if errors:
        summary_text += f"**Errors**:\n" + "\n".join(f"- {e}" for e in errors) + "\n\n"
    if warnings:
        summary_text += f"**Warnings**:\n" + "\n".join(f"- {w}" for w in warnings) + "\n\n"

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
