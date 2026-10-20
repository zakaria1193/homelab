#!/usr/bin/env bash
# Stub `systemctl` for test_ai_verify.sh. Never touches the real systemd.
# Answers only what services/AI/Makefile's `verify` asks: `cat <unit>` (does
# it exist in this scope) and `show -p <Prop> --value <unit>`.
#
# Scenario comes from env vars:
#   STUB_USER_UNITS    - space-separated units that exist in user scope
#   STUB_SYSTEM_UNITS  - space-separated units that exist in system scope
#   STATE_<unit>       - ActiveState for that unit (default: inactive);
#   SUB_<unit>         - SubState for that unit (default: dead)
#   ENABLED_<unit>     - UnitFileState for that unit (default: enabled)
# <unit> in the STATE_/SUB_/ENABLED_ names has every `-` turned into `_`,
# since make/shell variable names cannot contain `-`.
set -u

scope_user=0
args=()
for a in "$@"; do
	if [ "$a" = "--user" ]; then
		scope_user=1
	else
		args+=("$a")
	fi
done

cmd="${args[0]:-}"

case "$cmd" in
cat)
	unit="${args[1]:-}"
	if [ "$scope_user" = 1 ]; then
		list="${STUB_USER_UNITS:-}"
	else
		list="${STUB_SYSTEM_UNITS:-}"
	fi
	for u in $list; do
		[ "$u" = "$unit" ] && exit 0
	done
	exit 1
	;;
show)
	prop=""
	unit=""
	i=1
	n=${#args[@]}
	while [ "$i" -lt "$n" ]; do
		case "${args[$i]}" in
		-p)
			i=$((i + 1))
			prop="${args[$i]:-}"
			;;
		--value) : ;;
		*) unit="${args[$i]}" ;;
		esac
		i=$((i + 1))
	done
	safe="$(printf '%s' "$unit" | tr '-' '_')"
	case "$prop" in
	ActiveState)
		var="STATE_$safe"
		;;
	SubState)
		var="SUB_$safe"
		;;
	UnitFileState)
		var="ENABLED_$safe"
		;;
	*)
		exit 0
		;;
	esac
	eval "val=\"\${${var}:-}\""
	case "$prop" in
	ActiveState) echo "${val:-inactive}" ;;
	SubState) echo "${val:-dead}" ;;
	UnitFileState) echo "${val:-enabled}" ;;
	esac
	exit 0
	;;
*)
	exit 1
	;;
esac
