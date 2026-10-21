#!/usr/bin/env bash
# Exercises services/common.mk's systemd-* targets against a throwaway
# fixture Makefile, with stub systemctl/sudo/journalctl/loginctl first on
# PATH - never the real systemd, never a real sudo prompt. See ticket
# homelab-0017.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
COMMON_MK="$ROOT/services/common.mk"

# Makefiles already moved onto common.mk - the static bare-sudo check below
# covers this list and common.mk itself. Each later plan item that moves a
# service over adds its Makefile here.
MIGRATED_MAKEFILES=(
	"$COMMON_MK"
	"$ROOT/services/AI/aicliAI/Makefile"
	"$ROOT/services/status/Makefile"
	"$ROOT/services/AI/arrMcpAI/Makefile"
	"$ROOT/services/AI/openhandsAI/Makefile"
	"$ROOT/services/AI/playwrightMcpAI/Makefile"
	"$ROOT/services/AI/hermesAI/Makefile"
	"$ROOT/services/AI/claudeRcAI/Makefile"
	"$ROOT/services/supabase-keepalive/Makefile"
	"$ROOT/services/media-autopilot/Makefile"
	"$ROOT/services/media/Makefile"
)

BIN_DIR="$(mktemp -d)"
EMPTY_BIN_DIR="$(mktemp -d)"
WORKDIR="$(mktemp -d)"
WORKDIR_T="$(mktemp -d)"
WORKDIR_B="$(mktemp -d)"
SYSTEM_DIR="$(mktemp -d)"
USER_DIR="$(mktemp -d)"
STUB_LOG="$(mktemp)"
trap 'rm -rf "$BIN_DIR" "$EMPTY_BIN_DIR" "$WORKDIR" "$WORKDIR_T" "$WORKDIR_B" "$SYSTEM_DIR" "$USER_DIR" "$STUB_LOG"' EXIT

cp "$HERE/stub-systemctl.sh" "$BIN_DIR/systemctl"
cp "$HERE/stub-sudo.sh" "$BIN_DIR/sudo"
cp "$HERE/stub-journalctl.sh" "$BIN_DIR/journalctl"
cp "$HERE/stub-loginctl.sh" "$BIN_DIR/loginctl"
chmod +x "$BIN_DIR"/*

cat >"$WORKDIR/fixture.service.template" <<'EOF'
[Unit]
Description=fixture

[Service]
{{USER_LINE}}
WorkingDirectory={{CURR_DIR}}
Environment="PATH={{PATH_VAL}}"
ExecStart=/bin/true

[Install]
WantedBy=default.target
EOF

cat >"$WORKDIR/Makefile" <<EOF
SERVICE_NAME = fixture-svc
UNIT_TEMPLATE = fixture.service.template
include $COMMON_MK

env-setup:
	@:
EOF

# ------------------------------------------------------------- timer fixture
cat >"$WORKDIR_T/fixture-timer.service.template" <<'EOF'
[Unit]
Description=fixture timer service

[Service]
Type=oneshot
WorkingDirectory={{CURR_DIR}}
Environment="PATH={{PATH_VAL}}"
ExecStart=/bin/true

[Install]
WantedBy=default.target
EOF

cat >"$WORKDIR_T/fixture-timer.timer.template" <<'EOF'
[Unit]
Description=fixture timer

[Timer]
OnBootSec=1min
Unit=fixture-timer.service

[Install]
WantedBy=timers.target
EOF

cat >"$WORKDIR_T/Makefile" <<EOF
TIMER_UNIT = fixture-timer
include $COMMON_MK

env-setup:
	@:
EOF

# --------------------------------------------------- combined fixture (both)
cp "$WORKDIR/fixture.service.template" "$WORKDIR_B/fixture.service.template"
cp "$WORKDIR_T/fixture-timer.service.template" "$WORKDIR_B/fixture-timer-b.service.template"
cp "$WORKDIR_T/fixture-timer.timer.template" "$WORKDIR_B/fixture-timer-b.timer.template"

cat >"$WORKDIR_B/Makefile" <<EOF
SERVICE_NAME = fixture-svc
UNIT_TEMPLATE = fixture.service.template
TIMER_UNIT = fixture-timer-b
include $COMMON_MK

env-setup:
	@:
EOF

FAILED=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() {
	printf '  \033[31mFAIL\033[0m %s\n' "$1"
	FAILED=1
}

# mk <target> [env assignments...] - runs the fixture Makefile's target with
# the stub bin dir first on PATH and a fresh (truncated) stub log; sets
# $out and $code for the caller to assert on.
mk() {
	local target="$1"
	shift
	: >"$STUB_LOG"
	rm -f "$WORKDIR/fixture-svc.service"
	out="$(env PATH="$BIN_DIR:$PATH" STUB_LOG="$STUB_LOG" \
		SYSTEM_UNIT_DIR="$SYSTEM_DIR" USER_UNIT_DIR="$USER_DIR" \
		"$@" make -C "$WORKDIR" --no-print-directory "$target" 2>&1)"
	code=$?
	log="$(cat "$STUB_LOG")"
}

reset_dirs() {
	rm -f "$SYSTEM_DIR"/fixture-svc.service "$USER_DIR"/fixture-svc.service
}

# mkt <target> [env assignments...] - same as mk(), against the timer fixture.
mkt() {
	local target="$1"
	shift
	: >"$STUB_LOG"
	rm -f "$WORKDIR_T/fixture-timer.service" "$WORKDIR_T/fixture-timer.timer"
	out="$(env PATH="$BIN_DIR:$PATH" STUB_LOG="$STUB_LOG" \
		SYSTEM_UNIT_DIR="$SYSTEM_DIR" USER_UNIT_DIR="$USER_DIR" \
		"$@" make -C "$WORKDIR_T" --no-print-directory "$target" 2>&1)"
	code=$?
	log="$(cat "$STUB_LOG")"
}

reset_dirs_t() {
	rm -f "$SYSTEM_DIR"/fixture-timer.service "$SYSTEM_DIR"/fixture-timer.timer \
	      "$USER_DIR"/fixture-timer.service "$USER_DIR"/fixture-timer.timer
}

# mkb <target> [env assignments...] - same as mk(), against the combined
# (service + timer in one include) fixture.
mkb() {
	local target="$1"
	shift
	: >"$STUB_LOG"
	rm -f "$WORKDIR_B/fixture-svc.service" "$WORKDIR_B/fixture-timer-b.service" "$WORKDIR_B/fixture-timer-b.timer"
	out="$(env PATH="$BIN_DIR:$PATH" STUB_LOG="$STUB_LOG" \
		SYSTEM_UNIT_DIR="$SYSTEM_DIR" USER_UNIT_DIR="$USER_DIR" \
		"$@" make -C "$WORKDIR_B" --no-print-directory "$target" 2>&1)"
	code=$?
	log="$(cat "$STUB_LOG")"
}

reset_dirs_b() {
	rm -f "$SYSTEM_DIR"/fixture-svc.service "$USER_DIR"/fixture-svc.service \
	      "$SYSTEM_DIR"/fixture-timer-b.service "$SYSTEM_DIR"/fixture-timer-b.timer \
	      "$USER_DIR"/fixture-timer-b.service "$USER_DIR"/fixture-timer-b.timer
}

# ---------------------------------------------------------- systemd-restart
reset_dirs
mk systemd-restart STUB_USER_ENABLED=fixture-svc
if [ "$code" -eq 0 ] && grep -q '^systemctl user restart fixture-svc$' <<<"$log" && ! grep -q sudo <<<"$log"; then
	pass "systemd-restart: user unit enabled -> user restart, no sudo"
else
	fail "systemd-restart: user unit enabled -> user restart, no sudo (exit=$code log=[$log])"
fi

reset_dirs
mk systemd-restart STUB_USER_ENABLED=fixture-svc STUB_USER_ACTIVE=
if [ "$code" -eq 0 ] && grep -q '^systemctl user restart fixture-svc$' <<<"$log" && ! grep -q sudo <<<"$log"; then
	pass "systemd-restart: crashed but enabled user unit -> user restart"
else
	fail "systemd-restart: crashed but enabled user unit -> user restart (exit=$code log=[$log])"
fi

reset_dirs
mk systemd-restart STUB_USER_ENABLED= SUDO_N_OK=1
if [ "$code" -eq 0 ] && grep -q '^sudo systemctl restart fixture-svc$' <<<"$log"; then
	pass "systemd-restart: no user unit -> sudo -n systemctl restart"
else
	fail "systemd-restart: no user unit -> sudo -n systemctl restart (exit=$code log=[$log])"
fi

reset_dirs
mk systemd-restart STUB_USER_ENABLED= SUDO_N_OK=0
if [ "$code" -ne 0 ]; then
	pass "systemd-restart: no sudo and no user unit -> fails fast"
else
	fail "systemd-restart: no sudo and no user unit -> fails fast (exit=$code log=[$log])"
fi

# --------------------------------------------------- systemd-restart-if-installed
reset_dirs
mk systemd-restart-if-installed STUB_USER_ENABLED=fixture-svc
if [ "$code" -eq 0 ] && grep -q '^systemctl user restart fixture-svc$' <<<"$log"; then
	pass "systemd-restart-if-installed: enabled in user scope -> user restart"
else
	fail "systemd-restart-if-installed: enabled in user scope -> user restart (exit=$code log=[$log])"
fi

reset_dirs
mk systemd-restart-if-installed STUB_USER_ENABLED= STUB_SYSTEM_ENABLED=fixture-svc SUDO_N_OK=1
if [ "$code" -eq 0 ] && grep -q '^sudo systemctl restart fixture-svc$' <<<"$log"; then
	pass "systemd-restart-if-installed: enabled in system scope only -> sudo restart"
else
	fail "systemd-restart-if-installed: enabled in system scope only -> sudo restart (exit=$code log=[$log])"
fi

reset_dirs
mk systemd-restart-if-installed STUB_USER_ENABLED= STUB_SYSTEM_ENABLED=
if [ "$code" -eq 0 ] && ! grep -q restart <<<"$log"; then
	pass "systemd-restart-if-installed: not installed anywhere -> exit 0, no restart"
else
	fail "systemd-restart-if-installed: not installed anywhere -> exit 0, no restart (exit=$code log=[$log])"
fi

# ----------------------------------------------------------- systemd-logs
reset_dirs
mk systemd-logs STUB_USER_ENABLED=fixture-svc
if [ "$code" -eq 0 ] && grep -q '^journalctl user -u fixture-svc -n 30 -f$' <<<"$log"; then
	pass "systemd-logs: user unit enabled -> user journalctl"
else
	fail "systemd-logs: user unit enabled -> user journalctl (exit=$code log=[$log])"
fi

reset_dirs
mk systemd-logs STUB_USER_ENABLED= SUDO_N_OK=1
if [ "$code" -eq 0 ] && grep -q '^sudo journalctl -u fixture-svc -n 30 -f$' <<<"$log"; then
	pass "systemd-logs: no user unit -> sudo -n journalctl"
else
	fail "systemd-logs: no user unit -> sudo -n journalctl (exit=$code log=[$log])"
fi

# ----------------------------------------------------------- systemd-setup
reset_dirs
mk systemd-setup SUDO_N_OK=1
unit="$SYSTEM_DIR/fixture-svc.service"
if [ "$code" -eq 0 ] && [ -f "$unit" ] && grep -q '^User=' "$unit" \
	&& grep -q "WorkingDirectory=$WORKDIR" "$unit" \
	&& grep -q '^sudo systemctl enable fixture-svc$' <<<"$log" \
	&& grep -q 'system scope' <<<"$out"; then
	pass "systemd-setup: system scope installs to SYSTEM_UNIT_DIR with a User= line"
else
	fail "systemd-setup: system scope (exit=$code out=[$out] log=[$log])"
fi

reset_dirs
mk systemd-setup SUDO_N_OK=0
unit="$USER_DIR/fixture-svc.service"
if [ "$code" -eq 0 ] && [ -f "$unit" ] && ! grep -q '^User=zfadli\|^User=[a-z]' "$unit" \
	&& grep -q '^loginctl enable-linger' <<<"$log" \
	&& grep -q 'user scope' <<<"$out"; then
	pass "systemd-setup: user scope installs to USER_UNIT_DIR with no User= value, runs linger"
else
	fail "systemd-setup: user scope (exit=$code out=[$out] log=[$log] unit=[$(cat "$unit" 2>/dev/null)])"
fi

reset_dirs
: >"$USER_DIR/fixture-svc.service"
mk systemd-setup SUDO_N_OK=1
if [ "$code" -ne 0 ] && grep -qi 'already installed as a user unit' <<<"$out" && ! grep -q enable <<<"$log"; then
	pass "systemd-setup: unit present in user scope -> system setup refuses"
else
	fail "systemd-setup: unit present in user scope -> system setup refuses (exit=$code out=[$out] log=[$log])"
fi
rm -f "$USER_DIR/fixture-svc.service"

reset_dirs
: >"$SYSTEM_DIR/fixture-svc.service"
mk systemd-setup SUDO_N_OK=0
if [ "$code" -ne 0 ] && grep -qi 'already installed as a system unit' <<<"$out" && ! grep -q loginctl <<<"$log"; then
	pass "systemd-setup: unit present in system scope -> user setup refuses"
else
	fail "systemd-setup: unit present in system scope -> user setup refuses (exit=$code out=[$out] log=[$log])"
fi
rm -f "$SYSTEM_DIR/fixture-svc.service"

# ------------------------------------------------------------ systemd-stop
reset_dirs
: >"$USER_DIR/fixture-svc.service"
mk systemd-stop STUB_USER_ENABLED=fixture-svc SUDO_N_OK=1
if [ "$code" -eq 0 ] && [ ! -f "$USER_DIR/fixture-svc.service" ] && grep -q '^systemctl user stop fixture-svc$' <<<"$log"; then
	pass "systemd-stop: stops and removes the user unit, then tries system scope too"
else
	fail "systemd-stop: stops and removes the user unit (exit=$code log=[$log])"
fi

# ------------------------------------------------------------- timer-restart
reset_dirs_t
mkt timer-restart STUB_USER_ENABLED=fixture-timer.timer
if [ "$code" -eq 0 ] && grep -q '^systemctl user restart fixture-timer.timer$' <<<"$log" && ! grep -q sudo <<<"$log"; then
	pass "timer-restart: user timer enabled -> user restart, no sudo"
else
	fail "timer-restart: user timer enabled -> user restart, no sudo (exit=$code log=[$log])"
fi

reset_dirs_t
mkt timer-restart STUB_USER_ENABLED= SUDO_N_OK=1
if [ "$code" -eq 0 ] && grep -q '^sudo systemctl restart fixture-timer.timer$' <<<"$log"; then
	pass "timer-restart: no user timer -> sudo -n systemctl restart"
else
	fail "timer-restart: no user timer -> sudo -n systemctl restart (exit=$code log=[$log])"
fi

reset_dirs_t
mkt timer-restart STUB_USER_ENABLED= SUDO_N_OK=0
if [ "$code" -ne 0 ]; then
	pass "timer-restart: no sudo and no user timer -> fails fast"
else
	fail "timer-restart: no sudo and no user timer -> fails fast (exit=$code log=[$log])"
fi

# --------------------------------------------------------------- timer-logs
reset_dirs_t
mkt timer-logs STUB_USER_ENABLED=fixture-timer.timer
if [ "$code" -eq 0 ] && grep -q '^journalctl user -u fixture-timer.service -n 50 --no-pager$' <<<"$log"; then
	pass "timer-logs: user timer enabled -> user journalctl"
else
	fail "timer-logs: user timer enabled -> user journalctl (exit=$code log=[$log])"
fi

reset_dirs_t
mkt timer-logs STUB_USER_ENABLED= SUDO_N_OK=1
if [ "$code" -eq 0 ] && grep -q '^sudo journalctl -u fixture-timer.service -n 50 --no-pager$' <<<"$log"; then
	pass "timer-logs: no user timer -> sudo -n journalctl"
else
	fail "timer-logs: no user timer -> sudo -n journalctl (exit=$code log=[$log])"
fi

# -------------------------------------------------------------- timer-setup
reset_dirs_t
mkt timer-setup SUDO_N_OK=1
svc="$SYSTEM_DIR/fixture-timer.service"
tmr="$SYSTEM_DIR/fixture-timer.timer"
if [ "$code" -eq 0 ] && [ -f "$svc" ] && [ -f "$tmr" ] \
	&& grep -q "WorkingDirectory=$WORKDIR_T" "$svc" \
	&& grep -q '^sudo systemctl enable --now fixture-timer.timer$' <<<"$log" \
	&& grep -q 'system scope' <<<"$out"; then
	pass "timer-setup: system scope installs both units to SYSTEM_UNIT_DIR"
else
	fail "timer-setup: system scope (exit=$code out=[$out] log=[$log])"
fi

reset_dirs_t
mkt timer-setup SUDO_N_OK=0
svc="$USER_DIR/fixture-timer.service"
tmr="$USER_DIR/fixture-timer.timer"
if [ "$code" -eq 0 ] && [ -f "$svc" ] && [ -f "$tmr" ] \
	&& grep -q '^loginctl enable-linger' <<<"$log" \
	&& grep -q 'user scope' <<<"$out"; then
	pass "timer-setup: user scope installs both units to USER_UNIT_DIR, runs linger"
else
	fail "timer-setup: user scope (exit=$code out=[$out] log=[$log])"
fi

reset_dirs_t
: >"$USER_DIR/fixture-timer.timer"
mkt timer-setup SUDO_N_OK=1
if [ "$code" -ne 0 ] && grep -qi 'already installed as a user timer' <<<"$out" && ! grep -q enable <<<"$log"; then
	pass "timer-setup: unit present in user scope -> system setup refuses"
else
	fail "timer-setup: unit present in user scope -> system setup refuses (exit=$code out=[$out] log=[$log])"
fi
rm -f "$USER_DIR/fixture-timer.timer"

# --------------------------------------------------------------- timer-stop
reset_dirs_t
mkt timer-stop
if [ "$code" -eq 0 ] && ! grep -q disable <<<"$log"; then
	pass "timer-stop: nothing installed -> exit 0, no-op"
else
	fail "timer-stop: nothing installed -> exit 0, no-op (exit=$code log=[$log])"
fi

reset_dirs_t
: >"$USER_DIR/fixture-timer.service"
: >"$USER_DIR/fixture-timer.timer"
mkt timer-stop STUB_USER_ENABLED=fixture-timer.timer SUDO_N_OK=1
if [ "$code" -eq 0 ] && [ ! -f "$USER_DIR/fixture-timer.timer" ] && grep -q '^systemctl user disable --now fixture-timer.timer$' <<<"$log"; then
	pass "timer-stop: stops and removes the user timer, then tries system scope too"
else
	fail "timer-stop: stops and removes the user timer (exit=$code log=[$log])"
fi

# ------------------------------------------------------------- timer-status
reset_dirs_t
mkt timer-status STUB_USER_ENABLED= SUDO_N_OK=0
if [ "$code" -eq 0 ] && grep -qi "is not installed" <<<"$out"; then
	pass "timer-status: not installed -> [INFO] message"
else
	fail "timer-status: not installed -> [INFO] message (exit=$code out=[$out])"
fi

reset_dirs_t
mkt timer-status STUB_USER_ENABLED=fixture-timer.timer
if [ "$code" -eq 0 ] && grep -q '^systemctl user list-timers fixture-timer.timer --all --no-pager$' <<<"$log" \
	&& grep -q '^systemctl user status fixture-timer.timer --no-pager$' <<<"$log"; then
	pass "timer-status: user timer enabled -> user list-timers + status"
else
	fail "timer-status: user timer enabled -> user list-timers + status (exit=$code log=[$log])"
fi

# --------------------------------------------- combined fixture (both blocks)
reset_dirs_b
mkb systemd-restart STUB_USER_ENABLED=fixture-svc
if [ "$code" -eq 0 ] && grep -q '^systemctl user restart fixture-svc$' <<<"$log"; then
	pass "combined fixture: systemd-restart still works alongside a timer block"
else
	fail "combined fixture: systemd-restart (exit=$code log=[$log])"
fi

reset_dirs_b
mkb timer-restart STUB_USER_ENABLED=fixture-timer-b.timer
if [ "$code" -eq 0 ] && grep -q '^systemctl user restart fixture-timer-b.timer$' <<<"$log"; then
	pass "combined fixture: timer-restart works alongside a service block"
else
	fail "combined fixture: timer-restart (exit=$code log=[$log])"
fi

# --------------------------------------------------------- make -n (dry run)
for t in systemd-setup systemd-stop systemd-status systemd-restart systemd-logs systemd-restart-if-installed; do
	out="$(env PATH="$EMPTY_BIN_DIR:/usr/bin:/bin" make -C "$WORKDIR" --no-print-directory -n "$t" 2>&1)"
	code=$?
	if [ "$code" -eq 0 ]; then
		pass "make -n $t: succeeds with no systemctl/sudo/journalctl/loginctl on PATH"
	else
		fail "make -n $t: should succeed without shelling out (exit=$code out=[$out])"
	fi
done

for t in timer-setup timer-stop timer-status timer-restart timer-logs; do
	out="$(env PATH="$EMPTY_BIN_DIR:/usr/bin:/bin" make -C "$WORKDIR_T" --no-print-directory -n "$t" 2>&1)"
	code=$?
	if [ "$code" -eq 0 ]; then
		pass "make -n $t: succeeds with no systemctl/sudo/journalctl/loginctl on PATH"
	else
		fail "make -n $t: should succeed without shelling out (exit=$code out=[$out])"
	fi
done

# ------------------------------------------------- static: no bare sudo ---
py_out="$(python3 "$HERE/check_bare_sudo.py" "${MIGRATED_MAKEFILES[@]}" 2>&1)"
py_code=$?
if [ "$py_code" -eq 0 ]; then
	pass "no bare (non -n, unguarded) sudo in common.mk or migrated Makefiles"
else
	fail "bare sudo found: $py_out"
fi

echo "=========================================="
echo "test_common_mk.sh summary"
echo "=========================================="
if [ "$FAILED" -eq 0 ]; then
	echo "[OK] All checks passed"
else
	echo "[FAIL] One or more checks failed"
fi
exit $FAILED
