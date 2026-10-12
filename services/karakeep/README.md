# Karakeep stack

Docker compose stack: `karakeep` (web, port 3000), `meilisearch` (search
index, pinned `v1.13.3`), `chrome` (headless browser used to render saved
pages). Public hostname `keep.` — see the root `CLAUDE.md` §5.

```bash
make -C services/karakeep start    # docker compose up -d
make -C services/karakeep status   # docker compose ps
make -C services/karakeep logs     # docker compose logs -f
```

## Upgrading

```bash
make -C services/karakeep upgrade   # pull, recreate changed containers, verify
```

`upgrade` runs `docker compose pull` then `up -d`; compose only recreates the
container whose image actually changed. It ends by calling `make verify`,
which checks that `web`, `meilisearch` and `chrome` each have a running,
healthy container, waiting briefly for one that is still restarting. It
exits non-zero (naming the container) if any is not.

`KARAKEEP_VERSION` in `.env`, if set, and `meilisearch:v1.13.3` are pulled
as-is — pinned tags never move on an upgrade. The weekly cron
(`make -C services/AI upgrade`, Sun 04:00) runs this stack's `upgrade` too;
see the root `CLAUDE.md` §4.8.

Dangling images are pruned host-wide after a successful run, not per-stack —
see `services/media/README.md` → *Upgrading* for the prune and rollback
notes, which apply here too.
