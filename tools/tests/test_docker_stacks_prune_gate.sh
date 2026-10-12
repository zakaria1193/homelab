#!/usr/bin/env bash
# Exercises tools/docker-stacks-prune-gate.sh against a stub `docker`, never
# the real daemon. Covers: prune runs when every stack and unit is clean,
# and - the important case - no prune after a failure, whether that failure
# is a Docker stack problem or the caller reporting its systemd units as not
# all running.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../docker-stacks-prune-gate.sh"
STUB="$HERE/stub-docker.sh"
STACK_A="$(mktemp -d)"
STACK_B="$(mktemp -d)"
PRUNE_LOG="$(mktemp)"
trap 'rm -rf "$STACK_A" "$STACK_B" "$PRUNE_LOG"' EXIT

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

prune_called() { [ -s "$PRUNE_LOG" ]; }

run() {
	# run <expected-exit> <units-ok> <description> <env assignments...>
	local expected="$1" units_ok="$2" desc="$3"
	shift 3
	: >"$PRUNE_LOG"
	out="$(env DOCKER_BIN="$STUB" STUB_PRUNE_LOG="$PRUNE_LOG" VERIFY_SETTLE_SECS=1 "$@" "$SCRIPT" "$units_ok" "$STACK_A" "$STACK_B" 2>&1)"
	rc=$?
	last_out="$out"
	if [ "$rc" -eq "$expected" ]; then
		pass "$desc (exit $rc)"
	else
		fail "$desc: expected exit $expected, got $rc"$'\n'"$out"
	fi
}

echo "docker-stacks-prune-gate.sh"

run 0 0 "all stacks running, units ok -> prune runs" \
	STUB_SERVICES="a" STUB_RUNNING="a"
prune_called && pass "prune was called" || fail "prune was not called, expected it to run"

run 0 0 "all stacks running, PRUNE=0 -> verify only" \
	STUB_SERVICES="a" STUB_RUNNING="a" PRUNE=0
prune_called && fail "prune was called with PRUNE=0" || pass "prune was not called"

run 1 1 "all stacks running, units FAILED -> no prune" \
	STUB_SERVICES="a" STUB_RUNNING="a"
prune_called && fail "prune was called despite a failed unit" || pass "prune was not called"

run 1 0 "a stack has no container -> no prune" \
	STUB_SERVICES="a b" STUB_RUNNING="a"
prune_called && fail "prune was called despite a failed container" || pass "prune was not called"
case "$last_out" in
*"failed containers:"*"$(basename "$STACK_A"):b"*) pass "failed containers line names project:service" ;;
*) fail "expected a 'failed containers:' line naming the project and service, got:"$'\n'"$last_out" ;;
esac

run 1 0 "Docker unreachable -> no prune" \
	STUB_SERVICES="a" STUB_RUNNING="a" STUB_INFO_OK=0
prune_called && fail "prune was called while Docker was unreachable" || pass "prune was not called"

[ "$FAILED" = "0" ] && echo "OK" || echo "FAILURES"
exit "$FAILED"
