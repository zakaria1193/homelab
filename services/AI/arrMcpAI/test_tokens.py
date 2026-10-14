#!/usr/bin/env python3
"""Verify Arr suite API keys against local services."""

import json
import subprocess
import sys
from pathlib import Path

def main():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        print("[ERR] .env file not found in services/AI/arrMcpAI")
        sys.exit(1)

    tokens = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip().strip("\"'")

    endpoints = [
        ("RADARR_API_KEY", "Radarr", "http://127.0.0.1:7878/api/v3/system/status"),
        ("SONARR_API_KEY", "Sonarr", "http://127.0.0.1:8989/api/v3/system/status"),
        ("PROWLARR_API_KEY", "Prowlarr", "http://127.0.0.1:9696/api/v1/system/status"),
        ("READARR_API_KEY", "Chaptarr (Books)", "http://127.0.0.1:8789/api/v1/system/status"),
    ]

    print("Testing Arr Stack API Keys against local REST APIs ...\n")
    all_ok = True
    for key_name, label, base_url in endpoints:
        key_val = tokens.get(key_name, "")
        if not key_val:
            print(f"[SKIP] {key_name} ({label}) is empty / not set\n")
            continue

        masked = key_val[:4] + "..." + key_val[-4:] if len(key_val) >= 8 else "***"
        print(f"Verifying {key_name} for {label} ({masked})...")
        url = f"{base_url}?apiKey={key_val}"
        cmd = ["curl", "-s", "-m", "5", url]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            if not res.stdout:
                print(f"  [WARN] Service {label} is offline or unreachable on {base_url}\n")
                continue
            data = json.loads(res.stdout)
            if "version" in data:
                print(f"  [OK] Valid API Key (Version: {data.get('version')}, Branch: {data.get('branch', 'main')})\n")
            elif "message" in data:
                all_ok = False
                print(f"  [FAIL] Rejected by {label}: {data.get('message')}\n")
            else:
                print(f"  [INFO] Response: {res.stdout[:100]}\n")
        except Exception as e:
            print(f"  [WARN] Could not parse response from {label}: {e} (stdout: {res.stdout[:80]})\n")

    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
