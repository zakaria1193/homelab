"""Executors: the engines a pipeline board runs its model stages with.

A board picks one in its settings (frontmatter `executor:`); the dropdown on
the page lists EXECUTORS. Each executor runs one stage headlessly and returns
its text output. Add an engine by subclassing Executor and registering it.
"""

import os
import shutil
import subprocess

# What each stage may do. Planning and review only read; execution edits files
# inside its own git worktree.
READ_ONLY = "read_only"
EDIT = "edit"
READ_ONLY_TOOLS = ("Read", "Glob", "Grep", "Bash(git log:*)", "Bash(git diff:*)",
                   "Bash(git show:*)", "Bash(git status:*)", "Bash(ls:*)")


class ExecutorError(Exception):
    pass


class Executor:
    name = ""
    label = ""

    def available(self):
        """(ok, detail) - whether this engine can run on this host."""
        raise NotImplementedError

    def run(self, prompt, cwd, model, effort, access, timeout, permission_mode="auto", log_path=None):
        """Run one stage; return its output text or raise ExecutorError."""
        raise NotImplementedError


class ClaudeExecutor(Executor):
    """`claude -p` (Claude Code, headless). Reuses the login in ~/.claude."""

    name = "claude"
    label = "Claude Code (claude -p)"

    def binary(self):
        return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")

    def available(self):
        path = self.binary()
        if not os.path.isfile(path):
            return False, "claude CLI not found (curl -fsSL https://claude.ai/install.sh | bash)"
        return True, path

    def command(self, model, effort, access, permission_mode="auto"):
        cmd = [self.binary(), "-p", "--model", model, "--effort", effort, "--output-format", "text"]
        if access == READ_ONLY:
            # Planning and review can read the repo and its history, never write:
            # anything outside this allow-list is refused without asking.
            return cmd + ["--permission-mode", "dontAsk", "--allowedTools", *READ_ONLY_TOOLS]
        return cmd + ["--permission-mode", permission_mode]

    def run(self, prompt, cwd, model, effort, access, timeout, permission_mode="auto", log_path=None):
        ok, detail = self.available()
        if not ok:
            raise ExecutorError(detail)
        cmd = self.command(model, effort, access, permission_mode)
        try:
            res = subprocess.run(cmd, input=prompt, cwd=cwd, capture_output=True, text=True,
                                 timeout=timeout, env=dict(os.environ))
        except subprocess.TimeoutExpired:
            raise ExecutorError(f"timed out after {timeout // 60} min")
        except OSError as e:
            raise ExecutorError(str(e))
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"$ {' '.join(cmd[:1] + cmd[2:])}  (cwd {cwd}, exit {res.returncode})\n")
                if res.stderr.strip():
                    f.write(res.stderr[-4000:] + "\n")
        if res.returncode != 0:
            raise ExecutorError(f"exit {res.returncode}: {(res.stderr or res.stdout).strip()[-600:]}")
        return res.stdout.strip()


EXECUTORS = {e.name: e for e in (ClaudeExecutor(),)}


def list_executors():
    """For the settings dropdown: every registered engine and whether it works here."""
    out = []
    for e in EXECUTORS.values():
        ok, detail = e.available()
        out.append({"name": e.name, "label": e.label, "available": ok, "detail": detail})
    return out
