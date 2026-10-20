"""Health-check -> Slack notifier.

Runs as `status_server.py --notify`, outside the cockpit daemon, so a dead
daemon is just another down entry. One sweep: probe every eligible entry in
services.conf, compare against the last sweep's state, and send at most one
Slack message for anything that is newly bad (two bad sweeps in a row) or
newly back up.
"""

import csv
import json
import os
import subprocess
import time

from .config import DOWN, HERE, LINK_HOST, PORT, REPO_ROOT, SHELL, UNKNOWN, WARN, load_checks
from .probes import run_check

STATE_PATH = os.path.join(HERE, "notify-state.json")
LOG_PATH = os.path.join(HERE, "notify.log")
LOG_MAX_LINES = 500

WEBHOOKS_CSV = os.path.join(REPO_ROOT, "tools", "slack_webhooks.csv")
NOTIFY_SCRIPT = os.path.join(REPO_ROOT, "tools", "slackbot-notify.sh")
DEFAULT_CHANNEL = "#homelab-alerts"
TITLE = "Homelab health alert"

_DEFAULT_ENTRY = {"bad": False, "streak": 0, "notified": False}


def eligible_checks(checks=None):
    """Every services.conf entry a sweep probes: no launchers, no `notify = 0`,
    and not the card watching this notifier's own log. That card goes amber
    when a send fails, so alerting on it only queues a message about Slack
    that cannot reach Slack, and keeps the card amber with it."""
    if checks is None:
        checks = load_checks()
    return [
        c for c in checks
        if c["type"] != SHELL
        and c.get("notify", True)
        and os.path.realpath(c.get("path") or "") != os.path.realpath(LOG_PATH)
    ]


def load_state(path):
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
    os.replace(tmp, path)


def append_log(path, line, max_lines=LOG_MAX_LINES):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = "%s %s" % (stamp, line)
    lines = []
    if os.path.isfile(path):
        with open(path) as handle:
            lines = handle.read().splitlines()
    lines.append(entry)
    with open(path, "w") as handle:
        handle.write("\n".join(lines[-max_lines:]) + "\n")


def lookup_webhook(channel, csv_path=WEBHOOKS_CSV):
    """The webhook row for `channel` in slack_webhooks.csv, or "" if none.

    Looked up here, by us, and passed with `--webhook` so
    slackbot-notify.sh never falls back to SLACK_WEBHOOK_URL or #general.
    """
    target = (channel or "").strip().lower().lstrip("#")
    if not target or not os.path.isfile(csv_path):
        return ""
    try:
        with open(csv_path, newline="") as handle:
            for row in csv.DictReader(handle):
                chan = (row.get("channel") or "").strip().lower().lstrip("#")
                webhook = (row.get("webhook_url") or "").strip()
                if chan == target and webhook:
                    return webhook
    except OSError:
        return ""
    return ""


def compute_sweep(checks, results, state):
    """Compare this sweep's `results` (by name) against the stored `state`.

    Returns (proposed, pending, bad_list, back_list):
    - `proposed` is the new state for entries that need no Slack message -
      safe to save regardless of whether a send later succeeds.
    - `pending` is the new state for entries in `bad_list`/`back_list`: only
      commit it once the message carrying it has actually been sent.
    Entries no longer in `checks` (removed, or now `notify = 0`) are simply
    absent from both, which is how they get dropped from the state file.
    """
    proposed = {}
    pending = {}
    bad_list = []
    back_list = []
    for check in checks:
        name = check["name"]
        result = results[name]
        state_now = result["state"]
        prev = state.get(name, _DEFAULT_ENTRY)

        if state_now == UNKNOWN:
            proposed[name] = prev
            continue

        is_bad = state_now in (DOWN, WARN)
        if is_bad:
            streak = prev["streak"] + 1 if prev["bad"] else 1
            if streak >= 2 and not prev["notified"]:
                bad_list.append((check, result))
                pending[name] = {"bad": True, "streak": streak, "notified": True}
            else:
                proposed[name] = {"bad": True, "streak": streak, "notified": prev["notified"]}
        else:
            if prev["bad"] and prev["notified"]:
                back_list.append((check, result))
                pending[name] = {"bad": False, "streak": 0, "notified": False}
            else:
                proposed[name] = {"bad": False, "streak": 0, "notified": False}
    return proposed, pending, bad_list, back_list


def cockpit_url():
    return "http://%s:%d/" % (LINK_HOST or "localhost", PORT)


def build_message(bad_list, back_list):
    """One Slack message for a sweep that has something to say."""
    lines = []
    if bad_list:
        lines.append("*Down:*")
        for check, result in bad_list:
            lines.append(
                "• *%s* (%s) — %s — %s"
                % (check["name"], check["group"], result["state"], result.get("detail", ""))
            )
    if back_list:
        if lines:
            lines.append("")
        lines.append("*Back up:*")
        for check, result in back_list:
            lines.append("• *%s* (%s)" % (check["name"], check["group"]))
    lines.append("")
    lines.append(cockpit_url())
    status = "error" if bad_list else "ok"
    return TITLE, "\n".join(lines), status


def send_slack(title, message, status, channel, webhook):
    try:
        result = subprocess.run(
            [
                NOTIFY_SCRIPT,
                "--title", title,
                "--status", status,
                "--channel", channel,
                "--webhook", webhook,
                message,
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def run_sweep(checks, run_check_fn, state_path, log_path, channel, csv_path=WEBHOOKS_CSV, sender=send_slack):
    """One sweep: probe, compare, maybe send, persist, log. Returns an exit code."""
    state = load_state(state_path)
    results = {check["name"]: run_check_fn(check) for check in checks}
    proposed, pending, bad_list, back_list = compute_sweep(checks, results, state)

    if not bad_list and not back_list:
        save_state(state_path, proposed)
        append_log(log_path, "notify: sweep ok")
        return 0

    webhook = lookup_webhook(channel, csv_path)
    if not webhook:
        final = dict(proposed)
        for name in pending:
            final[name] = state.get(name, _DEFAULT_ENTRY)
        save_state(state_path, final)
        append_log(log_path, "notify: FAILED no webhook for %s" % channel)
        return 1

    title, message, status = build_message(bad_list, back_list)
    sent = sender(title, message, status, channel, webhook)

    final = dict(proposed)
    if sent:
        final.update(pending)
        save_state(state_path, final)
        append_log(log_path, "notify: sweep ok")
        return 0

    for name in pending:
        final[name] = state.get(name, _DEFAULT_ENTRY)
    save_state(state_path, final)
    append_log(log_path, "notify: FAILED slack send failed")
    return 1


def main():
    channel = os.environ.get("STATUS_NOTIFY_CHANNEL", "").strip() or DEFAULT_CHANNEL
    try:
        checks = eligible_checks()
    except SystemExit as exc:
        append_log(LOG_PATH, "notify: FAILED %s" % exc.code)
        return 1
    except Exception as exc:  # a broken services.conf must not crash the timer silently
        append_log(LOG_PATH, "notify: FAILED %s" % exc)
        return 1

    return run_sweep(checks, run_check, STATE_PATH, LOG_PATH, channel, WEBHOOKS_CSV)
