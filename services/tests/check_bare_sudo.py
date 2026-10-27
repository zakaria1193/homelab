#!/usr/bin/env python3
"""Fail if a Makefile has a `sudo` call that is neither `sudo -n` nor sitting
inside a shell conditional that already tested `sudo -n true`.

Recipes in this repo write a scope-detecting block as one long shell command
joined by backslash-newlines ("if sudo -n true; then ... fi", continued with
a trailing backslash), so a logical line is built by re-joining lines ending
in a backslash before checking them.
"""
import re
import sys


def logical_lines(text):
    out = []
    buf = ""
    for line in text.splitlines():
        if not buf and line.lstrip().startswith("#"):
            continue
        buf = line if not buf else buf + " " + line.strip()
        stripped = buf.rstrip()
        if stripped.endswith("\\"):
            buf = stripped[:-1]
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def violations(path):
    with open(path) as f:
        text = f.read()
    found = []
    for ln in logical_lines(text):
        if not re.search(r"\bsudo\b", ln):
            continue
        guarded = "sudo -n true" in ln
        for m in re.finditer(r"\bsudo\b(\s+-n\b)?", ln):
            if not m.group(1) and not guarded:
                found.append(ln.strip()[:160])
                break
    return found


def main(paths):
    ok = True
    for path in paths:
        for ln in violations(path):
            print(f"{path}: bare sudo (neither -n nor guarded by 'sudo -n true'): {ln}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
