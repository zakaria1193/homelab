# aicli

One place every homelab caller reaches `claude` and `agy` through. Changing a
binary path, a model name, a standard flag or the `/usage` parsing is a
one-file change (`aicli.toml`) instead of several.

aicli only builds an argv and runs the real, unmodified CLI under the user's
own login. It never reads, stores or forwards OAuth tokens
(`~/.claude/.credentials.json`, `~/.gemini/`), and it never calls a vendor
backend itself.

This is the core command (`aicli.py`). The HTTP service (`server.py`) and the
systemd unit that fronts it for text callers like ai-job-search land in a
later step of ticket homelab-0013 - see that ticket for the full plan.

## Files

- `aicli.toml` - the one config file: per tool, `bin`, standard `args`,
  `model_flag`, `effort_flag` and a `low`/`default`/`deep` tier table.
  `AICLI_CONFIG` points aicli at a different file (tests use it).
- `aicli.py` - the `aicli` command: `which`, `argv`, `run`, `usage`.
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
aicli argv --tool <claude|agy> [--tier low|default|deep] [--effort low|medium|high] [--json] [-- args...]
```
Prints the argv that `run` would exec: one shell-quoted line by default, or a
JSON array with `--json`. For callers that launch the CLI themselves (tmux,
systemd). `--tier` defaults to `default`. If `args` already holds the model
or effort flag, aicli does not add its own.

```
aicli run --tool <claude|agy> [--tier ...] [--effort ...] [-- args...]
```
Same options as `argv`, but `exec`s that argv - the exit code, signals,
stdin/stdout and TTY are exactly the real CLI's.

```
aicli usage [--json]
```
Runs `claude -p /usage` and `agy -p /usage` side by side and parses them
(moved as-is from `services/status/usage.py`). Exits 0 even when a tool's
state is `unknown`; the state is in the output. `--json` prints
`{"claude": {state, detail, bars}, "agy": {...}}`.

## Install

```
make install   # links ~/.local/bin/aicli -> aicli.py
make test      # runs the unit tests against the fake CLI
```

Callers inside this repo call `services/AI/aicliAI/aicli.py` by its repo
path, so they don't depend on the `~/.local/bin/aicli` link. The link exists
for other repos (pjm, ai-job-search) to pick up later.
