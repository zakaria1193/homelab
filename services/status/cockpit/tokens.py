"""On-demand verification and roster of homelab API tokens and credentials."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import REPO_ROOT

CACHE_FILE = Path(
    os.environ.get("HOMELAB_TOKENS_CACHE", "~/.local/state/homelab/tokens_cache.json")
).expanduser()


def _load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_cache() -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(_TEST_CACHE, indent=2), encoding="utf-8")
    except Exception:
        pass


_TEST_CACHE: dict[str, dict[str, Any]] = _load_cache()

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
        "id": "cf_pages_salsa_social",
        "service": "Cloudflare",
        "name": "salsa-social CI Pages Deploy Token",
        "variable": "CLOUDFLARE_PAGES_DEPLOY_SALSA_SOCIAL_CI",
        "env_path": "services/cloudflare/.env",
        "description": "Pages edit for salsa-social GitHub Actions deploy (no IP limit, expires 2027-10-15)",
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
        "id": "supabase_mgmt",
        "service": "Supabase",
        "name": "Management Access Token (supabase)",
        "variable": "SUPABASE_ACCESS_TOKEN",
        "env_path": "services/supabase/.env",
        "description": "Management API personal access token used directly from services/supabase",
        "kind": "supabase",
    },
    {
        "id": "github",
        "service": "GitHub",
        "name": "Personal Access Token",
        "variable": "GH_TOKEN",
        "env_path": "services/github/.env",
        "description": "GitHub API token for repo and workflow automation",
        "kind": "github",
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
        "id": "chaptarr",
        "service": "Chaptarr",
        "name": "Chaptarr API Key",
        "variable": "READARR_API_KEY",
        "env_path": "services/AI/arrMcpAI/.env",
        "description": "Local Chaptarr REST API key (books & audiobooks) for arr-mcp integration",
        "kind": "arr",
        "endpoint": "http://127.0.0.1:8789/api/v1/system/status",
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
        "id": "karakeep_ai",
        "service": "Karakeep",
        "name": "AI Inference (agy)",
        "variable": "OPENAI_BASE_URL",
        "env_path": "services/karakeep/.env",
        "description": "Local agy model via aicli for Karakeep tagging and summaries",
        "kind": "ai_endpoint",
    },
    {
        "id": "karakeep_meili",
        "service": "Karakeep",
        "name": "Meilisearch Master Key",
        "variable": "MEILI_MASTER_KEY",
        "env_path": "services/karakeep/.env",
        "description": "Master key for Karakeep full-text search backend",
        "kind": "meili",
        "endpoint": "http://127.0.0.1:7700/keys?limit=1",  # /health answers without a key
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


def is_failure(result: dict[str, Any]) -> bool:
    """A result counts as a failure (fails --strict, triggers the Slack alert) only
    when its status is "error". `Missing` values and `Offline` local services stay
    "warn" and never fail."""
    return result.get("status") == "error"


def _cloudflare_window(result: dict[str, Any], now: datetime | None = None) -> tuple[str | None, str]:
    """Why a token Cloudflare calls valid cannot be used right now: (badge, message),
    or (None, "") when it is usable now.
    /tokens/verify answers success for a token whose not_before is still ahead."""
    now = now or datetime.now(timezone.utc)

    def _at(key):
        raw = result.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None

    not_before, expires_on = _at("not_before"), _at("expires_on")
    if not_before and now < not_before:
        return "Not yet valid", f"Not usable before {result['not_before']}"
    if expires_on and now >= expires_on:
        return "Expired", f"Expired on {result['expires_on']}"
    return None, ""


# -- Header builders: how a kind sends its secret ---------------------------

def _hdr_bearer(val: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {val}"}


def _hdr_supabase(val: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {val}", "Accept": "application/json"}


def _hdr_slack_app(val: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {val}", "Content-Type": "application/x-www-form-urlencoded"}


def _hdr_api_key(val: str) -> dict[str, str]:
    return {"X-Api-Key": val}


def _hdr_jellyfin(val: str) -> dict[str, str]:
    return {"Authorization": f'MediaBrowser Token="{val}"'}


def _hdr_github(val: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {val}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "homelab-token-check",
    }


def _hdr_none(_val: str) -> dict[str, str]:
    return {}


# -- URL resolvers for kinds whose endpoint isn't a plain fixed string ------

def _ai_endpoint_url(target: dict[str, Any]) -> str:
    base = _read_env_val(target["env_path"], target["variable"]).strip()
    base = base.replace("host.docker.internal", "127.0.0.1")
    if not base:
        base = "http://127.0.0.1:8500/v1"
    return base.rstrip("/") + "/models"


# -- Success predicate + message builder, per kind --------------------------
# Each evaluate(body, response, now) returns the result dict's ok/status/badge/message.

def _eval_cloudflare(body, _response, now):
    if not body.get("success"):
        errs = ", ".join(e.get("message", "") for e in body.get("errors", []))
        return {"ok": False, "status": "error", "badge": "Rejected", "message": errs or "Cloudflare error"}
    msgs = ", ".join(m.get("message", "") for m in body.get("messages", []))
    result = body.get("result") or {}
    st = result.get("status", "active")
    badge, window_msg = _cloudflare_window(result, now)
    if badge:
        return {"ok": False, "status": "error", "badge": badge, "message": window_msg}
    return {
        "ok": True,
        "status": "active" if st == "active" else "warn",
        "badge": "Active" if st == "active" else st.capitalize(),
        "message": msgs or "Valid token",
    }


def _eval_supabase(body, _response, _now):
    if isinstance(body, list):
        names = [p.get("name", p.get("id", "")) for p in body if isinstance(p, dict)]
        return {"ok": True, "status": "active", "badge": "Active", "message": f"Valid token ({len(body)} projects: {', '.join(names)})"}
    return {"ok": False, "status": "error", "badge": "Error", "message": str(body)[:100]}


def _eval_slack_bot(body, _response, _now):
    if body.get("ok"):
        return {"ok": True, "status": "active", "badge": "Active", "message": f"User: {body.get('user')} on {body.get('team')}"}
    return {"ok": False, "status": "error", "badge": "Rejected", "message": f"Slack: {body.get('error')}"}


def _eval_slack_app(body, _response, _now):
    if body.get("ok"):
        return {"ok": True, "status": "active", "badge": "Active", "message": "Socket Mode endpoint authenticated"}
    return {"ok": False, "status": "error", "badge": "Rejected", "message": f"Slack: {body.get('error')}"}


def _eval_arr(body, _response, _now):
    if "version" in body:
        return {"ok": True, "status": "active", "badge": "Active", "message": f"Version: {body.get('version')} (branch: {body.get('branch', 'main')})"}
    if "message" in body:
        return {"ok": False, "status": "error", "badge": "Rejected", "message": body.get("message")}
    return {"ok": True, "status": "active", "badge": "Active", "message": "Connected"}


def _eval_jellyfin(body, _response, _now):
    if "Version" in body:
        return {"ok": True, "status": "active", "badge": "Active", "message": f"Version: {body.get('Version')} ({body.get('ServerName')})"}
    return {"ok": False, "status": "error", "badge": "Rejected", "message": "Key rejected by Jellyfin"}


def _eval_ai_endpoint(body, _response, _now):
    if "data" in body:
        models = [m.get("id") for m in body.get("data", [])]
        return {"ok": True, "status": "active", "badge": "Active", "message": f"aicli Active ({len(models)} models available)"}
    return {"ok": False, "status": "error", "badge": "Error", "message": str(body)[:100]}


def _eval_meili(body, _response, _now):
    if "results" in body:
        return {"ok": True, "status": "active", "badge": "Active", "message": "Meilisearch master key accepted"}
    return {"ok": False, "status": "warn", "badge": "Warning", "message": f"Status: {body}"}


def _eval_hass(body, _response, _now):
    if "message" in body:
        return {"ok": True, "status": "active", "badge": "Active", "message": body.get("message", "API running")}
    return {"ok": False, "status": "warn", "badge": "Warning", "message": str(body)[:80]}


def _eval_github(body, response, _now):
    if "login" in body:
        scopes = response.headers.get("X-OAuth-Scopes") if response is not None else None
        scope_str = f"Scopes: {scopes}" if scopes else "Fine-grained token"
        return {"ok": True, "status": "active", "badge": "Active", "message": f"User: {body.get('login')} | {scope_str}"}
    return {"ok": False, "status": "error", "badge": "Rejected", "message": "GitHub rejected the token"}


# -- The kind table: one entry per kind, no if/elif dispatch ----------------

KIND_DEFS: dict[str, dict[str, Any]] = {
    "cloudflare": {
        "url": "https://api.cloudflare.com/client/v4/user/tokens/verify",
        "headers": _hdr_bearer,
        "timeout": 5,
        "evaluate": _eval_cloudflare,
    },
    "supabase": {
        "url": "https://api.supabase.com/v1/projects",
        "headers": _hdr_supabase,
        "timeout": 6,
        "evaluate": _eval_supabase,
    },
    "slack_bot": {
        "url": "https://slack.com/api/auth.test",
        "headers": _hdr_bearer,
        "timeout": 5,
        "evaluate": _eval_slack_bot,
    },
    "slack_app": {
        "url": "https://slack.com/api/apps.connections.open",
        "headers": _hdr_slack_app,
        "data": b"",
        "timeout": 5,
        "evaluate": _eval_slack_app,
    },
    "arr": {
        "headers": _hdr_api_key,
        "timeout": 4,
        "evaluate": _eval_arr,
    },
    "jellyfin": {
        "headers": _hdr_jellyfin,
        "timeout": 4,
        "evaluate": _eval_jellyfin,
    },
    "ai_endpoint": {
        "dynamic_url": _ai_endpoint_url,
        "headers": _hdr_none,
        "timeout": 4,
        "evaluate": _eval_ai_endpoint,
    },
    "meili": {
        "headers": _hdr_bearer,
        "timeout": 3,
        "evaluate": _eval_meili,
    },
    "hass": {
        "headers": _hdr_bearer,
        "timeout": 4,
        "evaluate": _eval_hass,
    },
    "github": {
        "url": "https://api.github.com/user",
        "headers": _hdr_github,
        "timeout": 10,
        "evaluate": _eval_github,
    },
}


def _url_for(target: dict[str, Any], kind_def: dict[str, Any]) -> str:
    if kind_def.get("url"):
        return kind_def["url"]
    dynamic: Callable[[dict[str, Any]], str] | None = kind_def.get("dynamic_url")
    if dynamic:
        return dynamic(target)
    return target.get("endpoint", "")


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
        res = {"id": token_id, "ok": False, "status": "warn", "badge": "Missing", "message": "Variable not set in .env", "tested_at": now_iso}
        _TEST_CACHE[token_id] = res
        _save_cache()
        return res

    kind_def = KIND_DEFS[target["kind"]]
    url = _url_for(target, kind_def)
    headers = kind_def["headers"](val)
    data = kind_def.get("data")
    timeout = kind_def.get("timeout", 5)

    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            res = kind_def["evaluate"](body, response, datetime.now(timezone.utc))
        res["tested_at"] = now_iso

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
    _save_cache()
    return res


def test_all() -> list[dict[str, Any]]:
    """Test every token sequentially on demand."""
    results = []
    for item in TOKEN_DEFS:
        results.append(test_token(item["id"]))
    _save_cache()
    return results
