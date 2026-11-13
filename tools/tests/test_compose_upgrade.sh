#!/usr/bin/env bash
# Exercises tools/compose-upgrade.sh against a stub `docker`, never the real
# daemon. Covers: no containers -> SKIP, exit 0, no pull/up call; containers
# present -> pull then up -d; pull fails -> exit non-zero and no up -d;
# Docker unreachable -> exit non-zero, no pull.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../compose-upgrade.sh"
STUB="$HERE/stub-docker.sh"
STACK_DIR="$(mktemp -d)"
CALL_LOG="$(mktemp)"
trap 'rm -rf "$STACK_DIR" "$CALL_LOG"' EXIT

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

called() { grep -qx "$1" "$CALL_LOG" 2>/dev/null; }

run() {
	# run <expected-exit> <description> <env assignments...>
	local expected="$1" desc="$2"
	shift 2
	: >"$CALL_LOG"
	out="$(env DOCKER_BIN="$STUB" STUB_CALL_LOG="$CALL_LOG" VERIFY_SETTLE_SECS=1 "$@" "$SCRIPT" "$STACK_DIR" test-stack 2>&1)"
	rc=$?
	last_out="$out"
	if [ "$rc" -eq "$expected" ]; then
		pass "$desc (exit $rc)"
	else
		fail "$desc: expected exit $expected, got $rc"$'\n'"$out"
	fi
}

echo "compose-upgrade.sh"

run 0 "no containers -> SKIP, exit 0" \
	STUB_SERVICES="a b" STUB_RUNNING=""
case "$last_out" in
*SKIP*"not pulled, not started"*) pass "SKIP line explains nothing was pulled or started" ;;
*) fail "expected a SKIP line, got:"$'\n'"$last_out" ;;
esac
called pull && fail "pull was called on a stopped stack" || pass "pull was not called"
called up && fail "up was called on a stopped stack" || pass "up was not called"

run 0 "containers present -> pull then up -> verify OK" \
	STUB_SERVICES="a b" STUB_RUNNING="a b"
called pull && pass "pull was called" || fail "pull was not called"
called up && pass "up was called" || fail "up was not called"

run 1 "pull fails -> exit non-zero, no up -d" \
	STUB_SERVICES="a b" STUB_RUNNING="a b" STUB_PULL_OK=0
called pull && pass "pull was called" || fail "pull was not called"
called up && fail "up was called despite a failed pull" || pass "up was not called"
case "$last_out" in
*"pull failed"*) pass "failure names the pull step" ;;
*) fail "expected a message naming the failed pull, got:"$'\n'"$last_out" ;;
esac

run 1 "Docker unreachable -> exit non-zero, no pull" \
	STUB_SERVICES="a b" STUB_RUNNING="a b" STUB_INFO_OK=0
called pull && fail "pull was called while Docker was unreachable" || pass "pull was not called"
called up && fail "up was called while Docker was unreachable" || pass "up was not called"

# Git worktree resolution: a stack inside a linked worktree must resolve
# to the main repository checkout so compose bind mounts don't point at the worktree.
WT_REPO="$(mktemp -d)"
WT_DIR="$(mktemp -d)"
ARGS_LOG="$(mktemp)"
git -C "$WT_REPO" init -q -b main
git -C "$WT_REPO" config user.email "test@example.com"
git -C "$WT_REPO" config user.name "test"
mkdir -p "$WT_REPO/services/stack-a"
echo "services: {}" > "$WT_REPO/services/stack-a/docker-compose.yml"
git -C "$WT_REPO" add . && git -C "$WT_REPO" commit -q -m "init"
git -C "$WT_REPO" worktree add -q -b branch-wt "$WT_DIR" main

env DOCKER_BIN="$STUB" STUB_ARGS_LOG="$ARGS_LOG" STUB_SERVICES="a" STUB_RUNNING="" \
	"$SCRIPT" "$WT_DIR/services/stack-a" stack-a >/dev/null 2>&1 || true
if grep -q -- "--project-directory $WT_REPO/services/stack-a" "$ARGS_LOG"; then
	pass "linked worktree STACK_DIR resolves to main repository checkout"
else
	fail "expected compose to use main repo project-directory, got args:"$'\n'"$(cat "$ARGS_LOG")"
fi
git -C "$WT_REPO" worktree remove -f "$WT_DIR" >/dev/null 2>&1 || true
rm -rf "$WT_REPO" "$WT_DIR" "$ARGS_LOG"

[ "$FAILED" = "0" ] && echo "OK" || echo "FAILURES"
exit "$FAILED"
