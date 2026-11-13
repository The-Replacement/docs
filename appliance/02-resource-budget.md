# 02 — Resource budget

**Deliverable 2.** What each service costs, what it should be allowed to cost,
and how to enforce it.

## Measured on the host itself

`docker stats --no-stream` from `audit-mainframe.sh`, 2026-11-13 21:59 UTC, four
minutes after boot, stack up and streaming:

| Container | CPU | Memory | % of 30.55 GiB |
|---|---|---|---|
| `radio-indiegen` | 0.01 % | 84 MiB | 0.27 % |
| `radio-caddy` | 0.00 % | 13.1 MiB | 0.04 % |
| `radio-liquidsoap` | 8.93 % | 67.3 MiB | 0.22 % |
| `radio-mediamtx` | 0.00 % | 13.9 MiB | 0.04 % |
| `radio-icecast` | 0.32 % | 2.8 MiB | 0.01 % |
| `searxng` (unrelated) | 0.00 % | 99.6 MiB | 0.32 % |
| `jellyfin` (unrelated) | 0.01 % | 142.4 MiB | 0.46 % |

**Total for the entire radio stack: 181 MiB and ~9 % of one core**, on a box with
32 GiB. Host load average at that moment: 0.47 on 8 threads.

This settles the question the box was shut down over: **the radio stack is not
memory-hungry.** See [03](03-thermal-and-memory.md) for what actually consumed
the memory.

Two other measured facts that belong in a budget:

- Docker build cache: **21.1 GB**, of which 17.5 GB reclaimable — the residue of
  image builds running on the host.
- Disk: 93 GB used of 914 GB (11 %). Disk is not a constraint; the build cache is
  the only thing that grows without a ceiling.

## Measured baselines (second host, same images)

Measured with `infra/deploy/measure-runtime.sh` on a workstation (i5-6300U,
16 GB) running the **same pinned images**, Liquidsoap streaming, no camera.
Method: 15 samples, 2 s apart. Included because it samples over time instead of
a single instant.

| Container | Image | Mean CPU | Peak CPU | Peak RSS |
|---|---|---|---|---|
| `radio-caddy` | `caddy:2-alpine` | 0.1 % | 1.3 % | **15.1 MiB** |
| `radio-icecast` | `build: ./icecast` | 1.2 % | 7.2 % | **2.1 MiB** |
| `radio-liquidsoap` | `savonet/liquidsoap:v2.4.6` | 7.2 % | 8.2 % | **71.3 MiB** |
| `radio-mediamtx` | `bluenviron/mediamtx:1.21.2` | 0.0 % | 0.0 % | **8.9 MiB** |

Memory is the reliable part of this table: RSS for a fixed workload does not
depend on the CPU model. CPU percentages are single-core percentages on a
dual-core Skylake laptop and should be treated as an order of magnitude, not a
target.

What the numbers say, before anything else:

- **The serving path is almost free.** Caddy + Icecast + MediaMTX together are
  under 30 MiB. This is not what ran the box out of memory.
- **Liquidsoap at 7 % of a laptop core** is the real-time audio path with MP3
  encoding. It is not the problem either.
- **The memory went somewhere else.** Either the camera encoder, TTS, image
  builds, Jellyfin transcodes, or several of them at once.

## Not measured — and why

| Workload | Status | Basis for the estimate |
|---|---|---|
| `cam` (ffmpeg → H.264) | **ESTIMATED** 1.0–2.0 cores at 720p30, 300–600 MiB | x264 `veryfast` at 720p30 is roughly one core on Haswell-era hardware; `-preset` and `-crf` in `cam/capture.sh` decide the multiple. Verify with `docker stats` while the camera runs. |
| `mario` (Kokoro ONNX TTS) | **MEASURED from the OOM dump** ~340–535 MiB anon RSS, 1.6 GiB virtual per instance | The kernel's OOM dump on 2026-11-13 lists each `mario` with `total-vm ~1 620 000 kB`. That is the real per-instance cost — and it is why 67 of them at once took the box down. |
| `indiegen` render | **ESTIMATED** ≤ 1.5 GiB, 1 core, ~7 min per cycle | The generator streams arrays specifically to stay under 1.5 GB (`README.md`); single-threaded, BLAS pinned to one thread, 10 tracks per 6 h cycle. Idle container footprint measured: 84 MiB. |
| Jellyfin | **UNKNOWN** | Depends entirely on whether something triggers a transcode. That is the point: it is unbounded by nature. |

## The budget

Requests are what the service needs to work. Limits are what it is allowed to
take before the kernel says no. The gap between them is headroom for a burst,
not a promise.

| Service | CPU request | CPU limit | Mem limit | Notes |
|---|---|---|---|---|
| `icecast` | — | 0.5 | 128 MiB | Serving is cheap; the limit only catches a runaway. |
| `liquidsoap` | 0.25 | 1.0 | 512 MiB | Real-time deadline. Never starve it with a lower CPU share. |
| `caddy` | — | 0.5 | 256 MiB | Holds TLS state and file handles, not buffers. |
| `mediamtx` | — | 0.5 | 256 MiB | WebRTC buffers per viewer; the number to watch is viewer count. |
| `cam` | 1.0 | 2.0 | 768 MiB | The one that actually needs cores. `-preset` is the lever. |
| `mario` | 0.5 | 1.5 | 1.5 GiB | Hourly, exits. The peak is a model load, not a leak. |
| `indiegen` | 1.0 | 1.5 | 2 GiB | Single render thread; 1.5 GiB is the design target, the 2 GiB limit is the guard rail. |

Sum of limits is deliberately **above** the machine's RAM. Limits are a
containment device, not a partition: two services are never at their peak at the
same moment unless something is wrong, and if they are, the box should degrade,
not die.

Sum of *requests* is what the box must actually have free. With the table above:
2.75 cores and 4.2 GiB before the OS, plus whatever monitoring costs (see
[04-monitoring-architecture.md](04-monitoring-architecture.md)).

## How to enforce it

Docker Compose, no orchestration needed:

```yaml
services:
  cam:
    cpus: 2.0                 # hard ceiling, Docker maps this to cpu.max
    mem_limit: 768m           # hard ceiling; OOM-kills this container, not the host
    memswap_limit: 768m       # no swap for it: swapping a real-time encoder is worse than failing
    pids_limit: 256           # fork bomb containment
    cpu_shares: 2048          # relative weight when contended (default 1024)
```

Three nuances that decide whether this helps or hurts:

1. **`memswap_limit == mem_limit`** prevents the container from swapping. For
   Liquidsoap and the camera encoder that is correct: a swapped encoder misses
   its deadline anyway, and the swap traffic is what makes the whole box crawl
   before the OOM killer arrives. For `mario` and `indiegen` (batch work), swap
   is acceptable if it exists at all — see [03](03-thermal-and-memory.md).
2. **`cpus` is per-container, not a reservation.** `cpu_shares` is what decides
   who wins a contention. Give Liquidsoap a high share and a modest ceiling.
3. **A limit that is too tight is a new failure mode.** If Liquidsoap is capped
   at 256 MiB it will be killed mid-track on a library rotation. Set the limit
   from the measured peak times 2, not from an aspiration.

## Scheduling the heavy jobs

The three expensive things on this box are not steady-state; they are bursts.
Bursts are a calendar problem.

| Job | Trigger today | Problem | Change |
|---|---|---|---|
| `docker compose build mario` (and `cam`) | `post-receive` on the host, on every code push | An image build competes with the live encoder for RAM and disk I/O. It can happen at any time, including during a library rotation. | Build on a workstation, push the image, or at minimum run the build with `nice`/`ionice` and a build-time `mem_limit` (BuildKit supports it). |
| `indiegen` render | Every 6 h (`INDIEGEN_INTERVAL_SECONDS=21600`), 10 tracks, ~7 min | Fine, unless it lands on top of a TTS run or a Jellyfin transcode. | Keep the 6 h interval; align the hourly TTS cron away from the render window. |
| `mario` refresh | Hourly cron | Peak memory is a full model load. | Hourly is fine; make sure it never overlaps the render. A 7-minute window every 6 hours is easy to avoid. |

A simple alignment rule: renders at `:00` every 6 h, TTS at `:15` past odd
hours. Two lines of cron, and the two memory peaks never meet.

## Verification, after the caps are in

```bash
# every running container reports a limit
docker inspect $(docker ps -q) \
  --format '{{.Name}} mem={{.HostConfig.Memory}} cpus={{.HostConfig.NanoCpus}}'

# nothing was OOM-killed in the last 24h
journalctl -k --since '24 hours ago' | grep -i 'killed process'

# the reservations actually hold under load
./deploy/measure-runtime.sh 300
```

The budget is wrong until a measurement agrees with it. If `cam` peaks at
1.9 cores against a 2.0 limit, the next camera firmware update will push it over.
