"""HTML pages. Each is one string with __PLACEHOLDER__ tokens that
cockpit.handler fills in before sending it.

A moved page (see cockpit/templates/README or the homelab-0009 ticket) is a
shell file read once at import through load_template(), plus its own
static/<page>.css and static/<page>.js; a page not yet moved still builds
its string here from theme.THEME."""

import os

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


def load_template(name):
    """The contents of cockpit/templates/<name>, read once at import time."""
    with open(os.path.join(_TEMPLATES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()
