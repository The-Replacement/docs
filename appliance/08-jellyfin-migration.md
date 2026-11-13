# 08 — Migrating Jellyfin and unrelated services off the appliance

**Deliverable 8.** What is on the box that has nothing to do with the radio, and
where it should go.

## Inventory (audited 2026-11-13)

| Workload | Type | Cost measured | Radio-related |
|---|---|---|---|
| `jellyfin` | container, `jellyfin/jellyfin:12.1.20260915` | 142 MiB idle; **unbounded** during a transcode (~2 GiB, all cores) | no |
| `searxng` | container + `searxng_searxng-cache` volume | ~100 MiB | no |
| `transmission-daemon` | systemd, web RPC on `0.0.0.0:9091` | ~20 MiB | no |
| Jellyfin EPG refresh | cron, daily 04:00, `~/.config/jellyfin-epg/` | small, but it is a second cron on the box | no |
| `cloudflared` | systemd, Cloudflare Tunnel | ~40 MiB | **yes** — this is the ingress |
| `searxng` volume, `~/media` (54 GB of shows) | disk | 54 GB of 93 GB used | no |

Note the asymmetry: the radio itself is ~400 MiB of containers. The unrelated
workloads are a similar order of magnitude at idle and **unbounded** at peak.
Jellyfin's transcode is the only process on this box that can legitimately take
every core and multiple gigabytes, and it does so on demand, on a schedule nobody
controls.

## Options

### Option 1 — Move to another always-on device (recommended)

| Target | Fit |
|---|---|
| A NAS that already runs 24/7 (Synology/QNAP) | Best. Jellyfin ships as a package, hardware transcoding on Intel NAS is good, storage is already there |
| A Raspberry Pi 5 with an SSD | Fine for direct play and light transcode (1080p H.264). 4K is not realistic |
| The workstation (not always-on) | Acceptable if you only watch when it is on; loses the "media server" property |
| A second-hand mini-PC (N100) | Best cost/benefit if there is no NAS: ~€150, quicksync, 24/7 power draw under 10 W |

Steps:

1. Stop the container on the appliance: `docker stop jellyfin && docker update --restart=no jellyfin`.
2. Copy the config and media: `~/servers/jellyfin` (config) and `~/media` (54 GB).
   Verify checksums before deleting anything.
3. Install Jellyfin on the target, point it at the same libraries.
4. Watch something on the target; confirm playback before removing the source.
5. Only then remove the volumes and the cron entry
   (`~/.config/jellyfin-epg/refresh-guide.sh`).

### Option 2 — Keep it, but cage it

If no second device exists yet and watching matters more than the stream's
latency:

```yaml
  jellyfin:
    cpus: 2.0
    mem_limit: 3g
    memswap_limit: 3g
    pids_limit: 512
    blkio_config:
      weight: 200          # below the radio's write path
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
```

Honest assessment: a 3 GiB cap does not stop a 4K transcode from being killed
mid-movie, and a killed transcode is a user complaint that arrives at the same
time as a stream stutter. Caging is a stopgap, not a design.

### Option 3 — Schedule Jellyfin

For a workload with a predictable usage pattern, run it on a schedule instead of
24/7: `systemd` timer that starts the container in the evening and stops it at
night. It does not remove the contention, it makes it predictable. Combine with
Option 2 if Option 1 is not available this month.

## Decision rule

The appliance has exactly one purpose. A service that is not part of the stream
either:

1. moves to a device that exists for it (Option 1), or
2. stays with hard caps and an explicit acceptance that it can degrade the
   stream (Option 2), or
3. stops being a 24/7 service (Option 3).

"Leave it as is, it has always worked" is not on the list. It is what the box was
doing on 2026-11-13 when 67 TTS renders and a global OOM took everything down at
once.

## What migrates with the radio regardless

- **`cloudflared`** stays: it is the ingress. If it leaves, the stream has no
  public path.
- **`chrony`, `unattended-upgrades`, `docker`, the journal** stay: they are the
  appliance's own services.
- **Nothing else** has a claim on this host by default.

## Storage note

54 GB of `~/media` on the same NVMe as the music library and Docker. Even after
Jellyfin moves, that media is dead weight on an appliance: if the disk fills, the
failure will look like a radio bug (segments can't be written, renders fail on
publish). Move the media with Jellyfin, or delete it.
