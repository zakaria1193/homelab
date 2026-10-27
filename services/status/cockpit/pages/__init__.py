"""HTML pages. Each module holds the __PLACEHOLDER__-carrying shell string
that cockpit.handler fills in before sending it.

Every page is a shell file in cockpit/templates/, read once at import through
load_template(), plus its own static/<page>.css and static/<page>.js
(homelab-0009). A page module itself holds only that load_template() call and
whatever placeholder-filling logic the handler needs."""

import os

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


def load_template(name):
    """The contents of cockpit/templates/<name>, read once at import time."""
    with open(os.path.join(_TEMPLATES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()
