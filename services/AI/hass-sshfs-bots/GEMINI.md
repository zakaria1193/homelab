# Home Assistant Config Bot Workspace

You are working in the Home Assistant SSHFS configuration workspace (`hass-sshfs-bots`) on `192.168.1.10`.
The Home Assistant configuration files from the Raspberry Pi (`192.168.1.11`) are mounted under `./config/`.

## Key Guidelines:
- Inspect configuration files under `./config/` (such as `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, `ui-lovelace.yaml`).
- Always validate YAML syntax carefully before saving.
- Do not remove existing integrations or entities without checking dependencies.
- Changes made in `./config/` are immediately synced to the Raspberry Pi over SSHFS.
