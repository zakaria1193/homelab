"""Which build this process is running: commit and start time, read once at import.

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


COMMIT = _commit()
STARTED = int(time.time())


def info():
    return {"id": "%s-%d" % (COMMIT, STARTED), "commit": COMMIT, "started": STARTED}
