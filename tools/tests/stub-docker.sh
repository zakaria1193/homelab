#!/usr/bin/env bash
# Stub `docker` for test_compose_verify.sh, test_docker_stacks_prune_gate.sh
# and test_compose_upgrade.sh. Never touches the real daemon.
# Scenario comes from env vars:
#   STUB_SERVICES   - space-separated service names (`compose config --services`)
#   STUB_RUNNING    - services that have a container at all (`compose ps -q`)
#   STUB_UNHEALTHY  - services whose container health is "unhealthy"
#   STUB_EXITED     - services whose container exists but has exited; like
#                     the real docker, `compose ps` lists them only with -a
#   STUB_INFO_OK    - "0" makes `docker info` fail (daemon unreachable)
#   STUB_PRUNE_LOG  - if set, `docker image prune -f` appends a line to this
#                     file, so a test can assert whether it was called at all
#   STUB_CALL_LOG   - if set, `compose pull` and `compose up -d` each append
#                     a line ("pull" / "up") to this file
#   STUB_PULL_OK    - "0" makes `compose pull` fail; default success
set -u

if [ "$1" = "info" ]; then
	[ "${STUB_INFO_OK:-1}" = "1" ] && exit 0 || exit 1
fi

if [ "$1" = "image" ] && [ "${2:-}" = "prune" ]; then
	[ -n "${STUB_PRUNE_LOG:-}" ] && echo "called" >>"$STUB_PRUNE_LOG"
	echo "Total reclaimed space: 0B"
	exit 0
fi

if [ "$1" = "inspect" ]; then
	fmt="$3"
	cid="${4:-}"
	svc="${cid#cid-}"
	case "$fmt" in
	*State.Status*)
		if printf '%s\n' "${STUB_EXITED:-}" | grep -qw "$svc"; then
			echo "exited"
		else
			echo "running"
		fi
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
	all=0
	for a in "${args[@]}"; do
		case "$a" in
		config) sub=config ;;
		ps) sub=ps ;;
		pull) sub=pull ;;
		up) sub=up ;;
		-a) all=1 ;;
		esac
	done
	listed="${STUB_RUNNING:-}"
	[ "$all" = "1" ] && listed="$listed ${STUB_EXITED:-}"
	if [ "$sub" = "config" ]; then
		printf '%s\n' $STUB_SERVICES
		exit 0
	fi
	if [ "$sub" = "pull" ]; then
		[ -n "${STUB_CALL_LOG:-}" ] && echo "pull" >>"$STUB_CALL_LOG"
		[ "${STUB_PULL_OK:-1}" = "1" ] && exit 0 || exit 1
	fi
	if [ "$sub" = "up" ]; then
		[ -n "${STUB_CALL_LOG:-}" ] && echo "up" >>"$STUB_CALL_LOG"
		exit 0
	fi
	if [ "$sub" = "ps" ]; then
		last="${args[${#args[@]}-1]}"
		if [ "$last" != "-q" ] && [ "$last" != "ps" ]; then
			if printf '%s\n' $listed | grep -qx "$last"; then
				echo "cid-$last"
			fi
			exit 0
		fi
		for s in $listed; do echo "cid-$s"; done
		exit 0
	fi
	exit 1
fi

exit 1
