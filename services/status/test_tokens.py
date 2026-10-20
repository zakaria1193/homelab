#!/usr/bin/env python3
"""CLI runner to verify configured homelab API keys, tokens, and credentials.

With no --env, checks every entry in TOKEN_DEFS (one full run, shared with the
cockpit's "Test All"). With --env <path>, checks only the entries whose
env_path resolves to that same file, so each service's `make test-tokens` can
point this at its own .env.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from cockpit.config import REPO_ROOT
from cockpit.tokens import TOKEN_DEFS, is_failure, test_all, test_token


def _resolve(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(REPO_ROOT, path)
    return os.path.realpath(path)


def _matching_defs(env_path):
    if env_path is None:
        return list(TOKEN_DEFS)
    target = _resolve(env_path)
    return [d for d in TOKEN_DEFS if _resolve(d["env_path"]) == target]


def _print_results(results):
    active = warn = err = 0
    for res in results:
        status = res.get("status", "unknown")
        if res.get("ok"):
            active += 1
            icon = "[PASS]"
        elif status == "warn":
            warn += 1
            icon = "[WARN]"
        else:
            err += 1
            icon = "[FAIL]"
        print(f" {icon:<7} {res.get('id', ''):<18} [{res.get('badge', ''):<8}] {res.get('message', '')}")

    print("=" * 70)
    print(
        f"Token verification complete: {active} active, {warn} warnings, "
        f"{err} errors out of {len(results)} total."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", help="Only check tokens whose env_path resolves to this file")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when a check fails")
    args = parser.parse_args()

    defs = _matching_defs(args.env)
    if args.env is not None and not defs:
        print(f"[ERROR] --env {args.env} matched no TOKEN_DEFS entry.")
        return 2

    print("Testing homelab API tokens and credentials...")
    print("=" * 70)

    if args.env is None:
        results = test_all()
    else:
        results = [test_token(item["id"]) for item in defs]

    _print_results(results)

    if args.strict and any(is_failure(r) for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
