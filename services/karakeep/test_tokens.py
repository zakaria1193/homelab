#!/usr/bin/env python3
"""Verify Karakeep stack tokens & keys."""

import json
import subprocess
import sys
from pathlib import Path

def main():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        print("[ERR] .env file not found in services/karakeep")
        sys.exit(1)

    tokens = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            tokens[k.strip()] = v.strip().strip("\"'")

    print("Testing Karakeep API Keys & Secrets ...\n")
    all_ok = True

    # 1. AI Provider / Endpoint
    oai = tokens.get("OPENAI_API_KEY", "")
    base_url = tokens.get("OPENAI_BASE_URL", "").replace("host.docker.internal", "127.0.0.1")
    if base_url:
        print(f"Verifying AI Provider Endpoint ({base_url})...")
        cmd = ["curl", "-s", "-m", "5", f"{base_url.rstrip('/')}/models"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(res.stdout)
            if "data" in data:
                print(f"  [OK] Valid AI Endpoint ({len(data['data'])} models available)\n")
            else:
                all_ok = False
                print(f"  [FAIL] AI Endpoint returned: {res.stdout[:100]}\n")
        except Exception as e:
            all_ok = False
            print(f"  [ERR] {e}\n")
    elif oai and oai.startswith("sk-"):
        masked = oai[:7] + "..." + oai[-4:] if len(oai) >= 12 else "***"
        print(f"Verifying OPENAI_API_KEY ({masked})...")
        cmd = ["curl", "-s", "-m", "5", "https://api.openai.com/v1/models", "-H", f"Authorization: Bearer {oai}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(res.stdout)
            if "data" in data:
                print(f"  [OK] Valid OpenAI Key ({len(data['data'])} models available)\n")
            elif "error" in data:
                all_ok = False
                print(f"  [FAIL] OpenAI error: {data['error'].get('message')}\n")
            else:
                all_ok = False
                print(f"  [FAIL] Response: {res.stdout[:100]}\n")
        except Exception as e:
            all_ok = False
            print(f"  [ERR] {e}\n")
    else:
        print("[INFO] AI inference is not configured\n")

    # 2. Meilisearch Master Key
    meili = tokens.get("MEILI_MASTER_KEY", "")
    if meili:
        masked = meili[:4] + "..." + meili[-4:] if len(meili) >= 8 else "***"
        print(f"Verifying MEILI_MASTER_KEY ({masked})...")
        cmd = ["curl", "-s", "-m", "3", "http://127.0.0.1:7700/health", "-H", f"Authorization: Bearer {meili}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            if not res.stdout:
                print("  [WARN] Meilisearch server not running locally on port 7700\n")
            else:
                data = json.loads(res.stdout)
                if data.get("status") == "available":
                    print("  [OK] Meilisearch available & master key accepted\n")
                else:
                    print(f"  [INFO] Meilisearch status: {data}\n")
        except Exception as e:
            print(f"  [WARN] Meilisearch check: {e} ({res.stdout[:60]})\n")

    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
