# 02 — Design: one scheduler, a resource gate, retention as code

The target is a box that runs four loops without supervision. Nothing here is
speculative infrastructure: it is systemd, cgroups and shell, on the hardware
already in place.

## 1. One job model instead of cron soup

Today three independent schedules compete. Replace them with a single wrapper,
`radio-job`, run by systemd timers. The wrapper is the only thing that knows
about priorities, locks and resource conditions.

```
radio-job render      # indiegen cycle (heavy: 1 core, ~7 min, 1.5 GB)
radio-job tts         # mario bucket  (heavy: 1 core, minutes, 535 MB peak)
radio-job preflight   # the gate's verdict, alone, for debugging
radio-job gc          # retention (light, I/O heavy)
radio-job verify      # health probes, writes the status file
```

Properties that matter:

- **One lock per class.** `render` and `tts` share an "heavy" lock; `rotate` takes
  it too, because a rotation while a render publishes is how a library ends up
  half-written. `gc` and `verify` never block anything.
- **Priority by cgroup, not by hope.** All batch jobs run in
  `radio-batch.slice` with `CPUWeight=20` and `MemoryMax=` a share of the box.
  The audio path stays in `docker.slice` untouched. A starving batch job is a
  correct outcome; a starving encoder is not.
- **One place to change a schedule.** Intervals live in a single env file, not in
  three crontabs on two machines.

### The resource gate

Before a heavy job starts, `radio-job` asks three questions and defers if any
answer is bad:

```bash
# 1. thermal
pkg=$(cat /sys/class/thermal/thermal_zone*/temp | sort -n | tail -1)
[ $((pkg/1000)) -ge 78 ] && defer "hot: ${pkg}mC"

# 2. memory pressure (PSI, 60 s window)
psi=$(awk '/^some/ {print $2}' /proc/pressure/memory)      # avg60
[ "${psi#avg60=}" -gt 10 ] && defer "memory pressure: $psi"

# 3. is the stream healthy right now?
radio-probe audio || defer "stream unhealthy"
```

A deferred job is not a failed job: it retries on the next tick (15 min) and
records `deferred` in the status file. Deferral is how the station avoids
generating at the exact moment the machine cannot afford it — the thing cron
cannot express.

**This is the edge.** The decision is local, it is made from sensors, and it has
no network dependency.

## 2. Retention as code

`radio-job gc` runs nightly at 04:30 (after the 04:00 EPG job leaves), and is
the only thing that deletes. Every class of data has a stated bound:

| Data | Growth (measured) | Bound | Command |
|---|---|---|---|
| Docker build cache | 21.1 GB, 17.5 GB reclaimable | 5 GB | `docker builder prune --keep-storage 5GB -f` |
| Unused images | 14 images, 8.5 GB | keep last 2 per service | `docker image prune -f` (dangling) + explicit `rmi` of tagged leftovers older than 30 d |
| Journal | 116 MB today, unbounded | 1 GB | `journalctl --vacuum-size=1G` (plus `SystemMaxUse=1G` in config) |
| Container logs | now capped at 10 MB × 3 | — | compose `logging` |
| `data/mario-refresh.log` | capped | 1 MB | existing truncation |
| `data/deploy.log` | append-only | 10 MB | rotate in `gc` |
| `data/ac1-soak-*.log` | one file per run | keep 10 | `ls -t | tail -n +11 | xargs rm` |
| `data/indiegen/runs/` | one dir per cycle | keep 50 | oldest-first removal |
| `music-audio/`, `music/` | bounded by design | 10 tracks | `rotate_library` |
| `data/host/` | bounded by design | 1 bucket | `prune_host_dir` |

Two rules make this safe:

1. **`gc` never deletes anything a running container has open.** Docker prunes
   respect that; the shell deletes are restricted to `data/` files matched by
   glob, never `find -delete` over a tree.
2. **`gc` logs what it freed, per line, to `data/gc.log`.** A retention policy
   that cannot be audited is a policy that will one day eat something important.

Disk guard, independent of `gc`: if `df` reports < 5 GB free, `rotate` refuses to
publish (the library stays as it is, the stream keeps playing) and the alert
fires. Never let the *publisher* be the thing that discovers a full disk.

## 3. The self-heal ladder

Escalate only as far as needed, and verify each step before the next.

| Level | Trigger | Action | Verify | Autonomy |
|---|---|---|---|---|
| 0 | Container not running | Docker restarts it | `docker ps` + healthcheck | ✅ already |
| 1 | Icecast has a source but bytes are not moving for 60 s | Restart `liquidsoap` (max 3 in 30 min, then stop trying) | Byte-rate probe | ✅ safe to automate |
| 2 | `caddy` unhealthy | Restart `caddy` (max 3 in 30 min) | 404-without-token probe | ✅ safe |
| 3 | Temperature > 80 °C for 5 min | `docker compose stop cam indiegen`; block batch jobs | Temperature < 70 °C for 10 min before resuming | ✅ safe |
| 4 | Memory PSI `full` > 5 % for 5 min | Stop batch jobs, then `cam` | PSI returns to 0 | ✅ safe |
| 5 | Temperature > 90 °C for 1 min | Controlled `docker compose down`, then `shutdown` | — | ✅ but announce first |
| 6 | Anything above repeats 3× in an hour | **Stop automating.** Write a one-line diagnosis to the status file and alert | — | human |

Level 6 is the important one. An autonomous system that loops forever on a
physical fault (dust, dead fan) converts a repairable problem into a destroyed
machine. After three identical escalations, the correct action is to stay down
and say why.

## 4. One status surface

A single file, rewritten by `verify` every 5 minutes, and a single command that
prints it:

```json
{
  "ts": "2026-11-13T22:15:00Z",
  "stream": {"source": true, "bytes_per_s": 16012, "title": "Mano Firme - Puerto Vidrio"},
  "door": {"closed_without_token": true},
  "camera": {"fresh": false, "reason": "no device"},
  "content": {"tracks": 10, "catalog_ok": true, "last_render": "2026-11-13T18:00:12Z",
              "last_tts": "2026-11-13T22:00:41Z",
              "next_render_in_s": 14112},
  "resources": {"pkg_c": 43, "mem_avail_mb": 29652, "disk_free_gb": 783,
                "containers_capped": true},
  "jobs": {"last_gc": "2026-11-13T04:30:02Z", "deferred": []}
}
```

Why a file and not a dashboard: the dashboard needs a network and a browser. The
file is readable over SSH at 3 a.m., is what the alerting agent pushes, and is
what a human checks after two weeks away. `radio status` prints it as text.

Bonus: it is served to the player as `/host/status.json` (the door already maps
`/host/*`), so the page can honestly say *"last new track: 3 hours ago"* — the
station reporting on itself to its listeners.

## 5. Reproducibility

Everything above is worthless if rebuilding the box is archaeology. The
appliance must be reconstructible from:

1. `git clone The-Replacement/radio` + `indiegenerator`
2. `.env` from the password manager (variable names are in `.env.example`)
3. `infra/deploy/bootstrap.sh` — installs Docker, creates the user, drops
   `radio-job`, the timers, the `radio-batch.slice`, `ufw` rules, zram
4. `music-audio/` + `music/` from the backup (or a fresh render, which takes
   seven minutes and is the whole point of determinism)

If step 3 does not exist, the "appliance" is a pet. It is also the cheapest
deliverable in this document.
