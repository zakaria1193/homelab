#!/usr/bin/env bash
# Stub `loginctl` for test_common_mk.sh - logs the call and succeeds, so
# `enable-linger` never touches the real session manager.
set -u
if [ -n "${STUB_LOG:-}" ]; then
	printf 'loginctl %s\n' "$*" >>"$STUB_LOG"
fi
exit 0
