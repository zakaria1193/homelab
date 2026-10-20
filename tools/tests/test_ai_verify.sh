#!/usr/bin/env bash
# Exercises the real services/AI/Makefile `verify` target with a stub
# `systemctl` first on PATH and the existing stub-docker.sh as DOCKER_BIN -
# never the real systemd or Docker daemon. MEDIA_DIR/KARAKEEP_DIR point at
# throwaway temp dirs; the stub docker answers their service lists from env,
# so the directories never need a real docker-compose.yml.
#
# Covers: all units active and stacks running -> exit 0; an enabled unit
# failed -> exit non-zero, unit named; a disabled/masked unit that is down
# -> SKIP, exit 0; a unit not installed -> SKIP; a failed container -> exit
# non-zero, project:service named.
#
# Clears MAKEFLAGS/MAKELEVEL itself so running under the root `make test`
# cannot leak that invocation's AUTO_HEAL=1 into this one's `make verify`.
unset MAKEFLAGS MAKELEVEL
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
AI_DIR="$ROOT/services/AI"
STUB_SYSTEMCTL="$HERE/stub-systemctl.sh"
STUB_DOCKER="$HERE/stub-docker.sh"

BIN_DIR="$(mktemp -d)"
cp "$STUB_SYSTEMCTL" "$BIN_DIR/systemctl"
chmod +x "$BIN_DIR/systemctl"
MEDIA_DIR="$(mktemp -d)"
KARAKEEP_DIR="$(mktemp -d)"
trap 'rm -rf "$BIN_DIR" "$MEDIA_DIR" "$KARAKEEP_DIR"' EXIT

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

# Every unit services/AI/Makefile's AI_SERVICE_UNITS resolves for the real
# service dirs, as of this ticket - the names systemctl is actually asked
# about.
ALL_UNITS="hermes-ai openhands-ai ai-job-search arr-mcp-backend playwright-mcp claude-rc-ai antigravity-cli-daemon aicli-ai pjm"

# all_active_env: prints STATE_/SUB_/ENABLED_ assignments making every unit
# in ALL_UNITS active (env var names can't hold `-`, so each one is turned
# into `_`), so a scenario only needs to override the exceptions.
all_active_env() {
	for u in $ALL_UNITS; do
		local safe="${u//-/_}"
		printf 'STATE_%s=active SUB_%s=running ENABLED_%s=enabled ' "$safe" "$safe" "$safe"
	done
}

run() {
	# run <expected-exit> <description> <env assignments...>
	local expected="$1" desc="$2"
	shift 2
	out="$(env PATH="$BIN_DIR:$PATH" DOCKER_BIN="$STUB_DOCKER" VERIFY_SETTLE_SECS=0 \
		STUB_USER_UNITS="$ALL_UNITS" STUB_SERVICES="svc" STUB_RUNNING="svc" \
		$(all_active_env) "$@" \
		make -C "$AI_DIR" --no-print-directory verify \
		MEDIA_DIR="$MEDIA_DIR" KARAKEEP_DIR="$KARAKEEP_DIR" AUTO_HEAL=0 PRUNE=0 2>&1)"
	rc=$?
	last_out="$out"
	if [ "$rc" -eq "$expected" ]; then
		pass "$desc (exit $rc)"
	else
		fail "$desc: expected exit $expected, got $rc"$'\n'"$out"
	fi
}

echo "test_ai_verify.sh"

run 0 "all units active, stacks running -> OK"

# `make` itself always exits 2 on a failed recipe, regardless of the
# underlying command's own exit status - only "zero or not" survives through
# it, which is all `make upgrade`'s caller (this test, or `make test`) needs.
run 2 "an enabled unit failed -> FAIL, unit named" \
	STATE_hermes_ai=failed SUB_hermes_ai=failed ENABLED_hermes_ai=enabled
case "$last_out" in
*"hermes-ai"*) pass "failed unit is named" ;;
*) fail "expected hermes-ai to be named, got:"$'\n'"$last_out" ;;
esac

run 0 "a disabled unit that is down -> SKIP" \
	STATE_pjm=inactive SUB_pjm=dead ENABLED_pjm=disabled
case "$last_out" in
*"pjm"*SKIP*) pass "disabled unit is skipped" ;;
*) fail "expected pjm to be SKIPped, got:"$'\n'"$last_out" ;;
esac

run 0 "a masked unit that is down -> SKIP" \
	STATE_pjm=inactive SUB_pjm=dead ENABLED_pjm=masked
case "$last_out" in
*"pjm"*SKIP*) pass "masked unit is skipped" ;;
*) fail "expected pjm to be SKIPped, got:"$'\n'"$last_out" ;;
esac

run 0 "a unit not installed -> SKIP" \
	STUB_USER_UNITS="$(printf '%s' "$ALL_UNITS" | sed 's/\baicli-ai\b//')"
case "$last_out" in
*"aicli-ai"*SKIP*"not installed"*) pass "missing unit is skipped as not-installed" ;;
*) fail "expected aicli-ai to be SKIPped as not installed, got:"$'\n'"$last_out" ;;
esac

run 2 "a failed container -> FAIL, project:service named" \
	STUB_SERVICES="svc missing" STUB_RUNNING="svc"
case "$last_out" in
*":missing"*) pass "failed container names project:service" ;;
*) fail "expected a project:missing to be named, got:"$'\n'"$last_out" ;;
esac

[ "$FAILED" = "0" ] && echo "OK" || echo "FAILURES"
exit "$FAILED"
