#!/usr/bin/env python3
"""Verify Supabase Management API token."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        print("[ERR] .env file not found in services/supabase.")
        sys.exit(1)

    tokens = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip().strip("\"'")

    token = tokens.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        print("[FAIL] SUPABASE_ACCESS_TOKEN is not configured in .env")
        sys.exit(1)

    masked = token[:7] + "..." + token[-4:] if len(token) > 11 else "***"
    print(f"Testing Supabase Management API Token ({masked}) against https://api.supabase.com/v1/projects ...\n")

    req = urllib.request.Request(
        "https://api.supabase.com/v1/projects",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "homelab-supabase-token-test",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            projects = json.loads(resp.read().decode())
            names = [p.get("name", p.get("id", "")) for p in projects if isinstance(p, dict)]
            print(f"  [OK] Valid token. Accessible projects ({len(projects)}): {', '.join(names)}\n")
    except urllib.error.HTTPError as e:
        print(f"  [FAIL] Supabase API returned HTTP {e.code}: {e.reason}\n")
        sys.exit(1)
    except Exception as e:
        print(f"  [ERR] Failed to verify Supabase token: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
