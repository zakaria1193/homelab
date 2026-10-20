"""Loads the two modules that live outside this package by file path.

`cron_manager` (tools/cron-manager) and `aicli` (services/AI/aicliAI) are
shared with other tools and keep their own directories, so they are not
moved under `cockpit/`. Importing them by path - instead of a `sys.path`
insert - keeps that the only exception to "no sys.path edits in cockpit/".
"""

import importlib.util
import sys


def load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
