#!/usr/bin/env bash
# Pulls and restarts a docker compose stack, but respects a stack that was
# stopped on purpose (`make stop` / `docker compose down`): a stack with no
# container at all is left alone, not pulled and not started. Shared by
# services/media/Makefile and services/karakeep/Makefile (`make upgrade`),
# and exercised directly by tools/tests/test_compose_upgrade.sh with a stub
# `docker` on PATH.
#
#   compose-upgrade.sh <stack-dir> [project-name]
#
# Order: Docker unreachable -> FAIL, exit non-zero (not read as "stopped").
# No containers for the project -> SKIP, exit 0, nothing pulled or started.
# Otherwise `compose pull`; a failed pull -> FAIL, exit non-zero, `up -d` is
# not run (the old containers keep running). Then `compose up -d`, then
# compose-verify.sh; the exit status is that of the first failing step, or 0.
set -u

STACK_DIR="${1:?usage: compose-upgrade.sh <stack-dir> [project-name]}"
PROJECT="${2:-$(basename "$STACK_DIR")}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DOCKER="${DOCKER_BIN:-}"
[ -z "$DOCKER" ] && DOCKER="$(command -v docker 2>/dev/null || true)"
[ -z "$DOCKER" ] && [ -x /snap/bin/docker ] && DOCKER=/snap/bin/docker
if [ -z "$DOCKER" ]; then
	echo "[FAIL] docker is not on PATH or at /snap/bin/docker"
	exit 1
fi

compose() {
	"$DOCKER" compose --project-directory "$STACK_DIR" -f "$STACK_DIR/docker-compose.yml" -p "$PROJECT" "$@"
}

if ! "$DOCKER" info >/dev/null 2>&1; then
	echo "[FAIL] $PROJECT: Docker daemon not reachable"
	exit 1
fi

running_ids="$(compose ps -a -q 2>/dev/null)"
if [ -z "$running_ids" ]; then
	echo "[SKIP] $PROJECT: stopped (no containers) - not pulled, not started; 'make start' brings it up"
	exit 0
fi

echo "=== Pulling $PROJECT images ==="
if ! compose pull; then
	echo "[FAIL] $PROJECT: pull failed, old containers left running"
	exit 1
fi

if ! compose up -d; then
	echo "[FAIL] $PROJECT: up -d failed"
	exit 1
fi

DOCKER_BIN="$DOCKER" "$HERE/compose-verify.sh" "$STACK_DIR" "$PROJECT"
