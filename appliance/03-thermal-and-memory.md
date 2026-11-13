# 03 — Thermal and memory: analysis and runbooks

**Deliverable 5.** Why the box got hot and ran out of memory, what to watch, and
what to do at 3 a.m.

This is the document that matters most, because the failure already happened
once and the machine is the same machine.

## Part 1 — Thermal

### How a small always-on box overheats

Four mechanisms, in the order they are usually guilty:

1. **Dust.** A 1–2 mm felt layer on a heatsink fin stack cuts airflow far more
   than it looks like it should. It builds over months; the failure arrives as a
   sudden "it was fine last week".
2. **Airflow, not fan count.** A box in a closed shelf, or with its intake
   against a wall, recirculates its own exhaust. Ambient inside the case can sit
   10–15 °C above the room.
3. **Sustained load at a burst thermal design.** Consumer coolers are specified
   for boost bursts. Six containers, an encoder with a real-time deadline and an
   hourly TTS peak is *sustained*. The cooler was never asked to do this.
4. **Thermal paste and mounting.** After 3–5 years, paste pumps out and dries.
   Idle temperatures creep up 5–10 °C, and nobody notices because nothing was
   measuring them.

None of these is fixed by software. Software decides **whether you find out in
time**.

### What the host actually measures

Audited 2026-11-13, four minutes after boot, stack streaming, no camera:

| Reading | Value |
|---|---|
| Package (`coretemp`) | 42 °C |
| Cores | 39–40 °C |
| NVMe composite | 24.9 °C |
| Fan 1 / fan 2 | **0 rpm** |
| Trip points | 110 °C (TCPU zone), `crit` 100 °C (coretemp) |
| Thermal throttle events, previous boot | **none found** |

The fan being off at 42 °C is correct behaviour, not a fault. It also means the
previous shutdown is **not explained by the thermal log**: the journal for that
boot contains no `cpu clock throttled`, no critical-temperature trip. If the box
felt hot, the kernel did not see it — which makes ambient airflow, a closed lid
over the intake, or dust the things to inspect physically, and makes
`ThermalThrottle` the alert that will settle the argument if it recurs.

### Temperature bands for 24/7 operation

For consumer Intel/AMD desktop silicon (`coretemp`, `k10temp`), package
temperature:

| Band | Range | Meaning | Action |
|---|---|---|---|
| Normal | < 60 °C | Fine indefinitely | none |
| Warm | 60–70 °C | Sustained but acceptable | watch the trend |
| Hot | 70–80 °C | Cooling is marginal for 24/7 | clean, improve airflow, lower the clock ceiling |
| Critical | > 80 °C sustained | Throttling will start; the box is being damaged slowly | act now, not tomorrow |
| Shutdown | ≥ 95–100 °C (`crit`) | Hardware protection | the box will protect itself by dying |

Two things this table does not cover:

- **NVMe drives.** `Composite` above 70 °C under sustained write throttles hard.
  Relevant here: the music library is rewritten every 6 h, and image builds write
  tens of GB. Watch `nvme` sensors separately.
- **VRM and PCH.** Not usually exposed. If the box throttles with a cool CPU,
  suspect the motherboard's power delivery, not the cooler.

Absolute numbers matter less than the **trend**. A box that idles at 45 °C and
reaches 72 °C under load is healthy. A box that idles at 62 °C is one warm day
from trouble, regardless of what the load figure says.

### Reading it

```bash
# every sensor, labelled
sensors

# the kernel's own view, with trip points
for z in /sys/class/thermal/thermal_zone*; do
  printf '%s: %s\n' "$(cat "$z/type")" "$(cat "$z/temp")"
done

# did it throttle since boot? (the only question that matters retroactively)
journalctl -k -b | grep -iE 'throttl|thermal|critical temperature|mce:'
dmesg | grep -i 'cpu clock throttled'
```

On Intel, `cpu clock throttled` in `dmesg` is the smoking gun. On AMD, look for
`Tctl`/`Tdie` in `sensors` and for boost clocks collapsing under load:

```bash
watch -n1 'grep "cpu MHz" /proc/cpuinfo | head -4'
```

If the clock drops from ~3.0 GHz to 800 MHz–1.2 GHz while the temperature sits
at 95 °C, that is thermal throttling, and every service on the box is now
slower than the budget assumes — including the audio encoder with a deadline.

### Fixes, in order of cost

1. **Clean it.** Power off, unplug, compressed air through the fins *and* the
   fan hub, hold the fan so it does not spin. Free.
2. **Fix the airflow.** Intake and exhaust clear by 10 cm; not in a closed
   cabinet; not on top of another heat source. Free.
3. **Replace the paste.** ~€5 and 30 minutes, once every few years. The single
   highest-yield maintenance action on an old box.
4. **Add or replace the fan.** A 120 mm fan at low RPM moves more air more
   quietly than a 40 mm screamer.
5. **Cap the clock.** `cpufreq` governor `powersave` instead of `performance`,
   or set `energy_performance_preference=balance_power`. Costs some encoder
   headroom, buys 5–10 °C.
6. **Move the box.** A shelf near the floor in a room with airflow beats a
   closed cabinet in a warm room, every time.

### Fan control on a server install

A minimal Ubuntu Server has no fan curve management: the BIOS decides. If the
BIOS curve is lazy (quiet-first), the box runs hot at idle-adjacent loads.

```bash
sudo apt install lm-sensors fancontrol
sudo sensors-detect --auto
sudo pwmconfig          # interactive: maps fan to temperature source
sudo systemctl enable --now fancontrol
```

Two rules: never let `fancontrol` own a fan the BIOS also controls without
verifying it survives a reboot; and set the minimum PWM low enough that the fan
is not audible from another room — a box that gets unplugged because it whines
protects nothing.

## Post-mortem: the 2026-11-13 OOM (measured, not hypothesised)

Recovered from the host's journal for the previous boot, before anything was
changed.

**What the kernel said** (`journalctl -k -b -1`):

```
oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=init.scope,
         mems_allowed=0,global_oom,task_memcg=/system.slice/docker-e3b41...
Out of memory: Killed process 69366 (mario) total-vm:1618308kB, anon-rss:340788kB
```

- `global_oom` with `constraint=CONSTRAINT_NONE`: **no cgroup limit was hit.**
  The kernel had to choose globally, because nothing on the host was bounded.
- `task_memcg=/system.slice/docker-…` identifies the victim's cgroup — a
  container — but the *shortage* was system-wide.

**What was running**: the OOM dumps list **67 distinct `mario` processes** alive
at the same time, each with `total-vm ≈ 1.6 GB` and 100–535 MiB of anonymous
RSS, plus a `docker` and a `docker-compose` CLI per invocation. Eleven OOM events
between 17:23 and 17:58 UTC.

**What that means**: 67 × ~120 MiB anon ≈ 8 GB of render memory alone, on top of
page cache and the rest, with **no limit anywhere** to stop instance 68 from
starting. The `mario-refresh.sh` script in the deployed tree does contain a
`flock` guard, so the concurrent launches did not come from a clean cron run —
how they were started is **UNKNOWN** (no shell history on the host, no
persistent `docker events`). What is not unknown is the shape: a 120 MiB TTS
process with no concurrency cap and no memory limit.

**What did NOT cause it**: total RAM. `sar -r` for the same day shows the box at
**4.3 % memory used** and 29.7 GiB available during normal operation. The box is
not too small.

**Fixes, in order of stopping this specific failure**:

1. `mem_limit` + `pids_limit` on the `mario` service — a limit turns the kill
   into "one container died" instead of "the host died".
2. A hard concurrency cap: `flock` on the render, **and** a check that refuses
   to start when another `mario` process exists.
3. `OomKill` and `MarioConcurrent` alerts ([05](05-alert-catalog.md)).
4. Move the render off the appliance ([07](07-topology.md)).

## Part 2 — Memory

### What actually consumed it

Docker does not OOM-kill the host; the kernel does. The candidates, in order of
how much they can move the needle on this specific box:

| Consumer | Character | Why it is a suspect |
|---|---|---|
| **Image builds** (`docker compose build mario`, `build cam`) | burst, unbounded, runs **on the host** from `post-receive` | BuildKit + pip/npm + apt layers easily take 1–3 GB. Triggered by an ordinary `git push`, at any hour. |
| **Jellyfin transcode** | burst, unbounded | ffmpeg transcoding holds frame buffers per stream; one 4K transcode can take 2 GB. |
| **`indiegen` render** | 1.5 GB for ~7 min, every 6 h | Designed to stream arrays to stay under 1.5 GB, but that is a design target, not a measured ceiling. |
| **`mario` TTS** | peak on model load, hourly | ONNX model + voices file into RSS; exits after. Peak, not mean. |
| **Page cache** | not a leak | Reclaimable. `MemFree` near zero with `MemAvailable` healthy is normal and good. Do not "fix" it. |
| **Journal / Docker logs** | slow growth | `journalctl` unconstrained plus container logs can reach gigabytes, then `docker` and disk I/O suffer. |

The dangerous combination is **two of these at once**: a build while a render
runs, or a Jellyfin transcode during TTS. Individually each fits. Together they
exceed a machine whose total is unknown but clearly not generous.

### The metric that matters

`MemAvailable`, not `MemFree`. `MemFree` excludes reclaimable cache and makes
every healthy Linux box look like it is dying.

```bash
awk '/MemAvailable|MemTotal|SwapFree|SwapTotal/ {print}' /proc/meminfo
cat /proc/pressure/memory      # some/full, avg10/60/300
```

PSI is the honest signal, because it measures **stalls**, not headroom:

- `some` rising → some tasks are waiting on memory reclaim. Early warning.
- `full` above 0 for minutes → everything is stalling. The box is effectively
  down even though it is up.

Thresholds used in the alert catalog: `memory some avg60 > 10 %` warns;
`memory full avg10 > 5 %` is critical.

### Swap: three options, one answer

| Option | Behaviour | Verdict for this box |
|---|---|---|
| **No swap** | OOM killer fires cleanly, kills the largest consumer | Acceptable, but the kill is abrupt and picks its victim by size, not importance. |
| **Disk swap on an SSD** | Buys time; causes write amplification; makes a stalling box thrash for minutes instead of dying | Worst of both. Use only as a small emergency cushion (2–4 GB, `vm.swappiness=10`). |
| **zram** | Compressed RAM block device; ~2–3× effective capacity; no disk I/O | Best fit. zram absorbs the TTS peak that would otherwise kill something. |

Recommendation: **zram only**, no disk swap, `vm.swappiness` left at its modern
default (100 for zram-based systems is correct — the kernel's default reflects
zram behaviour, and lowering it to 10 is a habit from disk swap).

`vm.overcommit_memory=0` (heuristic) stays. `1` would let a build allocate beyond
RAM and get killed later, deeper into the job.

### Protecting what must not die

The OOM killer scores by memory footprint; the audio encoder is small, so it is
normally safe. It is *not* safe when the box is at the edge and a 3 GB build
appears, because the victim selection includes the whole cgroup.

Two levers:

```bash
# per-container: make the container itself the preferred victim, so the kill
# stays inside the offender instead of escalating
docker update --oom-score-adj 500 radio-indiegen
docker update --oom-score-adj 500 radio-cam

# per-container: never kill these
docker update --oom-score-adj -500 radio-liquidsoap
docker update --oom-score-adj -500 radio-icecast
```

Plus the container memory limits from [02](02-resource-budget.md). A limited
container that exceeds its limit is killed **inside its own cgroup**: the rest of
the box keeps running. That is the single most valuable change on this host,
because it converts a total outage into one dead container and a restart.

## Runbook A — the box is hot

**Trigger:** package temperature > 80 °C sustained for 5 min, or a throttle
event in `dmesg`.

1. Confirm it is real, not a sensor glitch:
   `sensors | head -30` — core and package within ~5 °C of each other.
2. Reduce load now, in this order (cheapest and most reversible first):
   ```bash
   docker compose -f ~/servers/radio/docker-compose.yml stop cam   # biggest core consumer
   docker compose -f ~/servers/radio/docker-compose.yml stop indiegen  # stops renders
   ```
   The stream keeps playing: neither is on the audio path.
3. If the temperature keeps climbing, stop the stack and let it cool:
   ```bash
   docker compose -f ~/servers/radio/docker-compose.yml down
   ```
   The stream is already degraded; a dead box is worse than a silent one.
4. Only shut down if the temperature is still rising after the load is gone, or
   if you smell/see something you do not like. `sudo shutdown -h now`.
5. When it is back: clean it, check the fan curve, and re-run the audit. Do not
   declare it fixed because it booted.

## Runbook B — the box is out of memory

**Trigger:** OOM-kill in `journalctl -k`, or `memory full` PSI pinned.

1. Find the victim and the winner:
   ```bash
   journalctl -k --since '1 hour ago' | grep -i 'killed process'
   ```
   The line names the process, its RSS and its `total-vm`.
2. Stop the burst, not the service:
   ```bash
   docker compose -f ~/servers/radio/docker-compose.yml stop indiegen
   docker compose -f ~/servers/radio/docker-compose.yml stop cam
   ```
3. Confirm the stream is still up before anything else:
   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' https://stream.daza.ar/
   ```
4. Record what was running: `docker stats --no-stream` and the two crons. The
   overlap is the bug, not the service.
5. If it repeats at the same hour, the schedule is wrong. Move the TTS cron
   away from the render window, and make the build not run on this host.

## Runbook C — the box is unreachable

1. It is not slow, it is gone: no ping, no SSH.
2. Physical presence required. Check power LED, then fans (spinning = alive but
   wedged; silent = powered off or PSU).
3. If fans are spinning but no network: it may be alive at the console. Attach a
   keyboard/monitor and look at the screen before pulling the plug — a panic
   message or a thermal shutdown message is evidence you cannot recover later.
4. Hard power cycle only after that. Then read the journal from the previous
   boot: `journalctl -k -b -1 | tail -100`.

## Preventive checklist

Weekly, five minutes:

- [ ] Peak temperature since last week (Grafana or `journalctl` grep)
- [ ] Throttle events: none
- [ ] `MemAvailable` minimum
- [ ] OOM kills: none
- [ ] Swap/zram used: stable, not growing
- [ ] Disk: > 20 % free on `/` and on the Docker root

Quarterly:

- [ ] Dust
- [ ] Fan hear-test (a bearing going bad is audible before it is measurable)
- [ ] `docker system df` — images and build cache are this box's disk leak
