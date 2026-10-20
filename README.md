# Personal Homelab

This repository is my homelab as code. Every service is a directory with a
`Makefile`, a `.env.example`, a systemd unit template and a README, and every
running thing is listed on one page: the **cockpit** (`services/status`).

- [CLAUDE.md](CLAUDE.md) is the operating manual: topology, bootstrap order,
  the service inventory and day-2 operations.
- [AGENTS.md](AGENTS.md) holds the standards every service is written to.

## What runs here

- **Cockpit** (`services/status`): one page with every service, quick links,
  terminals and Slack health alerts.
- **AI services** (`services/AI`): pjm, aicli, Hermes, OpenHands, the AI job
  search, arr-mcp, Playwright MCP, and Claude/Antigravity Remote Control.
  Native systemd units; `make -C services/AI summary` shows them all.
- **Media** (`services/media`, Docker Compose): Jellyfin, Sonarr, Radarr,
  Chaptarr, Prowlarr, Transmission. `services/media-autopilot` keeps the
  disk at what is being watched plus the next two episodes.
- **Karakeep** (`services/karakeep`, Docker Compose): bookmarks.
- **Home Assistant** and the **Cloudflare Tunnel** run on a Raspberry Pi 4.

Secrets are committed encrypted with `git-crypt`; run `git-crypt unlock`
after cloning.
