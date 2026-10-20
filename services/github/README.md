# GitHub Service & Credentials

This directory manages credentials, configuration, and verification tooling for GitHub integrations (CLI tools, AI agent workflows, and systemd units).

---

## Credentials & Tokens

Environment secrets are tracked and encrypted via `git-crypt` in `.env`:

| Variable | Scope & Description | Managed Location |
|---|---|---|
| `GH_TOKEN` | GitHub Personal Access Token (fine-grained or classic) used by CLI tools (`gh`), AI agent runs (`pjm`, `claude`, `agy`), and git over HTTPS/API | Tracked in `services/github/.env` |

---

## Systemd Drop-in Integration

System-level services (`tmux-server.service`, `pjm.service`, `claude-rc-ai-pjm.service`) load environment secrets directly from this directory via drop-in configuration:

```ini
[Service]
EnvironmentFile=-/home/zfadli/my_repos/homelab/services/github/.env
```

---

## Testing API Tokens

`make test-tokens` runs the shared checker (`services/status/test_tokens.py --env .env --strict`), which checks the `github` `TOKEN_DEFS` entry in `services/status/cockpit/tokens.py` against `https://api.github.com/user` — the same entry the cockpit's Tokens tab uses. `--strict` exits non-zero if GitHub rejects the token.

```bash
make test-tokens
```

---

## Makefile Targets

| Target | Description |
|---|---|
| `make help` | Displays available targets |
| `make test-tokens` | Runs `services/status/test_tokens.py --env .env --strict`, checking `GH_TOKEN` against `https://api.github.com/user` |
| `make status` | Displays configuration status |
| `make install` | Verifies local configuration |
| `make env-setup` | Creates `.env` from `.env.example` if missing |
| `make clean` | Cleans local state |
