#!/usr/bin/env bash
# Put the submodule services' .env files back where they are read.
#
# A submodule is its own repository, so this one cannot track a file inside it:
# `services/AI/auto-job-applier/.env` can only ever be committed to the upstream
# it came from, which is somebody else's. Registering such a path in
# /.gitattributes does nothing at all - it is not that the file is committed in
# the clear, it is that it is not committed.
#
# So the real file lives in services/AI/env/ (git-crypt encrypted, like every
# other service .env) and is symlinked into the submodule, where systemd and
# docker read it exactly as before. Run this after `git-crypt unlock` on a fresh
# clone; it is idempotent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# <link to create>:<file it points at, relative to the link's directory>
# Only for submodules that do NOT track their own .env. ai-job-search and
# auto-job-applier both commit theirs inside their own repository, so their
# file already arrives with `git submodule update` and must be left alone -
# symlinking it there only makes the submodule permanently dirty.
LINKS=(
  "services/AI/paperclipAI/paperclip-mcp/.env:../../env/paperclip-mcp.env"
)

made=0 kept=0 missing=0
for entry in "${LINKS[@]}"; do
  link="${entry%%:*}"
  target="${entry#*:}"
  dir="$(dirname "$link")"
  source="$REPO_ROOT/services/AI/env/$(basename "$target")"

  if [ ! -e "$source" ]; then
    echo "  [SKIP] $link - $source is missing (did you run 'git-crypt unlock'?)"
    missing=$((missing + 1))
    continue
  fi
  if [ ! -d "$dir" ]; then
    echo "  [SKIP] $link - $dir is missing (did you run 'git submodule update --init'?)"
    missing=$((missing + 1))
    continue
  fi
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$target" ]; then
    kept=$((kept + 1))
  else
    # A real file here would be the pre-symlink arrangement, or a copy someone
    # made by hand. Keep it: it may hold keys this repo has never seen.
    if [ -f "$link" ] && [ ! -L "$link" ]; then
      mv "$link" "$link.before-link"
      echo "  [KEPT] $link moved aside to $(basename "$link").before-link"
    fi
    ln -sfn "$target" "$link"
    echo "  [LINK] $link -> $target"
    made=$((made + 1))
  fi

  # Keep `git status` inside the submodule quiet about a link that is ours.
  gitdir="$(git rev-parse --git-dir 2>/dev/null)/modules/$(echo "$dir" | sed 's#^\./##')"
  exclude="$gitdir/info/exclude"
  if [ -d "$(dirname "$exclude")" ] && ! grep -qxF ".env" "$exclude" 2>/dev/null; then
    echo ".env" >> "$exclude"
  fi
done

echo "[OK] $made linked, $kept already in place, $missing skipped."
