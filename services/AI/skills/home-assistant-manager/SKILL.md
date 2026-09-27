---
name: home-assistant-manager
description: Manage Home Assistant configuration safely and fast — edit and deploy YAML (automations, blueprints, scripts, scenes, templates, MQTT), enforce clean remote git repository status upon connection (everything committed or gitignored so pushes never break), validate with ha core check, deploy via git or rapid scp, reload-vs-restart correctly, verify changes from logs, traces and entity state, and build Lovelace dashboards. Use for any Home Assistant config, automation, template, or dashboard work over SSH/hass-cli/MCP.
---

# Home Assistant Manager

Operate a remote Home Assistant instance precisely: make a change, get it live, prove it
worked. Optimize for the fewest safe round-trips.

## Assumptions
- The repo you're editing **is** the HA `/config` (or `/homeassistant`) dir, git-connected to the instance.
- The remote instance uses `receive.denyCurrentBranch updateInstead` with a push-to-checkout hook (e.g. `rpi: zfadli@192.168.1.11:/homeassistant`), meaning `git push rpi main` updates live files immediately.
- `root@homeassistant.local` in generic examples is a placeholder; in this workspace use `rpi` (`192.168.1.11`).
- Access via one or more of: `hass-cli` (REST), SSH `ha`, or an MCP server (see below).
- Only edit `.yaml`/`.yml`/`.md`. Never read/write `.env` or `secrets.yaml`; use `!secret`.

## Repository Hygiene — Clean Upon Connection & Zero-Tolerance for Dirty Remote
**CRITICAL RULE: Everything in the repository must be either committed or gitignored.**
Because the remote uses `receive.denyCurrentBranch updateInstead`, **ANY uncommitted change or untracked non-ignored file on the remote will block or break `git push rpi main`**.

### Pre-flight Clean Check (Run immediately upon connection / session start)
Before editing or deploying, ALWAYS inspect and ensure remote working tree cleanliness:
```bash
~/.gemini/config/skills/home-assistant-manager/scripts/ensure-clean.sh
# or manually via SSH:
ssh rpi "cd /homeassistant && git status --porcelain"
```

### Clean-Up Protocol if Remote is Dirty:
1. **Runtime / cache / noise**:
   - If files are ephemeral (logs, caches, databases, media, core dumps), ensure pattern is in `.gitignore` on both remote and local.
2. **HACS updates (`custom_components/`, `www/community/`) or blueprints (`blueprints/`)**:
   - If HACS or the UI updated components or downloaded blueprints:
     ```bash
     # 1. Fix ownership if root-owned files or FETCH_HEAD blocked git
     ssh rpi "sudo -n chown -R \$(id -un):\$(id -gn) /homeassistant/.git 2>/dev/null || true"
     # 2. Stage and commit on remote
     ssh rpi "cd /homeassistant && git add -A && git commit -m 'chore(remote): capture remote changes (HACS/components/blueprints)'"
     # 3. Pull into local repo and sync to GitHub
     git -C /home/zfadli/my_repos/home-assistant-config pull rpi main
     git -C /home/zfadli/my_repos/home-assistant-config push origin main
     # 4. Sync remote origin tracking ref
     ssh rpi "cd /homeassistant && git update-ref refs/remotes/origin/main \$(git rev-parse HEAD)"
     ```
3. **Verify clean state**:
   - Confirm `ssh rpi "cd /homeassistant && git status"` reports:
     `nothing to commit, working tree clean`
   - **NEVER attempt `git push rpi main` while the remote working tree is dirty.**

## Remote access — pick the right tool
- **SSH `ha`** — always works, needs no local env. Use for `ha core check|restart|logs|info`.
- **`hass-cli`** (REST) — state/service calls, but needs `HASS_SERVER`/`HASS_TOKEN` in the
  shell *before* the session starts. If they're unset, hass-cli falls back to the wrong
  host (localhost) and errors — don't retry, check `[ -n "$HASS_TOKEN" ]` once, then use
  SSH or MCP instead.
- **MCP** (preferred when available) — first-class tools for live state/control, no env
  juggling. Official `mcp_server` integration (HA core ≥2025.2) or community `ha-mcp`
  (richer, 80+ tools). Use it instead of shelling out when present.

## The deploy pipeline (the one canonical flow)
0. **Pre-flight:** Verify remote is clean (`ensure-clean.sh`). If dirty, clean up first.
1. **Edit YAML locally.**
2. **Validate:** `ssh rpi "ha core check"` (slow, ~30-60s — see "when to skip" below).
3. **Commit & Push-to-Deploy:**
   - `git add <files> && git commit -m "feat/fix(domain): description"`
   - `git push rpi main` (live files updated immediately via push-to-checkout hook)
   - `git push origin main` (remote GitHub backup & tracking)
4. **Apply:** **reload** if possible, else **restart** (table below).
5. **Verify:** Check logs and entity states (next section), and verify remote repo remains clean.

**Rapid iteration:** skip git and `scp` straight to the instance, then reload — good for
dashboards and tight test loops. Commit to git only once stable.
`scp automations.yaml rpi:/homeassistant/` → reload.

**When to skip `ha core check`:** it parses the whole config and is slow. For an isolated
YAML edit you're confident in, a domain reload surfaces errors faster and the logs tell
you immediately. Always run it before a *restart* or for `configuration.yaml` changes.

## Reload vs restart
| Change | Action |
|--------|--------|
| automations, scripts, scenes, groups, template entities, themes | **reload** the domain (`hass-cli service call automation.reload`, etc.) |
| `configuration.yaml` core, new integrations, platform sensors (min/max), MQTT sensor/binary_sensor platforms, dashboard registry (`lovelace_dashboards`) | **restart** (`ssh … "ha core restart"`, ~30s) |

Prefer reload. Never restart without a passing `ha core check`. Before risky changes
(core `configuration.yaml` surgery, removing an integration), snapshot first — it's cheap:
`ssh root@homeassistant.local "ha backups new --name pre-<change>"`.

## Verify — don't assume it worked
1. Reload/restart the right domain.
2. For automations, **trigger manually** for instant feedback:
   `hass-cli service call automation.trigger --arguments entity_id=automation.<id>`
   (or call the service via MCP). This **bypasses `conditions` by default** — it proves the
   actions, not the gate. To test conditions too, pass `skip_condition: false` or exercise
   the real trigger, then read the automation's trace in the UI.
3. Read the logs filtered to your change:
   `ssh root@homeassistant.local "ha core logs | grep -iE '<name>|error' | tail -20"`.
   Good: `Running automation actions`, `Executing step …`. Bad: `Invalid data for
   call_service`, `TypeError`, `Template variable warning`, `Error executing script`.
4. Confirm the real outcome: device/sensor state (`hass-cli state get <entity>`), or ask
   the user for notification-type actions.
5. On error: fix → re-pull/scp → reload → re-check. Loop until clean.

## Automations — write modern syntax
HA 2024.10 renamed the keys; legacy syntax still works but don't emit it in new code:
top-level `triggers:/conditions:/actions:` (plural), `trigger:` not `platform:` inside a
trigger, `action:` not `service:` for calls. Every automation gets a stable `id:` (traces
and UI editing need it) plus an `alias`.

**Full automation reference** (syntax table, `mode:` behavior, blueprints, trace debugging,
pitfalls) → read [`reference/automations.md`](reference/automations.md) when writing or
debugging automations.

## Templates — the precision rules
- Always coerce types before comparing: `states('sensor.x') | int(0) < 7`. Bare states are
  strings; `'5' < 7` raises `TypeError`. Provide a default (`int(0)`) so startup `None`
  doesn't error.
- Test in **Developer Tools → Template** before committing.
- `state_attr(...)` returns `None` if the entity/attr is missing — guard it.

## Conventions
- Surgical edits; preserve comments; 2-space indent.
- Validate before restart; prefer reload; verify from logs.
- Use context7 MCP for current HA docs before non-trivial or unfamiliar config.

## Dashboards
### Mandatory load path — a dashboard change is NOT done until it is live AND seen
Editing a repo file like `dashboards/*.yaml` and running `git push` does **not** change what
the user sees if the dashboard is in **storage mode**. HA renders storage dashboards from
`.storage/lovelace.<id>` and never reads the repo YAML. The YAML in the repo is only a
mirror. Past failure: the edit was committed and pushed, reported as done, and the graph
never appeared.

Every dashboard change follows these steps in order:
1. **Find the mode:** `ssh rpi "cat /homeassistant/.storage/lovelace_dashboards"` shows
   `mode` and `url_path` for each dashboard. `mode: yaml` (or a `lovelace:` block in
   `configuration.yaml`) means the YAML file is live. `storage` means it is not.
2. **Pull the live config first:** `scripts/ha-dashboard.sh get <url_path> live.json`.
   Diff it against the repo copy. Any difference is a manual UI edit made by the user.
   Build on the live config and never overwrite those edits with a stale repo copy. Then
   bring the repo mirror up to date.
3. **Edit surgically.** Change only the view or section you mean to change, and keep the
   file's indentation style. Re-dumping the whole file produces a formatting diff of
   thousands of lines. Then assert `yaml.safe_load(repo) == intended config`.
4. **Load it:** `scripts/ha-dashboard.sh push <url_path> dashboards/<file>.yaml`. This uses
   websocket `lovelace/config/save`, needs only stdlib Python on the host, and appears on
   the next browser refresh with no restart. Never edit `.storage/lovelace.*` by hand.
   Those edits are cached in memory, need a restart, and risk corruption.
5. **Verify the round-trip:** `ha-dashboard.sh get` again and compare it to the repo. They
   must be equal.
6. **Verify visually with Playwright:** navigate to `http://192.168.1.11:8123/<url_path>/<view>`,
   screenshot the page, and check every requested change: layout, column span, card order,
   badges, and graphs that contain data. If HA shows the login page, ask the user to log
   in inside the Playwright browser. Do not skip this step.
7. **Stop after the Playwright check.** Report what the screenshot shows and wait for the
   user. Don't keep iterating or add extra changes. Commit the repo mirror and push it
   (`rpi` + `origin`) only after the check passes.

Adding a *new* dashboard to `.storage/lovelace_dashboards` still needs a restart.
Logs and entity state won't catch a broken card or a wrong layout. Only the visual check does.

**Full dashboard reference** (view types, card catalog, template cards, tablet layout,
pitfalls, debugging) → read [`reference/dashboards.md`](reference/dashboards.md) when doing
UI work. Modern HA: native **sections** view (drag-drop grid, badges, `heading` cards) and
feature-rich **tile** cards now cover most needs without custom cards; reach for Mushroom
only when you want its specific look.

## Quick reference
```bash
# Repository hygiene (MANDATORY on connection / before deploy)
~/.gemini/config/skills/home-assistant-manager/scripts/ensure-clean.sh
# or manual check:
ssh rpi "cd /homeassistant && git status --porcelain"

# Validate / apply
ssh rpi "ha core check"
ssh rpi "ha core restart"
git push rpi main && git push origin main     # push-to-deploy live + remote backup

# Logs
ssh rpi "ha core logs | grep -iE 'error|<name>' | tail -20"

# State / services (needs env loaded, or use MCP)
hass-cli state get <entity>
hass-cli service call <domain>.reload
hass-cli service call automation.trigger --arguments entity_id=automation.<id>

# Rapid deploy
scp <file>.yaml rpi:/homeassistant/ && hass-cli service call automation.reload

# Storage-mode dashboards (live config via websocket; then Playwright check, then STOP)
scripts/ha-dashboard.sh get  dashboard-sensors live.json
scripts/ha-dashboard.sh push dashboard-sensors dashboards/dashboard_sensors.yaml

# No HASS_TOKEN locally and `ssh rpi ha …` says unauthorized? Use a login shell on the host:
ssh rpi "bash -lc 'ha core check'"
ssh rpi 'bash -lc "curl -s -X POST -H \"Authorization: Bearer \$SUPERVISOR_TOKEN\" http://supervisor/core/api/services/automation/reload"'
```
