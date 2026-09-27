#!/usr/bin/env python3
"""Homelab Cron Job Manager & Viewer.

Manages scheduled maintenance, security audits, updates, and custom background
tasks for the homelab. Operates via CLI or imports cleanly into server routes.
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_CRON_FILE = os.path.join(HERE, "crontab.json")
SLACK_SCRIPT = os.path.join(REPO_ROOT, "tools", "slackbot-notify.sh")


def load_jobs(json_path=DEFAULT_CRON_FILE):
    """Load job definitions from JSON file."""
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("jobs", [])
    except Exception as e:
        print(f"Error reading {json_path}: {e}", file=sys.stderr)
        return []


def save_jobs(jobs, json_path=DEFAULT_CRON_FILE):
    """Save job definitions to JSON file."""
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"jobs": jobs}, f, indent=2)
            f.write("\n")
        return True
    except Exception as e:
        print(f"Error writing to {json_path}: {e}", file=sys.stderr)
        return False


def list_jobs(json_path=DEFAULT_CRON_FILE):
    """Return structured job list."""
    return load_jobs(json_path)


def add_job(job_id, name, schedule, command, category="General", description="", json_path=DEFAULT_CRON_FILE):
    """Add a new cron job to the registry."""
    jobs = load_jobs(json_path)
    for j in jobs:
        if j.get("id") == job_id:
            return {"ok": False, "message": f"Job ID '{job_id}' already exists."}

    new_job = {
        "id": job_id,
        "name": name,
        "schedule": schedule,
        "enabled": True,
        "category": category,
        "command": command,
        "description": description,
    }
    jobs.append(new_job)
    if save_jobs(jobs, json_path):
        return {"ok": True, "job": new_job}
    return {"ok": False, "message": "Failed to save job registry."}


def toggle_job(job_id, target_state=None, json_path=DEFAULT_CRON_FILE):
    """Enable or disable a cron job."""
    jobs = load_jobs(json_path)
    found = False
    new_state = False
    for j in jobs:
        if j.get("id") == job_id:
            found = True
            if target_state is None:
                j["enabled"] = not j.get("enabled", True)
            else:
                j["enabled"] = bool(target_state)
            new_state = j["enabled"]
            break

    if not found:
        return {"ok": False, "message": f"Job ID '{job_id}' not found."}

    if save_jobs(jobs, json_path):
        return {"ok": True, "id": job_id, "enabled": new_state}
    return {"ok": False, "message": "Failed to update job state."}


def delete_job(job_id, json_path=DEFAULT_CRON_FILE):
    """Remove a job from the registry."""
    jobs = load_jobs(json_path)
    initial_count = len(jobs)
    jobs = [j for j in jobs if j.get("id") != job_id]
    if len(jobs) == initial_count:
        return {"ok": False, "message": f"Job ID '{job_id}' not found."}

    if save_jobs(jobs, json_path):
        return {"ok": True, "id": job_id}
    return {"ok": False, "message": "Failed to save updated job list."}


def run_job(job_id, json_path=DEFAULT_CRON_FILE):
    """Execute a single job on demand and notify Slack."""
    jobs = load_jobs(json_path)
    target = None
    for j in jobs:
        if j.get("id") == job_id:
            target = j
            break

    if not target:
        return {"ok": False, "message": f"Job ID '{job_id}' not found."}

    cmd = target.get("command", "")
    name = target.get("name", job_id)
    print(f"Running job [{job_id}] '{name}'...")
    start_time = time.time()

    proc = subprocess.run(cmd, shell=True, cwd=REPO_ROOT, capture_output=True, text=True)
    duration = time.time() - start_time
    success = proc.returncode == 0

    status_flag = "ok" if success else "error"
    title = f"Cron Job Executed: {name}"
    summary = (
        f"Job `{job_id}` finished in {duration:.1f}s with exit code {proc.returncode}.\n\n"
        f"```\n{proc.stdout[-500:]}\n{proc.stderr[-500:]}\n```"
    )

    if os.path.exists(SLACK_SCRIPT):
        subprocess.run(
            [SLACK_SCRIPT, "-t", title, "-s", status_flag, summary],
            cwd=REPO_ROOT,
            capture_output=True,
        )

    return {
        "ok": success,
        "id": job_id,
        "exit_code": proc.returncode,
        "duration": duration,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def render_table(jobs):
    """Format job list for clean terminal display."""
    if not jobs:
        return "No scheduled jobs registered."

    lines = []
    lines.append(f"{'STATUS':<10} {'ID':<22} {'SCHEDULE':<12} {'CATEGORY':<14} {'NAME'}")
    lines.append("-" * 80)
    for j in jobs:
        status = "[ACTIVE]" if j.get("enabled", True) else "[DISABLED]"
        lines.append(
            f"{status:<10} {j.get('id', ''):<22} {j.get('schedule', ''):<12} {j.get('category', ''):<14} {j.get('name', '')}"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Homelab Cron Job Manager & Viewer")
    subparsers = parser.add_subparsers(dest="action")

    # List
    subparsers.add_parser("list", help="List all registered cron jobs")

    # Add
    add_p = subparsers.add_parser("add", help="Add a new cron job")
    add_p.add_argument("--id", required=True, help="Unique job ID")
    add_p.add_argument("--name", required=True, help="Human-readable job name")
    add_p.add_argument("--schedule", required=True, help="Cron expression (e.g. '0 9 * * 1')")
    add_p.add_argument("--command", required=True, help="Shell command to run")
    add_p.add_argument("--category", default="General", help="Job category (e.g. Security, Maintenance)")
    add_p.add_argument("--description", default="", help="Description of job purpose")

    # Toggle
    toggle_p = subparsers.add_parser("toggle", help="Enable or disable a job")
    toggle_p.add_argument("--id", required=True, help="Job ID to toggle")

    # Delete
    del_p = subparsers.add_parser("delete", help="Delete a job")
    del_p.add_argument("--id", required=True, help="Job ID to delete")

    # Run
    run_p = subparsers.add_parser("run", help="Run a job immediately on demand")
    run_p.add_argument("--id", required=True, help="Job ID to execute")

    args = parser.parse_args()

    if not args.action or args.action == "list":
        jobs = list_jobs()
        print(render_table(jobs))
    elif args.action == "add":
        res = add_job(args.id, args.name, args.schedule, args.command, args.category, args.description)
        if res.get("ok"):
            print(f"[OK] Added job '{args.id}' successfully.")
        else:
            print(f"[ERROR] {res.get('message')}")
    elif args.action == "toggle":
        res = toggle_job(args.id)
        if res.get("ok"):
            state_str = "enabled" if res.get("enabled") else "disabled"
            print(f"[OK] Job '{args.id}' is now {state_str}.")
        else:
            print(f"[ERROR] {res.get('message')}")
    elif args.action == "delete":
        res = delete_job(args.id)
        if res.get("ok"):
            print(f"[OK] Deleted job '{args.id}'.")
        else:
            print(f"[ERROR] {res.get('message')}")
    elif args.action == "run":
        res = run_job(args.id)
        if res.get("ok"):
            print(f"[OK] Job '{args.id}' completed successfully in {res.get('duration'):.1f}s.")
        else:
            print(f"[FAILED] Job '{args.id}' exited with code {res.get('exit_code')}.")


if __name__ == "__main__":
    main()
