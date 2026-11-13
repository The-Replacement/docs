# 05 — Alert rule catalog

**Deliverable 4.** Concrete thresholds, the window that makes each one
meaningful, the severity, and what should happen automatically — if anything.

Defaults are tuned for the host as audited on 2026-11-13: i7-1165G7, 4C/8T,
32 GiB RAM, 8 GiB disk swap, NVMe 914 GB (11 % used), idle package 42 °C, fans
at 0 RPM when idle.

## Thermal

| Rule | Condition | For | Severity | Action |
|---|---|---|---|---|
| `TempWarm` | package > 70 °C | 10 min | warning | Notice the trend; check dust/airflow at the next visit |
| `TempHot` | package > 80 °C | 5 min | **critical** | Stop `cam` and `indiegen`; stream keeps playing |
| `TempCritical` | package > 90 °C | 1 min | **critical** | Stop the stack (`docker compose down`), let it cool |
| `ThermalThrottle` | `dmesg`/journal contains `cpu clock throttled` | any occurrence | **critical** | The box is losing performance silently; same remediation as `TempHot` |
| `FanDead` | `fan1_rpm == 0` while package > 55 °C | 5 min | **critical** | Fan stopped or seized; power down before it cooks |
| `NvmeHot` | NVMe `Composite` > 70 °C | 10 min | warning | Sustained writes (renders, builds) are throttling the disk |

Why duration matters: a single 82 °C sample during a render is normal. Five
minutes at 82 °C is a cooling failure. Alerts without a `for` clause page people
for transients and get muted.

## Memory

| Rule | Condition | For | Severity | Action |
|---|---|---|---|---|
| `OomKill` | any `Out of memory: Killed process` in kernel log | immediate | **critical** | Kill event is immediate truth. Capture the OOM dump (it names every process) before the journal rotates |
| `MemPressure` | PSI `memory some avg60` > 10 % | 5 min | warning | Something is stalling on reclaim |
| `MemStalled` | PSI `memory full avg10` > 5 % | 5 min | **critical** | The box is up but not working; stop batch work |
| `MemAvailableLow` | `MemAvailable` < 1.5 GiB | 5 min | **critical** | Below this, an encoder allocation can fail |
| `SwapGrowing` | `SwapFree` declining > 100 MiB/hour sustained | 1 h | warning | Leak or oversized batch job. On the audited baseline, swap used was 0.23 % and flat |
| `MarioConcurrent` | concurrent `mario` processes > 2 | 1 min | **critical** | See the incident below: this is the exact shape of the 2026-11-13 OOM |
| `ContainerNearLimit` | `container_memory_working_set / limit > 0.9` | 10 min | warning | The container will be killed soon; the limit is too tight or the workload grew |

`MarioConcurrent` is not a generic rule — it is this host's specific failure,
encoded. On 2026-11-13 at 17:23 UTC there were **67 distinct `mario` processes
alive at once**, each with the Kokoro model loaded (~120–140 MiB anon RSS plus
~1.6 GiB virtual), and the kernel OOM-killed globally.

## CPU and load

| Rule | Condition | For | Severity | Action |
|---|---|---|---|---|
| `LoadSustained` | `load1 / cores` > 1.0 | 15 min | warning | On 8 threads, load > 8 |
| `LoadCritical` | `load1 / cores` > 2.0 | 15 min | **critical** | Encoders will miss deadlines; find the offender |
| `CpuPressure` | PSI `cpu some avg60` > 25 % | 15 min | warning | Threads waiting for CPU |
| `ContainerRestartLoop` | restart count increases ≥ 3 in 15 min | — | critical | A crash loop; read `docker logs` and stop it rather than let it retry |

## Disk

| Rule | Condition | For | Severity | Action |
|---|---|---|---|---|
| `DiskHigh` | any mount > 85 % | 30 min | warning | Docker build cache is the usual culprit on this host: 21.1 GB of cache, 17.5 GB reclaimable, measured |
| `DiskCritical` | any mount > 95 % | 10 min | **critical** | Prune images/cache now; the stream needs room for segments and renders |
| `InodeHigh` | inode use > 85 % | 30 min | warning | Not a risk with ext4 here (1 % used) but btrfs snapshots change that |
| `DockerCacheGrowth` | build cache > 30 GB | 6 h | warning | Run `docker builder prune` — a build that runs on the host grows it forever |

## Services

| Rule | Condition | For | Severity | Action |
|---|---|---|---|---|
| `BoxDown` | dead-man heartbeat missing | 5 min | **critical** | Nothing else will fire. This is the rule that matters |
| `IcecastNoSource` | `icestats.source` absent | 2 min | **critical** | Liquidsoap disconnected: the URL answers but is silent |
| `AudioStalled` | `total_bytes_read` rate ≈ 0 while a source is connected | 60 s | **critical** | Encoder stalled |
| `GateOpen` | `GET /` without token returns anything but 404 | 5 min | **critical** | A Caddyfile change opened the door |
| `CaddyDown` | TCP 443 refuses / TLS fails | 2 min | critical | The only door |
| `CameraStale` | newest `.m3u8` older than 15 s | 2 min | warning | ffmpeg died or the USB camera dropped off the bus |
| `MarioStale` | newest `/data/host/*.wav` older than 2 h | 30 min | warning | TTS stopped producing; the station slowly runs out of voice |
| `IndiegenStale` | `state.json` mtime older than interval + 30 min | 30 min | warning | Rotation stopped; the library never changes again |
| `LibraryEmpty` | `*.flac` count in `music-audio` == 0, or `catalog.json` fails to parse | immediate | **critical** | The publish deleted before writing |
| `DeployFailed` | `data/deploy.log` contains `FALLO` | immediate | warning | A push deployed nothing |

## Dead-man switch

The only rule that survives a dead host. Configure the external check to expect
a ping every 60 s and to alert after 5 minutes of silence. Verify it once, on
purpose:

```bash
sudo systemctl stop radio-heartbeat.timer
# wait; confirm the external check actually pages
sudo systemctl start radio-heartbeat.timer
```

An unverified dead-man switch is decoration.

## What should NOT be automated

| Tempting automation | Why not |
|---|---|
| Restart the box when it is hot | The heat does not go away because the kernel changed |
| Raise a container's memory limit when it nears it | Converts a contained kill into a global OOM — this is exactly how 2026-11-13 happened |
| Auto-resume `indiegen` after an OOM | Renders are the memory peak; auto-resuming replays the failure at machine speed |
| Auto-restart `cam` in a loop | Without the device, it crash-loops and hides the real cause |
| Auto-prune Docker on a threshold | Can delete the image a running container needs; make it a scheduled task with a human reading the output |

## Safe to automate

| Automation | Bounded by |
|---|---|
| Restart `caddy`/`icecast` if unhealthy | max 3 attempts in 10 min, then stop and alert |
| Stop `cam`/`indiegen` above 80 °C | Once; do not restart until temperature is under 70 °C for 10 min |
| Controlled shutdown above 90 °C | Only after the alert has been sent |
| Prune build cache weekly | Off-peak, keep last 5 GB |
