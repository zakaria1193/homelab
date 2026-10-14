# Cloudflare Service & Credentials

This directory manages credentials, configuration, and tooling for Cloudflare integration (DNS Zone records and Cloudflare Workers).

> [!NOTE]
> **No Local Services Running Currently**:
> There is no local stuff / daemon running on this host right now.
> - Cloudflare ingress tunnels (`cloudflared`) run on the dedicated network gateway (Raspberry Pi 4).
> - Cloudflare Workers run serverless on Cloudflare's global edge network.
> - This directory currently acts as the central credential and automation store for Cloudflare API management.

---

## Credentials & Tokens

Environment secrets are tracked and encrypted via `git-crypt` in `.env`:

| Variable | Scope & Description |
|---|---|
| `CLOUDFLARE_ZONE_DNS_ZAKARIAFADLICOM_FROM_HOME_IP_ONLY` | Zone DNS edit token for `zakariafadli.com` (restricted to home IP). |
| `CLOUDFLARE_WORKERS_API_TOKEN_FROM_HOME_IP_ONLY` | Workers edit & deploy token (restricted to home IP). |

---

## Makefile Targets

| Target | Description |
|---|---|
| `make help` | Displays available targets |
| `make install` | Verifies environment files |
| `make status` | Displays configuration & daemon status |
| `make env-setup` | Creates `.env` from `.env.example` if missing |
| `make clean` | Cleans up local state |
