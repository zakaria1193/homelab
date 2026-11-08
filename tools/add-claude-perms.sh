#!/usr/bin/env bash
# Run by hand on a homelab machine: adds Claude Code permission rules to ~/.claude/settings.json.
# Harmless commands go under allow; risky ones (merges, secrets, DELETE calls, deploys) go under ask,
# so each one prompts at the terminal. Backs up the file first; safe to run again.
set -euo pipefail
f="$HOME/.claude/settings.json"
mkdir -p "$HOME/.claude"
[ -f "$f" ] && cp "$f" "$f.bak-$(date +%Y%m%d-%H%M%S)"
python3 - "$f" <<'PY'
import json, os, sys, tempfile
path = sys.argv[1]
data = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else {}
allow_rules = [
  "Bash(git fetch:*)", "Bash(git checkout:*)", "Bash(git worktree:*)",
  "Bash(pnpm install:*)", "Bash(gh pr create:*)", "Bash(grep:*)", "Bash(rg:*)",
]
ask_rules = [
  "Bash(gh pr merge:*)", "Bash(gh secret:*)",
  "Bash(curl -s -X DELETE:*)", "Bash(curl -X DELETE:*)",
  "Bash(curl -X POST https://api.cloudflare.com:*)",
  "Bash(pnpm deploy:*)", "Bash(pnpm exec wrangler:*)",
]
perms = data.setdefault("permissions", {})
allow = perms.setdefault("allow", [])
ask = perms.setdefault("ask", [])
allow[:] = [r for r in allow if r not in ask_rules]  # risky ones must prompt
for r in allow_rules:
    if r not in allow: allow.append(r)
for r in ask_rules:
    if r not in ask: ask.append(r)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
with os.fdopen(fd, "w") as out:
    json.dump(data, out, indent=2); out.write("\n")
json.load(open(tmp))
os.replace(tmp, path)
print(json.dumps(data["permissions"], indent=2))
PY
echo "Done. Restart Claude Code sessions on this machine for the rules to apply."
