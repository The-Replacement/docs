# 03 — Roadmap

Ordered so that each step is independently useful, testable, and shippable in one
sitting. Nothing later depends on something that has not landed.

## Step 1 — Bound the machine (done 2026-11-13)

Caps and log rotation in `docker-compose.yml` (#102). Without this, every later
step runs on a box that can still be taken down by its own batch jobs.

**Verify:** `docker inspect` shows non-zero `Memory`/`NanoCpus` on all six
services; a render stays under 1.5 GiB.

## Step 2 — Retention as code

`radio-job gc` + `data/gc.log` + disk guard in `rotate`. This is the smallest
change with the largest effect over months: it removes the only unbounded growth
on the box (21 GB of build cache and counting).

**Issue:** "Add radio-job gc: retention policy for cache, images, journal, logs".
**Verify:** run it twice; second run frees ~0. Disk usage must be lower and the
log must account for every byte.

## Step 3 — The status surface

`radio-job verify` writing `data/status.json`, `radio status` reading it, and the
player reading `/host/status.json`.

**Issue:** "Add a single status file and `radio status` command".
**Verify:** every field is populated from a real probe; unplug the camera and
watch `camera.reason` change.

This step is worth doing early because it becomes the test harness for everything
after it: you cannot verify self-healing without a signal that says what is
broken.

## Step 4 — The resource gate and one scheduler

`radio-job` with `render|tts|rotate`, the shared heavy lock, `radio-batch.slice`,
and deferral on thermal/PSI/stream-health. Replaces three cron entries.

**Issue:** "Replace cron entries with radio-job and a resource gate".
**Verify:** force a deferral (write a fake temperature or run a CPU burner) and
confirm the job defers instead of starting; confirm the stream is unaffected.

## Step 5 — The self-heal ladder, levels 1–4

Watchdog for Liquidsoap byte-rate, Caddy restart, thermal and memory shedding,
with budgets and backoff. Level 5 (controlled shutdown) after levels 1–4 have
been exercised at least once on purpose.

**Issue:** "Implement the self-heal ladder with bounded retries".
**Verify:** kill `liquidsoap`'s source (`docker exec ... kill`) and watch the
ladder bring audio back without a human.

## Step 6 — The deploy guard (done 2026-11-13 for the symptom)

`post-receive` refuses to run on a detached HEAD. The class of bug — "deploy
succeeded, nothing changed" — deserves a test as well as a guard.

**Issue:** "post-receive: fail loudly instead of succeeding on a detached HEAD".
**Verify:** detach HEAD on the host, push, confirm the push is rejected with a
clear message.

## Step 7 — Bootstrap

`infra/deploy/bootstrap.sh`: from a fresh Ubuntu install to a running station.
This is what makes the appliance reproducible rather than a pet, and it is the
only way to test that the previous six steps are complete.

**Issue:** "Add a bootstrap script for a radio appliance".
**Verify:** rebuild a VM (or a spare machine) and get audio playing from it,
using only the repo and the `.env`.

## Step 8 — Optional: content self-assessment

Once the four loops are stable, the last autonomy question is content: *if
renders keep producing, does the library stay interesting?* The gates already
measure loudness, peak and clip; the sweep measures trajectory. Extending that to
"this cycle produced 10 tracks that are not near-duplicates of the current
library" is a content-quality loop, not an uptime loop.

Deliberately last, and deliberately optional: an autonomous station that
reliably broadcasts mediocre music is better than an intelligent station that
reliably stops.

## What is explicitly not on this roadmap

- Any dependency on a network service for generation or retention.
- Any automatic change to audio settings (bitrate, presets, LUFS targets). Those
  are measured by gates; a machine should not retune the product it is being
  judged on.
- Any "self-upgrade" of the OS or Docker images without a human reading the
  changelog. Unattended security updates: yes. Unattended feature updates on the
  box that has to stay on air: no.
