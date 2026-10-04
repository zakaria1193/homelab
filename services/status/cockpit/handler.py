"""The HTTP layer: auth, routing, and the JSON API behind every page."""

import base64
import hmac
import html
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, quote, urlparse

import antigravity_rc
import claude_rc
import ideas_manager
from ideas_page import IDEAS_PAGE
import supabase_keepalive
from supabase_keepalive import SUPABASE_PAGE
import terminal
import tmux_manager
import usage

from .actions import add_ai_session, delete_ai_session, toggle_unit_enable
from .auth import issue_ticket, mint_session, redeem_ticket, valid_session, verify_cf_access_jwt
from .config import (
    BASIC_PASSWORD,
    BASIC_USER,
    CF_ACCESS_ENABLED,
    CONFIG_PATH,
    LOG_LINES,
    LOG_LINES_MAX,
    RC_MANAGE,
    REFRESH,
    REPO_ROOT,
    REQUIRE_CF_ACCESS,
    SESSION_COOKIE,
    SESSION_DAYS,
    TERMINAL_ENABLED,
    TERMINAL_IDLE,
    TITLE,
    USAGE_ENABLED,
)
from .pages.antigravity_rc import AGY_RC_PAGE
from .pages.claude_rc import RC_PAGE
from .pages.cron import CRON_PAGE
from .pages.login import LOGIN_PAGE
from .pages.logs import LOG_PAGE
from .pages.main import PAGE
from .pages.projects import PROJECTS_PAGE
from .pages.terminal import TERMINAL_PAGE
from .pages.tmux import TMUX_PAGE
from . import projects
from .probes import fetch_logs, find_check, login_shell, working_dir
from .snapshot import snapshot

CRON_TOOL_DIR = os.path.join(REPO_ROOT, "tools", "cron-manager")
if CRON_TOOL_DIR not in sys.path:
    sys.path.insert(0, CRON_TOOL_DIR)
import cron_manager


class StatusHandler(BaseHTTPRequestHandler):
    server_version = "HomelabStatus/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep journald readable
        if os.environ.get("STATUS_ACCESS_LOG"):
            super().log_message(fmt, *args)

    def _send(self, code, body, content_type, extra_headers=()):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra_headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _cookies(self):
        jar = {}
        for chunk in self.headers.get("Cookie", "").split(";"):
            key, _, value = chunk.strip().partition("=")
            if key:
                jar[key] = value
        return jar

    def _credentials_match(self, user, password):
        # compare_digest on both halves: a wrong user must cost the same as a
        # wrong password.
        return hmac.compare_digest(user, BASIC_USER) and hmac.compare_digest(
            password, BASIC_PASSWORD
        )

    def _https(self):
        """Whether the browser reached us over TLS (cloudflared says so)."""
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def _session_cookie(self, token, days):
        bits = ["%s=%s" % (SESSION_COOKIE, token), "Path=/", "HttpOnly", "SameSite=Lax"]
        if days:  # no Max-Age = a session cookie, gone when the browser closes
            bits.append("Max-Age=%d" % (days * 86400))
        if self._https():
            bits.append("Secure")
        return "; ".join(bits)

    @staticmethod
    def _safe_next(raw):
        """Only ever redirect back into this site."""
        target = raw or "/"
        if not target.startswith("/") or target.startswith("//"):
            return "/"
        return target

    def _render_login(self, next_path, error=""):
        page = (
            LOGIN_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__NEXT__", html.escape(self._safe_next(next_path), quote=True))
            .replace("__DAYS__", str(SESSION_DAYS))
            .replace("__ERROR__", '<div class="bad">%s</div>' % html.escape(error)
                     if error else "")
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _do_login(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        form = parse_qs(self.rfile.read(max(0, min(length, 8000))).decode("utf-8", "replace"))
        next_path = self._safe_next((form.get("next") or ["/"])[0])
        user = (form.get("user") or [""])[0]
        password = (form.get("password") or [""])[0]

        if not self._credentials_match(user, password):
            time.sleep(1)  # blunt the obvious brute force
            self._render_login(next_path, "Wrong user or password.")
            return

        # Ticked: a cookie that outlives the browser. Unticked: one that does
        # not - the login still stops being asked for on every page of this
        # visit, which is what basic auth used to do.
        days = SESSION_DAYS if (form.get("remember") or [""])[0] else 0
        self._send(
            303, "", "text/plain; charset=utf-8",
            [("Location", next_path),
             ("Set-Cookie", self._session_cookie(mint_session(days or 1), days))],
        )

    def _logout(self):
        self._send(
            303, "", "text/plain; charset=utf-8",
            [("Location", "/login"),
             ("Set-Cookie", "%s=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
              % SESSION_COOKIE)],
        )

    def _deny(self, path):
        """Send whoever this is to the right kind of "you are not logged in".

        A browser gets the login form, so it can tick "keep me signed in";
        curl, the JSON API and the mobile app keep the basic-auth challenge
        they already speak.
        """
        if "text/html" in self.headers.get("Accept", ""):
            self._send(303, "", "text/plain; charset=utf-8",
                       [("Location", "/login?next=" + quote(path))])
            return
        self._send(
            401,
            "unauthorized\n",
            "text/plain; charset=utf-8",
            [("WWW-Authenticate", 'Basic realm="%s"' % TITLE)],
        )

    def _authorized(self):
        if CF_ACCESS_ENABLED:
            cf_jwt = self.headers.get("Cf-Access-Jwt-Assertion", "")
            cf_email = self.headers.get("Cf-Access-Authenticated-User-Email", "")
            if cf_jwt or cf_email:
                if verify_cf_access_jwt(cf_jwt, cf_email):
                    return True
                return False
            elif REQUIRE_CF_ACCESS:
                return False

        if not BASIC_USER and not BASIC_PASSWORD:
            return True
        if valid_session(self._cookies().get(SESSION_COOKIE, "")):
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        user, _, password = decoded.partition(":")
        return self._credentials_match(user, password)

    def _render_logs(self, params):
        name = (params.get("service") or [""])[0]
        check = find_check(name)
        if check is None:
            self._send(404, "unknown service\n", "text/plain; charset=utf-8")
            return

        try:
            lines = int((params.get("lines") or [str(LOG_LINES)])[0])
        except ValueError:
            lines = LOG_LINES
        lines = max(1, min(lines, LOG_LINES_MAX))

        text, source = fetch_logs(check, lines)

        if params.get("raw"):
            self._send(200, text + "\n", "text/plain; charset=utf-8")
            return

        link_choices = []
        for choice in (50, 200, 1000, LOG_LINES_MAX):
            css = ' class="on"' if choice == lines else ""
            link_choices.append(
                '<a href="/logs?service=%s&lines=%d"%s>%d</a>'
                % (quote(name), choice, css, choice)
            )

        page = (
            LOG_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__NAME__", html.escape(name))
            .replace("__SOURCE__", html.escape(source or "no log source"))
            .replace("__LINE_LINKS__", "".join(link_choices))
            .replace("__LOG__", html.escape(text))
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _render_agy_rc(self):
        page = (
            AGY_RC_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__MANAGE__", "true" if RC_MANAGE else "false")
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _render_rc(self):
        options = "".join(
            '<option%s>%s</option>' % (" selected" if mode == "auto" else "", mode)
            for mode in claude_rc.PERMISSION_MODES
        )
        page = (
            RC_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__PERMISSIONS__", options)
            .replace("__MANAGE__", "true" if RC_MANAGE else "false")
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _read_json(self):
        """Body of a management POST, or None when it is not one we accept.

        Two things stand between the page and a cross-site request: the JSON
        content type (a form post cannot send it without CORS) and an Origin
        that has to match the host this request arrived on.
        """
        if "application/json" not in self.headers.get("Content-Type", ""):
            return None
        origin = self.headers.get("Origin", "")
        host = self.headers.get("X-Forwarded-Host", "") or self.headers.get("Host", "")
        if origin:
            origin_netloc = urlparse(origin).netloc
            origin_host = urlparse(origin).hostname
            request_host = host.split(":")[0]
            if origin_netloc != host and origin_host != request_host:
                return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > 64_000:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _rc_api(self, path, body):
        if path == "/api/claude-rc/validate":
            result = claude_rc.validate_workspace(
                body.get("workspace", ""), body.get("spawn", "worktree")
            )
            self._send(200, json.dumps(result) + "\n", "application/json; charset=utf-8")
            return
        elif path == "/api/antigravity-rc/validate":
            result = antigravity_rc.validate_workspace(body.get("workspace", ""))
            self._send(200, json.dumps(result) + "\n", "application/json; charset=utf-8")
            return

        if not RC_MANAGE:
            self._send(403, "instance management is disabled\n",
                       "text/plain; charset=utf-8")
            return

        name = str(body.get("name", ""))
        if path == "/api/antigravity-rc/action":
            result = antigravity_rc.run(str(body.get("verb", "")), name)
            result.setdefault("message", "")
        elif path == "/api/antigravity-rc/create":
            result = antigravity_rc.create(
                name,
                body.get("workspace", ""),
                body.get("port", ""),
                str(body.get("session", "")).strip(),
                config_path=CONFIG_PATH,
            )
        elif path == "/api/antigravity-rc/delete":
            result = antigravity_rc.delete(name, config_path=CONFIG_PATH)
        elif path == "/api/claude-rc/action":
            result = claude_rc.run(str(body.get("verb", "")), name)
            result.setdefault("message", "")
        elif path == "/api/claude-rc/create":
            result = claude_rc.create(
                name,
                body.get("workspace", ""),
                body.get("spawn", "worktree"),
                body.get("capacity", "8"),
                body.get("permission", "auto"),
                str(body.get("session", "")).strip(),
                config_path=CONFIG_PATH,
            )
        elif path == "/api/claude-rc/delete":
            result = claude_rc.delete(name, config_path=CONFIG_PATH)
        else:
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return
        self._send(200, json.dumps(result) + "\n", "application/json; charset=utf-8")

    def _render_supabase(self):
        page = SUPABASE_PAGE.replace("__TITLE__", html.escape(TITLE))
        self._send(200, page, "text/html; charset=utf-8")

    def _render_tmux(self):
        page = (
            TMUX_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__PREFIX__", html.escape(tmux_manager.TMUX_PREFIX))
            .replace("__REPO_ROOT__", html.escape(REPO_ROOT))
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _render_ideas(self):
        page = (
            IDEAS_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__VAULT_PATH__", html.escape(ideas_manager.get_display_path()))
            .replace(
                "__LOGOUT__",
                ' · <a href="/logout">sign out</a>'
                if BASIC_USER or BASIC_PASSWORD
                else "",
            )
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _render_cron(self):
        page = CRON_PAGE.replace("__TITLE__", html.escape(TITLE))
        self._send(200, page, "text/html; charset=utf-8")

    @staticmethod
    def _where(params):
        """Shell target from the query string, constrained to the two we run."""
        return "host" if (params.get("where") or [""])[0] == "host" else "auto"

    def _render_terminal(self, params):
        service = (params.get("service") or [""])[0]
        session = (params.get("session") or [""])[0]
        cmd = (params.get("cmd") or [""])[0]
        if cmd not in ("agy", "claude"):
            cmd = ""

        if session == "new":
            session = "term-%s" % time.strftime("%H%M%S")

        if not service and not session:
            self._send(400, "expected a service or session parameter\n", "text/plain; charset=utf-8")
            return

        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return

        where = self._where(params)
        if session:
            check = None
            target_dir = os.path.expanduser("~")
            _, _, _, _, tmux_session = terminal.build_command(
                None, target_dir, login_shell(), where, session=session, cmd=cmd, create=False
            )
            clean_session = tmux_session or session
            display_name = clean_session[len(tmux_manager.TMUX_PREFIX):] if clean_session.startswith(tmux_manager.TMUX_PREFIX) else clean_session
            label = "tmux [%s]" % clean_session
        else:
            check = find_check(service)
            if check is None:
                self._send(404, "unknown service\n", "text/plain; charset=utf-8")
                return
            _, _, label, _, tmux_session = terminal.build_command(
                check, working_dir(check), login_shell(), where, cmd=cmd
            )
            display_name = service

        page = (
            TERMINAL_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__NAME__", html.escape(display_name))
            .replace("__SERVICE__", html.escape(service))
            .replace("__SESSION__", html.escape(session))
            .replace("__WHERE__", html.escape(where))
            .replace("__CMD__", html.escape(cmd))
            .replace("__COMMAND__", html.escape(label))
            .replace("__TMUX_SESSION__", html.escape(tmux_session or ""))
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _issue_terminal_ticket(self, params):
        service = (params.get("service") or [""])[0]
        session = (params.get("session") or [""])[0]
        cmd = (params.get("cmd") or [""])[0]
        create_flag = (params.get("create") or [""])[0] == "1"
        if cmd not in ("agy", "claude"):
            cmd = ""
        try:
            cols = int((params.get("cols") or ["80"])[0])
            rows = int((params.get("rows") or ["24"])[0])
        except ValueError:
            cols, rows = 80, 24
        if session == "new":
            session = "term-%s" % time.strftime("%H%M%S")
            create_flag = True
        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return
        if not service and not session:
            self._send(400, "missing service or session parameter\n", "text/plain; charset=utf-8")
            return
        if service and find_check(service) is None:
            self._send(404, "unknown service\n", "text/plain; charset=utf-8")
            return
        if session and not create_flag and tmux_manager.is_available():
            clean_s = tmux_manager.sanitize_name(session)
            if not tmux_manager.has_session(clean_s):
                prefixed = "%s%s" % (tmux_manager.TMUX_PREFIX, clean_s)
                if tmux_manager.has_session(prefixed):
                    clean_s = prefixed
                else:
                    self._send(404, "session ended or not found\n", "text/plain; charset=utf-8")
                    return
        token = issue_ticket(service, self._where(params), session=session, cmd=cmd, cols=cols, rows=rows)
        body = json.dumps({"ticket": token}) + "\n"
        self._send(200, body, "application/json; charset=utf-8")

    def _open_terminal_socket(self, params):
        key = self.headers.get("Sec-WebSocket-Key", "")
        ticket = (params.get("ticket") or [""])[0]
        if not key or not ticket:
            self._send(400, "bad websocket handshake\n", "text/plain; charset=utf-8")
            return

        if not TERMINAL_ENABLED:
            self._send(403, "terminals are disabled\n", "text/plain; charset=utf-8")
            return

        service, where, session, cmd, cols, rows = redeem_ticket(ticket)
        if service is None and session is None:
            self._send(403, "invalid or expired ticket\n", "text/plain; charset=utf-8")
            return

        if session:
            target_dir = os.path.expanduser("~")
            argv, cwd, _, init, session_name = terminal.build_command(
                None, target_dir, login_shell(), where, session=session, cmd=cmd, create=True
            )
        else:
            check = find_check(service)
            if check is None:
                self._send(404, "unknown service\n", "text/plain; charset=utf-8")
                return
            argv, cwd, _, init, session_name = terminal.build_command(
                check, working_dir(check), login_shell(), where, cmd=cmd
            )

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", terminal.accept_key(key))
        self.end_headers()

        terminal.run_session(
            self.request,
            argv,
            cwd,
            idle_timeout=TERMINAL_IDLE,
            init=init,
            session_name=session_name,
            cols=cols,
            rows=rows,
        )

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/login":
            self._do_login()
            return

        if not self._authorized():
            self._deny(self.path)
            return

        if path == "/api/supabase/toggle":
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"ok": False, "message": "expected a same-origin JSON body"}) + "\n", "application/json; charset=utf-8")
                return
            res = supabase_keepalive.set_paused(str(body.get("ref", "")), bool(body.get("paused")))
            self._send(200, json.dumps(res) + "\n", "application/json; charset=utf-8")
            return

        if path.startswith("/api/tmux/"):
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"ok": False, "message": "expected a same-origin JSON body"}) + "\n", "application/json; charset=utf-8")
                return
            if path == "/api/tmux/kill":
                res = tmux_manager.kill_session(str(body.get("session", "")))
                self._send(200, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/tmux/rename":
                res = tmux_manager.rename_session(
                    str(body.get("old_name", "") or body.get("session", "")),
                    str(body.get("new_name", "") or body.get("name", "")),
                )
                self._send(200, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/tmux/create":
                res = tmux_manager.create_session(
                    str(body.get("name", "")),
                    cwd=str(body.get("cwd", "")).strip() or None,
                    command=str(body.get("command", "")).strip() or None,
                )
                self._send(200, json.dumps(res) + "\n", "application/json; charset=utf-8")
            else:
                self._send(404, json.dumps({"ok": False, "message": "not found"}) + "\n", "application/json; charset=utf-8")
            return

        if path == "/api/service/toggle-enable":
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"ok": False, "message": "expected a same-origin JSON body"}) + "\n", "application/json; charset=utf-8")
                return
            service = str(body.get("service", ""))
            target = body.get("enabled")
            res = toggle_unit_enable(service, target)
            code = 200 if res.get("ok") else 400
            self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            return

        if path == "/api/projects/save":
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"ok": False, "message": "expected a same-origin JSON body"}) + "\n", "application/json; charset=utf-8")
                return
            res = projects.save(body.get("projects") if isinstance(body, dict) else None)
            self._send(200 if res.get("ok") else 400, json.dumps(res) + "\n", "application/json; charset=utf-8")
            return

        if path.startswith("/api/ai-sessions/"):
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"ok": False, "message": "expected a same-origin JSON body"}) + "\n", "application/json; charset=utf-8")
                return
            if path == "/api/ai-sessions/add":
                res = add_ai_session(
                    name=str(body.get("name", "")),
                    dir_path=str(body.get("path", "")),
                    note=str(body.get("note", "")),
                )
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/ai-sessions/delete":
                res = delete_ai_session(str(body.get("name", "")))
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            else:
                self._send(404, json.dumps({"ok": False, "message": "not found"}) + "\n", "application/json; charset=utf-8")
            return

        if path.startswith("/api/ideas/"):
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"ok": False, "message": "expected a same-origin JSON body"}) + "\n", "application/json; charset=utf-8")
                return
            if path == "/api/ideas/add":
                res = ideas_manager.add_idea(
                    title=str(body.get("title", "")),
                    category=str(body.get("category", "Next up")),
                    target_file=str(body.get("target_file", "2 - Money making.md")),
                    status=str(body.get("status", "untagged")),
                    notes=str(body.get("notes", "")),
                    tags=ideas_manager.normalize_tags(body.get("tags"))
                    + (["owned"] if body.get("is_owned") else []),
                )
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/ideas/update-status":
                res = ideas_manager.update_idea_status(
                    idea_id=str(body.get("id", "")),
                    new_status=str(body.get("status", "")),
                    reason=str(body.get("reason", "")),
                )
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/ideas/toggle-check":
                res = ideas_manager.toggle_idea_check(str(body.get("id", "")))
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/ideas/delete":
                res = ideas_manager.delete_idea(str(body.get("id", "")))
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path in ("/api/ideas/update", "/api/ideas/edit"):
                res = ideas_manager.update_idea(
                    idea_id=str(body.get("id", "")),
                    title=body.get("title"),
                    notes=body.get("notes"),
                    category=body.get("category"),
                    status=body.get("status"),
                    tags=body.get("tags"),
                )
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/ideas/boards/create":
                res = ideas_manager.create_board(
                    str(body.get("name", "")),
                    sections=[str(x) for x in (body.get("sections") or [])] or None,
                    parent=body.get("parent") or None,
                    adopt=bool(body.get("adopt", True)),
                )
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/ideas/challenge":
                res = ideas_manager.challenge_rejection(
                    str(body.get("id", "")), str(body.get("challenge", "")))
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/ideas/answer-challenge":
                res = ideas_manager.answer_challenge(
                    str(body.get("id", "")),
                    str(body.get("answer", "")),
                    str(body.get("verdict", "")),
                    new_status=str(body.get("target_status") or "next"),
                )
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            else:
                self._send(404, json.dumps({"ok": False, "message": "not found"}) + "\n", "application/json; charset=utf-8")
            return

        if path.startswith("/api/cron/"):
            body = self._read_json()
            if body is None:
                self._send(400, json.dumps({"ok": False, "message": "expected a same-origin JSON body"}) + "\n", "application/json; charset=utf-8")
                return
            if path == "/api/cron/add":
                res = cron_manager.add_job(
                    job_id=str(body.get("id", "")),
                    name=str(body.get("name", "")),
                    schedule=str(body.get("schedule", "")),
                    command=str(body.get("command", "")),
                    category=str(body.get("category", "General")),
                    description=str(body.get("description", "")),
                )
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/cron/toggle":
                res = cron_manager.toggle_job(str(body.get("id", "")))
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/cron/delete":
                res = cron_manager.delete_job(str(body.get("id", "")))
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            elif path == "/api/cron/run":
                res = cron_manager.run_job(str(body.get("id", "")))
                code = 200 if res.get("ok") else 400
                self._send(code, json.dumps(res) + "\n", "application/json; charset=utf-8")
            else:
                self._send(404, json.dumps({"ok": False, "message": "not found"}) + "\n", "application/json; charset=utf-8")
            return

        if not path.startswith("/api/claude-rc/") and not path.startswith("/api/antigravity-rc/"):
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return

        body = self._read_json()
        if body is None:
            self._send(400, "expected a same-origin JSON body\n",
                       "text/plain; charset=utf-8")
            return
        self._rc_api(path, body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/healthz":
            self._send(200, "ok\n", "text/plain; charset=utf-8")
            return

        # The WebSocket carries its own credential: a single-use ticket minted
        # by the authenticated page. Browsers do not reliably replay basic-auth
        # headers on an upgrade request, so the ticket is checked instead.
        if path == "/ws/terminal":
            self._open_terminal_socket(params)
            return

        # The login form is the one page you must be able to reach logged out.
        if path == "/login":
            if not BASIC_USER and not BASIC_PASSWORD:
                self._send(303, "", "text/plain; charset=utf-8", [("Location", "/")])
            elif self._authorized():
                self._send(303, "", "text/plain; charset=utf-8",
                           [("Location", self._safe_next((params.get("next") or ["/"])[0]))])
            else:
                self._render_login((params.get("next") or ["/"])[0])
            return
        if path == "/logout":
            self._logout()
            return

        if not self._authorized():
            self._deny(self.path)
            return

        if path == "/":
            page = (
                PAGE.replace("__TITLE__", TITLE)
                .replace("__REFRESH__", str(REFRESH))
                .replace("__LOGOUT__", ' · <a href="/logout">sign out</a>'
                         if BASIC_USER or BASIC_PASSWORD else "")
            )
            self._send(200, page, "text/html; charset=utf-8")
        elif path == "/api/status":
            body = json.dumps(snapshot(), indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/projects":
            page = PROJECTS_PAGE.replace("__TITLE__", html.escape(TITLE)).replace("__REFRESH__", str(REFRESH))
            if (params.get("embedded") or [""])[0] == "1":
                page = page.replace("<body>", '<body class="embedded">', 1)
            self._send(200, page, "text/html; charset=utf-8")
        elif path == "/api/projects":
            body = json.dumps(projects.rows(), indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/api/usage":
            body = json.dumps(usage.snapshot() if USAGE_ENABLED else None, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/claude-rc":
            self._render_rc()
        elif path == "/api/claude-rc":
            body = json.dumps({"instances": claude_rc.instances(),
                               "manage": RC_MANAGE}, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/antigravity-rc":
            self._render_agy_rc()
        elif path == "/api/antigravity-rc":
            body = json.dumps({"instances": antigravity_rc.instances(),
                               "manage": RC_MANAGE}, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/supabase":
            self._render_supabase()
        elif path == "/api/supabase":
            body = json.dumps(supabase_keepalive.roster(), indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/tmux":
            self._render_tmux()
        elif path == "/api/tmux":
            sessions = tmux_manager.list_sessions()
            body = json.dumps({
                "sessions": sessions,
                "count": len(sessions),
                "prefix": tmux_manager.TMUX_PREFIX,
            }, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/cron":
            self._render_cron()
        elif path == "/api/cron":
            jobs = cron_manager.list_jobs()
            body = json.dumps({"ok": True, "jobs": jobs, "count": len(jobs)}, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path in ("/idea", "/ideas"):
            self._render_ideas()
        elif path == "/api/ideas":
            f_filter = (params.get("file") or [None])[0]
            s_filter = (params.get("status") or [None])[0]
            q_search = (params.get("q") or [None])[0]
            ideas = ideas_manager.list_all_ideas(file_filter=f_filter, status_filter=s_filter, search=q_search)
            cats = ideas_manager.get_categories()
            stats = ideas_manager.get_stats()
            body = json.dumps({"ok": True, "ideas": ideas, "categories": cats, "stats": stats,
                               "backends": ideas_manager.discover_backend_files()}, indent=2) + "\n"
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/terminal":
            self._render_terminal(params)
        elif path == "/api/terminal-ticket":
            self._issue_terminal_ticket(params)
        elif path == "/logs":
            self._render_logs(params)
        elif path == "/api/logs":
            params["raw"] = ["1"]
            self._render_logs(params)
        else:
            self._send(404, "not found\n", "text/plain; charset=utf-8")
