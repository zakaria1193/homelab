#!/usr/bin/env bash
# ==============================================================================
# optiplex-ai-tmux.sh - Homelab OptiPlex AI CLI tmux session wrapper
# ==============================================================================
# Ensures that anytime `agy` or `claude` is used interactively on the OptiPlex,
# it runs inside a named tmux session that is visible from the status website
# (http://192.168.1.10:8300 / https://homelab.zakariafadli.com).
#
# Session names follow the homelab cockpit standard:
#   cockpit-<workspace>-<tool> (e.g. cockpit-homelab-agy, cockpit-myrepos-claude)
#
# Non-interactive executions (pipes, redirects, -p, --print, --version, daemons)
# pass straight through to the real binary without spawning a tmux session.
# ==============================================================================

set -e

# Identify which tool was invoked
INVOKED_NAME="$(basename "$0")"
CMD=""
if [ "$INVOKED_NAME" = "agy" ] || [ "$INVOKED_NAME" = "claude" ]; then
    CMD="$INVOKED_NAME"
elif [ "$1" = "agy" ] || [ "$1" = "claude" ]; then
    CMD="$1"
    shift
else
    echo "Usage: $0 [agy|claude] [args...]" >&2
    exit 1
fi

# Locate the real binary (excluding /usr/local/bin to prevent loops)
find_real_bin() {
    local target="$1"
    if [ "$target" = "agy" ]; then
        if [ -x "/home/zfadli/.local/bin/agy" ]; then
            echo "/home/zfadli/.local/bin/agy"
            return 0
        fi
    elif [ "$target" = "claude" ]; then
        if [ -x "/home/zfadli/.npm-global/bin/claude" ]; then
            echo "/home/zfadli/.npm-global/bin/claude"
            return 0
        fi
    fi

    local p
    local old_ifs="$IFS"
    IFS=:
    for p in $PATH; do
        if [ "$p" != "/usr/local/bin" ] && [ "$p" != "/usr/local/sbin" ] && [ -x "$p/$target" ]; then
            IFS="$old_ifs"
            echo "$p/$target"
            return 0
        fi
    done
    IFS="$old_ifs"

    echo "Error: real binary for '$target' not found." >&2
    return 1
}

REAL_BIN="$(find_real_bin "$CMD")"
if [ -z "$REAL_BIN" ] || [ ! -x "$REAL_BIN" ]; then
    echo "Error: unable to resolve underlying executable for '$CMD'." >&2
    exit 1
fi

# Fast-path check 1: Explicit bypass flag --no-tmux
FILTERED_ARGS=()
BYPASS_TMUX=0
for arg in "$@"; do
    if [ "$arg" = "--no-tmux" ]; then
        BYPASS_TMUX=1
    else
        FILTERED_ARGS+=("$arg")
    fi
done

if [ "$BYPASS_TMUX" -eq 1 ]; then
    exec "$REAL_BIN" "${FILTERED_ARGS[@]}"
fi

# Fast-path check 2: Not a terminal (stdin or stdout piped / redirected / background daemon)
if [ ! -t 0 ] || [ ! -t 1 ]; then
    exec "$REAL_BIN" "$@"
fi

# Fast-path check 3: Non-interactive arguments or daemons
for arg in "$@"; do
    case "$arg" in
        -p|--print|--prompt|--remote-control|remote-control|-v|--version|-h|--help|update|changelog)
            exec "$REAL_BIN" "$@"
            ;;
    esac
done

# Fast-path check 4: Already inside a tmux session ($TMUX is set)
if [ -n "$TMUX" ]; then
    # Already inside tmux; rename current window for clarity and pass through
    tmux rename-window "$CMD" 2>/dev/null || true
    exec "$REAL_BIN" "$@"
fi

# Fast-path check 5: tmux not installed
if ! command -v tmux >/dev/null 2>&1; then
    exec "$REAL_BIN" "$@"
fi

# Resolve workspace / session name using homelab services.conf and git root
SESSION_NAME="$(python3 -c '
import os, sys, configparser, subprocess, re

cmd = sys.argv[1]
cwd = os.path.realpath(os.getcwd())
config_path = "/home/zfadli/my_repos/homelab/services/status/services.conf"

def resolve():
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
        if git_root:
            return os.path.basename(git_root)
    except Exception:
        pass

    if os.path.isfile(config_path):
        try:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(config_path)
            status_dir = os.path.dirname(os.path.realpath(config_path))
            repo_root = os.path.dirname(os.path.dirname(status_dir))
            
            candidates = []
            for sec in parser.sections():
                s_dir = parser.get(sec, "dir", fallback="")
                if not s_dir:
                    continue
                if s_dir == ".":
                    abs_dir = repo_root
                elif not os.path.isabs(s_dir):
                    abs_dir = os.path.normpath(os.path.join(repo_root, s_dir))
                else:
                    abs_dir = os.path.normpath(s_dir)
                abs_dir = os.path.realpath(abs_dir)
                if cwd == abs_dir or cwd.startswith(abs_dir + "/"):
                    priority = 10 if parser.get(sec, "group", fallback="") == "AI Sessions" else 0
                    candidates.append((priority, len(abs_dir), sec))
            if candidates:
                candidates.sort(reverse=True)
                return candidates[0][2]
        except Exception:
            pass

    base = os.path.basename(cwd)
    if not base or cwd == os.path.expanduser("~"):
        return "optiplex"
    return base

name = resolve()
clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-") or "default"
print(f"cockpit-{clean}-{cmd}")
' "$CMD")"

if [ -z "$SESSION_NAME" ]; then
    SESSION_NAME="cockpit-optiplex-$CMD"
fi

# Ensure tmux server is ready
if ! tmux has-session 2>/dev/null && [ $? -ne 1 ]; then
    # Start tmux server if it was not running
    systemctl --user start tmux-server 2>/dev/null || sudo systemctl start tmux-server 2>/dev/null || true
fi

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    PANE_CMD="$(tmux list-panes -t "$SESSION_NAME" -F "#{pane_current_command}" 2>/dev/null | head -n 1)"
    if [ "$PANE_CMD" = "agy" ] || [ "$PANE_CMD" = "claude" ] || [ "$PANE_CMD" = "node" ]; then
        # Actively running: attach right into the ongoing session
        echo "⚡ Attaching to active tmux session: $SESSION_NAME"
        exec tmux -u attach-session -t "$SESSION_NAME"
    elif [ "$PANE_CMD" = "zsh" ] || [ "$PANE_CMD" = "bash" ] || [ "$PANE_CMD" = "sh" ]; then
        # Idle at shell prompt: send command and attach
        QUOTED_CMD="$(printf '%q ' "$REAL_BIN" "$@")"
        tmux send-keys -t "$SESSION_NAME" "cd $(printf %q "$PWD") && $QUOTED_CMD" C-m
        echo "⚡ Starting $CMD in existing tmux session: $SESSION_NAME"
        exec tmux -u attach-session -t "$SESSION_NAME"
    else
        # Any other command or state: attach
        echo "⚡ Attaching to tmux session: $SESSION_NAME"
        exec tmux -u attach-session -t "$SESSION_NAME"
    fi
else
    # Create new session in current working directory and run the command directly
    echo "⚡ Spawning $CMD in tmux session: $SESSION_NAME"
    tmux new-session -d -s "$SESSION_NAME" -c "$PWD" "$REAL_BIN" "$@"
    exec tmux -u attach-session -t "$SESSION_NAME"
fi
