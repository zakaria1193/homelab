#!/usr/bin/env bash
# Stub `systemctl` for test_common_mk.sh. Never touches the real systemd.
#
# Scope comes from a leading --user flag (stripped before the case below).
# "Is this unit on?" comes from env lists (space-separated unit names):
#   STUB_USER_ACTIVE / STUB_SYSTEM_ACTIVE    - is-active succeeds
#   STUB_USER_ENABLED / STUB_SYSTEM_ENABLED  - is-enabled succeeds
# Every call is appended to $STUB_LOG (one line), so the test can assert
# which scope and command a target actually reached.
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
	printf 'systemctl %s %s\n' "$scope" "${args[*]:-}" >>"$STUB_LOG"
fi

member() {
	local needle="$1"
	shift
	for w in "$@"; do
		[ "$w" = "$needle" ] && return 0
	done
	return 1
}

cmd="${args[0]:-}"
last="${args[*]: -1}"

case "$cmd" in
daemon-reload | enable | disable | stop | restart)
	exit 0
	;;
status)
	echo "(stub status for $last)"
	exit 0
	;;
is-active)
	if [ "$scope" = user ]; then
		member "$last" ${STUB_USER_ACTIVE:-} && exit 0 || exit 3
	else
		member "$last" ${STUB_SYSTEM_ACTIVE:-} && exit 0 || exit 3
	fi
	;;
is-enabled)
	if [ "$scope" = user ]; then
		member "$last" ${STUB_USER_ENABLED:-} && exit 0 || exit 1
	else
		member "$last" ${STUB_SYSTEM_ENABLED:-} && exit 0 || exit 1
	fi
	;;
list-unit-files)
	exit 1
	;;
*)
	exit 1
	;;
esac
