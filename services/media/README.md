# Media stack

Docker compose stack: Jellyfin, Sonarr, Radarr, Readarr, Prowlarr and
Transmission. Ports and public hostnames are in the root `CLAUDE.md` §5.

```bash
docker compose up -d      # start
docker compose ps         # status
docker compose logs -f radarr
```

## Indexers (Prowlarr)

Public torrent indexers, synced by Prowlarr to Radarr, Sonarr and Readarr:
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
  public hostname - Readarr pointed at `media.zakariafadli.com/readarr`, which
  returns 404.

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
