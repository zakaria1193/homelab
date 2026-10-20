#!/usr/bin/env bash
# Exercises tools/auto-heal-and-notify.sh against a stub repo: a fake
# services/AI/Makefile whose `verify` records the AUTO_HEAL it sees, no aicli
# (so no agy runs) and no slackbot-notify.sh (so nothing is posted).
#
# The case that matters: `make upgrade` calls `verify AUTO_HEAL=1`, and make
# passes that to every nested make through MAKEFLAGS. The heal's re-check
# must still run with AUTO_HEAL=0, or it would call the heal again forever.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../auto-heal-and-notify.sh"
STUB_ROOT="$(mktemp -d)"
trap 'rm -rf "$STUB_ROOT"' EXIT

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

mkdir -p "$STUB_ROOT/services/AI"
cat >"$STUB_ROOT/services/AI/Makefile" <<'MK'
verify:
	@echo "$(AUTO_HEAL)" >> $(CURDIR)/verify-calls
	@exit $(VERIFY_EXIT)
MK

run() {
	# run <verify-exit> <expected-exit> <description>
	local verify_exit="$1" expected="$2" desc="$3"
	: >"$STUB_ROOT/services/AI/verify-calls"
	out="$(env REPO_ROOT="$STUB_ROOT" MAKEFLAGS="AUTO_HEAL=1 PRUNE=1" VERIFY_EXIT="$verify_exit" \
		timeout 60 "$SCRIPT" "fake-unit-$$" "" 2>&1)"
	rc=$?
	calls="$(tr '\n' ' ' <"$STUB_ROOT/services/AI/verify-calls")"
	if [ "$rc" -ne "$expected" ]; then
		fail "$desc: expected exit $expected, got $rc"$'\n'"$out"
	elif [ "$calls" != "0 " ]; then
		fail "$desc: re-check should run once with AUTO_HEAL=0, saw [$calls]"
	else
		pass "$desc (exit $rc, re-check AUTO_HEAL=0)"
	fi
}

echo "auto-heal-and-notify.sh"
run 0 0 "re-check passes -> healed"
run 1 1 "re-check fails -> alert path, no recursion"

exit "$FAILED"
