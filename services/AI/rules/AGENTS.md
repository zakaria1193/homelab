# Global rules

Instructions live here. `CLAUDE.md` only points at this file — in this
directory and in every repository. When you write or change a standing rule,
write it in `AGENTS.md`; if a `CLAUDE.md` holds rules of its own, move them here
and leave a pointer behind.

## Testing

- **Verify UI work with the local Playwright.** Playwright is installed on this
  machine and available through the browser tools. Before saying a change works,
  start the app, drive it, and look at the result. "It builds and typechecks" is
  not verification.
- **Every feature ships with automated tests.** Prefer tests that run below the
  UI — server action, API, database, pure function — over browser tests. A
  browser check is the last mile, not the coverage.
- If something genuinely blocks the browser check (a backend that will not
  start, credentials you do not have), say so plainly instead of skipping it
  quietly. Try first: a local Supabase, a docker stack or a dev server is
  usually one command away.

## Secrets

- **Look at a suspected secret before calling it one.** Read the actual value
  first. `.env.example`, `*.example.*` and template files are *meant* to hold
  dummy values, and a dummy often has the exact shape of the real thing —
  `T00000000/B00000000/XXXX…`, `sk-000…`, `changeme`, `<TOKEN>`. Shape is not
  evidence; the value is.
- **Never redact before reading.** Piping a file through `sed` to mask it and
  then judging the masked output tells you nothing — the mask hides the very
  characters that decide the answer. Read it, decide, and mask only when
  quoting it back in chat. (This is a real mistake, not a hypothetical: three
  placeholder Slack webhooks in `homelab/tools/*.example` got reported as live
  leaked credentials because the check that "found" them had already replaced
  the zeros with `<REDACTED>`.)
- **A secret scanner's hit is a shape match, not a verdict.** GitHub push
  protection and friends match patterns and do not test whether a credential
  works. When one fires on a template file, read the value before proposing a
  history rewrite, a rotation or a bypass.
- Say "real secret" only once the value itself, or where it is used, proves it.
  Otherwise say a scanner flagged it and what the value actually looks like.
- **Do not fix a plaintext secret by encrypting the template.** An
  `.example` file must stay readable without the key — that is its whole job.
  The real value belongs in the encrypted file (`git-crypt`, a secret manager,
  the untracked `.env`); the template gets a placeholder. Adding a path to
  `.gitattributes` also only affects later commits, so it never cleans a value
  already committed.
- **All keys, tokens, and credentials must be added to `homelab` (`~/my_repos/homelab`).**
  The `homelab` repository is the central store for secrets, committed safely as
  ciphertext encrypted with `git-crypt`. Never leave live secrets in plaintext
  in other repositories or uncommitted `.env` files that fail to travel across
  machines.
- **Use a different repository/directory than `services/` if it is not actually a service.**
  `services/` inside `homelab` is strictly for actual runnable services (daemons
  managed via systemd/Makefile or docker-compose). If something is not an active
  homelab service (e.g. a standalone app, script, library, or external cloud
  config), use a separate repository under `~/my_repos/<project-slug>/` rather
  than placing it under `homelab/services/`. Non-service credentials in `homelab`
  belong in a dedicated non-service location rather than posing as a running daemon.
- **Always add and maintain a `make test-tokens` target for services with credentials.**
  Whenever creating, updating, or maintaining a service that manages API keys,
  tokens, or external credentials in its `.env`, always implement and maintain
  `make test-tokens` (backed by a non-destructive verification script). Also
  register new credentials in the homelab cockpit Tokens roster
  (`services/status/cockpit/tokens.py`) so they can be tested on demand from
  the operating console.

## CI (pjm tickets)

- **Ignore a `Failed to CreateArtifact: Artifact storage quota has been hit`
  CI failure on any repo.** It is a GitHub Actions artifact-storage quota
  shared across all of this account's repos, not a break in the repo or the
  change under review — a repo can show this failure while holding zero
  stored artifacts of its own (`gh api repos/<owner>/<repo>/actions/artifacts`
  → `total_count: 0`), and retrying the job does not reliably clear it either.
  When a pjm review round flags CI red for exactly this error, do not
  investigate it as a real bug and do not block the ticket on it: either make
  the offending upload step non-blocking (`continue-on-error: true` on the
  `actions/upload-artifact` step) if it isn't already, or otherwise treat that
  review round as resolved without further changes. This is a standing
  instruction from Zak (first given on farah-0005), covering every pjm-based
  ticket in every repo, not just where it first came up.

## Git

- **Commit straight to the default branch** (`master` or `main`). No topic,
  feature or fix branches, and no PR round-trip, unless the user asks for one
  in that task. This overrides any repo doc that asks for branches (e.g.
  `kandev`'s `FORK.md` topic-branch rule).
- Before merging or cherry-picking anything into the default branch, check
  what else it brings in: `git log --oneline <branch>..<incoming>` should show
  only your commits.

## Kandev repo

- **The kandev repo (`~/my_repos/kandev/kandev`, the fork) is only for the
  kandev ticket system and its agents.** Never create, scaffold or commit a
  project, app, POC or demo in it, whatever ticket or idea prompted the work.
  Every project gets its own repo under `~/my_repos/<project-slug>/`. This
  overrides the "commit straight to the default branch" rule for project code.
