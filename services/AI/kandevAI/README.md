# Kandev (our fork)

Spec-driven kanban that runs CLI coding agents (Claude Code, Codex, Gemini
CLI...) with their own logins: per-step agent profiles and models, git
worktrees, WIP limits, human gates, subtasks, and an MCP server.

We run **our fork**, [zakaria1193/kandev](https://github.com/zakaria1193/kandev),
built from source. Its `FORK.md` lists every change and the rules that keep it
rebase-able on upstream [kdlbs/kandev](https://github.com/kdlbs/kandev).

| | |
|---|---|
| Unit | `kandev` (system scope) |
| Web UI + API | `http://<host>:3040` (login required, `KANDEV_FEATURES_AUTH=true`) |
| MCP | `http://<host>:3040/mcp` (same login) |
| Data | `~/.kandev` (SQLite, worktrees, sessions, logs) |
| Build | `~/my_repos/kandev/kandev` → bundle in `~/.local/share/kandev-fork` |
| Toolchain | Go 1.26.0 in `~/.local/go-1.26.0`, pnpm 9.15.9 via corepack, Node ≥ 24 |

## Make targets

```bash
make install   # toolchain + clone the fork + build the runtime bundle (~5 min)
make start     # render kandev.service, install and start it
make status | logs | restart | stop
make upgrade   # fast-forward the fork's main, rebuild, restart
```

Updating the fork itself (rebasing on upstream, adding a patch) happens in
`~/my_repos/kandev/kandev` following its `FORK.md`; then `make upgrade` here.

## MCP for Claude Code and agy

`kandev_mcp.py` makes sure the MCP really works, then connects a CLI to it:

1. Starts the `kandev` unit if it is not running, then waits for `/health`.
2. Opens an MCP session on `/mcp` with `KANDEV_MCP_TOKEN` and lists the tools.
   If the token is missing or refused, it logs in with the admin account from
   `.env`, creates a new API token, and saves it to `.env`.
3. Registers the server as `kandev` in Claude Code (user scope, so every
   session on this box gets it, Remote Control ones too) and in agy.

```bash
make mcp                          # steps 1-3 for both CLIs
./kandev_mcp.py check             # steps 1-2 only
./kandev_mcp.py claude [args]     # steps 1-3, then start claude
make test                         # tests against a fake Kandev
```

On the cockpit, the `kandev-board` row under AI Sessions runs the last form
from its claude and agy buttons (`claude_command` / `agy_command` in
`services.conf`).

## Configuration (`.env`, git-crypt encrypted)

See `.env.example`. Notable keys:

- `KANDEV_FEATURES_AUTH=true` - Kandev has no login otherwise; anyone who can
  reach the port could make agents run commands on this host.
- `KANDEV_ADMIN_EMAIL` / `KANDEV_ADMIN_PASSWORD` - the admin account created at
  first setup.
- `KANDEV_MCP_TOKEN` - API token for the MCP; `kandev_mcp.py` creates it when empty.
- `KANDEV_FORK_UNLISTED_MODELS=true` - fork feature: profiles may use models
  the CLI accepts but Kandev's catalog does not list yet (`claude-opus-5-5`).

## Slack notifications

The fork's `type: slack` notification provider (`fork/slack-notify`) posts a
message whenever a task enters a step, completes, or an agent asks a
clarifying question. Every step where a card waits for the owner (Spec
feedback, Human check, Ideas' Review…) is covered, so the board does not need
polling.

- **Token**: `SLACK_BOT_TOKEN` in `.env` (git-crypt), an `xoxb-` bot token with
  `chat:write` + `chat:write.public`. The backend reads it from its own
  process env (`os.Getenv`), loaded via the unit's `EnvironmentFile=`, so a
  token change needs `make restart`, not just `make notifications`.
- **Provider body**: `notifications/slack.json`, no token in it. Fields:
  `default_channel`, `channels` (workspace name or id -> channel), `step_names`
  (case-insensitive filter, `task.step_entered` only), `base_url` (used to
  build the `Open in Kandev` link).
- **Apply it**: `make notifications` GETs `/api/v1/notification-providers`,
  matches by name (`Slack`), and PATCHes if found or POSTs if not -
  idempotent, so re-running it never creates a second provider (two providers
  would mean two posts for the same event). `make notifications-check` GETs
  every live workspace/workflow/step and fails, listing the step, if one
  where a card waits for the user is missing from `step_names`.
- **The "every waiting step" rule**: any step with no `auto_start_agent`, not
  at position 0 (the inbox), and without `complete_task_on_enter` must be in
  `step_names`, or that workflow stops posting silently when it reaches that
  step. Today that is `Spec feedback` and `Human check` (kandev, Default
  Workspace) and `Review` (Ideas). Adding a workflow or a new waiting step
  means adding its name to `slack.json` - `make notifications-check` (and
  `tests/test_notifications.py`) catch a missed one.
  `Done` is intentionally left out: it both completes the task and enters a
  step, so `task.completed` alone announces it and avoids a double post.
- **Test it**: `POST /api/v1/notification-providers/<id>/test` after
  `make notifications`, then move a real task across a step in `step_names`
  and check `make logs` for `slack notification posted` (and no
  `notification delivery failed`).

```bash
make notifications        # upsert the provider from notifications/slack.json
make notifications-check  # drift check: every waiting step covered?
make test                 # offline unit tests, no Kandev or Slack needed
```

## Agent profiles in use

| Profile | Agent | Model | Effort | Mode |
|---|---|---|---|---|
| Strong - Opus 5.5 | Claude Code | `claude-opus-5-5` | high | auto |
| Mid - Sonnet 5 | Claude Code | `claude-sonnet-5` | default | auto |

`auto` lets Claude's classifier approve tool calls, so unattended steps do
not stop on permission prompts.

## Project workflow

The `kandev` workspace (Kanban) and the Default Workspace (Development) use
the same spec-driven board. The steps are set in the Kandev UI, not in this
repo.

| Step | Agent | What happens |
|---|---|---|
| Raw | none | New tickets land here. |
| Spec | Strong, WIP 1 | Writes the spec, planning only. Pulls the next Raw ticket when free. Goes to Plan, or to Spec feedback with an "Open questions" section. |
| Spec feedback | none | Waits for the owner. A reply on the card sends it back to Spec. |
| Plan | Strong | Splits the spec into small subtasks. |
| Execute | Mid | Does one subtask, then hands off to AI review. |
| AI review | Strong | Checks the change. Back to Execute while subtasks remain or fixes are needed. |
| Human check | none | Waits for the owner's approval. |
| Done | none | Complete. |

Each agent step starts a fresh session and ends it with the step, so no
session sits idle and loses the prompt cache.

Limits to know:

- Each step has one default exit. The other path (Spec -> Spec feedback,
  AI review -> Execute) depends on the agent following its prompt.
- Spec questions do not use Kandev's "ask" tool, which would keep a session
  open while it waits. Only the prompt enforces this.
- The WIP limit is per step, not per board. Once a ticket leaves Spec, the
  next Raw ticket can enter Spec.
