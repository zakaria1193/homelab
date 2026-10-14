"""On-demand verification and roster of homelab API tokens and credentials."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import REPO_ROOT

_TEST_CACHE: dict[str, dict[str, Any]] = {}

TOKEN_DEFS = [
    {
        "id": "cf_dns",
        "service": "Cloudflare",
        "name": "Zone DNS API Token",
        "variable": "CLOUDFLARE_ZONE_DNS_ZAKARIAFADLICOM_FROM_HOME_IP_ONLY",
        "env_path": "services/cloudflare/.env",
        "description": "Zone DNS edit token for zakariafadli.com (restricted to home IP)",
        "kind": "cloudflare",
    },
    {
        "id": "cf_workers",
        "service": "Cloudflare",
        "name": "Workers Edit API Token",
        "variable": "CLOUDFLARE_WORKERS_API_TOKEN_FROM_HOME_IP_ONLY",
        "env_path": "services/cloudflare/.env",
        "description": "Workers edit & deploy token (restricted to home IP)",
        "kind": "cloudflare",
    },
    {
        "id": "cf_create_tokens",
        "service": "Cloudflare",
        "name": "Create Tokens API Token",
        "variable": "CLOUDFLARE_CREATE_ADDITIONAL_TOKENS_2026_FROM_HOME_IP_ONLY",
        "env_path": "services/cloudflare/.env",
        "description": "Token creation API (Opus CI agents only, restricted to home IP, expires after 2026)",
        "kind": "cloudflare",
    },
    {
        "id": "supabase",
        "service": "Supabase",
        "name": "Management Access Token",
        "variable": "SUPABASE_ACCESS_TOKEN",
        "env_path": "services/supabase-keepalive/.env",
        "description": "Management API personal access token for weekly keepalive discovery",
        "kind": "supabase",
    },
    {
        "id": "pjm_slack_bot",
        "service": "PJM Slack",
        "name": "Slack Bot Token",
        "variable": "PJM_SLACK_BOT_TOKEN",
        "env_path": "services/AI/pjmAI/.env",
        "description": "Slack bot token (xoxb-...) for PJM project management automation",
        "kind": "slack_bot",
    },
    {
        "id": "pjm_slack_app",
        "service": "PJM Slack",
        "name": "Slack App Token",
        "variable": "PJM_SLACK_APP_TOKEN",
        "env_path": "services/AI/pjmAI/.env",
        "description": "Slack app token (xapp-...) for Socket Mode thread events",
        "kind": "slack_app",
    },
    {
        "id": "radarr",
        "service": "Radarr",
        "name": "Radarr API Key",
        "variable": "RADARR_API_KEY",
        "env_path": "services/AI/arrMcpAI/.env",
        "description": "Local Radarr REST API key for arr-mcp integration",
        "kind": "arr",
        "endpoint": "http://127.0.0.1:7878/api/v3/system/status",
    },
    {
        "id": "sonarr",
        "service": "Sonarr",
        "name": "Sonarr API Key",
        "variable": "SONARR_API_KEY",
        "env_path": "services/AI/arrMcpAI/.env",
        "description": "Local Sonarr REST API key for arr-mcp integration",
        "kind": "arr",
        "endpoint": "http://127.0.0.1:8989/api/v3/system/status",
    },
    {
        "id": "prowlarr",
        "service": "Prowlarr",
        "name": "Prowlarr API Key",
        "variable": "PROWLARR_API_KEY",
        "env_path": "services/AI/arrMcpAI/.env",
        "description": "Local Prowlarr REST API key for arr-mcp integration",
        "kind": "arr",
        "endpoint": "http://127.0.0.1:9696/api/v1/system/status",
    },
    {
        "id": "readarr",
        "service": "Readarr",
        "name": "Readarr API Key",
        "variable": "READARR_API_KEY",
        "env_path": "services/AI/arrMcpAI/.env",
        "description": "Local Readarr REST API key for arr-mcp integration",
        "kind": "arr",
        "endpoint": "http://127.0.0.1:8787/api/v1/system/status",
    },
    {
        "id": "jellyfin",
        "service": "Jellyfin",
        "name": "Jellyfin API Key",
        "variable": "JELLYFIN_API_KEY",
        "env_path": "services/media-autopilot/.env",
        "description": "Jellyfin API key for media-autopilot watched sync",
        "kind": "jellyfin",
        "endpoint": "http://127.0.0.1:8096/System/Info",
    },
    {
        "id": "karakeep_openai",
        "service": "Karakeep",
        "name": "OpenAI API Key",
        "variable": "OPENAI_API_KEY",
        "env_path": "services/karakeep/.env",
        "description": "OpenAI project key for Karakeep tagging and AI features",
        "kind": "openai",
    },
    {
        "id": "karakeep_meili",
        "service": "Karakeep",
        "name": "Meilisearch Master Key",
        "variable": "MEILI_MASTER_KEY",
        "env_path": "services/karakeep/.env",
        "description": "Master key for Karakeep full-text search backend",
        "kind": "meili",
        "endpoint": "http://127.0.0.1:7700/health",
    },
    {
        "id": "hass_token",
        "service": "Home Assistant",
        "name": "Long-Lived Access Token",
        "variable": "HASS_TOKEN",
        "env_path": "../home-assistant-config/.env",
        "description": "Long-lived access token for Home Assistant REST & WebSocket API",
        "kind": "hass",
        "endpoint": "http://192.168.1.11:8123/api/",
    },
]


def _read_env_val(rel_path: str, var_name: str) -> str:
    path = os.path.normpath(os.path.join(REPO_ROOT, rel_path))
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == var_name:
                        return v.strip().strip("\"'")
    except Exception:
        pass
    return ""


def _mask_value(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 8:
        return "***"
    return f"{val[:5]}...{val[-4:]}"


def roster() -> list[dict[str, Any]]:
    """Return all tokens with current cache status (only test on demand)."""
    items = []
    for item in TOKEN_DEFS:
        token_id = item["id"]
        val = _read_env_val(item["env_path"], item["variable"])
        cached = _TEST_CACHE.get(token_id)
        if cached:
            status = cached.get("status", "untested")
            badge = cached.get("badge", "Untested")
            message = cached.get("message", "")
            tested_at = cached.get("tested_at")
        else:
            status = "untested"
            badge = "Untested"
            message = "Not tested yet. Click Test to verify."
            tested_at = None

        items.append({
            "id": token_id,
            "service": item["service"],
            "name": item["name"],
            "variable": item["variable"],
            "env_path": item["env_path"],
            "description": item["description"],
            "has_value": bool(val),
            "masked": _mask_value(val),
            "status": status,
            "badge": badge,
            "message": message,
            "tested_at": tested_at,
        })
    return items


def test_token(token_id: str) -> dict[str, Any]:
    """Test a single token on demand."""
    target = None
    for item in TOKEN_DEFS:
        if item["id"] == token_id:
            target = item
            break
    if not target:
        return {"ok": False, "status": "error", "badge": "Error", "message": f"Unknown token ID: {token_id}"}

    val = _read_env_val(target["env_path"], target["variable"])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not val:
        res = {"ok": False, "status": "warn", "badge": "Missing", "message": "Variable not set in .env", "tested_at": now_iso}
        _TEST_CACHE[token_id] = res
        return res

    kind = target["kind"]
    try:
        if kind == "cloudflare":
            req = urllib.request.Request(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {val}"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
            if body.get("success"):
                msgs = ", ".join(m.get("message", "") for m in body.get("messages", []))
                st = body.get("result", {}).get("status", "active")
                res = {"ok": True, "status": "active" if st == "active" else "warn", "badge": "Active" if st == "active" else st.capitalize(), "message": msgs or "Valid token", "tested_at": now_iso}
            else:
                errs = ", ".join(e.get("message", "") for e in body.get("errors", []))
                res = {"ok": False, "status": "error", "badge": "Rejected", "message": errs or "Cloudflare error", "tested_at": now_iso}

        elif kind == "supabase":
            req = urllib.request.Request(
                "https://api.supabase.com/v1/projects",
                headers={"Authorization": f"Bearer {val}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, list):
                names = [p.get("name", p.get("id", "")) for p in data if isinstance(p, dict)]
                res = {"ok": True, "status": "active", "badge": "Active", "message": f"Valid token ({len(data)} projects: {', '.join(names)})", "tested_at": now_iso}
            else:
                res = {"ok": False, "status": "error", "badge": "Error", "message": str(data)[:100], "tested_at": now_iso}

        elif kind == "slack_bot":
            req = urllib.request.Request(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {val}"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("ok"):
                res = {"ok": True, "status": "active", "badge": "Active", "message": f"User: {data.get('user')} on {data.get('team')}", "tested_at": now_iso}
            else:
                res = {"ok": False, "status": "error", "badge": "Rejected", "message": f"Slack: {data.get('error')}", "tested_at": now_iso}

        elif kind == "slack_app":
            req = urllib.request.Request(
                "https://slack.com/api/apps.connections.open",
                data=b"",
                headers={"Authorization": f"Bearer {val}", "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("ok"):
                res = {"ok": True, "status": "active", "badge": "Active", "message": "Socket Mode endpoint authenticated", "tested_at": now_iso}
            else:
                res = {"ok": False, "status": "error", "badge": "Rejected", "message": f"Slack: {data.get('error')}", "tested_at": now_iso}

        elif kind == "arr":
            endpoint = target["endpoint"]
            req = urllib.request.Request(f"{endpoint}?apiKey={val}")
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8"))
            if "version" in data:
                res = {"ok": True, "status": "active", "badge": "Active", "message": f"Version: {data.get('version')} (branch: {data.get('branch', 'main')})", "tested_at": now_iso}
            elif "message" in data:
                res = {"ok": False, "status": "error", "badge": "Rejected", "message": data.get("message"), "tested_at": now_iso}
            else:
                res = {"ok": True, "status": "active", "badge": "Active", "message": "Connected", "tested_at": now_iso}

        elif kind == "jellyfin":
            endpoint = target["endpoint"]
            req = urllib.request.Request(f"{endpoint}?api_key={val}")
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8"))
            if "Version" in data:
                res = {"ok": True, "status": "active", "badge": "Active", "message": f"Version: {data.get('Version')} ({data.get('ServerName')})", "tested_at": now_iso}
            else:
                res = {"ok": False, "status": "error", "badge": "Rejected", "message": "Key rejected by Jellyfin", "tested_at": now_iso}

        elif kind == "openai":
            req = urllib.request.Request(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {val}"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            if "data" in data:
                res = {"ok": True, "status": "active", "badge": "Active", "message": f"Valid API Key ({len(data['data'])} models)", "tested_at": now_iso}
            else:
                res = {"ok": False, "status": "error", "badge": "Rejected", "message": "Unexpected response", "tested_at": now_iso}

        elif kind == "meili":
            endpoint = target["endpoint"]
            req = urllib.request.Request(endpoint, headers={"Authorization": f"Bearer {val}"})
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "available":
                res = {"ok": True, "status": "active", "badge": "Active", "message": "Meilisearch master key accepted", "tested_at": now_iso}
            else:
                res = {"ok": False, "status": "warn", "badge": "Warning", "message": f"Status: {data}", "tested_at": now_iso}

        elif kind == "hass":
            endpoint = target["endpoint"]
            req = urllib.request.Request(endpoint, headers={"Authorization": f"Bearer {val}"})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8"))
            if "message" in data:
                res = {"ok": True, "status": "active", "badge": "Active", "message": data.get("message", "API running"), "tested_at": now_iso}
            else:
                res = {"ok": False, "status": "warn", "badge": "Warning", "message": str(data)[:80], "tested_at": now_iso}

        else:
            res = {"ok": False, "status": "warn", "badge": "Unknown", "message": f"No test driver for kind: {kind}", "tested_at": now_iso}

    except urllib.error.HTTPError as err:
        try:
            body = err.read().decode("utf-8", "replace")
            err_json = json.loads(body)
            msg = err_json.get("message") or err_json.get("error", {}).get("message") or str(err)
        except Exception:
            msg = f"HTTP {err.code} {err.reason}"
        res = {"ok": False, "status": "error", "badge": f"HTTP {err.code}", "message": msg, "tested_at": now_iso}
    except urllib.error.URLError as err:
        res = {"ok": False, "status": "warn", "badge": "Offline", "message": f"Unreachable: {err.reason}", "tested_at": now_iso}
    except Exception as err:
        res = {"ok": False, "status": "error", "badge": "Error", "message": str(err), "tested_at": now_iso}

    res["id"] = token_id
    _TEST_CACHE[token_id] = res
    return res


def test_all() -> list[dict[str, Any]]:
    """Test every token sequentially on demand."""
    results = []
    for item in TOKEN_DEFS:
        results.append(test_token(item["id"]))
    return results
