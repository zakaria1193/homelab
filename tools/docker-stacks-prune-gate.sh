#!/usr/bin/env bash
# Verifies the Docker compose stacks (media, karakeep) and prunes dangling
# images, but only when every stack is running AND the caller's systemd units
# are also fine. Called by services/AI/Makefile's `verify` target, after the
# unit check, with the units' own ok/fail status as the first argument - a
# container problem must not trigger a prune, and neither must a unit
# problem, even if Docker itself looks clean.
#
#   docker-stacks-prune-gate.sh <units-ok: 0|1> <stack-dir> [<stack-dir> ...]
#
# Each <stack-dir> is verified with compose-verify.sh under its own basename
# as the compose project name (matches services/media and services/karakeep).
# Exercised by tools/tests/test_docker_stacks_prune_gate.sh with a stub
# `docker` on PATH - never the real daemon.
set -u

UNITS_OK="${1:?usage: docker-stacks-prune-gate.sh <units-ok 0|1> <stack-dir> [<stack-dir> ...]}"
shift
if [ "$#" -eq 0 ]; then
	echo "usage: docker-stacks-prune-gate.sh <units-ok 0|1> <stack-dir> [<stack-dir> ...]" >&2
	exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DOCKER="${DOCKER_BIN:-}"
[ -z "$DOCKER" ] && DOCKER="$(command -v docker 2>/dev/null || true)"
[ -z "$DOCKER" ] && [ -x /snap/bin/docker ] && DOCKER=/snap/bin/docker
if [ -z "$DOCKER" ]; then
	echo "[FAIL] docker is not on PATH or at /snap/bin/docker"
	exit 1
fi

fail=0
names=""
failed_containers=""
for dir in "$@"; do
	project="$(basename "$dir")"
	names="$names $project"
	echo "--- $project ---"
	out="$(DOCKER_BIN="$DOCKER" "$HERE/compose-verify.sh" "$dir" "$project" 2>&1)"
	rc=$?
	echo "$out"
	if [ "$rc" -ne 0 ]; then
		fail=1
		svcs="$(echo "$out" | sed -n 's/^\[FAIL\] failed services:[[:space:]]*//p')"
		for s in $svcs; do
			failed_containers="$failed_containers $project:$s"
		done
	fi
done

if [ "$fail" -eq 0 ] && [ "$UNITS_OK" = "0" ]; then
	echo "=== Pruning dangling images ==="
	prune_out="$("$DOCKER" image prune -f 2>&1)"
	echo "$prune_out"
	echo "[OK] AI services and Docker stacks ($(echo "$names" | sed 's/^ //; s/ /, /g')) upgraded and running"
	exit 0
else
	echo "[FAIL] Docker stacks not all running, or AI units failed - skipping prune"
	if [ -n "$failed_containers" ]; then
		echo "[FAIL] failed containers:$failed_containers"
	fi
	exit 1
fi
