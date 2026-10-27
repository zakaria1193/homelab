#!/usr/bin/env bash
# Tests for services/AI's unit registry: each service's own `print-units`
# target, and the top-level Makefile (summary/verify/print-units) that walks
# them. Reads output only - no sudo, no systemctl, no daemon-reload.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_DIR="$(dirname "$HERE")"

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

# A systemd unit name: no empty string, no stray `$` or `(` from an
# unexpanded make expression, no embedded whitespace.
is_valid_unit() {
	case "$1" in
	'' | *'$'* | *'('* | *' '*) return 1 ;;
	*) return 0 ;;
	esac
}

echo "services/AI print-units registry"

# 1. Every present directory prints one or more valid unit names; a directory
#    that is not checked out (e.g. a submodule) is noted, not failed.
while IFS= read -r entry; do
	[ -n "$entry" ] || continue
	dir="${entry%%:*}"
	unit="${entry#*:}"
	if [ -z "$unit" ]; then
		if [ -f "$AI_DIR/$dir/Makefile" ]; then
			fail "$dir: print-units printed nothing"
		else
			echo "  (skip) $dir: not present"
		fi
		continue
	fi
	if is_valid_unit "$unit"; then
		pass "$dir -> $unit"
	else
		fail "$dir -> '$unit' is not a valid unit name"
	fi
done < <(make -s --no-print-directory -C "$AI_DIR" print-units)

# 2. antigravityRcAI's default unit is the one actually installed on the
#    host (antigravity-cli-daemon), not the agy-remote-control the README and
#    CLAUDE.md used to claim.
agy_first="$(make -s --no-print-directory -C "$AI_DIR/antigravityRcAI" print-units | head -1)"
if [ "$agy_first" = "antigravity-cli-daemon" ]; then
	pass "antigravityRcAI default unit is antigravity-cli-daemon"
else
	fail "antigravityRcAI default unit: expected antigravity-cli-daemon, got '$agy_first'"
fi

# 2b. aicliAI prints its single unit, aicli-ai.
aicli_units="$(make -s --no-print-directory -C "$AI_DIR/aicliAI" print-units)"
if [ "$aicli_units" = "aicli-ai" ]; then
	pass "aicliAI prints aicli-ai"
else
	fail "aicliAI print-units: expected 'aicli-ai', got '$aicli_units'"
fi

# 3. claudeRcAI discovers one instance per .env.<name> / .env.<name>.example,
#    each listed once, with .env/.env.example staying the default instance.
# The Makefile includes services/common.mk via a path relative to its own
# directory, so the fixture is laid out at the same depth (TMP/services/AI/claudeRcAI)
# with a copy of common.mk at TMP/services/common.mk.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FIXTURE_RC="$TMP/services/AI/claudeRcAI"
mkdir -p "$FIXTURE_RC"
cp "$AI_DIR/claudeRcAI/Makefile" "$FIXTURE_RC/"
cp "$AI_DIR/../common.mk" "$TMP/services/common.mk"
touch "$FIXTURE_RC/.env.example" "$FIXTURE_RC/.env.alpha.example" "$FIXTURE_RC/.env.beta"
got="$(cd "$FIXTURE_RC" && make -s --no-print-directory print-units 2>&1)"
want="claude-rc-ai
claude-rc-ai-alpha
claude-rc-ai-beta"
if [ "$got" = "$want" ]; then
	pass "claudeRcAI print-units discovers .env.<name> and .env.<name>.example instances"
else
	fail "claudeRcAI print-units: expected:"$'\n'"$want"$'\n'"got:"$'\n'"$got"
fi

# 4. pjmAI is in the top-level registry as pjmAI:pjm.
if make -s --no-print-directory -C "$AI_DIR" print-units | grep -qx "pjmAI:pjm"; then
	pass "pjmAI:pjm is in the top-level registry"
else
	fail "pjmAI:pjm missing from the top-level registry"
fi

# 5. A directory whose print-units prints nothing is a registry bug: verify
#    must report FAIL (no units listed), not SKIP, and exit non-zero.
FIXTURE="$TMP/fixtures/empty-print-units"
mkdir -p "$FIXTURE"
cat >"$FIXTURE/Makefile" <<'EOF'
.PHONY: print-units
print-units:
	@true
EOF
out="$(cd "$AI_DIR" && make -s --no-print-directory verify VERIFY_SETTLE_SECS=0 AUTO_HEAL=0 PRUNE=0 \
	AI_SERVICE_DIRS="$FIXTURE" 2>&1)"
rc=$?
case "$out" in
*"FAIL  (no units listed)"*) pass "empty print-units reads as FAIL (no units listed)" ;;
*) fail "expected 'FAIL  (no units listed)', got:"$'\n'"$out" ;;
esac
if [ "$rc" -ne 0 ]; then
	pass "verify exits non-zero on a registry bug"
else
	fail "verify should have exited non-zero on a registry bug"
fi

echo
if [ "$FAILED" -eq 0 ]; then
	echo "[OK] all tests passed"
else
	echo "[FAIL] one or more tests failed"
fi
exit "$FAILED"
