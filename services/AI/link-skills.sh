#!/usr/bin/env bash
set -euo pipefail

# Link shared AI skills and MCP configuration to detected agent environments
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${SCRIPT_DIR}/skills"
MCP_CONFIG="${SCRIPT_DIR}/mcp_config.json"
HOMELAB_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== AI Skills & Config Installer ==="
echo "Source skills: ${SKILLS_DIR}"

if [[ ! -d "${SKILLS_DIR}" ]]; then
  echo "Error: Skills directory not found at ${SKILLS_DIR}" >&2
  exit 1
fi

link_skills_to() {
  local target_dir="$1"
  local agent_name="$2"

  mkdir -p "${target_dir}"
  echo "Linking skills to ${agent_name} (${target_dir})..."
  for skill_path in "${SKILLS_DIR}"/*; do
    if [[ -d "${skill_path}" ]]; then
      local skill_name
      skill_name="$(basename "${skill_path}")"
      ln -sfn "${skill_path}" "${target_dir}/${skill_name}"
      echo "  -> ${skill_name}"
    fi
  done
}

# 1. Claude Agent (~/.claude)
if [[ -d "${HOME}/.claude" ]]; then
  link_skills_to "${HOME}/.claude/skills" "Claude"

  if [[ -f "${MCP_CONFIG}" ]]; then
    ln -sfn "${MCP_CONFIG}" "${HOME}/.claude/mcp.json"
    echo "Linked MCP config to ${HOME}/.claude/mcp.json"
  fi
else
  echo "Skipping Claude (~/.claude not found)"
fi

# 2. Antigravity / AGY Agent (~/.gemini)
if [[ -d "${HOME}/.gemini" ]]; then
  link_skills_to "${HOME}/.gemini/config/skills" "Antigravity (AGY)"
else
  echo "Skipping Antigravity (~/.gemini not found)"
fi

# 3. Codex Agent (~/.codex)
if [[ -d "${HOME}/.codex" ]]; then
  link_skills_to "${HOME}/.codex/skills" "Codex"
else
  echo "Skipping Codex (~/.codex not found)"
fi

# 4. Homelab workspace local agent skills (.agents/skills)
if [[ -d "${HOMELAB_ROOT}/.agents" ]]; then
  link_skills_to "${HOMELAB_ROOT}/.agents/skills" "Homelab Workspace (.agents)"
fi

echo "=== Done ==="
