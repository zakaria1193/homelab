# Supabase Service & Credentials

This directory manages credentials, configuration, and verification tooling for Supabase integrations (Management API, database management, and systemd units).

---

## Credentials & Tokens

Environment secrets are tracked and encrypted via `git-crypt` in `.env`:

| Variable | Scope & Description | Managed Location |
|---|---|---|
| `SUPABASE_ACCESS_TOKEN` | Supabase Personal Access Token (Management API) used to list, inspect, and manage Supabase projects | Tracked in `services/supabase/.env`, symlinked to `/etc/supabase.env` for systemd drop-ins |

---

## Systemd Drop-in Integration

System-level services (`tmux-server.service`, `pjm.service`, `claude-rc-ai-pjm.service`) load environment secrets from `/etc/supabase.env`.

Running `make install` or `make start` symlinks:
```bash
/etc/supabase.env -> /home/zfadli/my_repos/homelab/services/supabase/.env
```

---

## Testing API Tokens

Verify the configured Supabase token using `make test-tokens`:

```bash
make test-tokens
```

---

## Makefile Targets

| Target | Description |
|---|---|
| `make help` | Displays available targets |
| `make test-tokens` | Verifies `SUPABASE_ACCESS_TOKEN` against `https://api.supabase.com/v1/projects` |
| `make status` | Displays configuration & symlink status |
| `make install` | Symlinks `.env` to `/etc/supabase.env` |
| `make env-setup` | Creates `.env` from `.env.example` if missing |
| `make stop` | Removes the system symlink `/etc/supabase.env` |
| `make clean` | Alias for `make stop` |
