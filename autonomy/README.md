# Autonomy: the radio as a self-sustaining appliance

The appliance research (`../appliance/`) answers "how does this box stop dying".
This section answers a different question: **how does this box keep producing a
radio without a human in the loop** — generating its own material, retiring what
it no longer needs, and recovering on its own.

It is a design document, not a description of what exists. Where something already
exists, it says so with a file reference.

## The four loops

A self-sustaining station needs four loops, and it currently has two of them.

| Loop | Question it answers | Today |
|---|---|---|
| **Produce** | Where does new content come from? | ✅ `indiegen` renders 10 tracks every 6 h; `mario` renders voice segments hourly |
| **Retire** | What removes content that is no longer wanted? | ✅ `indiegen` replaces the whole library atomically; `mario` prunes to the last bucket |
| **Sustain** | What keeps the machine able to run tomorrow? | ⚠️ partial — Docker build cache, journal and history grow unbounded; nothing prunes them |
| **Recover** | What happens after a failure with nobody watching? | ⚠️ partial — `restart: unless-stopped` and a signal-file watcher; nothing detects a silent stream |

The interesting asymmetry: **content lifecycle is solved, operational lifecycle is
not.** The station will not run out of music. It will run out of disk, or play
silence into a working Icecast, and neither event has an owner.

## What "self-sustaining" means, concretely

A station is self-sustaining when, with the operator away for two weeks:

1. The stream is still audible on day 14, from content generated after day 1.
2. No resource grows without a bound (disk, inodes, journal, images, logs).
3. Every failure either repaired itself or is visible in one place on return.
4. Nothing required a decision that only a human could make.
5. A fresh machine could be rebuilt from git — and the two files that are not
   derivable (`state.json`, `.env`) are kilobytes, not a backup system.

Those five are testable. "It feels automated" is not.

## The edge question, answered directly

"Have we considered the edge?" — yes, but not as a separate tier of machines.

The edge here is not additional compute. It is **local decision-making**:

- The box decides *whether it can afford* to generate right now (thermal,
  memory, load), instead of cron deciding by the clock.
- The box decides *what to delete* by policy, instead of a human noticing a full
  disk.
- The box decides *how far to degrade* (stop batch jobs, then the camera, then
  the stack) instead of dying all at once.

That is a scheduler with a resource gate, a retention policy expressed as code,
and a degradation ladder. All three run on the appliance, with no cloud
dependency, and that is deliberate: the station must keep broadcasting while the
internet is down, with the only external dependency being the tunnel that
delivers it.

Full reasoning and the failure it prevents: [`02-design.md`](02-design.md).

## Documents

| File | Contents |
|---|---|
| [`01-what-exists.md`](01-what-exists.md) | Code-verified inventory of today's autonomous behaviour, and the gaps with the failure each one causes |
| [`02-design.md`](02-design.md) | Target design: job model, resource gate, retention as code, self-heal ladder, status surface |
| [`03-roadmap.md`](03-roadmap.md) | Ordered, issue-sized steps, each independently shippable |
| [`04-disposability.md`](04-disposability.md) | Why there is no backup job, what is derivable, and the two files that are not |

## Non-goals

- **Not** a control plane. One host, one stream; Kubernetes would be a second
  thing to keep alive on the box that has to stay alive.
- **Not** cloud rendering. Generation stays on the mainframe by decision: the
  station must be able to produce material with no network.
- **Not** an AI DJ that decides the playlist from listener feedback. The
  determinism is the product; a feedback loop would make the station
  irreproducible.
