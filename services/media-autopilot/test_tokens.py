#!/usr/bin/env python3
"""Verify Media Autopilot API tokens."""

import json
import subprocess
import sys
from pathlib import Path

def main():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        print("[ERR] .env file not found in services/media-autopilot")
        sys.exit(1)

    tokens = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip().strip("\"'")

    print("Testing Media Autopilot API Tokens ...\n")
    all_ok = True

    jkey = tokens.get("JELLYFIN_API_KEY")
    if jkey:
        masked = jkey[:4] + "..." + jkey[-4:] if len(jkey) >= 8 else "***"
        print(f"Verifying JELLYFIN_API_KEY ({masked})...")
        url = f"http://127.0.0.1:8096/System/Info?api_key={jkey}"
        res = subprocess.run(["curl", "-s", "-m", "5", url], capture_output=True, text=True)
        try:
            if not res.stdout:
                print("  [WARN] Jellyfin server unreachable on http://127.0.0.1:8096\n")
            else:
                data = json.loads(res.stdout)
                if "Version" in data:
                    print(f"  [OK] Valid Jellyfin Key (Version: {data.get('Version')}, Name: {data.get('ServerName')})\n")
                else:
                    all_ok = False
                    print(f"  [FAIL] Rejected by Jellyfin: {res.stdout[:120]}\n")
        except Exception:
            all_ok = False
            print(f"  [FAIL] Invalid response: {res.stdout[:120]}\n")
    else:
        print("[WARN] JELLYFIN_API_KEY is not set in .env\n")

    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
