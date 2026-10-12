# media-autopilot

Keeps the disk at "what you are watching plus the next two episodes".

A systemd timer runs `autopilot.py` every five minutes. It reads watch state
from Jellyfin (every user) and, for each show Sonarr manages:

- **Weak helper, not a manager**: in any doubt it does nothing and leaves the show to
  you and the Sonarr UI. A show is acted on only when the furthest episode watched is
  also the one played most recently (so rewatching old episodes is never mistaken for
  progress) and that was within `STALE_DAYS` (30). Otherwise it skips the show. A show merely
  paused (nothing watched for `STALE_DAYS`) is skipped silently; genuinely unclear
  signals (a rewatch, no play dates) get one Slack line, repeated only if the reason changes.
- **Next episodes**: the `KEEP_AHEAD` (2) episodes after the furthest one
  watched or in progress are monitored, and searched if the file is missing.
  A search is repeated at most once a day.
- **Watched episodes**: an episode that any user finished more than
  `DELETE_AFTER_DAYS` (3) days ago is unmonitored and its file deleted. Partial
  playback moves the "furthest" marker but never makes an episode deletable.
- **Hopping shows**: shows you watch out of order (`hopping.json`: Modern Family and
  Grand Designs to start with) are never touched.
- **Unmonitored in Sonarr**: a show you unmonitor in Sonarr is left completely alone,
  like a hopping show. Unmonitoring a single episode in the "next" window works too
  (see next point).
- **Manual choices win**: an episode in the "next" window that you delete or
  unmonitor by hand is left alone for good (and unmonitored in Sonarr), never
  re-grabbed. Only the autopilot's own deletions are exempt from that rule.
- **Hopping shows are watched, too**: they are never touched, but if together they
  take more than `HOPPING_MAX_DISK_FRACTION` (half) of the disk, every run posts a
  Slack warning until you trim them in Sonarr. Warning only, nothing is deleted.
- **Abandoned shows**: a show that still takes space but has not been watched for
  `ABANDONED_DAYS` (365) - or, if never watched, was added that long ago - gets one Slack
  warning with its size. Nothing is deleted. Watching it again re-arms the warning.
- **Watched movies**: when someone finishes a movie (played within the last
  `MOVIE_WINDOW_DAYS`, 30), Slack gets a warning: it will be deleted in `MOVIE_WARN_DAYS`
  (7) days. A week later, if it is still not on the **maintained movies** list, it is
  unmonitored in Radarr and its file deleted (never earlier than `DELETE_AFTER_DAYS` after
  the last play, so a rewatch pushes it back). Adding it to the list during the week
  cancels the deletion; removing it later starts a fresh warning. Older plays (a library
  favourite) and unmonitored movies are left alone.
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
  maintained_movies.json             movies never deleted (edited from the cockpit)
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
(add or remove a show) and the maintained movies. From a terminal:
`python3 autopilot.py hopping add "<Sonarr title>"` / `hopping remove` / `hopping list`, and the
same three with `maintained` and a Radarr title (`Title` or `Title (Year)`).
