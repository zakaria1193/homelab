# supabase-keepalive

A free Supabase project is paused once it has been idle for about a week, and a
paused project has to be restored by hand before anything that depends on it
works again. This service makes sure that never happens: a systemd timer pings
every project once a week, and `make start` pings immediately if a week has
already gone by without one.

No web UI, no port, no dependencies beyond the Python that is already on the
machine.

```
supabase-keepalive/
  keepalive.py                         the pinger (standard library only)
  Makefile                             install / start / status / logs / stop
  supabase-keepalive.service.template  oneshot unit: one round of pings
  supabase-keepalive.timer.template    weekly schedule, Persistent=true
  .env.example                         the access token and any manual projects
  paused.json                          projects taken out of the rotation (committed)
  state.json                           last success, per project (git-ignored)
  keepalive.log                        what the cockpit card watches (git-ignored)
```

## Quick start

```sh
make install                  # checks python3, writes .env from the example
$EDITOR .env                  # put a Supabase personal access token in it
make start                    # enables the weekly timer, pings if overdue
make status                   # next run, last run, per-project last success
```

## Which projects get pinged

Either source works, and both can be used at once:

1. **Discovered** — put a personal access token from
   <https://supabase.com/dashboard/account/tokens> in `SUPABASE_ACCESS_TOKEN`.
   The job lists every project on the account through the Management API and
   reads each one's anon key itself, so a project you create later is covered
   without editing anything.
2. **Listed by hand** — `SUPABASE_PROJECTS`, one `name|url|anon_key[|table]`
   per line, for anything that token cannot see.

`make list` prints what would be pinged before the timer ever fires.

## Pausing a project

A project you no longer care about should not make the weekly run look broken.
Pause it and it is skipped: not pinged, not counted as a failure, and the
cockpit card stays green.

```sh
make pause PROJECT=bonjourAsso     # by name or by ref
make resume PROJECT=bonjourAsso
make list                          # each project, active or paused
```

The same switch is on the cockpit: the card's **projects** button opens
`/supabase`, which lists every configured project with a pause toggle. Both
write `paused.json`, which is committed in the clear — it names projects and
holds no keys, so the decision survives a fresh clone.

Pausing here only stops *this homelab* from pinging. It does not pause the
project at Supabase; left alone, a free project pauses itself after about a
week, which for bonjourAsso is the point.

When every configured project is paused the run still records a success. It did
exactly what it was told, so the card must not age out over it.

## What counts as a ping

One request to the project's PostgREST API, carrying the anon key. With
`SUPABASE_KEEPALIVE_TABLE` set it is `select … limit 1` against that table,
which is unmistakably a database query; without it the request goes to the
PostgREST root. Either way the project served a request, which is what the
inactivity clock measures.

A `4xx` still counts as reached — row-level security refusing an anonymous read
means the database was asked and answered. A `5xx`, a timeout or a DNS failure
does not, and is reported.

**A project that is already paused is reported, not pinged.** No request wakes
a paused project; only a restore from the dashboard does, and that is an
operator's decision rather than a weekly job's.

## The weekly promise

Three things keep it:

- `OnCalendar=Sun *-*-* 03:30` with `RandomizedDelaySec=30m` — the ordinary run.
- `Persistent=true` — if the machine was off on Sunday, systemd runs the missed
  job as soon as it is back, instead of waiting for the next Sunday.
- `make start` ends in `make ping-if-stale`, which pings immediately when
  `state.json` shows no success in the last seven days, and does nothing when
  it shows one. So installing, reinstalling, or upgrading the service always
  leaves a ping inside the window.

`make check` is the same question for a script: it exits non-zero when the last
successful run is more than a week old.

## Make targets

| Target | What it does |
|---|---|
| `make install` | Verifies `python3` and creates `.env` from `.env.example` |
| `make start` | Installs and enables the timer, then pings if overdue |
| `make status` | Timer schedule plus last run and per-project state |
| `make logs` | The last 50 runs from the journal |
| `make upgrade` | Regenerates the units from the templates, pings if overdue |
| `make stop` | Disables and removes the timer and its unit |
| `make ping` | Pings now, whatever the state file says |
| `make ping-if-stale` | Pings only if the last success is over `MAX_AGE_DAYS` old |
| `make list` | The projects that would be pinged |
| `make check` | Non-zero exit when no ping succeeded in the last week |
| `make pause PROJECT=<name\|ref>` | Take a project out of the weekly ping |
| `make resume PROJECT=<name\|ref>` | Put it back |
| `make test` | The suite: pausing, skipping, reporting — no network, no real project |

## Notifications

Per the homelab standard, a failed weekly run posts to Slack through
`tools/slackbot-notify.sh` with `--status error`, naming each project that was
not reached. `SUPABASE_KEEPALIVE_NOTIFY` takes `never`, `error` (default) or
`always`. A run that finds no projects configured at all exits non-zero and
stays quiet — that is a setup message, not an incident.

## Secrets

`.env` holds an access token that can read and administer every project on the
account, so it is committed encrypted like every other service `.env` here:

```sh
git-crypt status -e | grep supabase-keepalive     # must say "encrypted"
git add -f services/supabase-keepalive/.env
git show :services/supabase-keepalive/.env | head -c 12 | xxd   # \0GITCRYPT\0
```

The path is already registered in `/.gitattributes`.
