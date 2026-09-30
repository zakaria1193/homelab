#!/usr/bin/env python3
"""Make sure Kandev's MCP is up, then start Claude Code or agy wired to it.

    kandev_mcp.py check            Kandev running + MCP answers with our token
    kandev_mcp.py register         check, then register the MCP in claude and agy
    kandev_mcp.py claude|agy ARGS  register that one, then exec the CLI

The cockpit's Kandev session chip calls the last form, so a session opened from
the page always talks to a live Kandev. Stdlib only, like the cockpit.

"Up" means three things, checked in order and fixed where possible:
  1. the kandev unit is active - started if it is not;
  2. /health answers - waited for, up to START_TIMEOUT;
  3. /mcp accepts KANDEV_MCP_TOKEN and lists its tools - a missing or revoked
     token is replaced by a new one minted with the admin login from .env.
"""

import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env")
UNIT = "kandev"
SERVER = "kandev"  # the MCP server's name inside claude and agy
TOKEN_KEY = "KANDEV_MCP_TOKEN"
TOKEN_NAME = "homelab-cockpit"
START_TIMEOUT = 90
HTTP_TIMEOUT = 10


def log(msg):
    print("[kandev-mcp] %s" % msg, file=sys.stderr, flush=True)


def read_env():
    env = {}
    try:
        with open(ENV_FILE) as fh:
            for line in fh:
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#"):
                    env[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    return env


def write_env_key(key, value):
    """Set one key in .env, keeping every other line as it was."""
    with open(ENV_FILE) as fh:
        text = fh.read()
    line = "%s=%s" % (key, value)
    pattern = re.compile(r"^%s=.*$" % re.escape(key), re.M)
    if pattern.search(text):
        text = pattern.sub(lambda _match: line, text)
    else:
        text = text.rstrip("\n") + "\n\n# External MCP token (written by kandev_mcp.py)\n" + line + "\n"
    with open(ENV_FILE, "w") as fh:
        fh.write(text)


def base_url(env):
    return "http://127.0.0.1:%s" % env.get("KANDEV_SERVER_PORT", "3040")


# --------------------------------------------------------------------------- #
# 1-2. The unit and its health endpoint
# --------------------------------------------------------------------------- #
def unit_active():
    for scope in ([], ["--user"]):
        res = subprocess.run(["systemctl", *scope, "is-active", "--quiet", UNIT], check=False)
        if res.returncode == 0:
            return True
    return False


def start_unit():
    if os.path.exists("/etc/systemd/system/%s.service" % UNIT):
        cmd = ["sudo", "-n", "systemctl", "start", UNIT]
    elif os.path.exists(os.path.expanduser("~/.config/systemd/user/%s.service" % UNIT)):
        cmd = ["systemctl", "--user", "start", UNIT]
    else:
        cmd = ["make", "-C", HERE, "start"]  # never installed: render the unit too
    log("kandev is not running - %s" % " ".join(cmd))
    subprocess.run(cmd, check=True)


def healthy(env):
    try:
        with urllib.request.urlopen(base_url(env) + "/health", timeout=HTTP_TIMEOUT) as res:
            return res.status == 200
    except (urllib.error.URLError, OSError):
        return False


def ensure_running(env):
    if not unit_active():
        start_unit()
    deadline = time.monotonic() + START_TIMEOUT
    while not healthy(env):
        if time.monotonic() > deadline:
            raise SystemExit("[kandev-mcp] kandev did not answer /health within %ds - "
                             "see `make -C %s logs`" % (START_TIMEOUT, HERE))
        time.sleep(2)


# --------------------------------------------------------------------------- #
# 3. The MCP endpoint and its token
# --------------------------------------------------------------------------- #
def _rpc_body(raw):
    """A streamable-HTTP MCP reply is plain JSON or one SSE `data:` event."""
    text = raw.decode("utf-8", "replace").strip()
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return {}


def mcp_tools(env, token):
    """Handshake with /mcp and return its tool names; None when the token is refused."""
    url = base_url(env) + "/mcp"
    headers = {
        "Authorization": "Bearer %s" % token,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    def call(method, params=None, rid=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if rid is not None:
            msg["id"] = rid
        req = urllib.request.Request(url, json.dumps(msg).encode(), headers, method="POST")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as res:
            session = res.headers.get("Mcp-Session-Id")
            return session, _rpc_body(res.read())

    try:
        session, _ = call("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "homelab-kandev-mcp", "version": "1"},
        }, rid=1)
        if session:
            headers["Mcp-Session-Id"] = session
        call("notifications/initialized")
        _, reply = call("tools/list", {}, rid=2)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return None
        raise
    return [tool["name"] for tool in reply.get("result", {}).get("tools", [])]


def mint_token(env):
    email, password = env.get("KANDEV_ADMIN_EMAIL"), env.get("KANDEV_ADMIN_PASSWORD")
    if not (email and password):
        raise SystemExit("[kandev-mcp] no %s and no admin login in %s to mint one"
                         % (TOKEN_KEY, ENV_FILE))
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def post(path, body):
        req = urllib.request.Request(base_url(env) + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"}, method="POST")
        with opener.open(req, timeout=HTTP_TIMEOUT) as res:
            return json.loads(res.read())

    try:
        post("/api/v1/auth/login", {"email": email, "password": password})
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
        raise SystemExit(
            "[kandev-mcp] Kandev refused the admin login in .env, so no token can be minted.\n"
            "  Either fix KANDEV_ADMIN_PASSWORD, or create a token in Kandev\n"
            "  (Settings > Account > API Tokens) and put it in %s as\n"
            "  %s=kandev_pat_..." % (ENV_FILE, TOKEN_KEY))
    token =post("/api/v1/auth/tokens", {"name": TOKEN_NAME, "ttl_hours": 0})["token"]
    write_env_key(TOKEN_KEY, token)
    log("minted a new API token '%s' and saved it to .env as %s" % (TOKEN_NAME, TOKEN_KEY))
    return token


def ensure_mcp():
    """Return (url, token, tools) for a Kandev MCP that is verified to work."""
    env = read_env()
    ensure_running(env)
    token = env.get(TOKEN_KEY, "")
    tools = mcp_tools(env, token) if token else None
    if tools is None:
        log("%s is %s" % (TOKEN_KEY, "refused" if token else "not set"))
        token = mint_token(env)
        tools = mcp_tools(env, token)
        if tools is None:
            raise SystemExit("[kandev-mcp] /mcp refused a freshly minted token")
    if not tools:
        raise SystemExit("[kandev-mcp] /mcp answered but lists no tools")
    return base_url(env) + "/mcp", token, tools


# --------------------------------------------------------------------------- #
# Registration in the CLIs
# --------------------------------------------------------------------------- #
def register_claude(url, token):
    """User-scope entry, so every Claude session on this box (RC ones too) gets it."""
    want = {"type": "http", "url": url, "headers": {"Authorization": "Bearer %s" % token}}
    try:
        with open(os.path.expanduser("~/.claude.json")) as fh:
            have = json.load(fh).get("mcpServers", {}).get(SERVER)
    except (OSError, ValueError):
        have = None
    if have == want:
        return
    subprocess.run(["claude", "mcp", "remove", SERVER, "-s", "user"],
                   capture_output=True, check=False)
    subprocess.run(["claude", "mcp", "add-json", SERVER, json.dumps(want), "-s", "user"],
                   capture_output=True, check=True)
    log("registered %s in claude (user scope)" % SERVER)


def register_agy(url, token):
    # `agy mcp add` is add-or-update, so running it every time is idempotent.
    subprocess.run(["agy", "mcp", "add", "--header", "Authorization: Bearer %s" % token,
                    SERVER, url], capture_output=True, check=True)
    log("registered %s in agy" % SERVER)


REGISTER = {"claude": register_claude, "agy": register_agy}


def main(argv):
    verb = argv[1] if len(argv) > 1 else "check"
    if verb not in ("check", "register", *REGISTER):
        print(__doc__, file=sys.stderr)
        return 2
    url, token, tools = ensure_mcp()
    log("up: %s answers with %d tools" % (url, len(tools)))
    if verb == "check":
        return 0
    for tool in REGISTER if verb == "register" else (verb,):
        if shutil.which(tool):
            REGISTER[tool](url, token)
        elif verb != "register":
            raise SystemExit("[kandev-mcp] %s is not installed" % tool)
    if verb in REGISTER:
        os.execvp(verb, [verb, *argv[2:]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
