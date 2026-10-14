#!/usr/bin/env python3
"""CLI runner to verify all configured homelab API keys, tokens, and credentials."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from cockpit.tokens import test_all, TOKEN_DEFS


def main():
    print("Testing all homelab API tokens and credentials...")
    print("=" * 70)
    results = test_all()

    active_count = 0
    warn_count = 0
    err_count = 0

    for r in results:
        status = r.get("status", "unknown")
        token_id = r.get("id", "")
        badge = r.get("badge", "")
        message = r.get("message", "")

        if r.get("ok"):
            active_count += 1
            icon = "[PASS]"
        elif status == "warn":
            warn_count += 1
            icon = "[WARN]"
        else:
            err_count += 1
            icon = "[FAIL]"

        print(f" {icon:<7} {token_id:<18} [{badge:<8}] {message}")

    print("=" * 70)
    print(
        f"Token verification complete: {active_count} active, {warn_count} warnings, "
        f"{err_count} errors out of {len(results)} total."
    )

    if "--strict" in sys.argv and err_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
