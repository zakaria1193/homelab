# Antigravity Remote Control (`agy --remote-control`)

An always-on Antigravity daemon that publishes this box to the
[Antigravity Remote Control dashboard](https://antigravity.google.com), so agent
tasks can be driven from a browser on any other machine.

It is the Antigravity counterpart to [`../claudeRcAI`](../claudeRcAI), with one
structural difference worth knowing before you reach for `INSTANCE=`:

| | `claude remote-control` | `agy --remote-control` |
|---|---|---|
| Scope | one **directory** per process | one **machine** per daemon |
| Adding a workspace | new `.env.<name>`, new unit | nothing — pick the project in the web UI |
| Instances here | `claude-rc-ai`, `claude-rc-ai-paperclip` | just `agy-remote-control` |

That is why there is no `INSTANCE=` knob in this Makefile, and why the
per-workspace chips on the cockpit reach Antigravity through an `alt_link`
button rather than through a session of their own.

## Setup

```sh
make install     # must be run from a real terminal - see below
```

`make install` fetches the official `agy-daemon.sh` from
`https://antigravity.google/cli/agy-daemon.sh` and runs it. Upstream ships that
script alongside the CLI and it already writes the systemd user unit, a
port-probing launcher wrapper (hub port 4400-4499) and an auto-update timer, so
this Makefile drives it instead of reimplementing it and drifting.

**The install needs a TTY.** The daemon runs headless, but it cannot obtain its
own credentials: sign-in prints a URL and waits for you to paste a code back.
`make install` refuses to run without a terminal rather than leaving a
crash-looping unauthenticated unit behind. The token is written once to agy's
own store and reused across reboots.

## Targets

| Target | Effect |
|---|---|
| `make install` | Fetch the installer and run it (one-time interactive sign-in) |
| `make start` | Start the daemon |
| `make restart` | Restart it |
| `make stop` | Stop it **and remove** the unit, wrapper and update timer |
| `make status` | `systemctl --user status` plus the auto-update timer |
| `make logs` | Follow the journal |
| `make upgrade` | `agy update`, then restart the daemon |
| `make login` | Re-run sign-in after a token expiry or account switch |
| `make doctor` | Report binary, unit, instance name and hub port |

## Configuration

`.env` (seeded from `.env.example`, not committed — it holds no secrets):

| Key | Default | Meaning |
|---|---|---|
| `AGY_RC_NAME` | `homelab` | Name shown in the dashboard's machine list |
| `AGY_UPDATE_INTERVAL` | `daily` | systemd `OnCalendar` value for the update timer |
| `AGY_AUTO_UPDATE` | `1` | `0` installs with `--no-auto-update` |

The name the daemon last persisted is read back from
`~/.gemini/config/config.json` (`userSettings.cliRemoteControlHostname`), which
is what `make doctor` reports.

## Notes

- **Unit:** `agy-remote-control.service` (systemd **user** scope), plus
  `agy-remote-control-update.timer`. All are created by the vendor script, so
  there is no `.service.template` in this directory.
- **No Cloudflare route.** Google brokers the connection, the same way the
  Claude sessions are reached through `claude.ai` rather than through
  `cloudflared`. Nothing here listens on the LAN except the loopback hub port.
- Registered on the cockpit as `[antigravity-rc]` in
  `services/status/services.conf`.
