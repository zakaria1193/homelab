# Security Checker Service (`services/security/security-checker`)

A self-contained, reproducible homelab service that periodically audits exposed network endpoints, systemd daemon states, authentication controls, and Cloudflare Access protection.

---

## Directory Structure

```
services/security/security-checker/
├── Makefile                          # Automation targets (install, start, status, logs, run, upgrade, stop)
├── .env.example                      # Environment configuration template
├── .env                              # Local runtime environment file
├── security_checker.py               # Main security audit script
├── security-checker.service.template # Systemd service unit template
├── security-checker.timer.template   # Systemd timer unit template (weekly execution)
└── README.md                         # Documentation
```

---

## Management Interface

| Target | Description |
|---|---|
| `make install` | Verifies Python 3 prerequisites |
| `make start` | Installs systemd service & timer, enables and runs initial audit |
| `make status` | Displays systemd timer and service status |
| `make logs` | Follows live service logs via journalctl |
| `make run` | Runs `security_checker.py` audit on demand |
| `make upgrade` | Re-installs and restarts timer |
| `make stop` | Stops and removes systemd service & timer |
| `make clean` | Alias for `make stop` |

---

## AI Security Audit Engine

The security checker discovers services from `services/status/services.conf` and uses an AI CLI tool to audit service safety (checking for unauthenticated remote access, exposed terminal endpoints, or insecure options):

- **Default AI Engine**: `SECURITY_CHECKER_AI_CLI=agy` (Antigravity CLI)
- **Engine Selection**: Easily overridden in `.env`:
  ```ini
  # Use Claude CLI instead of agy:
  SECURITY_CHECKER_AI_CLI=claude
  
  # Enable/Disable AI security audits (1 = enabled, 0 = disabled):
  SECURITY_CHECKER_ENABLE_AI=1
  ```

---

## Agent Skill Scan (NVIDIA SkillSpector)

Step 5 of `run_audit()`, after the services.conf AI audit and before the
summary: scans the AI agent skills installed on dell for poisoned or
malicious content. Report only — nothing is moved, deleted or changed in the
scanned folders.

The step has two parts:

- **Part A — static scan.** NVIDIA SkillSpector
  (https://github.com/NVIDIA/skillspector) runs with machine-readable (JSON)
  output and a per-target timeout, with **static checks only** — no LLM
  provider, no API key. The checker parses the findings itself:
  - `critical`/`high` → **error** (fails the audit, red in Slack)
  - `medium`/`low` → **warning**
  - `info` → logged only
  - a target with no findings → one **passed** entry
  - each line reads `SkillSpector [<severity>] <skill path>: <rule / short reason>`
- **Part B — LLM review.** The checker sends each skill's main file
  (`SKILL.md`, or the agent file) to the CLI named in
  `SECURITY_CHECKER_AI_CLI` with `-p`, asking whether the file holds prompt
  injection, hidden instructions, data theft, or unsafe commands. Only the
  model's first `STATUS:` line counts:
  - `STATUS: RISKY` → **error**
  - `STATUS: WARNING` → **warning**
  - `STATUS: SAFE` → **passed**
  - anything else, a CLI failure, or a timeout → one **warning**
  - the file is sent as data between clear markers with an instruction to
    ignore instructions inside it, cut at 50 kB, run from an empty temp cwd,
    with the CLI's tools turned off where it allows it
  - each line reads `SkillSpector AI [<status>] <skill path>: <sentence>`
  - a git-ignored cache (`skillscan_cache.json`, keyed by real path +
    SHA-256 + CLI name) keeps every verdict, so an unchanged file is not
    re-sent to the CLI — a cached `RISKY` is still reported every week until
    the skill is fixed or removed

Default scanned folders (`SECURITY_CHECKER_SKILL_PATHS`, colon-separated,
`~` and globs expanded, each real path scanned once even via a symlink,
missing folders skipped silently):

```
~/.claude/skills                  - Claude Code's own installed skills
~/.claude/plugins                 - installed Claude Code plugins and
                                     the skills inside them
~/my_repos/*/.claude/skills       - project-local skills in every repo
~/.gemini/config/skills           - Antigravity (agy)'s installed skills
~/.gemini/antigravity-cli/plugins - installed agy plugins and the
                                     skills inside them
```

Toggles:

```ini
SECURITY_CHECKER_ENABLE_SKILLSCAN=1   # 0 disables the whole step (Part A + B)
SECURITY_CHECKER_ENABLE_AI=1          # 0 skips Part B only, Part A still runs
```

The Slack summary gains `Skills scanned: N in M folders`; findings are
capped at 10 per target in Slack (`+N more`) with the full list in
`security_checker.log`.

**Install**: `make install` installs the pinned SkillSpector release
(`SKILLSPECTOR_VERSION` in the Makefile) into a git-ignored `.venv` in this
service directory — nothing system-wide. `make upgrade` moves to the pin
written in the Makefile. The checker calls the scanner by its full venv path,
so `PATH` does not affect it (but `PATH` must still resolve the AI CLI for
Part B).
