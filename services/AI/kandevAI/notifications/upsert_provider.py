#!/usr/bin/env python3
"""Keep the Slack notification provider in sync with slack.json (idempotent
upsert), and check that step_names covers every step where a card waits on
the user (see notifications/slack.json and the "Slack notifications"
section of the README).
"""


def waiting_steps(steps):
    """Steps of one workflow where a card waits for the user: no
    auto_start_agent on enter, not the inbox (position 0), and not
    complete_task_on_enter."""
    result = []
    for step in steps:
        on_enter = step.get("events", {}).get("on_enter", [])
        auto_starts = any(event.get("type") == "auto_start_agent" for event in on_enter)
        if auto_starts or step.get("position") == 0 or step.get("complete_task_on_enter"):
            continue
        result.append(step)
    return result
