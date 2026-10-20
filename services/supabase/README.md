# Supabase Service & Credentials

This directory manages credentials, configuration, and verification tooling for Supabase integrations (Management API, database management, and systemd units).

---

## Credentials & Tokens

Environment secrets are tracked and encrypted via `git-crypt` in `.env`:

| Variable | Scope & Description | Managed Location |
|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | Supabase Personal Access Token (Management API) used to list, inspect, and manage Supabase projects | Tracked in `services/supabase/.env` |

---

## Systemd Drop-in Integration

System-level services (`tmux-server.service`, `pjm.service`, `claude-rc-ai-pjm.service`) load environment secrets directly from this directory via drop-in configuration:

```ini
[Service]
EnvironmentFile=-/home/zfadli/my_repos/homelab/services/supabase/.env
```

---

## Testing API Tokens

`make test-tokens` runs the shared checker (`services/status/test_tokens.py --env .env --strict`), which checks the `supabase_mgmt` `TOKEN_DEFS` entry in `services/status/cockpit/tokens.py` against `https://api.supabase.com/v1/projects` — the same entry the cockpit's Tokens tab uses. (`services/supabase-keepalive/.env` has its own `supabase` entry for the same variable.) `--strict` exits non-zero if the token is rejected.

```bash
make test-tokens
```

---

## Makefile Targets

| Target | Description |
|---|---|
| `make help` | Displays available targets |
| `make test-tokens` | Runs `services/status/test_tokens.py --env .env --strict`, checking `SUPABASE_ACCESS_TOKEN` against `https://api.supabase.com/v1/projects` |
| `make status` | Displays configuration status |
| `make install` | Verifies local configuration |
| `make env-setup` | Creates `.env` from `.env.example` if missing |
| `make clean` | Cleans local state |
