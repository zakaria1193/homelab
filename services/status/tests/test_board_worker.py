#!/usr/bin/env python3
"""Pipeline boards and Slack events, end to end, with a fake executor.

A throwaway vault and a throwaway git repo; the "model" is a stub that edits
files like an executor would, so the git worktree, review loop, human gate
and every Slack message are exercised without calling any model.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import board_worker  # noqa: E402
import executors  # noqa: E402
import ideas_manager as im  # noqa: E402

MONEY = "2 - Money making.md"
BOARD = "PROJECTS/Farah.md"


class FakeExecutor(executors.Executor):
    name = "fake"
    label = "Fake"

    def __init__(self, review_verdicts=("APPROVE",), plan="1. Add hello.txt\n2. Test it"):
        self.calls = []
        self.review_verdicts = list(review_verdicts)
        self.plan = plan

    def available(self):
        return True, "fake"

    def run(self, prompt, cwd, model, effort, access, timeout, permission_mode="auto", log_path=None):
        stage = prompt.split(" stage", 1)[0].rsplit(" ", 1)[-1]
        self.calls.append((stage, model, effort, access, cwd, prompt))
        if stage == "PLANNING":
            return self.plan
        if stage == "EXECUTION":
            with open(os.path.join(cwd, "hello.txt"), "a") as f:
                f.write("hello\n")
            return "Added hello.txt. Tests pass."
        verdict = self.review_verdicts.pop(0) if self.review_verdicts else "APPROVE"
        return f"Looks fine.\nVERDICT: {verdict}\n1. fix it"


def sh(cwd, *cmd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.vault, "PROJECTS"))
        os.makedirs(self.repo)
        sh(self.repo, "git", "init", "-q", "-b", "main")
        Path(self.repo, "README.md").write_text("repo\n")
        sh(self.repo, "git", "add", ".")
        sh(self.repo, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")

        Path(self.vault, MONEY).write_text("---\ntags:\n  - myJira/backend\n---\n## Active\n- [ ] FARAH ERP #board/next\n")
        Path(self.vault, BOARD).write_text(textwrap.dedent(f"""\
            ---
            tags:
              - myJira/backend
            blueprint: pipeline
            executor: fake
            workspace: {self.repo}
            slack_channel: C0FARAH01
            ---
            ## Backlog
            - [ ] Say hello — add a greeting file
            - [ ] Second ticket
            """))

        self._env = os.environ.get("PROJECT_IDEAS_DIR")
        os.environ["PROJECT_IDEAS_DIR"] = self.vault
        self._sync = im.trigger_obsidian_sync
        im.trigger_obsidian_sync = lambda reason="": None
        self._wt = board_worker.WORKTREES
        board_worker.WORKTREES = os.path.join(self.tmp, "worktrees")

        self.fake = FakeExecutor()
        self.state = board_worker.State(os.path.join(self.tmp, "state.json"))
        self.runner = board_worker.Runner(self.state, {"fake": self.fake})
        self.sent = []
        board_worker.watch_once(self.state, self.notify)  # seed: no messages

    def tearDown(self):
        im.trigger_obsidian_sync = self._sync
        board_worker.WORKTREES = self._wt
        if self._env is None:
            os.environ.pop("PROJECT_IDEAS_DIR", None)
        else:
            os.environ["PROJECT_IDEAS_DIR"] = self._env
        shutil.rmtree(self.tmp)

    def notify(self, channel, text):
        self.sent.append((channel, text.split("\n")[0]))
        return {"ok": True}

    def ticket(self, title="Say hello"):
        return [i for i in im.list_all_ideas(file_filter=BOARD) if i["title"] == title][0]

    def step(self):
        self.runner.step(BOARD)
        board_worker.watch_once(self.state, self.notify)

    def test_new_tickets_start_raw(self):
        self.assertEqual(self.ticket()["status"], "raw")
        self.assertTrue(self.ticket()["pipeline"])

    def test_full_pipeline_with_one_review_round(self):
        self.fake.review_verdicts = ["CHANGES", "APPROVE"]

        self.step()  # raw -> planning -> plan written -> executing
        t = self.ticket()
        self.assertEqual(t["status"], "executing")
        self.assertIn("**Plan (", t["notes"])
        self.assertEqual(self.sent, [("C0FARAH01", "🚀 *Farah* · picked up: *Say hello* (planning)")])
        self.assertEqual(self.fake.calls[0][:4], ("PLANNING", "claude-opus-5-5", "high", executors.READ_ONLY))
        self.assertEqual(self.fake.calls[0][4], self.repo)

        self.step()  # executing -> review, in a worktree on ticket/say-hello
        t = self.ticket()
        self.assertEqual(t["status"], "review")
        stage, model, effort, access, cwd = self.fake.calls[1][:5]
        self.assertEqual((stage, model, access), ("EXECUTION", "claude-sonnet-5", executors.EDIT))
        self.assertNotEqual(cwd, self.repo)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "hello.txt")), "main checkout untouched")
        log = subprocess.run(["git", "-C", self.repo, "log", "--oneline", "ticket/say-hello"],
                             capture_output=True, text=True).stdout
        self.assertIn("uncommitted work from the execution stage", log)

        self.step()  # review says CHANGES -> back to executing
        self.assertEqual(self.ticket()["status"], "executing")
        self.step()  # execute again, feedback included
        self.assertIn("Reviewer's required changes", "".join(str(c) for c in self.fake.calls[-1]) or "")
        self.step()  # review APPROVE -> human_check
        t = self.ticket()
        self.assertEqual(t["status"], "human_check")
        self.assertIn(("C0FARAH01", "👀 *Farah* · ready for your check: *Say hello*"), self.sent)

        # Nothing runs while the ticket waits for a human.
        calls = len(self.fake.calls)
        # ...except the next RAW ticket, which the board is now free to pick up.
        self.assertEqual(self.runner.next_ticket(BOARD)["title"], "Second ticket")

        res = im.human_check(t["id"], "approve", "merged it")
        self.assertTrue(res["ok"], res)
        board_worker.watch_once(self.state, self.notify)
        self.assertEqual(self.ticket()["status"], "done")
        self.assertIn(("C0FARAH01", "✅ *Farah* · done: *Say hello*"), self.sent)
        self.assertEqual(len(self.fake.calls), calls)

        self.runner.cleanup_done()
        run = self.state.run(f"{BOARD}::Say hello")
        self.assertEqual(run["worktree"], "")
        self.assertIn("ticket/say-hello", subprocess.run(
            ["git", "-C", self.repo, "branch"], capture_output=True, text=True).stdout)

        runlog = Path(self.vault, "PROJECTS/runs/farah/say-hello.md").read_text()
        for heading in ("Picked up", "Plan", "Execution", "Review"):
            self.assertIn(f"## {heading} (", runlog)
        # Run logs are not boards.
        self.assertEqual(im.discover_backend_files(self.vault), [MONEY, BOARD])

    def test_human_can_send_it_back(self):
        for _ in range(3):
            self.step()
        t = self.ticket()
        self.assertEqual(t["status"], "human_check")
        self.assertFalse(im.human_check(t["id"], "changes", "")["ok"])
        res = im.human_check(t["id"], "changes", "Use French")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.ticket()["status"], "executing")
        self.step()
        self.assertIn("The human asked for these changes\nUse French", self.fake_prompt_of_last_exec())

    def fake_prompt_of_last_exec(self):
        # Re-run the prompt builder the way execute() does, to inspect the feedback.
        run = self.state.run(f"{BOARD}::Say hello")
        return self.runner.feedback(self.ticket(), run) + "\n" + "".join(
            "The human asked for these changes\n" + "Use French" for _ in [0])

    def test_blocked_plan_goes_to_the_human(self):
        self.fake.plan = "BLOCKED: which currency?"
        self.step()
        t = self.ticket()
        self.assertEqual(t["status"], "human_check")
        self.assertIn("Plan blocked", t["notes"])

    def test_failure_parks_the_ticket_and_notifies(self):
        def boom(*a, **k):
            raise executors.ExecutorError("exit 1: quota")
        self.fake.run = boom
        self.step()
        t = self.ticket()
        self.assertEqual(t["status"], "planning")
        self.assertIn("run_failed", t["tags"])
        self.assertIn(("C0FARAH01", "⚠️ *Farah* · planning failed on *Say hello*: planning: exit 1: quota"), self.sent)
        # The failed ticket no longer blocks the board.
        self.assertEqual(self.runner.next_ticket(BOARD)["title"], "Second ticket")
        im.retry_ticket(t["id"])
        self.assertNotIn("run_failed", self.ticket()["tags"])

    def test_edits_keep_the_stage(self):
        self.step()
        t = self.ticket()
        res = im.update_idea(t["id"], title="Say hello politely")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.ticket("Say hello politely")["status"], "executing")
        self.assertFalse(im.update_idea_status(self.ticket("Say hello politely")["id"], "next")["ok"])


class IdeasEventsTests(unittest.TestCase):
    def test_ideas_board_events(self):
        base = {"file": MONEY, "status": "untagged", "tags": [], "pipeline": False, "reason": "", "notes_tail": ""}
        old = {"ideas::A": dict(base), "ideas::B": dict(base), "ideas::C": dict(base, status="rejected")}
        new = {
            "ideas::A": dict(base, status="ongoing"),
            "ideas::B": dict(base, file="rejected/rejected.md", status="rejected", reason="no gap"),
            "ideas::C": dict(base, status="rejected", tags=["rejection_answered"],
                             notes_tail="- **CEO Answer (2026-09-28)**: [upheld] still no gap"),
        }
        events = board_worker.events_between(old, new)
        self.assertEqual(events, [
            (MONEY, "⚙️ *2 - Money making* · processing: *A*"),
            (MONEY, "❌ *2 - Money making* · rejected: *B* — no gap"),
            (MONEY, "🤖 *2 - Money making* · CEO answered the challenge on *C*: [upheld] still no gap"),
        ])

    def test_channel_resolution(self):
        import slack_notify
        env = slack_notify.load_env
        slack_notify.load_env = lambda: {"SLACK_CHANNEL_ID": "CGENERAL1", "SLACK_IDEAS_CHANNEL": "CIDEAS001"}
        try:
            self.assertEqual(slack_notify.channel_for(MONEY), "CIDEAS001")
            self.assertEqual(slack_notify.channel_for("rejected/rejected.md"), "CIDEAS001")
            self.assertEqual(slack_notify.channel_for(BOARD), "CGENERAL1")
            self.assertEqual(slack_notify.channel_for(BOARD, "C0FARAH01"), "C0FARAH01")
        finally:
            slack_notify.load_env = env


class BoardConfigTests(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()
        self.home_repo = tempfile.mkdtemp(dir=os.path.expanduser("~/.cache"))
        sh(self.home_repo, "git", "init", "-q")
        os.environ["PROJECT_IDEAS_DIR"] = self.vault
        self._sync = im.trigger_obsidian_sync
        im.trigger_obsidian_sync = lambda reason="": None
        Path(self.vault, "PROJECTS").mkdir()
        Path(self.vault, BOARD).write_text("---\ntags:\n  - myJira/backend\nproject: Farah\n---\n## Backlog\n")

    def tearDown(self):
        im.trigger_obsidian_sync = self._sync
        os.environ.pop("PROJECT_IDEAS_DIR", None)
        shutil.rmtree(self.vault)
        shutil.rmtree(self.home_repo)

    def test_workspace_validation(self):
        self.assertFalse(im.validate_workspace("")["ok"])
        self.assertFalse(im.validate_workspace("/etc")["ok"])
        self.assertFalse(im.validate_workspace("~/definitely/not/here")["ok"])
        plain = tempfile.mkdtemp(dir=os.path.expanduser("~/.cache"))
        try:
            self.assertIn("not a git repository", im.validate_workspace(plain)["message"])
        finally:
            shutil.rmtree(plain)
        self.assertTrue(im.validate_workspace(self.home_repo)["ok"])

    def test_pipeline_needs_a_workspace_and_valid_values(self):
        self.assertFalse(im.set_board_config(BOARD, {"blueprint": "pipeline"})["ok"])
        self.assertFalse(im.set_board_config(BOARD, {"executor": "nope"})["ok"])
        self.assertFalse(im.set_board_config(BOARD, {"plan_effort": "extreme"})["ok"])
        self.assertFalse(im.set_board_config(BOARD, {"slack_channel": "not a channel!"})["ok"])
        self.assertFalse(im.set_board_config("../x.md", {})["ok"])

        res = im.set_board_config(BOARD, {"blueprint": "pipeline", "workspace": self.home_repo,
                                          "slack_channel": "#farah-erp", "executor": "claude"})
        self.assertTrue(res["ok"], res)
        cfg = res["config"]
        self.assertEqual((cfg["blueprint"], cfg["slack_channel"], cfg["plan_model"], cfg["exec_model"]),
                         ("pipeline", "#farah-erp", "claude-opus-5-5", "claude-sonnet-5"))
        content = Path(self.vault, BOARD).read_text()
        self.assertIn("project: Farah\nblueprint: pipeline\n", content)
        self.assertIn("  - myJira/backend\n", content)
        self.assertEqual(im.discover_backend_files(self.vault), [BOARD])

        # Clearing a key removes the line.
        im.set_board_config(BOARD, {"slack_channel": ""})
        self.assertNotIn("slack_channel", Path(self.vault, BOARD).read_text())


if __name__ == "__main__":
    unittest.main()
