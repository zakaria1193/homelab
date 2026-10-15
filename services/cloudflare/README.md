# Cloudflare Service & Credentials

This directory manages credentials, configuration, and verification tooling for Cloudflare integrations (DNS Zone records, Cloudflare Workers, and API token generation).

> [!NOTE]
> **No Local Service Daemons**:
> There are no local services or background daemons running on this host for Cloudflare.
> - **Tunnels**: Cloudflare Ingress tunnels (`cloudflared`) are managed exclusively via **Home Assistant apps / add-ons** on the network gateway (Raspberry Pi 4) — no local tunnel daemon code lives in this repository.
> - **Workers**: Cloudflare Workers execute serverless on Cloudflare's global edge network.
> - This directory acts as the central credential and verification store for Cloudflare API management.

---

## Credentials & Tokens

Environment secrets are tracked and encrypted via `git-crypt` in `.env`:

| Variable | Scope & Description | Agent / CI Policy |
|---|---|---|
| `CLOUDFLARE_ZONE_DNS_ZAKARIAFADLICOM_FROM_HOME_IP_ONLY` | Zone DNS edit token for `zakariafadli.com` | Restricted to home IP. |
| `CLOUDFLARE_WORKERS_API_TOKEN_FROM_HOME_IP_ONLY` | Workers edit & deploy token | Restricted to home IP. |
| `CLOUDFLARE_CREATE_ADDITIONAL_TOKENS_2026_FROM_HOME_IP_ONLY` | Token creation & management token (User > API Tokens: Edit / Create) | **Restricted to home IP. Expires after 2026.** MUST be used by **Opus-level or higher autonomous agents ONLY** to generate limited-scope tokens for specific GitHub CI/CD workflows (which cannot use the home-IP-restricted tokens). |
| `CLOUDFLARE_PAGES_DEPLOY_SALSA_SOCIAL_CI` | Pages: Edit on the account, minted from the create-tokens token (id `e9fcb5ce074cc844237d9074a25a9509`) | No IP limit. Used only by salsa-social GitHub Actions as repo secret `CLOUDFLARE_API_TOKEN`. Expires 2027-10-15. |

---

## Testing API Tokens

You can verify all configured tokens using `make test-tokens`:

```bash
make test-tokens
```

Or manually test any token with `curl` against Cloudflare's universal verification endpoint:

```bash
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer <TOKEN>"
```

Active tokens return `{"success": true, "result": {"status": "active"}, "messages": [{"message": "This API Token is valid and active"}]}`.

---

## Makefile Targets

| Target | Description |
|---|---|
| `make help` | Displays available targets |
| `make test-tokens` | Verifies all tokens against `https://api.cloudflare.com/client/v4/user/tokens/verify` |
| `make status` | Displays configuration & daemon status |
| `make install` | Verifies environment files |
| `make env-setup` | Creates `.env` from `.env.example` if missing |
| `make clean` | Cleans up local state |
