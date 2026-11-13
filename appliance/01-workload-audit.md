# 01 — Workload audit and isolation

**Deliverable 1.** The script is
[`infra/deploy/audit-mainframe.sh`](https://github.com/The-Replacement/infra/blob/main/deploy/audit-mainframe.sh).
This document says what to do with its output.

## Why an audit and not a compose file

`docker-compose.yml` describes six services. It says nothing about:

- Jellyfin, and whether anything else has been installed since
- cron jobs that shell into containers (`restart-on-signal.sh` runs every minute)
- systemd timers, snap packages, or a second Docker socket
- what is listening on the LAN that nobody remembers opening
- which directory is eating the disk

The host failed as a **whole machine**, so the machine is the unit of audit.

## Running it

Read-only, no root:

```bash
scp infra/deploy/audit-mainframe.sh kbdejavu@192.168.100.148:
ssh kbdejavu@192.168.100.148 'bash ~/audit-mainframe.sh' > audit-$(date +%F).txt
```

Or without copying the file:

```bash
ssh -t kbdejavu@192.168.100.148 'bash -s' < deploy/audit-mainframe.sh > audit.txt
```

Run it **after ten minutes of idle**, so the numbers are the machine's baseline
and not the tail of boot. Run it a second time while the radio is streaming;
the difference between the two runs is the radio's real cost.

What each section is for:

| Section | Question it answers |
|---|---|
| `host`, `cpu` | What is this machine, and how many threads does it actually have? `Thread(s) per core` matters more than the model name when sizing encoders. |
| `memory`, `pressure` | How close to the edge does it run *idle*? PSI `full` above zero means work is already stalling on memory. |
| `thermal` | The temperature band, the trip points, and **throttle events this boot**. A box that throttles at idle is a cooling problem, not a workload problem. |
| `disk` | Full disk is the failure that takes the box down slowly. Lua inodes fill silently on btrfs snapshots. |
| `systemd` | Every non-obvious service. This is where "other unidentified workloads" get names. |
| `processes` | Top CPU, plus every process with a non-zero `oom_score_adj` — the previous operator may already have protected something. |
| `docker` | Containers, images, volumes, and **limits** (`unlimited` on every line means the kernel decides who dies). |
| `network` | Listening ports. Anything listening on `0.0.0.0` is reachable from the LAN, whatever the firewall was supposed to do. |
| `scheduled work` | Cron and timers. The radio itself depends on two cron entries; anything else scheduled is a competitor for the same cores. |
| `packages` | Manual package count is a proxy for how much of the box is incidental. Debian's `apt-mark showmanual` is the honest list. |

## Classification

Every workload lands in exactly one bucket. The bucket decides the action, not
the operator's mood.

| Bucket | Definition | Action |
|---|---|---|
| **Radio-critical** | Without it there is no stream: `liquidsoap`, `icecast`, `caddy`, `cam`, `mediamtx`, `indiegen` | Stays. Gets CPU and memory reservations. |
| **Radio-adjacent** | The radio survives without it, but degrades: `mario` (host voice), monitoring agent, backup job, log shipping | Stays, capped, scheduled off the stream's critical path. |
| **Unrelated** | Nothing to do with the stream: Jellyfin (and its transcodes), searxng, archive, personal services | Leaves. See [08-jellyfin-migration.md](08-jellyfin-migration.md). |
| **Unknown** | Anything the audit found that nobody can name | Investigate before powering the stack up. An unnamed service is an unnamed failure mode. |

## Decision rules that avoid the argument

1. **A service that transcode video does not live with a service that encodes
   audio.** Jellyfin's transcode is bursts of every core; Liquidsoap's encoder
   is a real-time deadline. One of them loses, and it is whichever one the
   scheduler picked that second.
2. **Anything with a web UI for a human belongs somewhere a human is.** Jellyfin
   is watched on a TV; the radio is not watched.
3. **If it needs a port on the LAN, ask who opens it.** The radio publishes
   exactly one door. Every additional listener is an additional reason the host
   cannot be rebooted at 3 a.m.
4. **Two of the same kind is a pattern, not a coincidence.** Two media servers,
   two reverse proxies, two Docker sockets: pick one.

## When something is "probably needed"

The audit will surface services nobody remembers installing. The test is not
"might it be useful" — it is:

```bash
# 30 days of evidence, or it is not used
journalctl -u <unit> --since '30 days ago' | wc -l
docker logs --since 720h <container> 2>&1 | wc -l
```

A unit with no log lines in 30 days is not a service, it is a liability. Stop it,
disable it, and leave a note in this document. If it was needed, the note gets
corrected in a week; if it was not, the box has one fewer thing to keep warm.

## Output of this deliverable

Filled from the first real audit, 2026-11-13 21:59 UTC:

| Workload | Bucket | CPU (idle) | RSS | Disk | Ports | Decision |
|---|---|---|---|---|---|---|
| `radio-liquidsoap` | critical | 8.9 % | 67 MiB | — | none | stays |
| `radio-icecast` | critical | 0.3 % | 2.8 MiB | — | 8000 (internal) | stays |
| `radio-caddy` | critical | 0.0 % | 13 MiB | — | 8090, 8443 | stays — the door |
| `radio-mediamtx` | critical | 0.0 % | 13.9 MiB | — | 8189/udp (loopback) | stays |
| `radio-cam` | critical | (not running) | (not running) | — | — | stays; the largest unmeasured CPU cost |
| `radio-indiegen` | adjacent (batch) | 0.01 % | 84 MiB | writes `music*` | none | candidate to move to the workstation |
| `mario` (cron) | adjacent (batch) | — | **340–535 MiB** peak | writes `data/host` | none | cap concurrency now; move later |
| `cloudflared` | required (ingress) | 0.5 % | 41 MiB | — | outbound | stays |
| `jellyfin` | **unrelated** | 0.01 % | 142 MiB idle, ~2 GiB transcode | 54 GB media | 8096 loopback | moves off — [08](08-jellyfin-migration.md) |
| `searxng` | **unrelated** | 0.0 % | 100 MiB | volume | 8080 | moves off |
| `transmission-daemon` | **unrelated** | 0.2 % | 21 MiB | media | 9091, 51413 | disable |
| Jellyfin EPG cron | **unrelated** | — | — | — | — | remove with Jellyfin |
| `systemd-networkd-wait-online` | broken | — | — | — | — | failed every boot; mask |

Two rows deserve emphasis: the entire radio stack is **181 MiB**, and the only
process on the box that has ever demonstrably taken it down is `mario` — 67
concurrent instances of a ~120 MiB TTS render.

Nothing in this table is guessed except the `cam` row, which is marked
`(not running)` because there is no camera attached to the box at audit time. It
stays `ESTIMATED` until the camera is connected and `measure-runtime.sh` runs
with it.

