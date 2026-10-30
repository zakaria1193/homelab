"""Which build this process is running: commit and start time, read once.

The start time is taken at import; the commit is read on first use, so importing
this module runs no subprocess (tests that stub subprocess.run rely on that).

`make upgrade` restarts the service, so the start time is when this version went live.
"""

import subprocess
import time

from .config import HERE


def _commit():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


STARTED = int(time.time())
_COMMIT = None


def commit():
    global _COMMIT
    if _COMMIT is None:
        _COMMIT = _commit()
    return _COMMIT


def info():
    c = commit()
    return {"id": "%s-%d" % (c, STARTED), "commit": c, "started": STARTED}
