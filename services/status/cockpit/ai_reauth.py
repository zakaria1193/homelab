"""AI CLI Re-authentication helper for Homelab Cockpit.

Provides non-terminal, web-based OAuth re-authentication for Claude Code and AGY
so operators can re-authenticate remotely from mobile or desktop browsers without
struggling with tmux mouse wrapping, terminal selection, or copying long URLs.
"""

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from .config import REPO_ROOT

_login_lock = threading.Lock()
_current_claude_login = {
    "proc": None,
    "auth_url": "",
    "started": 0.0,
}

_URL_RE = re.compile(r"https://claude\.com/cai/oauth/authorize\?[^\s]+")


def _resolve_bin(tool):
    """Find the real binary path via aicli or fallback locations."""
    try:
        aicli_bin = os.path.expanduser("~/my_repos/aicli/aicli.py")
        if os.path.isfile(aicli_bin):
            res = subprocess.run(
                ["python3", aicli_bin, "which", tool],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
            path = res.stdout.strip()
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    except Exception:
        pass

    defaults = {
        "claude": os.path.expanduser("~/.npm-global/bin/claude"),
        "agy": os.path.expanduser("~/.local/bin/agy"),
    }
    cand = defaults.get(tool)
    if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
        return cand
    return None


def auth_status():
    """Returns {claude: {authenticated: bool, detail: str}, agy: {authenticated: bool, detail: str, account?: str}}."""
    status = {
        "claude": {"authenticated": False, "detail": "claude CLI not found"},
        "agy": {"authenticated": False, "detail": "agy CLI not found"},
    }

    # 1. Claude
    claude_bin = _resolve_bin("claude")
    if claude_bin:
        try:
            p = subprocess.run(
                [claude_bin, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            raw = (p.stdout or "").strip()
            # Try to parse JSON output from claude auth status
            data = {}
            try:
                data = json.loads(raw)
            except Exception:
                # Fallback: look for loggedIn in text
                pass

            logged_in = data.get("loggedIn") if isinstance(data, dict) else None
            if logged_in is True:
                method = data.get("authMethod", "oauth")
                status["claude"] = {
                    "authenticated": True,
                    "auth_method": method,
                    "detail": f"Authenticated ({method})",
                }
            else:
                status["claude"] = {
                    "authenticated": False,
                    "detail": "OAuth session expired and could not be refreshed",
                }
        except Exception as e:
            status["claude"] = {
                "authenticated": False,
                "detail": f"Check failed: {e}",
            }

    # 2. Antigravity (AGY)
    agy_bin = _resolve_bin("agy")
    if agy_bin:
        token_path = Path("~/.gemini/antigravity-cli/antigravity-oauth-token").expanduser()
        oauth_path = Path("~/.gemini/oauth_creds.json").expanduser()

        email = ""
        if token_path.is_file():
            try:
                tdata = json.loads(token_path.read_text(encoding="utf-8"))
                email = tdata.get("id_token_email") or ""
            except Exception:
                pass

        if not email and oauth_path.is_file():
            try:
                odata = json.loads(oauth_path.read_text(encoding="utf-8"))
                email = odata.get("email") or ""
            except Exception:
                pass

        if email or token_path.is_file() or oauth_path.is_file():
            acct_str = f" ({email})" if email else ""
            status["agy"] = {
                "authenticated": True,
                "account": email or "Google Account",
                "detail": f"Authenticated{acct_str}",
            }
        else:
            status["agy"] = {
                "authenticated": False,
                "detail": "Not signed in",
            }

    return status


def start_claude_login():
    """Start `claude auth login` and return {'ok': True, 'auth_url': 'https://...'}.

    Reuses an ongoing login session if started < 300s ago.
    """
    global _current_claude_login
    with _login_lock:
        now = time.time()
        proc = _current_claude_login.get("proc")
        if proc and proc.poll() is None and (now - _current_claude_login["started"]) < 300:
            if _current_claude_login["auth_url"]:
                return {"ok": True, "auth_url": _current_claude_login["auth_url"]}

        # Clean up any stale process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass

        _current_claude_login["proc"] = None
        _current_claude_login["auth_url"] = ""

        claude_bin = _resolve_bin("claude")
        if not claude_bin:
            return {"ok": False, "error": "claude executable not found"}

        try:
            p = subprocess.Popen(
                [claude_bin, "auth", "login"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            return {"ok": False, "error": f"Failed spawning claude: {e}"}

        # Read stdout to locate authorization URL
        auth_url = ""
        start_t = time.time()
        ansi_strip = re.compile(r"\x1b\][^\x07\x1b]*[\x07\x1b]|\x1b\[[0-9;]*[a-zA-Z]|\x07")
        while time.time() - start_t < 8.0:
            line = p.stdout.readline()
            if not line and p.poll() is not None:
                break
            clean_line = ansi_strip.sub(" ", line)
            m = _URL_RE.search(clean_line)
            if m:
                auth_url = m.group(0)
                break
            if "visit:" in clean_line:
                cand = clean_line.split("visit:")[-1].strip().split()[0]
                if cand.startswith("http"):
                    auth_url = cand
                    break
            time.sleep(0.05)

        if not auth_url:
            try:
                p.terminate()
            except Exception:
                pass
            return {"ok": False, "error": "Timed out waiting for Claude OAuth URL"}

        _current_claude_login["proc"] = p
        _current_claude_login["auth_url"] = auth_url
        _current_claude_login["started"] = now
        return {"ok": True, "auth_url": auth_url}


def submit_claude_code(code):
    """Submit the OAuth authorization code to the waiting `claude auth login` process."""
    global _current_claude_login
    with _login_lock:
        proc = _current_claude_login.get("proc")
        if not proc or proc.poll() is not None:
            return {
                "ok": False,
                "error": "No active Claude login session in progress. Please click 'Reauth Claude' again.",
            }

        code_clean = (code or "").strip()
        if not code_clean:
            return {"ok": False, "error": "Authorization code cannot be empty"}

        try:
            proc.stdin.write(code_clean + "\n")
            proc.stdin.flush()
        except OSError as e:
            return {"ok": False, "error": f"Failed writing code to CLI process: {e}"}

        try:
            stdout, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            _current_claude_login["proc"] = None
            _current_claude_login["auth_url"] = ""
            return {"ok": False, "error": "Login timed out while verifying authorization code with Anthropic."}

        _current_claude_login["proc"] = None
        _current_claude_login["auth_url"] = ""

        # Verify whether login succeeded
        st = auth_status()
        if st["claude"]["authenticated"]:
            return {"ok": True, "message": "Claude Code successfully authenticated!"}

        err_tail = (stderr or stdout or "Code rejected").strip()[-200:]
        return {"ok": False, "error": f"Claude authentication failed: {err_tail}"}


def cancel_claude_login():
    """Cancel any pending Claude login session."""
    global _current_claude_login
    with _login_lock:
        proc = _current_claude_login.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
        _current_claude_login["proc"] = None
        _current_claude_login["auth_url"] = ""
        return {"ok": True}
