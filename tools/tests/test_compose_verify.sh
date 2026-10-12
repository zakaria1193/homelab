#!/usr/bin/env bash
# Exercises tools/compose-verify.sh against a stub `docker`, never the real
# daemon. Covers: verify OK, verify FAIL, verify SKIP (stack never started),
# Docker not reachable (FAIL, not SKIP), and an unhealthy container (FAIL).
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../compose-verify.sh"
STUB="$HERE/stub-docker.sh"
STACK_DIR="$(mktemp -d)"
trap 'rm -rf "$STACK_DIR"' EXIT

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

run() {
	# run <expected-exit> <description> <env assignments...>
	local expected="$1" desc="$2"
	shift 2
	out="$(env DOCKER_BIN="$STUB" VERIFY_SETTLE_SECS=1 "$@" "$SCRIPT" "$STACK_DIR" test-stack 2>&1)"
	rc=$?
	last_out="$out"
	if [ "$rc" -eq "$expected" ]; then
		pass "$desc (exit $rc)"
	else
		fail "$desc: expected exit $expected, got $rc"$'\n'"$out"
	fi
}

echo "compose-verify.sh"

run 0 "all services running -> OK" \
	STUB_SERVICES="a b" STUB_RUNNING="a b"

run 1 "a service with no container -> FAIL" \
	STUB_SERVICES="a b" STUB_RUNNING="a"
case "$last_out" in
*"failed services:"*b*) pass "failed services line names the down service" ;;
*) fail "expected a 'failed services:' line naming b, got:"$'\n'"$last_out" ;;
esac

run 0 "stack never started -> SKIP, not FAIL" \
	STUB_SERVICES="a b" STUB_RUNNING=""
case "$last_out" in
*SKIP*) pass "SKIP line printed for a stack with no containers" ;;
*) fail "expected a SKIP line, got:"$'\n'"$last_out" ;;
esac

run 1 "Docker unreachable -> FAIL, not SKIP" \
	STUB_SERVICES="a b" STUB_RUNNING="a b" STUB_INFO_OK=0
case "$last_out" in
*SKIP*) fail "Docker-unreachable run printed SKIP; it must read as FAIL" ;;
*FAIL*) pass "Docker-unreachable run reads as FAIL" ;;
*) fail "unexpected output:"$'\n'"$last_out" ;;
esac

run 1 "unhealthy container -> FAIL" \
	STUB_SERVICES="a" STUB_RUNNING="a" STUB_UNHEALTHY="a"

[ "$FAILED" = "0" ] && echo "OK" || echo "FAILURES"
exit "$FAILED"
