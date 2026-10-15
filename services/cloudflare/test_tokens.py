#!/usr/bin/env python3
"""Verify Cloudflare API tokens against Cloudflare verification API."""

import json
import subprocess
import sys
from pathlib import Path

def main():
    env_file = Path(".env")
    if not env_file.exists():
        print("[ERR] .env file not found in current directory.")
        sys.exit(1)

    tokens = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip().strip("\"'")

    if not tokens:
        print("[WARN] No tokens found in .env")
        sys.exit(0)

    print("Testing Cloudflare API Tokens against https://api.cloudflare.com/client/v4/user/tokens/verify ...\n")
    all_ok = True
    for name, token in tokens.items():
        print(f"Verifying {name}...")
        cmd = [
            "curl",
            "-s",
            "-m",
            "10",
            "https://api.cloudflare.com/client/v4/user/tokens/verify",
            "-H",
            f"Authorization: Bearer {token}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(res.stdout)
            status = data.get("result", {}).get("status", "unknown") if data.get("result") else "error"
            msgs = ", ".join(m.get("message", "") for m in data.get("messages", []))
            errs = ", ".join(e.get("message", "") for e in data.get("errors", []))
            if data.get("success"):
                print(f"  [OK] Status: {status} | {msgs}\n")
            else:
                all_ok = False
                print(f"  [FAIL] Errors: {errs}\n")
        except Exception as e:
            all_ok = False
            print(f"  [ERR] Failed to parse API response: {e}\n")

    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
