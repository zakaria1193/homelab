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
import media_autopilot
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
    STATIC_DIR,
    TERMINAL_ENABLED,
    TERMINAL_IDLE,
    TITLE,
    USAGE_ENABLED,
    rc_locked_reason,
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

# /static/<name>: a flat file name ending in one of these, served from
# STATIC_DIR. Anything else - a subdirectory, no extension, another
# extension, a missing file - is a 404.
STATIC_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


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

    def _send_json(self, code, obj):
        self._send(code, json.dumps(obj) + "\n", "application/json; charset=utf-8")

    def _send_static(self, path):
        """Serve /static/<name>: a flat cockpit/static/*.css or *.js file."""
        name = path[len("/static/"):]
        content_type = STATIC_CONTENT_TYPES.get(os.path.splitext(name)[1])
        if not name or "/" in name or content_type is None:
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return
        try:
            with open(os.path.join(STATIC_DIR, name), "r", encoding="utf-8") as f:
                body = f.read()
        except OSError:
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return
        self._send(200, body, content_type)

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

    def _render_agy_rc(self, params):
        page = (
            AGY_RC_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__MANAGE__", "true" if RC_MANAGE else "false")
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _api_antigravity_rc(self, params):
        self._send_json(200, {"instances": antigravity_rc.instances(), "manage": RC_MANAGE})

    def _render_rc(self, params):
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

    def _api_claude_rc(self, params):
        self._send_json(200, {"instances": claude_rc.instances(), "manage": RC_MANAGE})

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

    def _rc_locked_response(self, workspace):
        # A workspace marked `rc_locked` in services.conf never gets a Remote
        # Control server, whatever the form or a hand-made request asks.
        reason = rc_locked_reason(workspace)
        if not reason:
            return None
        return {"ok": False, "path": "", "output": "",
                "message": "Remote Control is locked for this workspace: %s" % reason}

    def _require_rc_manage(self):
        if RC_MANAGE:
            return True
        self._send(403, "instance management is disabled\n", "text/plain; charset=utf-8")
        return False

    def _post_claude_rc_validate(self, body):
        locked = self._rc_locked_response(body.get("workspace", ""))
        if locked is not None:
            self._send_json(200, locked)
            return
        self._send_json(200, claude_rc.validate_workspace(
            body.get("workspace", ""), body.get("spawn", "worktree")
        ))

    def _post_claude_rc_create(self, body):
        locked = self._rc_locked_response(body.get("workspace", ""))
        if locked is not None:
            self._send_json(200, locked)
            return
        if not self._require_rc_manage():
            return
        self._send_json(200, claude_rc.create(
            str(body.get("name", "")),
            body.get("workspace", ""),
            body.get("spawn", "worktree"),
            body.get("capacity", "8"),
            body.get("permission", "auto"),
            str(body.get("session", "")).strip(),
            config_path=CONFIG_PATH,
        ))

    def _post_claude_rc_action(self, body):
        if not self._require_rc_manage():
            return
        result = claude_rc.run(str(body.get("verb", "")), str(body.get("name", "")))
        result.setdefault("message", "")
        self._send_json(200, result)

    def _post_claude_rc_delete(self, body):
        if not self._require_rc_manage():
            return
        self._send_json(200, claude_rc.delete(str(body.get("name", "")), config_path=CONFIG_PATH))

    def _post_antigravity_rc_validate(self, body):
        locked = self._rc_locked_response(body.get("workspace", ""))
        if locked is not None:
            self._send_json(200, locked)
            return
        self._send_json(200, antigravity_rc.validate_workspace(body.get("workspace", "")))

    def _post_antigravity_rc_create(self, body):
        locked = self._rc_locked_response(body.get("workspace", ""))
        if locked is not None:
            self._send_json(200, locked)
            return
        if not self._require_rc_manage():
            return
        self._send_json(200, antigravity_rc.create(
            str(body.get("name", "")),
            body.get("workspace", ""),
            body.get("port", ""),
            str(body.get("session", "")).strip(),
            config_path=CONFIG_PATH,
        ))

    def _post_antigravity_rc_action(self, body):
        if not self._require_rc_manage():
            return
        result = antigravity_rc.run(str(body.get("verb", "")), str(body.get("name", "")))
        result.setdefault("message", "")
        self._send_json(200, result)

    def _post_antigravity_rc_delete(self, body):
        if not self._require_rc_manage():
            return
        self._send_json(200, antigravity_rc.delete(str(body.get("name", "")), config_path=CONFIG_PATH))

    def _render_supabase(self, params):
        page = SUPABASE_PAGE.replace("__TITLE__", html.escape(TITLE))
        self._send(200, page, "text/html; charset=utf-8")

    def _api_supabase(self, params):
        self._send_json(200, supabase_keepalive.roster())

    def _post_supabase_toggle(self, body):
        self._send_json(200, supabase_keepalive.set_paused(
            str(body.get("ref", "")), bool(body.get("paused"))
        ))

    def _render_tmux(self, params):
        page = (
            TMUX_PAGE.replace("__TITLE__", html.escape(TITLE))
            .replace("__PREFIX__", html.escape(tmux_manager.TMUX_PREFIX))
            .replace("__REPO_ROOT__", html.escape(REPO_ROOT))
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _api_tmux(self, params):
        sessions = tmux_manager.list_sessions()
        self._send_json(200, {
            "sessions": sessions,
            "count": len(sessions),
            "prefix": tmux_manager.TMUX_PREFIX,
        })

    def _post_tmux_kill(self, body):
        self._send_json(200, tmux_manager.kill_session(str(body.get("session", ""))))

    def _post_tmux_rename(self, body):
        self._send_json(200, tmux_manager.rename_session(
            str(body.get("old_name", "") or body.get("session", "")),
            str(body.get("new_name", "") or body.get("name", "")),
        ))

    def _post_tmux_create(self, body):
        self._send_json(200, tmux_manager.create_session(
            str(body.get("name", "")),
            cwd=str(body.get("cwd", "")).strip() or None,
            command=str(body.get("command", "")).strip() or None,
        ))

    def _render_cron(self, params):
        page = CRON_PAGE.replace("__TITLE__", html.escape(TITLE))
        self._send(200, page, "text/html; charset=utf-8")

    def _api_cron(self, params):
        jobs = cron_manager.list_jobs()
        self._send_json(200, {"ok": True, "jobs": jobs, "count": len(jobs)})

    def _post_cron_add(self, body):
        res = cron_manager.add_job(
            job_id=str(body.get("id", "")),
            name=str(body.get("name", "")),
            schedule=str(body.get("schedule", "")),
            command=str(body.get("command", "")),
            category=str(body.get("category", "General")),
            description=str(body.get("description", "")),
        )
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_cron_toggle(self, body):
        res = cron_manager.toggle_job(str(body.get("id", "")))
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_cron_delete(self, body):
        res = cron_manager.delete_job(str(body.get("id", "")))
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_cron_run(self, body):
        res = cron_manager.run_job(str(body.get("id", "")))
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_ai_sessions_add(self, body):
        res = add_ai_session(
            name=str(body.get("name", "")),
            dir_path=str(body.get("path", "")),
            note=str(body.get("note", "")),
        )
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_ai_sessions_delete(self, body):
        res = delete_ai_session(str(body.get("name", "")))
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_service_toggle_enable(self, body):
        res = toggle_unit_enable(str(body.get("service", "")), body.get("enabled"))
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_projects_save(self, body):
        res = projects.save(body.get("projects") if isinstance(body, dict) else None)
        self._send_json(200 if res.get("ok") else 400, res)

    def _post_projects_push_all(self, body):
        self._send_json(200, projects.push_all())

    def _post_media_hopping(self, body):
        self._send_json(200, media_autopilot.edit(
            str(body.get("title", "")), bool(body.get("add")), kind="hopping"
        ))

    def _post_media_maintained(self, body):
        self._send_json(200, media_autopilot.edit(
            str(body.get("title", "")), bool(body.get("add")), kind="maintained"
        ))

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

        # These also land in data-* attributes on <body> (common.js'
        # pageConfig() reads them back), so every one is escaped for
        # attribute context, not just text content.
        page = (
            TERMINAL_PAGE.replace("__TITLE__", html.escape(TITLE, quote=True))
            .replace("__NAME__", html.escape(display_name, quote=True))
            .replace("__SERVICE__", html.escape(service, quote=True))
            .replace("__SESSION__", html.escape(session, quote=True))
            .replace("__WHERE__", html.escape(where, quote=True))
            .replace("__CMD__", html.escape(cmd, quote=True))
            .replace("__COMMAND__", html.escape(label, quote=True))
            .replace("__TMUX_SESSION__", html.escape(tmux_session or "", quote=True))
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
        self._send_json(200, {"ticket": token})

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

    def _render_main(self, params):
        page = (
            PAGE.replace("__TITLE__", TITLE)
            .replace("__REFRESH__", str(REFRESH))
            .replace("__LOGOUT__", ' · <a href="/logout">sign out</a>'
                     if BASIC_USER or BASIC_PASSWORD else "")
        )
        self._send(200, page, "text/html; charset=utf-8")

    def _api_status(self, params):
        self._send_json(200, snapshot())

    def _render_projects(self, params):
        page = PROJECTS_PAGE.replace("__TITLE__", html.escape(TITLE)).replace("__REFRESH__", str(REFRESH))
        if (params.get("embedded") or [""])[0] == "1":
            page = page.replace("<body>", '<body class="embedded">', 1)
        self._send(200, page, "text/html; charset=utf-8")

    def _api_projects(self, params):
        # GitHub counts cost a `gh` call, so only a page load asks for them.
        github = (params.get("github") or [""])[0] == "1"
        self._send_json(200, projects.rows(github=github))

    def _api_usage(self, params):
        self._send_json(200, usage.snapshot() if USAGE_ENABLED else None)

    def _render_media(self, params):
        self._send(200, media_autopilot.MEDIA_PAGE.replace("__TITLE__", html.escape(TITLE)),
                   "text/html; charset=utf-8")

    def _api_media(self, params):
        self._send_json(200, media_autopilot.roster())

    def _api_logs(self, params):
        params["raw"] = ["1"]
        self._render_logs(params)

    # Exact path -> bound GET handler, every one taking (params). The prefix
    # families of the old if/elif chain (/api/tmux/*, /api/cron/*, ...) are
    # one entry per path below, not a prefix match.
    GET_ROUTES = {
        "/": _render_main,
        "/api/status": _api_status,
        "/projects": _render_projects,
        "/api/projects": _api_projects,
        "/api/usage": _api_usage,
        "/claude-rc": _render_rc,
        "/api/claude-rc": _api_claude_rc,
        "/antigravity-rc": _render_agy_rc,
        "/api/antigravity-rc": _api_antigravity_rc,
        "/media": _render_media,
        "/api/media": _api_media,
        "/supabase": _render_supabase,
        "/api/supabase": _api_supabase,
        "/tmux": _render_tmux,
        "/api/tmux": _api_tmux,
        "/cron": _render_cron,
        "/api/cron": _api_cron,
        "/terminal": _render_terminal,
        "/api/terminal-ticket": _issue_terminal_ticket,
        "/logs": _render_logs,
        "/api/logs": _api_logs,
    }

    # Exact path -> bound POST handler, every one taking (body). do_POST reads
    # and validates the body once, before dispatch; a handler never sees a
    # request whose body failed that check.
    POST_ROUTES = {
        "/api/media/hopping": _post_media_hopping,
        "/api/media/maintained": _post_media_maintained,
        "/api/supabase/toggle": _post_supabase_toggle,
        "/api/tmux/kill": _post_tmux_kill,
        "/api/tmux/rename": _post_tmux_rename,
        "/api/tmux/create": _post_tmux_create,
        "/api/service/toggle-enable": _post_service_toggle_enable,
        "/api/projects/save": _post_projects_save,
        "/api/projects/push-all": _post_projects_push_all,
        "/api/ai-sessions/add": _post_ai_sessions_add,
        "/api/ai-sessions/delete": _post_ai_sessions_delete,
        "/api/cron/add": _post_cron_add,
        "/api/cron/toggle": _post_cron_toggle,
        "/api/cron/delete": _post_cron_delete,
        "/api/cron/run": _post_cron_run,
        "/api/claude-rc/validate": _post_claude_rc_validate,
        "/api/claude-rc/create": _post_claude_rc_create,
        "/api/claude-rc/action": _post_claude_rc_action,
        "/api/claude-rc/delete": _post_claude_rc_delete,
        "/api/antigravity-rc/validate": _post_antigravity_rc_validate,
        "/api/antigravity-rc/create": _post_antigravity_rc_create,
        "/api/antigravity-rc/action": _post_antigravity_rc_action,
        "/api/antigravity-rc/delete": _post_antigravity_rc_delete,
    }

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/login":
            self._do_login()
            return

        if not self._authorized():
            self._deny(self.path)
            return

        handler = self.POST_ROUTES.get(path)
        if handler is None:
            self._send_json(404, {"ok": False, "message": "not found"})
            return

        body = self._read_json()
        if body is None:
            self._send_json(400, {"ok": False, "message": "expected a same-origin JSON body"})
            return
        handler(self, body)

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

        # Cloudflare Access (private app) already gates every request from
        # outside the LAN before it reaches the cockpit; these files hold no
        # secrets, so a LAN client can fetch them without a cockpit login too.
        if path.startswith("/static/"):
            self._send_static(path)
            return

        if not self._authorized():
            self._deny(self.path)
            return

        handler = self.GET_ROUTES.get(path)
        if handler is None:
            self._send(404, "not found\n", "text/plain; charset=utf-8")
            return
        handler(self, params)
