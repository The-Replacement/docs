# 06 — Appliance hardening

**Deliverable 6.** Turning a general-purpose Ubuntu install that happens to run
the radio into a box whose only job is the radio.

## What the audit found

| Item | Finding |
|---|---|
| OS | Ubuntu 26.10, kernel 7.3.0, UEFI, headless |
| CPU | i7-1165G7, 4C/8T, governor `powersave` |
| RAM | 32 GiB, 8 GiB **disk** swap, no zram |
| Disk | 914 GB NVMe, 93 GB used (11 %), 21.1 GB of Docker build cache |
| Installed | 736 packages, 28 manually installed |
| Snaps | `core24`, `snapd`, `hwctl` |
| Services | `docker`, `containerd`, `cloudflared`, `transmission-daemon`, `ModemManager`, `multipathd`, `wpa_supplicant`, `netplan-wpa`, `bolt`, `chrony`, `unattended-upgrades` |
| Containers | 7 radio + `jellyfin` + `searxng` |
| Failed unit | `systemd-networkd-wait-online.service` (Wi-Fi + netplan mix) |
| Cron | Jellyfin EPG refresh (daily), radio watcher (every minute), Mario refresh (every hour) |
| Exposed ports | `22`, `8090`, `8443` (radio door), `8080` (searxng), `9091` + `51413` (transmission), `8096` loopback-only (Jellyfin) |

736 packages is not a minimal server; 28 manual installs is not a mess either.
The box is **not** a bloated desktop, and the problem was never "too many
packages". Keep that in perspective before ripping things out.

## What to remove, in order of value

### 1. The unrelated workloads (biggest win, zero risk to the radio)

```bash
docker stop jellyfin searxng && docker update --restart=no jellyfin searxng
sudo systemctl disable --now transmission-daemon
```

`transmission-daemon` listening on `0.0.0.0:9091` with a web RPC is the largest
unnecessary exposure on the LAN, and it is not part of the radio. Jellyfin and
searxng are memory and CPU that the appliance cannot attribute during an
incident. See [08-jellyfin-migration.md](08-jellyfin-migration.md).

### 2. Hardware-specific services that a headless appliance does not need

```bash
sudo systemctl disable --now ModemManager     # no cellular modem in use
sudo systemctl disable --now bolt             # Thunderbolt daemon
```

`multipathd` is harmless but pointless without SAN storage; leave it if unsure —
disabling storage daemons is the kind of change that bites weeks later.

Do **not** remove `wpa_supplicant`/`netplan`: the box is on Wi-Fi (`wlp0s20f3`),
and the wired interface `enp4s0` is DOWN. Wi-Fi on an always-on streaming host is
a separate risk — see below.

### 3. Snap packages

`hwctl` is a hardware-control snap (fan/power bits) installed from a
certification channel. It is doing nothing for the radio. Remove it if the fan
curve is managed by the firmware:

```bash
sudo snap remove hwctl
```

### 4. The failed unit

`systemd-networkd-wait-online` fails every boot because netplan drives
`wpa_supplicant` while `networkd` waits for a link it will never own. It is noise
that trains you to ignore red units:

```bash
sudo systemctl disable systemd-networkd-wait-online.service
# or mask it, if the appliance has no dependency on "network online"
```

## What to add

### zram instead of disk swap

Currently: an 8 GiB `/swap.img` on the NVMe, 0.23 % used. On an SSD, disk swap
turns a memory spike into minutes of I/O thrash; the box looks alive and serves
nothing.

```bash
sudo apt install zram-tools      # provides /etc/default/zramswap
# /etc/default/zramswap
#   ALGO=zstd
#   PERCENT=25          # 8 GiB of compressed RAM on a 32 GiB box
sudo swapoff /swap.img
sudo sed -i '/swap.img/d' /etc/fstab
sudo systemctl enable --now zramswap
```

Keep the disk swap **disabled** for a real-time encoder host: the audio path
must never wait on a disk. If a cushion is wanted for batch jobs, cap it at 2 GB
and set `vm.swappiness=10`.

### CPU governor

`powersave` on all eight threads. For a box whose job is a real-time encoder,
`powersave` is defensible (lower heat, and the encoder needs ~10 % of a core),
but it also means bursty work — builds, renders, TTS — takes longer and keeps
the box at high load for longer. The tradeoff is real:

```bash
# measure both before deciding, do not guess
sudo cpupower frequency-set -g performance   # run a render, watch temps
sudo cpupower frequency-set -g powersave
```

On the audited box, idle package temperature is 42 °C with the fan **off**,
which means there is thermal headroom. `powersave` is fine; the fan curve
matters far more.

### journald and log caps

```bash
# /etc/systemd/journald.conf
#   SystemMaxUse=1G
#   SystemMaxFileSize=100M
#   MaxRetentionSec=1month
sudo systemctl restart systemd-journald
```

Container logs are unbounded by default. In `docker-compose.yml`, per service:

```yaml
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }
```

`liquidsoap --verbose` writes a lot; without a cap it is the fastest-growing file
on the disk.

### unattended-upgrades with a policy

Already active. Confirm it does not reboot on its own — an unattended reboot mid
stream is an outage nobody attributes to updates:

```bash
grep -E 'Automatic-Reboot' /etc/apt/apt.conf.d/50unattended-upgrades
# Automatic-Reboot "false";
```

Nine pending upgrades at audit time. Reboots are a scheduled, announced action.

### A read-only root is NOT recommended here

It is the standard advice for appliances, and it is wrong for this one:

- Docker writes to `/var/lib/docker` constantly; a read-only root means a large
  writable overlay for exactly the parts that grow.
- The radio writes `music/`, `music-audio/`, `data/` on bind mounts.
- The deploy model is `git push` into a working tree on the host.

The security gain is real but small (the box is on a LAN, behind a tunnel, with
one door), and the operational cost is a new class of "why did the write fail"
incident. Prefer: minimal packages, no unrelated services, a firewall, and a
user that is not root for Docker access.

## Network exposure, which matters more than packages

Measured listeners: `22`, `8080` (searxng), `8090`/`8443` (radio), `9091`/`51413`
(transmission), plus WireGuard-less Wi-Fi on `192.168.100.148`.

For a single-purpose appliance, the target is:

| Port | Should be |
|---|---|
| `22` | LAN only, or Tailscale/WireGuard only |
| `8090`/`8443` | LAN only — the public path is the Cloudflare Tunnel (`cloudflared.service`) to Caddy |
| `8080`, `9091`, `51413` | gone (services removed) |

`ufw` with a default-deny inbound, allowing `22` and the tunnel's needs, is the
minimum. The `cloudflared` tunnel is the reason there is no port forward on the
router — keep it that way.

**Wi-Fi is the remaining structural weakness.** The wired NIC is down; the box
streams over `wlp0s20f3`. A stream that depends on Wi-Fi is a stream that dies
when the microwave runs. If a cable can reach the box, run the cable before
anything else in this document.

## Checklist

- [ ] Unrelated containers stopped and `restart=no`
- [ ] `transmission-daemon` disabled
- [ ] Unused hardware daemons disabled (`ModemManager`, `bolt`, optional `hwctl` snap)
- [ ] `systemd-networkd-wait-online` masked
- [ ] zram enabled, disk swap disabled
- [ ] `journald` capped; container log rotation set
- [ ] `unattended-upgrades` configured, auto-reboot off
- [ ] `ufw` default deny; only the door and SSH reachable
- [ ] Wired Ethernet if physically possible
