# aicli (homelab side)

aicli has its own repo, `~/my_repos/aicli`
([github.com/zakaria1193/aicli](https://github.com/zakaria1193/aicli)). Read its
README for what the command and the `aicli-ai` service do. This folder is the
homelab side, the same split as `pjmAI`:

- `aicli.service.template` - the systemd unit for the `aicli-ai` HTTP service
  (port 8500). It runs `$(AICLI_DIR)/server.py` with `AICLI_CONFIG` set to
  this folder's `aicli.toml`.
- `.env` / `.env.example` - the service's bind settings (`AICLI_HOST`,
  `AICLI_PORT`, `AICLI_MAX_CONCURRENT`, `AICLI_TIMEOUT`, `AICLI_USAGE_LOG`,
  `AICLI_API_KEY`). `.env` is committed via git-crypt like every other
  service's.
- `aicli.toml` - homelab's aicli config: binary paths, model tiers, the
  workload classes.
- `routes.json` - the live switchboard the cockpit's AI Routes tab
  (`/ai-routes`) and `aicli route` edit.

`make install` links `~/.config/aicli/aicli.toml` and
`~/.config/aicli/routes.json` to the two files here, so every `aicli` on this
host (pjm, social-helper, ai-job-search, the cockpit, the tmux wrapper,
auto-heal) uses homelab's config. Callers inside this repo find the code at
`$AICLI_DIR` (default: an `aicli` checkout next to this repo) and pass
`AICLI_CONFIG` themselves, so they don't depend on the links.

## Quick start

```
make install      # clones aicli to ~/my_repos/aicli if missing, links
                  # ~/.local/bin/aicli and ~/.config/aicli/{aicli.toml,routes.json}
make test         # aicli's own unit tests (fake CLI, no real quota)
make start        # renders the unit and starts aicli-ai (port 8500)
make status       # make logs / make stop / make restart
make upgrade      # git pull homelab and aicli, re-render the unit, restart
make test-tokens  # AICLI_API_KEY against the running service, and that it
                  # equals karakeep's OPENAI_API_KEY (CLAUDE.md §5)
```

`AICLI_DIR` and `AICLI_REPO` override where aicli is checked out and cloned
from. `make restart` also re-renders the unit, so a moved `AICLI_DIR` takes
effect on the next restart.
