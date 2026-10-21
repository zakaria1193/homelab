#!/usr/bin/env bash
# Stub `sudo` for test_common_mk.sh. Never prompts, never touches the real
# system - that is the whole point: a bare `sudo` in real life can hang on a
# password on a box with no cached credential, which is exactly the bug this
# ticket fixes, so the stub must never give a recipe a reason to rely on that
# hang being survivable.
#
# SUDO_N_OK=1 makes every call (with or without a leading -n) succeed and
# exec the wrapped command; SUDO_N_OK=0 (default) fails immediately, the way
# real sudo does non-interactively with no cached credential and no tty.
set -u

[ "${1:-}" = "-n" ] && shift

if [ -n "${STUB_LOG:-}" ]; then
	printf 'sudo %s\n' "$*" >>"$STUB_LOG"
fi

if [ "${SUDO_N_OK:-0}" != "1" ]; then
	echo "sudo: a password is required" >&2
	exit 1
fi

exec "$@"
