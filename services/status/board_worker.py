#!/usr/bin/env python3
"""Board worker: runs pipeline boards and tells Slack what moved.

Two jobs, one loop:

1. Pipeline runner. On every board whose blueprint is `pipeline` (see
   ideas_manager.BOARD_DEFAULTS), one ticket at a time goes
       raw -> planning   (strong model, high effort, read-only)
           -> executing  (mid model, in a git worktree on branch ticket/<slug>)
           -> review     (strong model, read-only; may send it back to executing)
           -> human_check  (waits for Approve / Request changes on the card)
           -> done
   Stage output goes to a run log note, PROJECTS/runs/<board>/<ticket>.md,
   and a one-line summary goes on the card.

2. Watcher. Compares every board with the last pass and posts transitions to
   the board's Slack channel, whoever made them (page, Idea Feasibility Agent, Obsidian,
   this worker): ideas boards on processing / rejected / shelved / challenge
   answers, pipeline boards on picked up / ready for check / done / failed.

    python3 board_worker.py            # run forever (the systemd unit)
    python3 board_worker.py --once     # one watcher pass + start due stages, then wait for them
"""

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time

import executors
import ideas_manager as im
import slack_notify

STATE_DIR = os.path.expanduser(os.environ.get("BOARD_WORKER_STATE", "~/.local/state/homelab/board-worker"))
WORKTREES = os.path.join(STATE_DIR, "worktrees")
POLL_SECONDS = int(os.environ.get("BOARD_WORKER_POLL", "15"))
COCKPIT_URL = os.environ.get("IDEAS_URL", "https://homelab.zakariafadli.com/idea")
TIMEOUTS = {
    "planning": int(os.environ.get("BOARD_PLAN_TIMEOUT", "1800")),
    "executing": int(os.environ.get("BOARD_EXEC_TIMEOUT", "3600")),
    "review": int(os.environ.get("BOARD_REVIEW_TIMEOUT", "1800")),
}
RUNS_DIR = "PROJECTS/runs"

log = logging.getLogger("board-worker")


def slugify(text, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s[:limit].rstrip("-") or "ticket")


def summary(text, limit=280):
    """First meaningful line of a stage's output, for the card."""
    for line in (text or "").split("\n"):
        line = re.sub(r"^[#>*\-\s]+", "", line).strip()
        if len(line) > 3:
            return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"
    return "(no output)"


def git(cwd, *args, check=True):
    res = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=120)
    if check and res.returncode != 0:
        raise executors.ExecutorError(f"git {' '.join(args)}: {res.stderr.strip()[-400:]}")
    return res.stdout.strip()


# ------------------------------------------------------------------ state --- #

class State:
    """Persisted worker memory: the last board snapshot and per-ticket runs."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.data = {"snapshot": None, "runs": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)

    def run(self, key):
        with self.lock:
            return self.data["runs"].setdefault(key, {})

    def update_run(self, key, **fields):
        with self.lock:
            self.data["runs"].setdefault(key, {}).update(fields)
        self.save()


# ---------------------------------------------------------------- watcher --- #

def group_of(file):
    """Ideas boards (top-level notes + rejected.md) are one group: a ticket
    moving to rejected.md is the same ticket changing status."""
    return "ideas" if ("/" not in file or file.startswith("rejected/")) else file


def snapshot(ideas):
    snap = {}
    for i in ideas:
        snap[f"{group_of(i['file'])}::{i['title']}"] = {
            "file": i["file"], "status": i["status"], "tags": i["tags"],
            "pipeline": bool(i.get("pipeline")), "reason": i.get("rejection_reason", ""),
            "notes_tail": i["notes"][-1500:],
        }
    return snap


def last_entry(notes, label):
    found = re.findall(rf"\*\*{label} \(([^)]*)\)\*\*:?\s*(.*)", notes or "")
    return found[-1][1].strip() if found else ""


def events_between(old, new):
    """[(board_file, message)] for everything worth a Slack message."""
    events = []
    for key, cur in new.items():
        prev = old.get(key)
        if prev is None:
            continue
        title = key.split("::", 1)[1]
        st, was = cur["status"], prev["status"]
        added = set(cur["tags"]) - set(prev["tags"])
        board = prev["file"] if group_of(prev["file"]) == "ideas" else cur["file"]
        name = board.rsplit("/", 1)[-1][:-3]
        if cur["pipeline"]:
            if was == "raw" and st != "raw":
                events.append((board, f"🚀 *{name}* · picked up: *{title}* (planning)"))
            if st == "human_check" and was != "human_check":
                events.append((board, f"👀 *{name}* · ready for your check: *{title}*"))
            if st == "done" and was != "done":
                events.append((board, f"✅ *{name}* · done: *{title}*"))
            if im.TAG_RUN_FAILED in added:
                why = last_entry(cur["notes_tail"], "Failed")
                events.append((board, f"⚠️ *{name}* · {cur['status']} failed on *{title}*: {why}"))
            continue
        if st != was:
            if st == "ongoing":
                events.append((board, f"⚙️ *{name}* · processing: *{title}*"))
            elif st == "rejected":
                events.append((board, f"❌ *{name}* · rejected: *{title}*" + (f" — {cur['reason']}" if cur["reason"] else "")))
            elif st == "shelved":
                events.append((board, f"🧊 *{name}* · shelved: *{title}*" + (f" — {cur['reason']}" if cur["reason"] else "")))
            elif st == "next" and was in ("rejected", "shelved"):
                events.append((board, f"♻️ *{name}* · back in Next: *{title}*"))
        if im.TAG_CHALLENGED in added:
            events.append((board, f"⚖️ *{name}* · rejection challenged: *{title}* — {last_entry(cur['notes_tail'], 'Challenge')}"))
        if im.TAG_ANSWERED in added:
            events.append((board, f"🤖 *{name}* · Idea Feasibility Agent answered the challenge on *{title}*: {last_entry(cur['notes_tail'], 'Feasibility Answer')}"))
    return events


# ----------------------------------------------------------------- runner --- #

PLAN_PROMPT = """You are the PLANNING stage of an automated ticket pipeline for the project "{board}".
The current directory is the project's repository. You can read it; you cannot change it.

Ticket: {title}
Details from the board:
{notes}

Write an implementation plan that a less capable engineer can execute without asking questions:
1. Goal and acceptance criteria.
2. Files to change or create, and what changes in each.
3. Ordered steps.
4. Tests to add or run, with the exact commands.
5. Risks and what must not change.

If the ticket is too vague to plan safely, start your answer with a line "BLOCKED:" followed by exactly
what the human must clarify. Output markdown only."""

EXEC_PROMPT = """You are the EXECUTION stage of an automated ticket pipeline for the project "{board}".
You are in a git worktree on branch {branch}. Only change files inside this directory.

Ticket: {title}

Implement the plan below. Run the tests it names. Commit your work on this branch with clear
messages (git add + git commit). Do not push, do not switch branches, do not rewrite history.
End with a short summary: what changed, test results, anything left undone.

# Plan
{plan}
{feedback}"""

REVIEW_PROMPT = """You are the REVIEW stage of an automated ticket pipeline for the project "{board}".
The current directory is the ticket's worktree (branch {branch}); you can read it, not change it.

Ticket: {title}

# Plan
{plan}

# Executor's summary
{execution}

# Diff ({base}..HEAD)
{diffstat}

{diff}

Review the change against the plan and its acceptance criteria: correctness, bugs, missing or
failing tests, unintended changes. Be concrete (file:line). End with exactly one line:
VERDICT: APPROVE
or
VERDICT: CHANGES
followed by the numbered list of required changes."""


class Runner:
    def __init__(self, state, executor_map=None):
        self.state = state
        self.executors = executor_map or executors.EXECUTORS
        self.busy = {}  # board file -> Thread

    # -- helpers ---------------------------------------------------------- #

    def ticket_key(self, board, title):
        return f"{board}::{title}"

    def find(self, board, title):
        for i in im.list_all_ideas(file_filter=board):
            if i["title"] == title:
                return i
        return None

    def run_log(self, board, title):
        rel = f"{RUNS_DIR}/{slugify(board.rsplit('/', 1)[-1][:-3])}/{slugify(title)}.md"
        return rel, os.path.join(im.get_ideas_dir(), rel)

    def append_log(self, board, title, heading, body):
        rel, path = self.run_log(board, title)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.isfile(path)
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write(f"# Run log: {title}\n\nBoard: [[{board[:-3]}]]\n")
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            f.write(f"\n## {heading} ({stamp})\n\n{body.strip()}\n")
        return rel

    def fail(self, board, title, stage, err):
        t = self.find(board, title)
        log.error("%s / %s: %s failed: %s", board, title, stage, err)
        self.append_log(board, title, f"{stage} failed", str(err))
        if t:
            im.set_stage(t["id"], t["status"], "Failed", f"{stage}: {str(err)[:300]}",
                         add_tags=(im.TAG_RUN_FAILED,))

    # -- scheduling ------------------------------------------------------- #

    def pipeline_boards(self):
        boards = []
        for f in im.discover_backend_files():
            cfg = im.get_board_config(f)
            if cfg and cfg["blueprint"] == "pipeline" and cfg["workspace"]:
                boards.append(cfg)
        return boards

    def next_ticket(self, board):
        tickets = [t for t in im.list_all_ideas(file_filter=board)
                   if t.get("pipeline") and im.TAG_RUN_FAILED not in t["tags"]]
        for t in tickets:  # resume whatever was in flight first
            if t["status"] in im.ACTIVE_STAGES:
                return t
        for t in tickets:
            if t["status"] == "raw":
                return t
        return None

    def tick(self, wait=False):
        """Start one stage on every idle pipeline board."""
        for cfg in self.pipeline_boards():
            th = self.busy.get(cfg["file"])
            if th and th.is_alive():
                continue
            if not self.next_ticket(cfg["file"]):
                continue
            th = threading.Thread(target=self.step, args=(cfg["file"],), daemon=True, name=cfg["file"])
            self.busy[cfg["file"]] = th
            th.start()
        if wait:
            for th in list(self.busy.values()):
                th.join()

    def step(self, board):
        """Advance the board's current ticket by one stage (synchronous)."""
        cfg = im.get_board_config(board)
        ticket = self.next_ticket(board)
        if not cfg or not ticket:
            return
        title = ticket["title"]
        executor = self.executors.get(cfg["executor"])
        if not executor:
            self.fail(board, title, ticket["status"], f"unknown executor '{cfg['executor']}'")
            return
        try:
            if ticket["status"] == "raw":
                rel, _ = self.run_log(board, title)
                self.append_log(board, title, "Picked up", f"Executor: {executor.label}")
                im.set_stage(ticket["id"], "planning", "Picked up",
                             f"by {cfg['executor']} · plan {cfg['plan_model']} · [[{rel[:-3]}|run log]]")
                ticket = self.find(board, title)
            if ticket["status"] == "planning":
                self.plan(cfg, executor, ticket)
            elif ticket["status"] == "executing":
                self.execute(cfg, executor, ticket)
            elif ticket["status"] == "review":
                self.review(cfg, executor, ticket)
        except executors.ExecutorError as e:
            t = self.find(board, title)
            self.fail(board, title, t["status"] if t else "stage", e)
        except Exception as e:  # never let one ticket kill the worker
            log.exception("unexpected error on %s / %s", board, title)
            self.fail(board, title, "stage", f"internal error: {e}")

    # -- stages ----------------------------------------------------------- #

    def plan(self, cfg, executor, ticket):
        board, title = cfg["file"], ticket["title"]
        prompt = PLAN_PROMPT.format(board=board.rsplit("/", 1)[-1][:-3], title=title,
                                    notes=ticket["notes"] or "(none)")
        out = executor.run(prompt, cfg["workspace"], cfg["plan_model"], cfg["plan_effort"],
                           executors.READ_ONLY, TIMEOUTS["planning"])
        self.append_log(board, title, "Plan", out)
        self.state.update_run(self.ticket_key(board, title), plan=out, review_rounds=0)
        if out.lstrip().upper().startswith("BLOCKED:"):
            im.set_stage(ticket["id"], "human_check", "Plan blocked", summary(out))
        else:
            im.set_stage(ticket["id"], "executing", "Plan", summary(out))

    def worktree(self, cfg, title):
        key = self.ticket_key(cfg["file"], title)
        run = self.state.run(key)
        path = run.get("worktree")
        if path and os.path.isdir(path):
            return run
        branch = f"ticket/{slugify(title)}"
        path = os.path.join(WORKTREES, slugify(cfg["file"].rsplit("/", 1)[-1][:-3]), slugify(title))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        base = git(cfg["workspace"], "rev-parse", "HEAD")
        exists = git(cfg["workspace"], "branch", "--list", branch)
        if exists:
            git(cfg["workspace"], "worktree", "add", path, branch)
        else:
            git(cfg["workspace"], "worktree", "add", "-b", branch, path, base)
        self.state.update_run(key, worktree=path, branch=branch, base=run.get("base") or base)
        return self.state.run(key)

    def feedback(self, ticket, run):
        parts = []
        if run.get("last_review"):
            parts.append("# Reviewer's required changes (address all of them)\n" + run["last_review"])
        human = re.findall(r"\*\*Human check \([^)]*\)\*\*:?\s*\[changes requested\]\s*(.*)", ticket["notes"])
        if human:
            parts.append("# The human asked for these changes\n" + human[-1])
        return ("\n\n" + "\n\n".join(parts)) if parts else ""

    def execute(self, cfg, executor, ticket):
        board, title = cfg["file"], ticket["title"]
        run = self.worktree(cfg, title)
        plan = run.get("plan") or "(plan missing - work from the ticket)\n" + ticket["notes"]
        prompt = EXEC_PROMPT.format(board=board.rsplit("/", 1)[-1][:-3], branch=run["branch"],
                                    title=title, plan=plan, feedback=self.feedback(ticket, run))
        out = executor.run(prompt, run["worktree"], cfg["exec_model"], cfg["exec_effort"],
                           executors.EDIT, TIMEOUTS["executing"],
                           permission_mode=cfg["exec_permission_mode"])
        # Commit anything the executor left uncommitted, so review sees it.
        if git(run["worktree"], "status", "--porcelain"):
            git(run["worktree"], "add", "-A")
            git(run["worktree"], "-c", "user.name=board-worker", "-c", "user.email=board-worker@localhost",
                "commit", "-m", f"{title} (uncommitted work from the execution stage)")
        commits = git(run["worktree"], "rev-list", "--count", f"{run['base']}..HEAD")
        self.append_log(board, title, "Execution", out + f"\n\nBranch `{run['branch']}`, {commits} commit(s) since `{run['base'][:10]}`.")
        self.state.update_run(self.ticket_key(board, title), execution=out)
        im.set_stage(ticket["id"], "review", "Execution",
                     f"{summary(out)} (branch `{run['branch']}`, {commits} commit(s))")

    def review(self, cfg, executor, ticket):
        board, title = cfg["file"], ticket["title"]
        key = self.ticket_key(board, title)
        run = self.worktree(cfg, title)
        diff = git(run["worktree"], "diff", f"{run['base']}..HEAD")
        if len(diff) > 150_000:
            diff = diff[:150_000] + "\n... (diff truncated; read the files directly)"
        prompt = REVIEW_PROMPT.format(
            board=board.rsplit("/", 1)[-1][:-3], branch=run["branch"], title=title,
            plan=run.get("plan", ""), execution=run.get("execution", ""), base=run["base"][:10],
            diffstat=git(run["worktree"], "diff", "--stat", f"{run['base']}..HEAD") or "(no changes)",
            diff=diff or "(empty diff)")
        out = executor.run(prompt, run["worktree"], cfg["review_model"], cfg["review_effort"],
                           executors.READ_ONLY, TIMEOUTS["review"])
        self.append_log(board, title, "Review", out)
        m = re.search(r"VERDICT:\s*(APPROVE|CHANGES)", out, re.IGNORECASE)
        verdict = m.group(1).upper() if m else "CHANGES"
        rounds = int(run.get("review_rounds", 0)) + (1 if verdict == "CHANGES" else 0)
        self.state.update_run(key, last_review=out if verdict == "CHANGES" else "", review_rounds=rounds)
        if verdict == "CHANGES" and rounds <= int(cfg["max_review_rounds"]):
            im.set_stage(ticket["id"], "executing", "Review",
                         f"[changes] round {rounds}/{cfg['max_review_rounds']}: {summary(out)}")
        else:
            note = "[approve]" if verdict == "APPROVE" else f"[changes after {rounds - 1} round(s), needs you]"
            im.set_stage(ticket["id"], "human_check", "Review",
                         f"{note} {summary(out)} — check branch `{run['branch']}` in {run['worktree']}")

    def cleanup_done(self):
        """Remove the worktree of a done ticket (its branch stays for merging)."""
        for key, run in list(self.state.data["runs"].items()):
            board, title = key.split("::", 1)
            t = self.find(board, title) if run.get("worktree") else None
            if t and t["status"] == "done" and os.path.isdir(run["worktree"]):
                cfg = im.get_board_config(board)
                res = subprocess.run(["git", "-C", cfg["workspace"], "worktree", "remove", run["worktree"]],
                                     capture_output=True, text=True)
                if res.returncode == 0:
                    self.state.update_run(key, worktree="")


# ------------------------------------------------------------------- loop --- #

def watch_once(state, notify=None):
    notify = notify or slack_notify.post
    snap = snapshot(im.list_all_ideas())
    old = state.data.get("snapshot")
    sent = []
    if old is not None:
        channels = {}
        for board, text in events_between(old, snap):
            if board not in channels:
                cfg = im.get_board_config(board) or {}
                channels[board] = slack_notify.channel_for(board, cfg.get("slack_channel", ""))
            res = notify(channels[board], f"{text}\n<{COCKPIT_URL}|open the board>")
            if not res.get("ok"):
                log.warning("slack post to %s failed: %s", channels[board], res.get("error"))
            sent.append((channels[board], text))
    state.data["snapshot"] = snap
    state.save()
    return sent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # The worker has no desktop session; syncing Obsidian is the cockpit's job.
    im.trigger_obsidian_sync = lambda reason="": None

    state = State(os.path.join(STATE_DIR, "state.json"))
    runner = Runner(state)
    log.info("vault %s; pipeline boards: %s", im.get_ideas_dir(),
             [b["file"] for b in runner.pipeline_boards()] or "none")
    while True:
        try:
            for ch, text in watch_once(state):
                log.info("notified %s: %s", ch, text)
            runner.tick(wait=args.once)
            runner.cleanup_done()
            if args.once:
                watch_once(state)
                return 0
        except Exception:
            log.exception("worker pass failed")
            if args.once:
                return 1
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
