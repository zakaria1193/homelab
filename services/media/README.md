# Media stack

Docker compose stack: Jellyfin, Sonarr, Radarr, Chaptarr, Prowlarr,
FlareSolverr and Transmission. Ports and public hostnames are in the root `CLAUDE.md` §5.

```bash
make -C services/media start    # docker compose up -d
make -C services/media status   # docker compose ps
make -C services/media logs     # docker compose logs -f
```

## Upgrading

```bash
make -C services/media upgrade   # pull, recreate changed containers, verify
```

`upgrade` runs `docker compose pull` then `up -d`; compose only recreates the
container whose image actually changed (a Jellyfin update does interrupt any
stream for about a minute, and `transmission` resumes on its own if an
image change restarts it mid-download — both accepted). It ends by calling
`make verify`, which checks that every service in `docker-compose.yml` has a
running, healthy container, waiting briefly for one that is still
restarting, and exits non-zero (naming the container) if any is not.

No `image:` line changes on an upgrade: `meilisearch` has no equivalent here,
but any tag this stack pins the same way would stay pinned. Floating tags
(`latest`, `release`, untagged — most of this stack) get the newest version.
The weekly cron (`make -C services/AI upgrade`, Sun 04:00) runs this stack's
`upgrade` too; see the root `CLAUDE.md` §4.8.

After a successful run (every stack pulled, every container running), the
run prunes dangling images host-wide (`docker image prune -f`) — tagged
images on other containers on this host (supabase, portainer) are not
touched. **Rollback after a prune**: the old image is gone, so going back
means pinning the previous tag in `docker-compose.yml` and pulling it.

## Indexers (Prowlarr)

Public torrent indexers, synced by Prowlarr to Radarr, Sonarr and Chaptarr:
The Pirate Bay, 1337x, Knaben, kickasstorrents.to, YTS, LimeTorrents,
TorrentDownload, Torrent Downloads, Uindex, ExtraTorrent.st, Torrentsome, and
Nyaa.si for anime.

- **FlareSolverr** (`flaresolverr`, port 8191) solves Cloudflare challenges.
  Prowlarr uses it as an indexer proxy for every indexer tagged
  `flaresolverr` - tag a new indexer when its test says "blocked by CloudFlare
  Protection".
- **DNS.** The ISP resolver (`192.168.1.254`) answers `127.0.0.1` for most
  torrent sites. `prowlarr` and `flaresolverr` therefore use `1.1.1.1` in
  `docker-compose.yml`; the other containers keep the default.
- Prowlarr reaches every app by LAN IP (`http://192.168.1.10:<port>`), not the
  public hostname.

## Books (Chaptarr)

Chaptarr replaced the retired Readarr on 2026-10-11. One instance handles both
formats, with two root folders: `/books/audiobooks` and `/books/written books`
(host: `$BOOKSDIR`). Its login is the one Readarr had.

- Prowlarr has no Chaptarr type; it is the **Readarr** application in Prowlarr,
  pointed at `http://192.168.1.10:8789`. Only indexers that return book results
  pass the sync test (TPB, kickass, ExtraTorrent, Nyaa).
- There is no database import from Readarr: authors were re-added and the
  files re-matched by a library scan. Readarr's config is kept in
  `~/backups/arr-config-2026-10-11.tgz`.
- arr-mcp's `READARR_*` settings point at Chaptarr.

Docker on this host is the **snap** (`snap.docker.dockerd`), so the daemon runs
under the AppArmor profile snapd generates for it.

## Known issue: containers lose DNS after a snapd update

**Symptom.** Radarr cannot find any movie when you add one, indexers in all the
*arrs fail, and `localhost:<port>` returns an empty reply (the LAN IP still
works). The daemon log shows:

```
[resolver] failed to query external DNS server ... write: permission denied
```

and the kernel log shows `apparmor="DENIED" operation="file_perm" class="net"
profile="snap.docker.dockerd" ... denied="send"`.

**Cause.** snapd 2.77 builds snap profiles with its own AppArmor parser 5.0
(ABI 5.0, fine-grained inet rules). The 6.14.0-37 kernel has a bug in that
code path that denies writes on sockets the profile allows
([LP #2141298](https://bugs.launchpad.net/snapd/+bug/2141298),
[docker-snap#350](https://github.com/canonical/docker-snap/issues/350)).
It started on 2026-09-30 when snapd refreshed itself to 2.77.1.

**Fix applied on 2026-10-11.** snapd rolled back to 2.76.3 (parser 4.1, no ABI
5.0) and its refreshes held, AppArmor still enforcing:

```bash
sudo snap revert snapd
sudo snap refresh --hold=720h snapd     # held until 2026-11-10
sudo snap restart docker.dockerd
```

Then run each *arr's indexer and download-client tests (Settings → Indexers /
Download Clients → Test All) so they leave the failure back-off.

**Before the hold expires**, check whether a kernel with the fix
(`apparmor: fix fine grained inet mediation sock_file_perm`) is installed. If
it is, `sudo snap refresh --unhold snapd`. If not, extend the hold.

## Disk guard

Transmission, Sonarr and Radarr all write to the same disk as the OS, and
nothing in them stops a download at a free-space limit (the *arr "minimum free
space" setting only blocks imports). `disk_guard.py`, run every minute by
`media-disk-guard.timer`, fills that gap: when free space on `$DLDIR` drops
under **100 GB** it pauses every active torrent, and when free space is back
above 120 GB it resumes exactly the torrents it paused (not ones paused by
hand), and posts both events to Slack `#media-server`. Installed by `make start`; `make guard-status` shows the timer and log.
Tune with `DISK_GUARD_MIN_FREE_GB` / `DISK_GUARD_RESUME_MARGIN_GB` in `.env`.
