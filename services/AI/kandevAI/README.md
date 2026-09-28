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
| Build | `~/my_repos/kandev` → bundle in `~/.local/share/kandev-fork` |
| Toolchain | Go 1.26.0 in `~/.local/go-1.26.0`, pnpm 9.15.9 via corepack, Node ≥ 24 |

## Make targets

```bash
make install   # toolchain + clone the fork + build the runtime bundle (~5 min)
make start     # render kandev.service, install and start it
make status | logs | restart | stop
make upgrade   # fast-forward the fork's main, rebuild, restart
```

Updating the fork itself (rebasing on upstream, adding a patch) happens in
`~/my_repos/kandev` following its `FORK.md`; then `make upgrade` here.

## Configuration (`.env`, git-crypt encrypted)

See `.env.example`. Notable keys:

- `KANDEV_FEATURES_AUTH=true` - Kandev has no login otherwise; anyone who can
  reach the port could make agents run commands on this host.
- `KANDEV_ADMIN_EMAIL` / `KANDEV_ADMIN_PASSWORD` - the admin account created at
  first setup.
- `KANDEV_FORK_UNLISTED_MODELS=true` - fork feature: profiles may use models
  the CLI accepts but Kandev's catalog does not list yet (`claude-opus-5-5`).

## Agent profiles in use

| Profile | Agent | Model | Mode |
|---|---|---|---|
| Strong - Opus 5.5 | Claude Code | `claude-opus-5-5` | auto |
| Mid - Sonnet 5 | Claude Code | `sonnet` | auto |

`auto` lets Claude's classifier approve tool calls, so unattended steps do
not stop on permission prompts.
