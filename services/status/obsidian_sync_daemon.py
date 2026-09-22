#!/usr/bin/env python3
"""Obsidian Sync Keeper Daemon.

Monitors Obsidian Remotely Save Dropbox sync.

NOTE: When the Obsidian desktop application is running, it already has an internal
periodic backup running every 30 minutes. While the desktop app is running, this
keeper service effectively stands by and does nothing.

When the desktop app is NOT running (e.g. closed, headless, background), this
service steps in and triggers an hourly sync if no sync has occurred in the last hour.

Logs are written with timestamps to stdout so systemd journalctl displays them
in the Homelab cockpit just like other services.
"""

import argparse
import datetime
import os
import signal
import sys
import time

# Ensure ideas_manager can be imported from current directory
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from ideas_manager import dispatch_obsidian_sync, get_sync_state, is_obsidian_running

DEFAULT_INTERVAL_SEC = 3600  # 1 hour
POLL_SLEEP_SEC = 30          # Check state every 30s
HEARTBEAT_INTERVAL_SEC = 1800 # Heartbeat every 30 mins


def log(level, message):
    """Format and print log message with ISO timestamp and flush stdout."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] [{level}] {message}", flush=True)


def format_duration(seconds):
    """Format seconds into readable string (e.g., '14m 20s', '1h 05m')."""
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem_sec = seconds % 60
    if minutes < 60:
        return f"{minutes}m {rem_sec:02d}s"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min:02d}m"


def print_status(interval_sec):
    """Print human-readable sync status and exit."""
    state = get_sync_state()
    last_ts = state.get("last_sync_timestamp", 0.0)
    last_trig = state.get("last_trigger", "never")
    last_time = state.get("last_sync_time") or "Never"
    status_str = state.get("status", "unknown")
    detail = state.get("detail", "")
    app_running = is_obsidian_running()

    now = time.time()
    elapsed = now - last_ts if last_ts > 0 else 0
    next_due_in = max(0, interval_sec - elapsed) if last_ts > 0 else 0

    print("Obsidian Sync Status:")
    print(f"  Desktop App:       {'Running (internal 30m auto-sync active)' if app_running else 'Not running (closed)'}")
    print(f"  Keeper Mode:       {'Idle / Standing by (app manages periodic sync)' if app_running else 'Active (triggers hourly sync if idle > 1h)'}")
    print(f"  Last Sync Time:    {last_time}")
    print(f"  Last Trigger:      {last_trig}")
    print(f"  Status:            {status_str}")
    if detail:
        print(f"  Detail:            {detail}")
    if last_ts > 0:
        print(f"  Time Since Sync:   {format_duration(elapsed)} ago")
        if not app_running:
            if elapsed >= interval_sec:
                print(f"  Next Keeper Sync:  DUE NOW (over {format_duration(interval_sec)} threshold)")
            else:
                print(f"  Next Keeper Sync:  in ~{format_duration(next_due_in)}")
    else:
        print("  Time Since Sync:   Never")


def run_daemon(interval_sec):
    """Main daemon loop. Stands by when Obsidian is running; triggers hourly when closed."""
    running = True

    def _sig_handler(sig, frame):
        nonlocal running
        signame = signal.Signals(sig).name
        log("SHUTDOWN", f"Obsidian sync keeper received {signame}. Stopping cleanly.")
        running = False

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)

    log("STARTUP", f"Obsidian Sync Keeper started. Hourly threshold: {format_duration(interval_sec)} (poll every {POLL_SLEEP_SEC}s).")

    state = get_sync_state()
    last_seen_ts = state.get("last_sync_timestamp", 0.0)
    last_heartbeat = time.time()
    obsidian_was_running = None

    while running:
        try:
            app_running = is_obsidian_running()
            now = time.time()
            state = get_sync_state()
            last_ts = state.get("last_sync_timestamp", 0.0)

            # Detect state transition of the Obsidian desktop app
            if app_running != obsidian_was_running:
                if app_running:
                    log("IDLE", "Obsidian desktop app is running (handles its own 30m periodic backup). Keeper is standing by / idle.")
                else:
                    log("ACTIVE", "Obsidian desktop app is closed. Hourly sync keeper is now actively monitoring.")
                obsidian_was_running = app_running
                last_heartbeat = now

            # Detect external sync (e.g. idea dropped via web page)
            if last_ts > last_seen_ts:
                elapsed_since_ext = now - last_ts
                log("EXTERNAL", f"Sync recorded via '{state.get('last_trigger')}' at {state.get('last_sync_time')}.")
                last_seen_ts = last_ts

            if app_running:
                # Desktop app handles periodic backup every 30m. Effectively do nothing!
                if (now - last_heartbeat) >= HEARTBEAT_INTERVAL_SEC:
                    log("HEARTBEAT", "Obsidian desktop app running (internal 30m auto-sync active). Keeper standing by.")
                    last_heartbeat = now
            else:
                # Desktop app is NOT running. We enforce the hourly sync threshold.
                elapsed = now - last_ts if last_ts > 0 else float("inf")

                if elapsed >= interval_sec:
                    if last_ts > 0:
                        log("TRIGGER", f"Obsidian app closed & threshold reached ({format_duration(elapsed)} elapsed >= {format_duration(interval_sec)}, last: '{state.get('last_trigger')}'). Triggering hourly sync...")
                    else:
                        log("TRIGGER", "Obsidian app closed & no previous sync recorded. Triggering initial sync...")

                    res = dispatch_obsidian_sync(reason="hourly_daemon")
                    if res.get("ok"):
                        log("OK", f"Hourly sync successfully dispatched ({res.get('detail', 'OK')}). Next check in {format_duration(interval_sec)}.")
                    else:
                        log("WARN", f"Sync dispatch reported: {res.get('detail', 'unknown error')}. Will retry on next cycle.")

                    state = get_sync_state()
                    last_seen_ts = state.get("last_sync_timestamp", now)
                    last_heartbeat = now
                else:
                    # Heartbeat when closed
                    if (now - last_heartbeat) >= HEARTBEAT_INTERVAL_SEC:
                        due_in = max(0, interval_sec - elapsed)
                        log("HEARTBEAT", f"Obsidian app closed. Last sync was {format_duration(elapsed)} ago (via '{state.get('last_trigger')}'). Next hourly sync in ~{format_duration(due_in)}.")
                        last_heartbeat = now

            # Sleep in 1-second increments for clean signal termination
            for _ in range(POLL_SLEEP_SEC):
                if not running:
                    break
                time.sleep(1)

        except Exception as exc:
            log("ERROR", f"Unexpected error in daemon loop: {exc}")
            time.sleep(POLL_SLEEP_SEC)

    log("EXIT", "Obsidian sync keeper daemon stopped.")


def main():
    parser = argparse.ArgumentParser(description="Obsidian Remotely Save sync keeper daemon")
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("OBSIDIAN_SYNC_INTERVAL_SEC", DEFAULT_INTERVAL_SEC)),
        help="Inactivity interval in seconds before triggering sync (default: 3600 = 1 hour)",
    )
    parser.add_argument(
        "--sync-now",
        action="store_true",
        help="Trigger an immediate Obsidian sync and exit",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display current sync status and schedule, then exit",
    )

    args = parser.parse_args()

    if args.status:
        print_status(args.interval)
        return

    if args.sync_now:
        log("TRIGGER", "Manual sync requested via --sync-now. Dispatching...")
        res = dispatch_obsidian_sync(reason="manual_cli")
        if res.get("ok"):
            log("OK", f"Sync successfully triggered: {res.get('detail')}")
            sys.exit(0)
        else:
            log("ERROR", f"Sync failed: {res.get('detail')}")
            sys.exit(1)

    run_daemon(args.interval)


if __name__ == "__main__":
    main()
