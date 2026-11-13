# 07 — Topology

**Deliverable 7.** One recommended architecture, three alternatives, and the
measurements behind the choice.

## What the box actually is

Measured 2026-11-13:

| | |
|---|---|
| CPU | i7-1165G7 — 4 cores / 8 threads, 4.7 GHz boost, 12 MiB L3 |
| RAM | 32 GiB, **4.3 % used at rest**, 30.5 GiB available |
| Disk | 914 GB NVMe, 11 % used |
| Thermal | 42 °C package at idle, fans at 0 RPM, trip points at 110 °C |
| Network | Wi-Fi only (`wlp0s20f3`), wired NIC down |
| Form factor | a ThinkPad laptop |

That last row reframes two things:

1. **Memory was never the constraint.** 32 GiB with everything running uses
   ~400 MiB. The OOM of 2026-11-13 was 67 concurrent TTS renders, not a machine
   that is too small.
2. **The battery is a built-in UPS.** At audit, AC connected, battery at 97 %
   and fully charged. A short power cut does not stop the stream. That is a
   feature worth preserving deliberately (charge threshold, keep it plugged),
   not a coincidence to ignore.

## Recommended: Compose on the host, with limits and one external signal

```
                    Internet
                        |
              Cloudflare (Pages: UI, Tunnel: ingress)
                        |
        +---------------|------------------ LAN 192.168.100.0/24
        |               |
  [ mainframe: Docker Compose ]
   caddy  icecast  liquidsoap  mediamtx  cam  indiegen  mario(on demand)
        |
        +-- alloy -> remote TSDB (metrics)
        +-- systemd timer -> external dead-man check
        +-- zram swap, no disk swap
        +-- per-service mem/cpu limits
```

Why this and not something more elaborate:

- The stack is **6 containers on one host** with a linear dependency order. A
  scheduler adds a control plane, an API server and a reconciliation loop to a
  box whose job is to encode one audio stream. Kubernetes' own components cost
  more RAM than the radio stack.
- The failure mode we are fixing is **unbounded concurrency**, and cgroup limits
  are the direct tool for it. Compose exposes them (`mem_limit`, `cpus`,
  `pids_limit`). Nothing else is needed.
- The deploy model (`git push` → hook) stays. It is the one thing on this box
  that works reliably and needs no new dependency.

Required changes to the current Compose, in priority order:

1. `mem_limit` + `memswap_limit` per service ([02](02-resource-budget.md)).
2. `pids_limit` — a fork storm is how the box died; `pids_limit: 256` per
   container turns it into a failing container instead of a dead host.
3. Container log rotation (`max-size: 10m`).
4. Resource guards on `indiegen` and `mario` specifically: they are the memory
   peaks, and `mario` must never run twice at once (a lock plus a hard cap).

## Alternative A — Proxmox with two VMs (radio + monitoring)

**Idea:** blast-radius isolation. A runaway transcode or a botched upgrade cannot
take the stream with it; snapshots make rollback trivial.

**Cost on this hardware:** Proxmox VE itself ~1 GiB, plus a second kernel and
userspace per VM. The radio VM would need the camera device passed through USB
(workable, adds a failure path). You would give up ~10–15 % of the box's memory
and gain an abstraction layer between the encoder and the device.

**Verdict:** the right answer if this box also had to host a NAS or several
tenants. For one radio stack and one monitoring agent, it buys isolation the
limits already provide, at the price of a second OS to maintain. **Not
recommended** for this host, **recommended** if the box is ever repurposed again
(it is exactly what stops "one box that runs everything" from recurring).

## Alternative B — k3s

**Idea:** resource control via requests/limits, self-healing, declarative
deploys.

**Cost:** k3s idles around 500–700 MiB with its datastore. The audio path
(Liquidsoap with a real-time deadline) would run under a scheduler that may evict
or reschedule it. USB camera device plugins are a known pain. Every benefit it
offers is already available from systemd + Compose on one host.

**Verdict:** rejected. This is a single-node appliance, not a fleet.

## Alternative C — Podman rootless

**Idea:** no daemon, rootless by default, systemd-native (`podman generate
systemd`, Quadlet).

**Cost:** a real migration for a stack that currently works; `docker compose`
files are mostly compatible but the ecosystem assumptions (healthchecks, socket
paths, `docker exec` in the runbooks) all change. Rootless container networking
for the camera device and for privileged ports adds friction to a stack that has
already been hardened the other way (cap_drop, non-root users, `NET_BIND_SERVICE`).

**Verdict:** a genuine improvement in security posture, and **not** worth doing in
the same window as a thermal/OOM crisis. Revisit after the stack is stable.

## Service split

| Component | Where it must run | Why |
|---|---|---|
| Liquidsoap, Icecast | appliance | The audio path has a real-time deadline; latency to the host is the product |
| Caddy | appliance | It is the door in front of the stream on the same host |
| MediaMTX + camera encode | appliance | The USB device is physical; encoding must be next to it |
| `indiegen` render | appliance today, **workstation tomorrow** | The render is CPU-bound and heavyweight. It produces files; files travel. Moving it off the appliance removes the biggest scheduled memory peak |
| `mario` TTS | appliance today, workstation-friendly | Same argument as the render, and it is the process that caused the OOM |
| Player UI (`web/`) | Cloudflare Pages | Already there. A UI has no business behind a box that overheats |
| Ingress | Cloudflare Tunnel | Already there. No port forward, no exposed origin IP |
| Metrics evaluation and alerting | outside the box | A dead box cannot report its own death |
| Backups | outside the box | Pull, never push |

The interesting conclusion: **the two jobs that killed the box are the two that
do not need to be on it.** Rendering and TTS are batch jobs with file outputs.
They can run on a workstation on the same LAN and publish into `music-audio/`
and `data/host/` — the appliance only has to serve what is already there.

## Scaling path

| Symptom | Next step |
|---|---|
| Renders starve the stream | Move renders to the workstation (above). No hardware purchase |
| One camera at 1080p is the CPU ceiling | Drop to 720p30 and `-preset veryfast`; x264 is the lever, not cores |
| Two cameras needed | This CPU (4C/8T Tiger Lake) can hold one encode plus audio comfortably, two is a regression risk. Add an edge box for the second camera and ship segments over the LAN |
| Library outgrows the disk | 914 GB is ~10 GB/1000 tracks at FLAC; not a near-term problem. External USB SSD before a new machine |
| Everything is fine but the box is 5 years old | The replacement is any 8-thread mini-PC with 16 GiB and an SSD. Nothing here needs a server |

## The one-sentence recommendation

Keep Docker Compose on this host, add cgroup limits and zram, move the two batch
jobs (render, TTS) off the appliance, and put alerting outside it — in that
order.
