#!/usr/bin/env bash
# Stub `docker` for test_compose_verify.sh. Never touches the real daemon.
# Scenario comes from env vars:
#   STUB_SERVICES   - space-separated service names (`compose config --services`)
#   STUB_RUNNING    - services that have a container at all (`compose ps -q`)
#   STUB_UNHEALTHY  - services whose container health is "unhealthy"
#   STUB_INFO_OK    - "0" makes `docker info` fail (daemon unreachable)
set -u

if [ "$1" = "info" ]; then
	[ "${STUB_INFO_OK:-1}" = "1" ] && exit 0 || exit 1
fi

if [ "$1" = "inspect" ]; then
	fmt="$3"
	cid="${4:-}"
	svc="${cid#cid-}"
	case "$fmt" in
	*State.Status*)
		echo "running"
		;;
	*Health*)
		if printf '%s\n' "${STUB_UNHEALTHY:-}" | grep -qw "$svc"; then
			echo "unhealthy"
		else
			echo "healthy"
		fi
		;;
	esac
	exit 0
fi

if [ "$1" = "compose" ]; then
	shift
	args=("$@")
	sub=""
	for a in "${args[@]}"; do
		case "$a" in
		config) sub=config ;;
		ps) sub=ps ;;
		esac
	done
	if [ "$sub" = "config" ]; then
		printf '%s\n' $STUB_SERVICES
		exit 0
	fi
	if [ "$sub" = "ps" ]; then
		last="${args[${#args[@]}-1]}"
		if [ "$last" != "-q" ] && [ "$last" != "ps" ]; then
			if printf '%s\n' "${STUB_RUNNING:-}" | grep -qw "$last"; then
				echo "cid-$last"
			fi
			exit 0
		fi
		for s in ${STUB_RUNNING:-}; do echo "cid-$s"; done
		exit 0
	fi
	exit 1
fi

exit 1
