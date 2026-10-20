# aicli

One place every homelab caller reaches `claude` and `agy` through. Changing a
binary path, a model name, a standard flag or the `/usage` parsing is a
one-file change (`aicli.toml`) instead of several.

aicli only builds an argv and runs the real, unmodified CLI under the user's
own login. It never reads, stores or forwards OAuth tokens
(`~/.claude/.credentials.json`, `~/.gemini/`), and it never calls a vendor
backend itself.

This is the core command (`aicli.py`) plus the HTTP service (`server.py`,
unit `aicli-ai`) that fronts it for text callers like ai-job-search. See
ticket homelab-0013 for the full plan.

## Files

- `aicli.toml` - the one config file: per tool, `bin`, standard `args`,
  `model_flag`, `effort_flag` and a `low`/`default`/`deep` tier table.
  `AICLI_CONFIG` points aicli at a different file (tests use it).
- `aicli.py` - the `aicli` command: `which`, `argv`, `run`, `resolve`,
  `usage`, `routes`, `route`.
- `routes.json` - the routing switchboard (workload classes, client
  overrides, OptiPlex projects), edited live from the cockpit's AI Routes tab
  or with `aicli route`. Next to `aicli.toml` unless `AICLI_ROUTES` says
  otherwise; the `[classes.*]` tables in `aicli.toml` are its defaults.
- `server.py` - the `aicli-ai` HTTP service: `/healthz`, `/v1/models`,
  `/v1/chat/completions`.
- `.env` / `.env.example` - the service's bind settings (`AICLI_HOST`,
  `AICLI_PORT`, `AICLI_MAX_CONCURRENT`, `AICLI_TIMEOUT`, `AICLI_USAGE_LOG`). `.env` is committed
  via git-crypt like every other service's, even though it holds no secrets.
- `aicli.service.template` - the systemd unit template rendered by `make start`.
- `tests/` - unit tests and the fake CLI they run against
  (`tests/fake_cli/`). No test runs the real `claude` or `agy`.

## Commands

```
aicli which <claude|agy>
```
Prints the absolute path of the real binary: the configured `bin` if it's
executable, otherwise the first match on `PATH` (skipping `/usr/local/bin`
and `/usr/local/sbin`, where the tmux wrapper's symlinks live, to avoid a
loop). Exits 1 with `<tool> CLI not found` if neither resolves.

```
aicli argv [--tool <claude|agy>] [--tier low|default|deep] [--effort low|medium|high]
           [--client <id>] [--class <name>] [--json] [-- args...]
```
Prints the argv that `run` would exec: one shell-quoted line by default, or a
JSON array with `--json`. For callers that launch the CLI themselves (tmux,
systemd). `--tier` defaults to `default`. If `args` already holds the model
or effort flag, aicli does not add its own. A tool with
`model_sets_effort = true` (agy: `gemini-3.8-flash-low` names its effort, and
agy rejects a different `--effort`) gets no effort flag at all when aicli adds
the tier's model; the tier decides.

`--client` and `--class` pick the tool and tier from `routes.json` instead:
a client's own row first (`pjm:p-0001:auto-execute` also matches
`pjm:auto-execute`), then its class. An explicit `--tool`, `--tier` or
`--effort` always wins. Without a class or a `--tool`, it exits 2.

```
aicli run [same options as argv] [--meta-out <path>] [-- args...]
```
Same options as `argv`, but `exec`s that argv - the exit code, signals,
stdin/stdout and TTY are exactly the real CLI's. Before the exec it appends
one line (client, class, tool, tier, model, quota) to `AICLI_USAGE_LOG`, and
`--meta-out` writes the same facts as JSON to `<path>`. The model and effort
are read back from the argv, so a caller's own `--model` is what gets
recorded.

```
aicli resolve [--client <id>] [--class <name>] [--tool ...] [--tier ...] [--quota] [--json]
```
Prints where a call would go (class, tool, tier, model) without running it.

```
aicli routes [--json]
aicli route set-class <name> --tool <claude|agy> [--tier ...]
aicli route set-client <id> [--class <name>] [--tool ...] [--tier ...]
aicli route remove-client <id>
```
Shows and edits `routes.json`.

```
aicli usage [--json]
```
Runs `claude -p /usage` and `agy -p /usage` side by side and parses them
(moved as-is from `services/status/usage.py`). Exits 0 even when a tool's
state is `unknown`; the state is in the output. `--json` prints
`{"claude": {state, detail, bars}, "agy": {...}}`.

## The service (`aicli-ai`)

An HTTP service on port 8500 speaking the OpenAI chat-completions protocol,
for text callers that can't exec the CLI themselves (ai-job-search, and
karakeep through the docker bridge). It binds `127.0.0.1` by default. A
non-loopback `AICLI_HOST` needs both `AICLI_ALLOW_NON_LOOPBACK=1` and
`AICLI_API_KEY`, or `server.py` refuses to start. Loopback callers need no
key; any other caller must send `Authorization: Bearer <AICLI_API_KEY>` on
`/v1/*` or gets a 401 (`/healthz` stays open). On dell it listens on
`0.0.0.0` for karakeep, whose `OPENAI_API_KEY` holds the same key.

- `GET /healthz` - `200 ok`, no CLI run.
- `GET /v1/models` - the ids `claude`, `agy` and `<tool>/<tier>` for every
  tier (8 ids). A bare tool id means its `default` tier.
- `POST /v1/chat/completions` - `model` one of those ids, `messages`
  flattened into one prompt, `reasoning_effort` maps to `--effort`,
  `stream: true|false`. Each request runs the CLI once through the same
  argv builder as `aicli run`, in an empty scratch directory, with no
  permission-skipping flag. At most `AICLI_MAX_CONCURRENT` runs happen at
  once; more wait their turn. Errors: 400 (bad request/unknown model), 413
  (prompt over 120 KiB), 502 (non-zero CLI exit), 504 (timeout).

### Token usage log

Every chat-completions request appends one JSON line per model to
`AICLI_USAGE_LOG` (default `~/.local/state/aicli/usage.jsonl`). `aicli run`
writes to the same file, with its own row shape (client, class, quota, no
token counts):

```
{"at": "2026-10-14T18:20:00+00:00", "tool": "claude", "tier": "default", "stream": false,
 "model": "claude-sonnet-5", "reported": true, "client": "pjm",
 "input": 3, "output": 7, "cache_write": 20, "cache_read": 100, "total": 130}
```

The counts come from the CLI's own final result: claude's `modelUsage` (one
line per model it used), agy's `usage` (often only a `total`). Non-streaming
claude runs use `--output-format json` so their counts can be read; agy without
streaming prints plain text, so its line says `"reported": false`. Failed runs
are logged too. A log that can't be written never fails the request. pjm's
Usage page draws these lines per model and per day, and the homelab cockpit's
AI Routes tab draws them per model and per client.

Every HTTP line also carries `client`: who made the request, for this log
only - it is never used for routing or auth. It is chosen in order: the
`X-Aicli-Client` request header, else the OpenAI `user` field of the request
body, else - for a non-loopback caller that passed the API key check -
the `AICLI_REMOTE_CLIENT` setting, else `"unknown"`. The name is trimmed,
stripped of control characters and cut to 80 characters. On dell,
`AICLI_REMOTE_CLIENT=karakeep:tagger` labels karakeep's calls, since it sends
neither the header nor the `user` field.

## Install

```
make install   # links ~/.local/bin/aicli -> aicli.py
make test      # runs the unit tests against the fake CLI
make start     # brings up the aicli-ai service via systemd (port 8500)
make status    # make logs / make stop / make upgrade / make restart
```

Callers inside this repo call `services/AI/aicliAI/aicli.py` by its repo
path, so they don't depend on the `~/.local/bin/aicli` link. The link exists
for other repos (pjm, ai-job-search) to pick up later.
