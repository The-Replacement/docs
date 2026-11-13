# The mainframe appliance

Research and plan for repurposing `mainframe` (Ubuntu Server, `192.168.100.148`)
as a **radio-dedicated appliance**.

## Starting point, honestly stated

The host is a **ThinkPad with an i7-1165G7, 32 GiB of RAM and a 914 GB NVMe**, running
Ubuntu 26.10 and Docker. It was offline when this research started; the audit on
2026-11-13 measured it live.

Two corrections to the original diagnosis, both from the box's own logs:

- **The memory problem was not total RAM.** The box runs at 4.3 % memory use and
  the radio stack is 181 MiB. On 2026-11-13 it was taken down by **67 concurrent
  TTS renders** with no limit of any kind to stop the 68th — a `global_oom`, in
  the kernel's words. See [03](03-thermal-and-memory.md).
- **No thermal throttling event exists in the journal.** Idle package temperature
  is 42 °C with the fan off. "It was overheating" is a physical observation, not
  a kernel-verified fact — which means the cooling work is preventive, and the
  monitoring must exist to catch it if it is real.

That last detail is the whole problem with the previous setup: when everything is
unlimited, the first symptom of overload is total failure, and the cause is
unattributable. The plan below is built around making failures **local, visible
and bounded** instead of researching the perfect fan curve.

## The nine deliverables

| # | Deliverable | Where |
|---|---|---|
| 1 | Workload audit script | [`infra/deploy/audit-mainframe.sh`](https://github.com/The-Replacement/infra/blob/main/deploy/audit-mainframe.sh) + [01-workload-audit.md](01-workload-audit.md) |
| 2 | Resource budget per service | [02-resource-budget.md](02-resource-budget.md) |
| 3 | Monitoring architecture | [04-monitoring-architecture.md](04-monitoring-architecture.md) |
| 4 | Alert rule catalog | [05-alert-catalog.md](05-alert-catalog.md) |
| 5 | Thermal and memory runbook | [03-thermal-and-memory.md](03-thermal-and-memory.md) |
| 6 | Appliance hardening guide | [06-hardening.md](06-hardening.md) |
| 7 | Topology recommendation | [07-topology.md](07-topology.md) |
| 8 | Jellyfin / unrelated-service migration | [08-jellyfin-migration.md](08-jellyfin-migration.md) |
| 9 | Control and access plan | [09-access-and-control.md](09-access-and-control.md) |

## Method, and its limits

1. **Inventory before opinion.** The audit script collects what is actually on
   the box: units, containers, cron, ports, disk, thermal envelope, memory
   pressure. No decision is made before that output exists.
2. **Measure what can be measured, label the rest.** Container footprints for
   `icecast`, `liquidsoap`, `caddy` and `mediamtx` were measured on a
   workstation running the same pinned images (see the budget document). The
   encoders that need hardware — camera capture, TTS — are ESTIMATED until the
   box is up.
3. **One purpose per machine.** If a workload cannot be reasoned about in
   isolation, it does not belong on the appliance.

## What this research deliberately does not do

- It does not recommend a specific fan, case or thermal paste. Those are
  physical, and the audit cannot see them. It gives the temperature bands and
  the throttling evidence to look for.
- It does not propose Kubernetes. A six-container single-host stack with a
  linear failover story does not need a control plane; the complexity would be
  paid for in RAM on the same box that ran out of RAM.
- It does not assume the hardware is adequate. There is a section on what to do
  if it is not.

## Reading order for someone in a hurry

1. [07-topology.md](07-topology.md) — the recommended shape, and why.
2. [02-resource-budget.md](02-resource-budget.md) — what each piece costs.
3. [05-alert-catalog.md](05-alert-catalog.md) — what will tell you it is going
   wrong, before it goes wrong.
4. [03-thermal-and-memory.md](03-thermal-and-memory.md) — what to do when it
   already has.
