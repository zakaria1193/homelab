# GitHub Service & Credentials

This directory manages credentials, configuration, and verification tooling for GitHub integrations (CLI tools, AI agent workflows, and systemd units).

---

## Credentials & Tokens

Environment secrets are tracked and encrypted via `git-crypt` in `.env`:

| Variable | Scope & Description | Managed Location |
|---|---|---|
| `GH_TOKEN` | GitHub Personal Access Token (fine-grained or classic) used by CLI tools (`gh`), AI agent runs (`pjm`, `claude`, `agy`), and git over HTTPS/API | Tracked in `services/github/.env`, symlinked to `/etc/pjm-github.env` for systemd drop-ins |

---

## Systemd Drop-in Integration

System-level services (`tmux-server.service`, `pjm.service`, `claude-rc-ai-pjm.service`) load environment secrets from `/etc/pjm-github.env`.

Running `make install` or `make start` symlinks:
```bash
/etc/pjm-github.env -> /home/zfadli/my_repos/homelab/services/github/.env
```

---

## Testing API Tokens

Verify the configured GitHub token using `make test-tokens`:

```bash
make test-tokens
```

---

## Makefile Targets

| Target | Description |
|---|---|
| `make help` | Displays available targets |
| `make test-tokens` | Verifies `GH_TOKEN` against `https://api.github.com/user` |
| `make status` | Displays configuration & symlink status |
| `make install` | Symlinks `.env` to `/etc/pjm-github.env` |
| `make env-setup` | Creates `.env` from `.env.example` if missing |
| `make stop` | Removes the system symlink `/etc/pjm-github.env` |
| `make clean` | Alias for `make stop` |
