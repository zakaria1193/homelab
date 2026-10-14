#!/usr/bin/env python3
"""Verify Supabase Management API token."""

import sys
from pathlib import Path

# Add current dir so keepalive can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))

from keepalive import access_token, api_get, from_env, load_env

def main():
    load_env()
    token = access_token()
    print("Testing Supabase Management API Token against https://api.supabase.com/v1/projects ...\n")
    if not token:
        print("[FAIL] SUPABASE_ACCESS_TOKEN is not configured in .env")
        sys.exit(1)

    masked = token[:7] + "..." + token[-4:] if len(token) > 11 else "***"
    print(f"Verifying SUPABASE_ACCESS_TOKEN ({masked})...")
    try:
        projects = api_get("/projects", token)
        names = [p.get("name", p.get("id", "")) for p in projects if isinstance(p, dict)]
        print(f"  [OK] Valid token. Accessible projects ({len(projects)}): {', '.join(names)}\n")
    except Exception as err:
        print(f"  [FAIL] Verification error: {err}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
