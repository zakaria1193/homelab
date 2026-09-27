#!/usr/bin/env bash
set -euo pipefail

# Ensure remote Home Assistant repository is 100% clean and synchronized.
# Everything must be either committed or gitignored so pushes never break.

REMOTE_HOST="${HA_REMOTE_HOST:-rpi}"
REMOTE_PATH="${HA_REMOTE_PATH:-/homeassistant}"
LOCAL_REPO="${HA_LOCAL_REPO:-/home/zfadli/my_repos/home-assistant-config}"

echo "==> Checking remote repository status at ${REMOTE_HOST}:${REMOTE_PATH}..."

# Check porcelain status on remote
DIRTY_FILES=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "${REMOTE_HOST}" "cd ${REMOTE_PATH} && git status --porcelain" || true)

if [ -z "${DIRTY_FILES}" ]; then
  echo "==> Remote repository is clean. Nothing to do."
  exit 0
fi

echo "==> Remote repository has uncommitted/untracked changes:"
echo "${DIRTY_FILES}"

echo "==> Ensuring proper .git permissions on remote..."
ssh "${REMOTE_HOST}" "sudo -n chown -R \$(id -un):\$(id -gn) ${REMOTE_PATH}/.git 2>/dev/null || true"

echo "==> Staging tracked/untracked components, blueprints, and config files on remote..."
ssh "${REMOTE_HOST}" "cd ${REMOTE_PATH} && git add -A"

# Verify what is staged
STAGED_DIFF=$(ssh "${REMOTE_HOST}" "cd ${REMOTE_PATH} && git diff --cached --name-only")
if [ -n "${STAGED_DIFF}" ]; then
  echo "==> Committing updates on remote:"
  echo "${STAGED_DIFF}"
  ssh "${REMOTE_HOST}" "cd ${REMOTE_PATH} && git commit -m 'chore(remote): capture remote changes (HACS/components/blueprints)'"
fi

# Pull remote commits into local workspace
if [ -d "${LOCAL_REPO}/.git" ]; then
  echo "==> Pulling changes into local repository (${LOCAL_REPO})..."
  git -C "${LOCAL_REPO}" pull "${REMOTE_HOST}" main

  echo "==> Pushing synchronized history to origin/main..."
  git -C "${LOCAL_REPO}" push origin main

  # Keep remote origin tracking ref synced
  CURRENT_COMMIT=$(git -C "${LOCAL_REPO}" rev-parse HEAD)
  ssh "${REMOTE_HOST}" "cd ${REMOTE_PATH} && git update-ref refs/remotes/origin/main ${CURRENT_COMMIT} 2>/dev/null || true"
fi

# Final verification
FINAL_STATUS=$(ssh "${REMOTE_HOST}" "cd ${REMOTE_PATH} && git status --porcelain" || true)
if [ -z "${FINAL_STATUS}" ]; then
  echo "==> SUCCESS: Remote repository is completely clean and synchronized."
else
  echo "==> WARNING: Unhandled files remain on remote:"
  echo "${FINAL_STATUS}"
  exit 1
fi
