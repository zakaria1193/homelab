# media-autopilot

Keeps the disk at "what you are watching plus the next two episodes".

A systemd timer runs `autopilot.py` every five minutes. It reads watch state
from Jellyfin (every user) and, for each show Sonarr manages:

- **Next episodes**: the `KEEP_AHEAD` (2) episodes after the furthest one
  watched or in progress are monitored, and searched if the file is missing.
  A search is repeated at most once a day.
- **Watched episodes**: an episode that any user finished more than
  `DELETE_AFTER_DAYS` (3) days ago is unmonitored and its file deleted. Partial
  playback moves the "furthest" marker but never makes an episode deletable.
- **Hopping shows**: shows you watch out of order (`hopping.json`: Modern Family and
  Grand Designs to start with) are never touched.
- **Manual choices win**: an episode in the "next" window that you delete or
  unmonitor by hand is left alone for good (and unmonitored in Sonarr), never
  re-grabbed. Only the autopilot's own deletions are exempt from that rule.
- **Safety**: at most `MAX_DELETES_PER_RUN` files per run.
- **Slack**: every event goes to `#media-server`, one message per run: episodes newly
  monitored, searches, deletions, the safety cap being hit, edits to the hopping list,
  a failed run (once per outage) and the recovery after it. A quiet run sends nothing.

No web UI, no port, no dependencies beyond the Python already on the machine.

```
media-autopilot/
  autopilot.py                       the job (standard library only)
  Makefile                           install / start / status / logs / stop
  media-autopilot.service.template   oneshot unit: one run
  media-autopilot.timer.template     every 5 minutes
  .env.example                       Jellyfin key and the policy knobs
  hopping.json                       shows left alone (edited from the cockpit)
  tests/test_autopilot.py            decisions against fake Sonarr/Jellyfin
  state.json, autopilot.log          runtime (git-ignored); the cockpit watches the log
```

## Quick start

```bash
cd services/media-autopilot
cp .env.example .env && $EDITOR .env   # JELLYFIN_API_KEY
make test
make dry-run      # shows what it would do, changes nothing
make start
make status
```

`.env` is committed as git-crypt ciphertext (see `/.gitattributes`).

## Customising

Everything is in `.env`: `KEEP_AHEAD`, `DELETE_AFTER_DAYS`, `MAX_DELETES_PER_RUN`.

The hopping shows are in `hopping.json`, which the cockpit's **Media** tab edits
(add or remove a show). From a terminal:
`python3 autopilot.py hopping add "<Sonarr title>"` / `hopping remove` / `hopping list`.
