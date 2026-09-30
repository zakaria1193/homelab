#!/usr/bin/env python3
"""Homelab cockpit.

Serves an always-on HTML page (plus a JSON API) showing the live state of every
homelab service. Deliberately depends on the Python standard library only, so it
stays reproducible on a fresh machine with no package installs.

Checks are declared in services.conf; see that file for the supported keys.
"""

import json
import sys
from http.server import ThreadingHTTPServer

import usage

# Re-exported: the tests and `status_server.<name>` callers predate the split.
from cockpit.auth import parse_jwt_payload, verify_cf_access_jwt  # noqa: F401
from cockpit.config import HOST, PORT, UNKNOWN, UP, USAGE_ENABLED, WARN, DOWN, load_checks  # noqa: F401
from cockpit.handler import StatusHandler, cron_manager  # noqa: F401
from cockpit.probes import check_logfile  # noqa: F401
from cockpit.snapshot import snapshot


def main():
    if "--once" in sys.argv:  # smoke test: print one snapshot and exit
        print(json.dumps(snapshot(), indent=2))
        return
    load_checks()  # fail fast on a broken config
    if USAGE_ENABLED:
        usage.snapshot()  # pre-warm usage cache in background
    server = ThreadingHTTPServer((HOST, PORT), StatusHandler)
    server.daemon_threads = True
    print("[OK] Homelab cockpit on http://%s:%d" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
