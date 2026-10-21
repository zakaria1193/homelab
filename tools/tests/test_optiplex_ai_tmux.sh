#!/usr/bin/env bash
# Exercises tools/optiplex-ai-tmux.sh's binary lookup against a fake aicli
# config and the fake CLI in aicli's repo (tests/fake_cli/), never a
# real `claude`/`agy`. See ticket homelab-0013.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SCRIPT="$HERE/../optiplex-ai-tmux.sh"
export AICLI_DIR="${AICLI_DIR:-$(dirname "$REPO_ROOT")/aicli}"
FAKE_CLI="$AICLI_DIR/tests/fake_cli"
if [ ! -d "$FAKE_CLI" ]; then
	echo "optiplex-ai-tmux.sh: SKIP (aicli not checked out at $AICLI_DIR)"
	exit 0
fi
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }

# `which` only needs each tool's `bin` - no model names here, so this test
# config stays clear of criterion 1 ("aicli.toml is the only place that
# names a model").
CONFIG="$TMP_DIR/aicli.toml"
cat >"$CONFIG" <<EOF
[claude]
bin = "$FAKE_CLI/fake-claude"

[agy]
bin = "$FAKE_CLI/fake-agy"
EOF

echo "optiplex-ai-tmux.sh"

# Non-TTY stdin (fast-path check 2) skips tmux entirely and execs the fake
# binary resolved through aicli, so this never needs a tmux server.
out="$(echo | AICLI_CONFIG="$CONFIG" "$SCRIPT" claude -p hello 2>&1)"
rc=$?
if [ "$rc" -eq 0 ] && [ "$out" = "[\"$FAKE_CLI/fake-claude\", \"-p\", \"hello\"]" ]; then
	pass "claude resolves through aicli and runs the fake binary"
else
	fail "claude resolve: expected the fake binary's argv, got (exit $rc): $out"
fi

out="$(echo | AICLI_CONFIG="$CONFIG" "$SCRIPT" agy -p world 2>&1)"
rc=$?
if [ "$rc" -eq 0 ] && [ "$out" = "[\"$FAKE_CLI/fake-agy\", \"-p\", \"world\"]" ]; then
	pass "agy resolves through aicli and runs the fake binary"
else
	fail "agy resolve: expected the fake binary's argv, got (exit $rc): $out"
fi

# aicli can't find the binary -> the wrapper prints aicli's own message and
# exits 1, never execing itself.
BAD_CONFIG="$TMP_DIR/bad-aicli.toml"
cat >"$BAD_CONFIG" <<EOF
[claude]
bin = "$TMP_DIR/missing"

[agy]
bin = "$TMP_DIR/missing"
EOF

out="$(echo | AICLI_CONFIG="$BAD_CONFIG" PATH=/usr/bin "$SCRIPT" claude -p hello 2>&1)"
rc=$?
if [ "$rc" -ne 0 ] && echo "$out" | grep -q "claude CLI not found"; then
	pass "missing binary: wrapper exits non-zero with aicli's own message"
else
	fail "missing binary: expected a non-zero exit with aicli's error, got (exit $rc): $out"
fi

if [ "$FAILED" -eq 0 ]; then
	echo "OK"
else
	echo "FAILED"
fi
exit "$FAILED"
