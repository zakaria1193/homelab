#!/usr/bin/env bash
# Stub `journalctl` for test_common_mk.sh - logs the call and returns at
# once, even with -f, so a test never blocks following a real journal.
set -u
scope=system
args=()
for a in "$@"; do
	if [ "$a" = "--user" ]; then
		scope=user
	else
		args+=("$a")
	fi
done
if [ -n "${STUB_LOG:-}" ]; then
	printf 'journalctl %s %s\n' "$scope" "${args[*]:-}" >>"$STUB_LOG"
fi
exit 0
