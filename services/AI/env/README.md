# services/AI/env

The `.env` files of the services whose own directory is a **submodule**.

A submodule is a separate repository, so this one cannot track a file inside
it: `services/AI/auto-job-applier/.env` could only ever be committed to the
upstream it was cloned from, which for that service is somebody else's public
repo. Registering such a path in `/.gitattributes` does not encrypt it — it
does nothing at all, because the file is never committed in the first place.
That is the trap this directory exists to close: a fresh clone used to come up
with those services silently unconfigured.

So the real file lives here, encrypted like every other service `.env`, and is
symlinked into the submodule where systemd and docker read it unchanged:

| This file | is linked to |
|---|---|
| *(none at the moment)* | |

**Check before adding one.** A submodule that tracks its own `.env` needs
nothing from this directory: the file arrives with `git submodule update` like
any other file in that repository, and symlinking over it only leaves the
submodule permanently dirty with a type change. That is why `ai-job-search` and
`auto-job-applier` are *not* listed above - both commit their `.env`
themselves. `git -C <submodule> ls-files .env` answers the question.

After `git-crypt unlock` on a new machine:

```sh
./tools/link-service-envs.sh     # idempotent; re-creates the symlinks
```

Adding another one: drop `<service>.env` here, register it in
`/.gitattributes`, and add the pair to `LINKS` in that script.
