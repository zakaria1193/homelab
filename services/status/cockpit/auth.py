"""Who may use the cockpit: Cloudflare Access, the login cookie, and the
single-use tickets that authorise a terminal WebSocket."""

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from .config import (
    BASIC_PASSWORD,
    BASIC_USER,
    CF_ACCESS_ALLOWED_EMAILS,
    CF_ACCESS_AUD,
    CF_ACCESS_TEAM_DOMAIN,
)


def parse_jwt_payload(jwt_str):
    """Parse JWT payload using Python standard library."""
    try:
        parts = jwt_str.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        rem = len(payload_b64) % 4
        if rem > 0:
            payload_b64 += "=" * (4 - rem)
        decoded = base64.urlsafe_b64decode(payload_b64)
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return None


def verify_cf_access_jwt(jwt_str, cf_email=""):
    """Validates Cloudflare Access JWT claims (aud, iss, exp, email)."""
    if not jwt_str:
        if cf_email and CF_ACCESS_ALLOWED_EMAILS:
            return cf_email.strip().lower() in CF_ACCESS_ALLOWED_EMAILS
        return bool(cf_email) if not CF_ACCESS_ALLOWED_EMAILS else False

    payload = parse_jwt_payload(jwt_str)
    if not payload:
        return False

    now = time.time()
    exp = payload.get("exp")
    if exp and int(exp) < now:
        return False

    if CF_ACCESS_AUD:
        aud = payload.get("aud")
        if isinstance(aud, list):
            if CF_ACCESS_AUD not in aud:
                return False
        elif aud != CF_ACCESS_AUD:
            return False

    if CF_ACCESS_TEAM_DOMAIN:
        expected_iss = "https://%s" % CF_ACCESS_TEAM_DOMAIN.rstrip("/")
        if payload.get("iss", "").rstrip("/") != expected_iss:
            return False

    user_email = payload.get("email") or cf_email
    if CF_ACCESS_ALLOWED_EMAILS:
        if not user_email or user_email.strip().lower() not in CF_ACCESS_ALLOWED_EMAILS:
            return False

    return True


# --------------------------------------------------------------------------- #
# Terminal tickets
# --------------------------------------------------------------------------- #
# Browsers do not reliably attach basic-auth headers to WebSocket upgrades, so
# the authenticated page mints a short-lived single-use ticket instead. Each
# ticket is bound to one service or tmux session.
TICKET_TTL = 60.0
_tickets = {}
_ticket_lock = threading.Lock()


def _session_key():
    """Signing key for the remember-me cookie.

    Derived from the credential itself: nothing to store on disk, it survives a
    restart, and every outstanding session dies the moment the password
    changes - which is exactly what you want from "log everyone out".
    """
    return hashlib.sha256(
        ("homelab-cockpit|%s|%s" % (BASIC_USER, BASIC_PASSWORD)).encode("utf-8")
    ).digest()


def mint_session(days):
    """A cookie value that proves a login happened, valid for `days`."""
    expiry = int(time.time()) + max(1, days) * 86400
    signature = hmac.new(
        _session_key(), ("v1|%d" % expiry).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return "%d.%s" % (expiry, signature)


def valid_session(token):
    expiry_text, _, signature = (token or "").partition(".")
    try:
        expiry = int(expiry_text)
    except ValueError:
        return False
    if expiry < time.time():
        return False
    expected = hmac.new(
        _session_key(), ("v1|%d" % expiry).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def issue_ticket(service, where, session="", cmd="", cols=80, rows=24):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _ticket_lock:
        for stale, item in list(_tickets.items()):
            expiry = item[-1]
            if expiry < now:
                del _tickets[stale]
        _tickets[token] = (service, where, session, cmd, cols, rows, now + TICKET_TTL)
    return token


def redeem_ticket(token):
    """Consume a ticket, returning (service, where, session, cmd, cols, rows)."""
    with _ticket_lock:
        entry = _tickets.pop(token, None)
    if entry is None:
        return None, None, None, "", 80, 24
    if len(entry) == 3:
        service, where, expiry = entry
        session, cmd, cols, rows = "", "", 80, 24
    elif len(entry) == 4:
        service, where, session, expiry = entry
        cmd, cols, rows = "", 80, 24
    elif len(entry) == 5:
        service, where, session, cmd, expiry = entry
        cols, rows = 80, 24
    else:
        service, where, session, cmd, cols, rows, expiry = entry
    if expiry < time.time():
        return None, None, None, "", 80, 24
    return service, where, session, cmd, cols, rows
