# Home Assistant SSHFS AI Workspace (`hass-sshfs-bots`)

A terminal-only workspace on the primary server (`192.168.1.10`) that mounts
Home Assistant's `/config` from the Raspberry Pi (`192.168.1.11`) over
**SSHFS** for the length of one interactive AI CLI session, then unmounts it.

---

## 1. Overview & Architecture

Home Assistant runs on the Raspberry Pi gateway (`192.168.1.11`). To safely
and interactively edit its YAML configuration, automations, scripts and
dashboards without running a heavyweight AI coding CLI on the Pi itself:

1. **SSHFS mount, on demand**: `make claude` / `make agy` mount the remote
   `/config` directory into `services/AI/hass-sshfs-bots/config/`, run the CLI
   in the foreground, and unmount on exit (normal exit, Ctrl-C, or a crash -
   `trap ... EXIT INT TERM` in each launcher script) or via `auto_unmount` in
   `SSHFS_OPTIONS` as a second line of defense.
2. **A terminal, not a service**: this is deliberately a `make` target you run
   from a shell, not a systemd daemon or a Claude/Antigravity Remote Control
   instance. The mount only exists while a human (or an agent driving a local
   terminal) is actively working, so there is nothing to keep running, nothing
   to decommission, and no session that outlives the person who started it.
3. **Cockpit integration**: registered under group `Home` as two `type =
   shell` launchers - `[home-assistant (claude)]` and `[home-assistant
   (agy)]` - next to the app's own `[home-assistant]` chip. Named after the
   app you are editing, not this directory's sshfs mechanism; each opens a
   real terminal on the box and types its `make` command for you.

---

## 2. Directory Structure

```text
services/AI/hass-sshfs-bots/
├── Makefile                          # mount, unmount, status, claude/agy launchers
├── hass-claude.sh / hass-agy.sh       # mount -> run CLI -> unmount, called by `make claude` / `make agy`
├── .env.example                      # SSH connection & mount path template
├── .env                              # active config (git-crypt encrypted)
├── .gitignore                        # excludes mounted files & temporary data
├── README.md                         # this file
├── GEMINI.md                         # prompting instructions for the agent working in ./config
└── config/                           # mountpoint for the Pi's Home Assistant configuration
```

---

## 3. Quick Start

```bash
# Prepare .env, the ~/hass_sshfs_workspace symlink, and verify sshfs is installed
make setup

# Mount, work, unmount - pick your CLI
make claude
make agy

# Just the mount lifecycle, without a CLI
make mount
make status
make unmount
```

---

## 4. Shell aliases

- `claude_hass` / `claude_hass_sshfs` - `cd ~/hass_sshfs_workspace && claude`
- `agy_hass` / `agy_hass_sshfs` - `cd ~/hass_sshfs_workspace && agy`
- **Symlink**: `~/hass_sshfs_workspace -> /home/zfadli/my_repos/homelab/services/AI/hass-sshfs-bots`

These are plain `cd && <cli>` aliases from the shell dotfiles, not this
repo, and skip the mount/unmount wrapper - use `make claude` / `make agy` (or
the cockpit's shell buttons) when you want the sshfs lifecycle handled for you.

---

## 5. Makefile Targets

| Target | Description |
|---|---|
| `make setup` | Prepare `.env`, the symlink, and verify `sshfs` is installed |
| `make mount` | Mount Home Assistant's `/config` from the Raspberry Pi via `sshfs` |
| `make unmount` | Safely (lazy-)unmount the `config/` directory |
| `make claude` | Mount, run `claude` in this workspace, unmount on exit |
| `make agy` | Mount, run `agy` in this workspace, unmount on exit |
| `make status` | Check whether `config/` is currently mounted |
| `make clean` | Alias for `make unmount` |
