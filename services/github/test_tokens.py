#!/usr/bin/env python3
"""Verify GitHub API token."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        print("[ERR] .env file not found in services/github.")
        sys.exit(1)

    tokens = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip().strip("\"'")

    gh_token = tokens.get("GH_TOKEN")
    if not gh_token:
        print("[FAIL] GH_TOKEN is not configured in .env")
        sys.exit(1)

    masked = gh_token[:15] + "..." + gh_token[-4:] if len(gh_token) > 19 else "***"
    print(f"Testing GitHub API Token ({masked}) against https://api.github.com/user ...\n")

    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "homelab-github-token-test",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            login = data.get("login", "unknown")
            user_type = data.get("type", "User")
            scopes = resp.headers.get("X-OAuth-Scopes")
            scope_str = f"Scopes: {scopes}" if scopes else "Fine-grained token"
            print(f"  [OK] Valid token for user: {login} ({user_type}) | {scope_str}\n")
    except urllib.error.HTTPError as e:
        print(f"  [FAIL] GitHub API returned HTTP {e.code}: {e.reason}\n")
        sys.exit(1)
    except Exception as e:
        print(f"  [ERR] Failed to verify GitHub API token: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
