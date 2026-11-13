# 09 — Control and access

**Deliverable 9.** How a human reaches the box, how the box reaches the internet,
and what to do when neither works.

## Current state (audited 2026-11-13)

| Path | State |
|---|---|
| SSH | `kbdejavu@192.168.100.148:22`, public on `0.0.0.0`, key auth working |
| Public ingress | `cloudflared.service`, tunnel to Caddy; no router port forward |
| Player UI | Cloudflare Pages (`radio.daza.ar`) |
| LAN | Wi-Fi `wlp0s20f3` → `192.168.100.148/24`; wired `enp4s0` **down** |
| Power | AC connected, battery 97 % (a built-in UPS) |
| Deploy | `git push mainframe master` — currently **broken** (see below) |

## SSH

Minimum hardening, in this order:

```bash
# 1. Prove key auth works for a second, independent key BEFORE disabling passwords.
ssh -o PreferredAuthentications=publickey kbdejavu@192.168.100.148 'echo key-ok'

# 2. /etc/ssh/sshd_config.d/10-appliance.conf
#    PasswordAuthentication no
#    KbdInteractiveAuthentication no
#    PermitRootLogin no
#    MaxAuthTries 3
sudo sshd -t && sudo systemctl reload ssh
```

Then decide the exposure. Three levels:

| Level | How | When |
|---|---|---|
| LAN only | `ufw` deny `22` except `192.168.100.0/24` | The laptop is on the same LAN |
| Overlay network | Tailscale (managed, NAT traversal) or WireGuard (self-hosted) | Control from anywhere, no port forward, no public SSH |
| Public SSH | never | — |

**Recommendation: Tailscale.** The box already depends on `cloudflared` for
ingress; adding a second managed component of the same kind is consistent, and
it removes SSH from the LAN surface entirely. WireGuard is the right choice if
the goal is to depend on no third party — it costs a key exchange instead of an
account.

Absolute rule: **no SSH port forward on the router.** The tunnel exists precisely
so the origin is not addressable from the internet. A single-purpose box with a
token-gated door and an SSH port open to the world is one credential-stuffing
campaign away from being someone else's proxy.

## The deploy path is broken right now

Verified on the host:

```
HEAD detached at b6d0328
refs/heads/master 005b013
receive.denyCurrentBranch updateInstead
```

`updateInstead` only moves a **checked-out branch**. With a detached HEAD there
is no checked-out branch, so a push updates `master` and leaves the working tree
where it was. The `post-receive` hook still runs — on the old tree — rebuilds
images from old code, and logs "deploy listo".

Evidence: `data/deploy.log` shows a successful deploy at 2026-11-13T19:50Z, but
the working tree is at `b6d0328` while `master` is `005b013`.

Fix on the host (one command, after confirming nothing is mid-deploy):

```bash
cd ~/servers/radio
git status                       # expect: clean
git checkout master              # reattach; content identical to b6d0328's tree? verify
git log --oneline -3
```

If the trees differ, `git checkout` refuses — then the box has local changes and
the right move is to stash or diff them first, never to force.

Add a guard so this cannot recur silently. In `post-receive`, before anything
else:

```sh
if ! git symbolic-ref -q HEAD >/dev/null; then
  log "FAIL: HEAD is detached; updateInstead cannot move the worktree. Deploy did nothing."
  exit 1
fi
```

## Safe operation over SSH

```bash
# read the deploy result, not the exit code of the push
tail -40 ~/servers/radio/data/deploy.log

# restart one service (never `up -d` for a rollback)
docker compose -f ~/servers/radio/docker-compose.yml restart caddy

# stop the two non-audio services to shed load
docker compose -f ~/servers/radio/docker-compose.yml stop cam indiegen
```

Never run `docker compose down` to "clean things up". It is the emergency action
for thermal runaway, not routine maintenance.

## Power and auto-restart

The ThinkPad's battery is the UPS: at audit, AC connected and battery at 97 %,
so a short outage does not interrupt the stream. Two settings make that a
deliberate property:

```bash
# Keep the battery out of the "sitting at 100% on mains" regime (ThinkPad):
ls /sys/class/power_supply/BAT0/charge_control_*
# start~40, end~80 is the usual longevity setting

# Resume after power loss is a firmware setting:
#   BIOS -> Power -> "After Power Loss: Power On"
# Verify by unplugging the box for 30 s, not by trusting the menu.
```

Laptop lid behaviour matters too: the audit reports `lid: open`. If the box is
ever closed, `systemd-logind` will suspend it on lid close unless configured not
to. Keep it open, or set `HandleLidSwitch=ignore` in `logind.conf` and **verify
the thermal story with the lid closed before trusting it** — a closed lid over a
keyboard that is the intake is the single most likely cause of a repeat.

## Out-of-band access

There is no IPMI, no BMC, no serial console: it is a laptop. Out-of-band means
physical. Therefore:

1. **Never deploy on a Friday evening** or before leaving the house.
2. **Always leave the box in a state that survives a power cut**: containers with
   `restart: unless-stopped`, `cloudflared` enabled, no pending manual step.
3. **A Wi-Fi-only host has no remote recovery.** If the stream dies because the
   AP rebooted, nothing reaches the box. Wired Ethernet is the mitigation, and it
   is a cable — no amount of software fixes it.

## Boot-time inventory, printed once per boot

The single most useful control measure on a headless box that failed once:
a summary at boot, in the journal and in the heartbeat payload.

```ini
# /etc/systemd/system/radio-boot-report.service
[Unit]
Description=Radio appliance boot report
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/radio-boot-report
```

The script prints: kernel version, current deployed commit **and whether HEAD is
attached**, container states, temperatures, `MemAvailable`, disk free, and the
last five lines of `data/deploy.log`. On this host, that report would have shown
the detached HEAD weeks earlier.

## Access checklist

- [ ] Key-only SSH, root login disabled
- [ ] SSH reachable over Tailscale/WireGuard or LAN only — not the internet
- [ ] No router port forward; ingress through the tunnel only
- [ ] Deploy HEAD reattached and guarded in `post-receive`
- [ ] Battery charge threshold set; BIOS "power on after loss" verified by test
- [ ] Lid-close behaviour decided and thermally verified
- [ ] Boot report installed, including the deploy state
