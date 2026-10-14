#!/usr/bin/env python3
"""Verify PJM Slack Bot and App Tokens."""

import json
import subprocess
import sys
from pathlib import Path

def main():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        print("[ERR] .env file not found in services/AI/pjmAI")
        sys.exit(1)

    tokens = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip().strip("\"'")

    print("Testing PJM Slack Tokens against Slack API ...\n")
    all_ok = True

    bot_token = tokens.get("PJM_SLACK_BOT_TOKEN")
    if bot_token:
        masked = bot_token[:8] + "..." + bot_token[-4:]
        print(f"Verifying PJM_SLACK_BOT_TOKEN ({masked})...")
        cmd = ["curl", "-s", "https://slack.com/api/auth.test", "-H", f"Authorization: Bearer {bot_token}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(res.stdout)
            if data.get("ok"):
                print(f"  [OK] Valid Bot Token (User: {data.get('user')}, Team: {data.get('team')})\n")
            else:
                all_ok = False
                print(f"  [FAIL] Slack error: {data.get('error')}\n")
        except Exception as e:
            all_ok = False
            print(f"  [ERR] {e}\n")
    else:
        print("[WARN] PJM_SLACK_BOT_TOKEN is not set\n")

    app_token = tokens.get("PJM_SLACK_APP_TOKEN")
    if app_token:
        masked = app_token[:8] + "..." + app_token[-4:]
        print(f"Verifying PJM_SLACK_APP_TOKEN ({masked})...")
        cmd = [
            "curl", "-s", "-X", "POST", "https://slack.com/api/apps.connections.open",
            "-H", f"Authorization: Bearer {app_token}",
            "-H", "Content-type: application/x-www-form-urlencoded"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(res.stdout)
            if data.get("ok"):
                print(f"  [OK] Valid App Token (Socket Mode endpoint ready)\n")
            else:
                all_ok = False
                print(f"  [FAIL] Slack error: {data.get('error')}\n")
        except Exception as e:
            all_ok = False
            print(f"  [ERR] {e}\n")
    else:
        print("[WARN] PJM_SLACK_APP_TOKEN is not set\n")

    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
