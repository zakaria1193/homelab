#!/usr/bin/env bash
# Asserts that every service in a docker compose stack has a running,
# healthy container. Shared by services/media/Makefile and
# services/karakeep/Makefile (`make verify`), and exercised directly by
# tools/tests/test_compose_verify.sh with a stub `docker` on PATH.
#
#   compose-verify.sh <stack-dir> [project-name]
#
# Prints one line per service (OK/FAIL/SKIP) and exits non-zero if any
# service that should be running is not.
set -u

STACK_DIR="${1:?usage: compose-verify.sh <stack-dir> [project-name]}"
PROJECT="${2:-$(basename "$STACK_DIR")}"
SETTLE_SECS="${VERIFY_SETTLE_SECS:-20}"

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

services="$(compose config --services 2>/dev/null | tr '\n' ' ')"
if [ -z "$services" ]; then
	echo "[FAIL] could not read the service list from $STACK_DIR/docker-compose.yml"
	exit 1
fi

# Docker not reachable at all (daemon down, socket refused) must FAIL, not
# SKIP: "cannot ask docker" must not look like "stack never started".
if ! "$DOCKER" info >/dev/null 2>&1; then
	for s in $services; do
		printf '  %-15s FAIL  (cannot reach Docker)\n' "$s"
	done
	echo "[FAIL] $PROJECT: Docker daemon not reachable"
	echo "[FAIL] failed services: $services"
	exit 1
fi

# -a: a container that crashed or exited is still listed, so a dead stack
# is a FAIL here, not "stack not started".
running_ids="$(compose ps -a -q 2>/dev/null)"
if [ -z "$running_ids" ]; then
	for s in $services; do
		printf '  %-15s SKIP  (stack not started)\n' "$s"
	done
	echo "[SKIP] $PROJECT: no containers on this host"
	exit 0
fi

fail=0
failed_services=""
for s in $services; do
	cid="$(compose ps -a -q "$s" 2>/dev/null)"
	if [ -z "$cid" ]; then
		printf '  %-15s FAIL  (no container)\n' "$s"
		fail=1
		failed_services="$failed_services $s"
		continue
	fi
	deadline=$(( $(date +%s) + SETTLE_SECS ))
	state=""
	health=""
	while :; do
		state="$("$DOCKER" inspect -f '{{.State.Status}}' "$cid" 2>/dev/null)"
		health="$("$DOCKER" inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null)"
		[ "$state" = "running" ] && [ "$health" != "starting" ] && break
		[ "$(date +%s)" -ge "$deadline" ] && break
		sleep 2
	done
	if [ "$state" = "running" ] && [ "$health" != "unhealthy" ]; then
		printf '  %-15s OK    (%s%s)\n' "$s" "$state" "${health:+/$health}"
	else
		printf '  %-15s FAIL  (%s%s)\n' "$s" "${state:-unknown}" "${health:+/$health}"
		fail=1
		failed_services="$failed_services $s"
	fi
done

if [ "$fail" -eq 0 ]; then
	echo "[OK] $PROJECT: all containers running"
	exit 0
else
	echo "[FAIL] $PROJECT: one or more containers not running"
	echo "[FAIL] failed services:$failed_services"
	exit 1
fi
