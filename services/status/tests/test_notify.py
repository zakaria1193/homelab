#!/usr/bin/env python3
"""Tests for cockpit.notify: the Slack health-check sweep.

Feeds fake probe results through run_sweep with a fake sender, so no real
Slack webhook or services.conf is touched.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cockpit import notify  # noqa: E402
from cockpit.config import DOWN, SHELL, UNKNOWN, UP, WARN  # noqa: E402

CHANNEL = "#homelab-alerts"


def check(name, group="Services", ctype="systemd", notify_flag=True):
    return {"name": name, "group": group, "type": ctype, "notify": notify_flag}


def result(state, detail="detail"):
    return {"state": state, "detail": detail}


class FakeSender:
    """Records every call; `ok` controls whether the send "succeeds"."""

    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def __call__(self, title, message, status, channel, webhook):
        self.calls.append(
            {"title": title, "message": message, "status": status, "channel": channel, "webhook": webhook}
        )
        return self.ok


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = str(Path(self.tmp.name) / "notify-state.json")
        self.log_path = str(Path(self.tmp.name) / "notify.log")
        self.csv_path = str(Path(self.tmp.name) / "slack_webhooks.csv")
        self._write_csv({CHANNEL: "https://hooks.slack.test/real"})

    def _write_csv(self, rows):
        with open(self.csv_path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["channel", "webhook_url", "description"])
            for channel, webhook in rows.items():
                writer.writerow([channel, webhook, "test"])

    def _sweep(self, checks, results, sender=None):
        sender = sender or FakeSender()
        code = notify.run_sweep(
            checks,
            lambda c: results[c["name"]],
            self.state_path,
            self.log_path,
            CHANNEL,
            self.csv_path,
            sender,
        )
        return code, sender

    def _state(self):
        return json.loads(Path(self.state_path).read_text())

    # -- the two-sweep rule --------------------------------------------- #

    def test_one_bad_sweep_sends_nothing(self):
        checks = [check("svc")]
        code, sender = self._sweep(checks, {"svc": result(DOWN)})
        self.assertEqual(code, 0)
        self.assertEqual(sender.calls, [])
        self.assertEqual(self._state()["svc"]["streak"], 1)

    def test_two_bad_sweeps_in_a_row_send_one_down_message(self):
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        code, sender = self._sweep(checks, {"svc": result(DOWN, "still down")})
        self.assertEqual(code, 0)
        self.assertEqual(len(sender.calls), 1)
        self.assertEqual(sender.calls[0]["status"], "error")
        self.assertIn("svc", sender.calls[0]["message"])
        self.assertIn("still down", sender.calls[0]["message"])
        self.assertTrue(self._state()["svc"]["notified"])

    def test_third_bad_sweep_and_red_to_amber_send_nothing(self):
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        self._sweep(checks, {"svc": result(DOWN)})  # sends the "down" message
        code, sender = self._sweep(checks, {"svc": result(WARN, "amber now")})
        self.assertEqual(code, 0)
        self.assertEqual(sender.calls, [])

    def test_recovery_sends_one_back_message(self):
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        self._sweep(checks, {"svc": result(DOWN)})
        code, sender = self._sweep(checks, {"svc": result(UP, "fine")})
        self.assertEqual(code, 0)
        self.assertEqual(len(sender.calls), 1)
        self.assertEqual(sender.calls[0]["status"], "ok")
        self.assertIn("svc", sender.calls[0]["message"])
        state = self._state()
        self.assertFalse(state["svc"]["bad"])
        self.assertFalse(state["svc"]["notified"])

    def test_one_bad_sweep_then_recovery_sends_nothing(self):
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        code, sender = self._sweep(checks, {"svc": result(UP)})
        self.assertEqual(code, 0)
        self.assertEqual(sender.calls, [])

    def test_unknown_changes_nothing(self):
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        before = self._state()
        code, sender = self._sweep(checks, {"svc": result(UNKNOWN, "can't tell")})
        self.assertEqual(code, 0)
        self.assertEqual(sender.calls, [])
        self.assertEqual(self._state(), before)

    # -- exclusions -------------------------------------------------------- #

    def test_notify_zero_and_shell_entries_never_alert(self):
        all_checks = [
            check("silenced", notify_flag=False),
            check("launcher", ctype=SHELL),
        ]
        results = {"silenced": result(DOWN), "launcher": result(DOWN)}
        eligible = notify.eligible_checks(all_checks)
        self.assertEqual(eligible, [])
        # Even if someone fed them in directly, two bad sweeps on an excluded
        # entry would otherwise notify - assert the filtering a caller is
        # expected to apply via eligible_checks() actually removes them.
        self._sweep(eligible, results)
        self._sweep(eligible, results)

    def test_disabled_unit_that_is_down_never_alerts(self):
        checks = [check("stopped")]
        down = {"state": DOWN, "detail": "inactive (dead)", "unit_file_state": "disabled"}
        self._sweep(checks, {"stopped": down})
        _, sender = self._sweep(checks, {"stopped": down})
        self.assertEqual(sender.calls, [])

    def test_failed_static_unit_still_alerts(self):
        checks = [check("oneshot")]
        failed = {"state": DOWN, "detail": "failed (failed)", "unit_file_state": "static"}
        self._sweep(checks, {"oneshot": failed})
        _, sender = self._sweep(checks, {"oneshot": failed})
        self.assertEqual(len(sender.calls), 1)

    def test_the_notifiers_own_log_card_never_alerts(self):
        own = check("health-notify")
        own["path"] = notify.LOG_PATH
        other = check("weekly-upgrade")
        other["path"] = "/tmp/elsewhere.log"
        self.assertEqual([c["name"] for c in notify.eligible_checks([own, other])], ["weekly-upgrade"])

    # -- grouping ------------------------------------------------------------ #

    def test_several_entries_going_bad_give_one_message(self):
        checks = [check("a"), check("b"), check("c")]
        bad = {"a": result(DOWN), "b": result(DOWN), "c": result(UP)}
        self._sweep(checks, bad)
        code, sender = self._sweep(checks, bad)
        self.assertEqual(code, 0)
        self.assertEqual(len(sender.calls), 1)
        self.assertIn("a", sender.calls[0]["message"])
        self.assertIn("b", sender.calls[0]["message"])
        self.assertNotIn("• *c*", sender.calls[0]["message"])

    # -- failure handling ---------------------------------------------------- #

    def test_failed_send_is_retried_next_sweep(self):
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        failing = FakeSender(ok=False)
        code, sender = self._sweep(checks, {"svc": result(DOWN)}, sender=failing)
        self.assertEqual(code, 1)
        self.assertEqual(len(failing.calls), 1)
        self.assertFalse(self._state()["svc"]["notified"])

        retry = FakeSender(ok=True)
        code, sender = self._sweep(checks, {"svc": result(DOWN)}, sender=retry)
        self.assertEqual(code, 0)
        self.assertEqual(len(retry.calls), 1)
        self.assertTrue(self._state()["svc"]["notified"])

    def test_no_webhook_row_sends_nothing_and_stays_pending(self):
        self._write_csv({"#general": "https://hooks.slack.test/general"})
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        code, sender = self._sweep(checks, {"svc": result(DOWN)})
        self.assertEqual(code, 1)
        self.assertEqual(sender.calls, [])
        self.assertFalse(self._state()["svc"]["notified"])
        log_text = Path(self.log_path).read_text()
        self.assertIn("notify: FAILED no webhook for %s" % CHANNEL, log_text)

        # The row shows up, and the pending alert goes out on the next try.
        self._write_csv({CHANNEL: "https://hooks.slack.test/real"})
        code, sender = self._sweep(checks, {"svc": result(DOWN)})
        self.assertEqual(code, 0)
        self.assertEqual(len(sender.calls), 1)
        self.assertNotIn("#general", sender.calls[0]["channel"])

    # -- entry lifecycle ------------------------------------------------------ #

    def test_entry_removed_while_bad_is_dropped_with_no_message(self):
        checks = [check("svc")]
        self._sweep(checks, {"svc": result(DOWN)})
        self._sweep(checks, {"svc": result(DOWN)})  # sends the "down" message, notified=True
        self.assertIn("svc", self._state())

        code, sender = self._sweep([], {})
        self.assertEqual(code, 0)
        self.assertEqual(sender.calls, [])
        self.assertNotIn("svc", self._state())


if __name__ == "__main__":
    unittest.main(verbosity=2)
