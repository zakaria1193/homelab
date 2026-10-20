#!/usr/bin/env bash
# Exercises the real services/AI/Makefile `upgrade` target inside a stub repo
# tree: stub sub-service Makefiles (ok or fail, picked by $FAIL_LIST), a stub
# tools/docker-stacks-prune-gate.sh (always "running", so the closing verify
# never depends on real docker/systemd), and a stub tools/slackbot-notify.sh
# that records its own arguments instead of posting anything.
#
# Proves: all sub-upgrades succeed -> exit 0, no Slack call; one fails -> the
# rest still run, the summary names it, exactly one `--status warn` call to
# #homelab-alerts naming it, exit non-zero; the Slack stub itself failing
# does not change that exit status.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
REAL_AI_MAKEFILE="$REPO_ROOT/services/AI/Makefile"

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

# Directories AI_SERVICE_DIRS walks in services/AI/Makefile that `upgrade`
# itself also calls (pjmAI is deliberately left out of `upgrade`).
SUB_DIRS="hermesAI openhandsAI ai-job-search/daemon arrMcpAI playwrightMcpAI claudeRcAI antigravityRcAI aicliAI"

build_stub_root() {
	local root="$1"
	mkdir -p "$root/services/AI" "$root/services/media" "$root/services/karakeep" \
		"$root/services/status" "$root/tools"
	cp "$REAL_AI_MAKEFILE" "$root/services/AI/Makefile"

	for d in $SUB_DIRS; do
		mkdir -p "$root/services/AI/$d"
		name="$(basename "$d")"
		cat >"$root/services/AI/$d/Makefile" <<MK
.PHONY: upgrade
upgrade:
	@case " \$\$FAIL_LIST " in \\
		*" $name "*) echo "stub $name upgrade: failing"; exit 7 ;; \\
		*) echo "stub $name upgrade: ok" ;; \\
	esac
MK
	done

	for name in media karakeep; do
		cat >"$root/services/$name/Makefile" <<MK
.PHONY: upgrade
upgrade:
	@case " \$\$FAIL_LIST " in \\
		*" $name "*) echo "stub $name upgrade: failing"; exit 7 ;; \\
		*) echo "stub $name upgrade: ok" ;; \\
	esac
MK
	done

	cat >"$root/services/status/Makefile" <<'MK'
.PHONY: test-tokens
test-tokens:
	@echo "stub test-tokens: ok"
MK

	# Always reports everything running, so the closing verify never touches
	# real systemd or docker - that is services/AI's own `verify`, covered by
	# tools/tests/test_ai_verify.sh, not this test.
	cat >"$root/tools/docker-stacks-prune-gate.sh" <<'SH'
#!/usr/bin/env bash
echo "[OK] AI services and Docker stacks upgraded and running"
exit 0
SH
	chmod +x "$root/tools/docker-stacks-prune-gate.sh"

	cat >"$root/tools/slackbot-notify.sh" <<'SH'
#!/usr/bin/env bash
if [ -n "${STUB_SLACK_LOG:-}" ]; then
	printf '%s\n' "$*" >>"$STUB_SLACK_LOG"
fi
[ "${STUB_SLACK_OK:-1}" = "0" ] && exit 3
exit 0
SH
	chmod +x "$root/tools/slackbot-notify.sh"
}

run_upgrade() {
	# run_upgrade <fail-list> <slack-ok 0|1> <call-log-file>
	env -u MAKEFLAGS -u MAKELEVEL \
		FAIL_LIST="$1" STUB_SLACK_OK="$2" STUB_SLACK_LOG="$3" \
		timeout 60 make --no-print-directory -C "$STUB_ROOT/services/AI" upgrade
}

echo "ai-services upgrade report"

# --- all sub-upgrades succeed ---------------------------------------------
STUB_ROOT="$(mktemp -d)"
CALL_LOG="$(mktemp)"
build_stub_root "$STUB_ROOT"
: >"$CALL_LOG"
out="$(run_upgrade "" 1 "$CALL_LOG" 2>&1)"
rc=$?
if [ "$rc" -eq 0 ]; then pass "all succeed -> exit 0"; else fail "all succeed -> expected exit 0, got $rc"$'\n'"$out"; fi
case "$out" in
*"[OK] All sub-upgrades succeeded"*) pass "all succeed -> prints the success line" ;;
*) fail "all succeed -> missing success line:"$'\n'"$out" ;;
esac
if [ -s "$CALL_LOG" ]; then fail "all succeed -> Slack was called unexpectedly: $(cat "$CALL_LOG")"; else pass "all succeed -> no Slack call"; fi
rm -rf "$STUB_ROOT"
rm -f "$CALL_LOG"

# --- one sub-upgrade fails (hermesAI) --------------------------------------
STUB_ROOT="$(mktemp -d)"
CALL_LOG="$(mktemp)"
build_stub_root "$STUB_ROOT"
: >"$CALL_LOG"
out="$(run_upgrade "hermesAI" 1 "$CALL_LOG" 2>&1)"
rc=$?
if [ "$rc" -ne 0 ]; then pass "one fails -> exit non-zero"; else fail "one fails -> expected non-zero exit, got $rc"$'\n'"$out"; fi
case "$out" in
*"stub openhandsAI upgrade: ok"*) pass "one fails -> the rest still ran" ;;
*) fail "one fails -> later sub-upgrades did not run:"$'\n'"$out" ;;
esac
case "$out" in
*"[FAIL]"*"sub-upgrade(s) failed"*"upgrade-hermes"*) pass "one fails -> summary names upgrade-hermes" ;;
*) fail "one fails -> summary does not name upgrade-hermes:"$'\n'"$out" ;;
esac
calls="$(wc -l <"$CALL_LOG" | tr -d ' ')"
if [ "$calls" = "1" ]; then pass "one fails -> exactly one Slack call"; else fail "one fails -> expected exactly one Slack call, got $calls: $(cat "$CALL_LOG")"; fi
slack_args="$(cat "$CALL_LOG")"
case "$slack_args" in
*"#homelab-alerts"*"--status warn"*"upgrade-hermes"*) pass "Slack call is a warn to #homelab-alerts naming upgrade-hermes" ;;
*) fail "Slack call missing expected arguments: $slack_args" ;;
esac
FAIL_ONLY_RC="$rc"
rm -rf "$STUB_ROOT"
rm -f "$CALL_LOG"

# --- same failure, but the Slack stub itself fails -------------------------
STUB_ROOT="$(mktemp -d)"
CALL_LOG="$(mktemp)"
build_stub_root "$STUB_ROOT"
: >"$CALL_LOG"
out="$(run_upgrade "hermesAI" 0 "$CALL_LOG" 2>&1)"
rc=$?
if [ "$rc" -eq "$FAIL_ONLY_RC" ]; then
	pass "Slack stub failing -> same exit status ($rc) as without it"
else
	fail "Slack stub failing -> exit status changed: $FAIL_ONLY_RC -> $rc"$'\n'"$out"
fi
case "$out" in
*"[WARN]"*) pass "Slack stub failing -> prints a [WARN] line and carries on" ;;
*) fail "Slack stub failing -> missing a [WARN] line:"$'\n'"$out" ;;
esac
rm -rf "$STUB_ROOT"
rm -f "$CALL_LOG"

[ "$FAILED" = "0" ] && echo "OK" || echo "FAILURES"
exit "$FAILED"
