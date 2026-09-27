#!/usr/bin/env bash
# Asserts the property tmux-server.service exists for: a cockpit restart must
# not take the shells with it. Runs against the live units on this host.
#
#   ./tests/test_tmux_persistence.sh        # includes the restart check
#   SKIP_RESTART=1 ./tests/...              # ownership checks only
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HERE
TMUX_UNIT="${TMUX_UNIT:-tmux-server}"
COCKPIT_UNIT="${COCKPIT_UNIT:-homelab-status}"
SESSION="cockpit-selftest-$$"
FAILED=0

pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILED=1; }
skip() { printf '  \033[33mSKIP\033[0m %s\n' "$1"; }

sctl() { systemctl "$@" 2>/dev/null || systemctl --user "$@" 2>/dev/null; }

cleanup() { tmux kill-session -t "$SESSION" 2>/dev/null; }
trap cleanup EXIT

echo "tmux session persistence"

command -v tmux >/dev/null 2>&1 || { fail "tmux is not installed"; exit 1; }

# 1. The dedicated unit is what runs the server.
if sctl is-active --quiet "$TMUX_UNIT"; then
	pass "$TMUX_UNIT is active"
else
	fail "$TMUX_UNIT is not active (run 'make tmux-setup')"
	exit 1
fi

# 2. The running server really sits in that unit's cgroup, not the cockpit's.
#    This is the whole point: systemd kills a unit's cgroup on stop.
tmux start-server 2>/dev/null
server_pid="$(sctl show "$TMUX_UNIT" -p MainPID --value)"
if [ -n "${server_pid:-}" ] && [ "$server_pid" != "0" ] \
	&& grep -q "$TMUX_UNIT" "/proc/$server_pid/cgroup" 2>/dev/null; then
	pass "tmux server (pid $server_pid) runs in $TMUX_UNIT's cgroup"
else
	fail "tmux server is not the main process of $TMUX_UNIT"
fi

for pid in $(pgrep -f '^tmux' 2>/dev/null); do
	if grep -q "$COCKPIT_UNIT" "/proc/$pid/cgroup" 2>/dev/null; then
		fail "a tmux process (pid $pid) still lives in $COCKPIT_UNIT's cgroup"
	fi
done

# 3. A session created the way the cockpit creates it.
python3 - "$SESSION" <<'PY'
import sys, os
sys.path.insert(0, os.environ["HERE"])
import tmux_manager
tmux_manager.ensure_session(sys.argv[1], cwd=os.path.expanduser("~"))
PY
if tmux has-session -t "$SESSION" 2>/dev/null; then
	pass "ensure_session() created $SESSION"
else
	fail "ensure_session() did not create $SESSION"
	exit 1
fi

# 4. The cockpit's password must not reach a shell inside that session.
tmux send-keys -t "$SESSION" 'env | grep -c "^STATUS_PASSWORD=" > /tmp/'"$SESSION"'.env 2>&1' C-m
sleep 2
if [ "$(cat "/tmp/$SESSION.env" 2>/dev/null)" = "0" ]; then
	pass "STATUS_PASSWORD is not in the session environment"
else
	fail "STATUS_PASSWORD leaked into the session environment"
fi
rm -f "/tmp/$SESSION.env"

# 5. The property itself: restart the cockpit, session survives.
if [ "${SKIP_RESTART:-0}" = "1" ]; then
	skip "cockpit restart (SKIP_RESTART=1)"
else
	if sudo -n true 2>/dev/null; then
		sudo systemctl restart "$COCKPIT_UNIT"
	else
		systemctl --user restart "$COCKPIT_UNIT"
	fi
	sleep 3
	if tmux has-session -t "$SESSION" 2>/dev/null; then
		pass "$SESSION survived a restart of $COCKPIT_UNIT"
	else
		fail "$SESSION died with $COCKPIT_UNIT"
	fi
	# And the shell in it is still usable, not just the session record.
	tmux send-keys -t "$SESSION" 'echo alive-$$ > /tmp/'"$SESSION"'.alive' C-m
	sleep 2
	if grep -q '^alive-' "/tmp/$SESSION.alive" 2>/dev/null; then
		pass "the shell inside it still answers"
	else
		fail "the session exists but its shell is gone"
	fi
	rm -f "/tmp/$SESSION.alive"
fi

# 6. Reachable over SSH means: default socket, no -L needed.
if tmux -S "${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/default" has-session -t "$SESSION" 2>/dev/null; then
	pass "session lives on the default socket (plain 'tmux attach' works over SSH)"
else
	fail "session is not on the default socket"
fi

[ "$FAILED" = "0" ] && echo "OK" || echo "FAILURES"
exit "$FAILED"
