#!/usr/bin/env python3
"""Slack ideas bot: drop ideas onto the cockpit's Obsidian board from Slack.

Runs over Socket Mode (an outbound WebSocket), so it needs no public URL and
no tunnel route. Credentials come from ~/.config/homelab/slack.env:

    SLACK_BOT_TOKEN   xoxb-...  (scopes: commands, chat:write, app_mentions:read, im:history)
    SLACK_APP_TOKEN   xapp-...  (connections:write, Socket Mode enabled)

Commands (as /idea, as an @mention, or in a DM to the bot):

    /idea                          open a form: title, board, category, labels, owned, notes
    /idea <title> [#tags] [— notes] drop a quick idea into the inbox
    /idea to <project>: <note>     append a note to the card that best matches <project>

Writes go through ideas_manager, the same code the /ideas page uses, so the
vault stays in the format Obsidian and the CEO agent expect.
"""

import logging
import os
import re
import sys

import ideas_manager

COCKPIT_URL = os.environ.get("IDEAS_URL", "https://homelab.zakariafadli.com/idea")
INBOX_CATEGORY = os.environ.get("SLACK_IDEAS_CATEGORY", "Inbox")
# Optional allow-list of Slack user ids (comma separated); empty = anyone in the workspace.
ALLOWED_USERS = {u.strip() for u in os.environ.get("SLACK_IDEAS_ALLOWED_USERS", "").split(",") if u.strip()}
MODAL_ID = "idea_modal"

HELP = (
    "*Drop ideas onto the board* (<{url}|cockpit /idea>)\n"
    "• `/idea` - open the form\n"
    "• `/idea Pet blog network #saas — reddit case study` - quick idea into the inbox\n"
    "• `/idea Farah stock alerts #owned` - `#owned` marks a founder mandate (no kill gates)\n"
    "• `/idea to farah erp: add low-stock alerts` - add a note to an existing card"
).format(url=COCKPIT_URL)

log = logging.getLogger("slack-ideas-bot")


def parse_idea_command(text):
    """Turn the text after /idea (or a mention) into an action dict.

    {"action": "modal"} | {"action": "help"}
    {"action": "append", "project": str, "note": str}
    {"action": "create", "title": str, "notes": str, "tags": [str]}
    """
    text = (text or "").strip()
    if not text:
        return {"action": "modal"}
    if text.lower() in ("help", "?", "-h", "--help"):
        return {"action": "help"}

    m = re.match(r"^to\s+(.+?)\s*:\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
    if m:
        return {"action": "append", "project": m.group(1).strip(), "note": m.group(2).strip()}

    tags = ideas_manager.extract_labels(text)
    body = ideas_manager.TAG_RE.sub("", text)
    parts = re.split(r"\s+(?:—|--)\s+", body, maxsplit=1)
    title = re.sub(r"\s+", " ", parts[0]).strip(" -—:")
    notes = parts[1].strip() if len(parts) > 1 else ""
    if not title:
        return {"action": "help"}
    return {"action": "create", "title": title, "notes": notes, "tags": tags}


def default_backend():
    """Board file quick ideas land in: SLACK_IDEAS_FILE, else the first backend."""
    backends = ideas_manager.discover_backend_files()
    wanted = os.environ.get("SLACK_IDEAS_FILE")
    if wanted and wanted in backends:
        return wanted
    for f in ideas_manager.DEFAULT_BACKENDS:
        if f in backends:
            return f
    return backends[0] if backends else ideas_manager.DEFAULT_BACKENDS[0]


def create_idea(title, notes="", tags=(), target_file=None, category=None):
    res = ideas_manager.add_idea(
        title=title,
        category=category or INBOX_CATEGORY,
        target_file=target_file or default_backend(),
        status="untagged",
        notes=notes,
        tags=list(tags),
    )
    if not res.get("ok"):
        return f":warning: Could not add the idea: {res.get('message')}"
    labels = " ".join(f"`#{t}`" for t in res.get("tags", []))
    return (f":bulb: Added *{res['title']}* to `{res['file']}` › {res['category']}"
            f"{' ' + labels if labels else ''}\n<{COCKPIT_URL}|View on the cockpit>")


def append_to_project(project, note, source="Slack"):
    matches = ideas_manager.find_ideas(project, limit=3)
    if not matches:
        return f":mag: No card matches *{project}*. Check the title on <{COCKPIT_URL}|the board>."
    res = ideas_manager.append_note(matches[0]["id"], note, source=source)
    if not res.get("ok"):
        return f":warning: Could not add the note: {res.get('message')}"
    reply = f":memo: Added to *{res['title']}* (`{res['file']}`)\n<{COCKPIT_URL}|View on the cockpit>"
    others = [m["title"] for m in matches[1:]]
    if others:
        reply += "\n_Other close matches: " + "; ".join(others) + " - be more specific to target those._"
    return reply


def handle_text(text, source="Slack"):
    """Run a text command. Returns the reply, or None when a modal should open."""
    cmd = parse_idea_command(text)
    if cmd["action"] == "modal":
        return None
    if cmd["action"] == "help":
        return HELP
    if cmd["action"] == "append":
        return append_to_project(cmd["project"], cmd["note"], source=source)
    return create_idea(cmd["title"], cmd["notes"], cmd["tags"])


def build_idea_modal(backends=None, channel_id=""):
    """Slack view for the full idea form."""
    backends = backends or ideas_manager.discover_backend_files() or ideas_manager.DEFAULT_BACKENDS
    default = default_backend()
    options = [{"text": {"type": "plain_text", "text": f[:75]}, "value": f} for f in backends]
    initial = next((o for o in options if o["value"] == default), options[0])

    def text_input(block_id, label, placeholder, optional=True, multiline=False):
        return {
            "type": "input",
            "block_id": block_id,
            "optional": optional,
            "label": {"type": "plain_text", "text": label},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "multiline": multiline,
                "placeholder": {"type": "plain_text", "text": placeholder},
            },
        }

    return {
        "type": "modal",
        "callback_id": MODAL_ID,
        "private_metadata": channel_id or "",
        "title": {"type": "plain_text", "text": "Drop an idea"},
        "submit": {"type": "plain_text", "text": "Add to board"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            text_input("title", "Idea", "e.g. Autonomous PR test triager", optional=False),
            {
                "type": "input",
                "block_id": "board",
                "label": {"type": "plain_text", "text": "Board"},
                "element": {"type": "static_select", "action_id": "value",
                            "options": options, "initial_option": initial},
            },
            text_input("category", "Category", f"Section heading (default: {INBOX_CATEGORY})"),
            text_input("tags", "Labels", "#saas #hardware"),
            {
                "type": "input",
                "block_id": "owned",
                "optional": True,
                "label": {"type": "plain_text", "text": "Founder mandate"},
                "element": {
                    "type": "checkboxes",
                    "action_id": "value",
                    "options": [{
                        "text": {"type": "plain_text", "text": "Owned - no auto-evaluation (#owned)"},
                        "value": "owned",
                    }],
                },
            },
            text_input("notes", "Notes", "Pain point, links, stack...", multiline=True),
        ],
    }


def parse_modal_values(values):
    """Pull the form fields out of a view_submission state."""
    def val(block):
        v = values.get(block, {}).get("value", {})
        if v.get("type") == "static_select":
            return (v.get("selected_option") or {}).get("value", "")
        if v.get("type") == "checkboxes":
            return [o.get("value") for o in v.get("selected_options") or []]
        return (v.get("value") or "").strip()

    tags = ideas_manager.normalize_tags(val("tags"))
    if "owned" in val("owned") and "owned" not in tags:
        tags.append("owned")
    return {
        "title": val("title"),
        "target_file": val("board"),
        "category": val("category") or INBOX_CATEGORY,
        "tags": tags,
        "notes": val("notes"),
    }


def allowed(user_id):
    return not ALLOWED_USERS or user_id in ALLOWED_USERS


def strip_mention(text):
    return re.sub(r"<@[A-Z0-9]+>", "", text or "").strip()


def build_app(app):
    """Register the handlers on a slack_bolt App."""

    @app.command("/idea")
    def on_idea(ack, body, client, respond):
        ack()
        if not allowed(body.get("user_id")):
            respond(text=":no_entry: You are not on this bot's allow-list.")
            return
        reply = handle_text(body.get("text", ""))
        if reply is None:
            client.views_open(trigger_id=body["trigger_id"],
                              view=build_idea_modal(channel_id=body.get("channel_id", "")))
            return
        respond(text=reply, response_type="ephemeral")

    @app.view(MODAL_ID)
    def on_modal_submit(ack, body, client, view):
        form = parse_modal_values(view["state"]["values"])
        if not form["title"]:
            ack(response_action="errors", errors={"title": "The idea needs a title"})
            return
        ack()
        user = body["user"]["id"]
        if not allowed(user):
            return
        reply = create_idea(form["title"], form["notes"], form["tags"],
                            target_file=form["target_file"], category=form["category"])
        client.chat_postMessage(channel=user, text=reply)

    @app.event("app_mention")
    def on_mention(event, say):
        if not allowed(event.get("user")):
            return
        reply = handle_text(strip_mention(event.get("text", ""))) or HELP
        say(text=reply, thread_ts=event.get("thread_ts") or event.get("ts"))

    @app.event("message")
    def on_dm(event, say):
        # Only direct messages from people; channel chatter is ignored.
        if event.get("channel_type") != "im" or event.get("bot_id") or event.get("subtype"):
            return
        if not allowed(event.get("user")):
            return
        say(text=handle_text(strip_mention(event.get("text", ""))) or HELP)

    return app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    missing = [k for k in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN") if not os.environ.get(k)]
    if missing:
        log.error("missing %s (expected in ~/.config/homelab/slack.env)", ", ".join(missing))
        return 1

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = build_app(App(token=os.environ["SLACK_BOT_TOKEN"]))
    log.info("ideas vault: %s; quick ideas go to %s > %s",
             ideas_manager.get_ideas_dir(), default_backend(), INBOX_CATEGORY)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
