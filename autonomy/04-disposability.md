# 04 — Disposability: the seed is the backup

There is no backup job for the radio, and that is a decision, not an oversight.

The station's content is **deterministic**: a seed plus a lane produces a plan,
and the plan produces the same audio byte for byte on the same machine. So the
expensive things — the FLAC library, the rendered voice segments, the metadata
catalogue, the HLS segments — are all *derivable*. Copying them would be copying
an answer that can be recomputed.

## What is disposable

| Data | Size now | Recovery |
|---|---|---|
| `music-audio/*.flac` | 10 tracks | `radio-job render` — ~7 min, same seeds give the same files |
| `music/*.json`, `catalog.json` | small | produced by the same render |
| `data/host/*.wav` (TTS) | ~140 MB | the next hourly cycle regenerates the current bucket |
| `data/cam/*` (HLS) | small | the camera writes new segments continuously |
| `data/indiegen/runs/` | small | run history; `gc` already deletes most of it |
| Docker images and build cache | 8.6 GB cache | rebuilt from the repo, by design (`post-receive` builds on push) |
| Logs, journals | 81 MB | the past; useful during an incident and then not |

Deleting any of that costs minutes of CPU, not content.

## What is not derivable

Exactly two things, and both are kilobytes:

1. **`data/indiegen/state.json`** — the seed cursor. Without it the generator
   restarts from `INDIEGEN_SEED_BASE` and the station begins a *different*
   musical history. Nothing breaks; the station simply stops being the same
   station it was yesterday.
2. **`.env` + `secrets/tokens.txt`** — the Icecast passwords and the listener
   access list. Without them: no stream credentials, and every listener needs a
   new invitation link.

Both fit in a single text paste. If losing them is unacceptable, the answer is
not a backup system — it is a copy of two small files somewhere that is not this
host, updated when they change (a password manager entry, or a private note).
A `tar` of `music-audio/` is 30 MB of recomputable audio; a copy of `state.json`
is the station's memory.

## Why this is the right policy here

Three reasons, in order of weight:

1. **A backup that is never restored is a hypothesis.** With one host, one
   operator and no restore drill, a backup job mostly produces a false sense of
   safety. Determinism produces a *tested* recovery path instead: the generator
   runs every six hours, so "rebuild the library" is exercised constantly.
2. **Retention and backup fight each other.** The station's job is to delete the
   old library every cycle. A backup that keeps what the rotation deletes turns
   a bounded disk into an unbounded archive of music nobody asked for.
3. **It keeps the failure surface small.** No second disk, no credentials for a
   remote bucket, no cron that fails silently at 03:00. The appliance has enough
   moving parts.

## The recovery procedure, for when it matters

```bash
# A track is corrupt, or the library is wrong after a bad render.
./scripts/radio-job.sh gc            # nothing to restore: drop the batch
docker compose run --rm indiegen serve --count 10 --seed-base 1000 --once
#  -> or simply wait for the next cycle (<= 6 h), or force one:
touch data/indiegen/trigger

# The whole box is gone.
git clone https://github.com/The-Replacement/radio && git clone .../indiegenerator
cp .env  # from the password manager
docker compose up -d icecast liquidsoap caddy mediamtx indiegen
#  -> the first cycle renders a fresh library from INDIEGEN_SEED_BASE
```

The second path is the bootstrap in [`03-roadmap.md`](03-roadmap.md) step 7, and
it is the reason that step exists: recovery must be a script, because the moment
you need it is the moment nobody wants to improvise.

## What "delete" means in practice

- `indiegen` already replaces the whole library every cycle. That is deletion by
  design and it is the point.
- `mario` keeps one bucket and prunes the rest.
- `radio-job gc` deletes cache, images, logs and run history nightly.
- Manual deletions (`rm -rf music-audio/*`) are safe: the next render refills it.

The only deletion that needs thought is `state.json` and `.env` — those two are
not derivable, and they are small enough to copy by hand.
