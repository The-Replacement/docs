# 01 — What already works, and what does not

Every row below was verified in code or on the host on 2026-11-13. "Verified"
means a file and line, or a command whose output is quoted.

## Produce — works

| Behaviour | Where | Detail |
|---|---|---|
| Batch generation from seeds | `indiegenerator/src/indiegen/serve.py` | `serve` loops on `INDIEGEN_INTERVAL_SECONDS` (21600 = 6 h), 10 tracks per cycle, seed strategy `advance` |
| Deterministic re-render | `indiegen render --from-plan` | A plan hash reproduces the same audio; the sweep job tests this |
| Voice segments | `radio/src/mario/gen.py`, cron hourly | Time-bucketed TTS (Kokoro ONNX), one bucket per hour |
| No manual step after generation | `radio/scripts/restart-on-signal.sh` | The generator writes `data/indiegen/restart-request`; a cron watcher restarts Liquidsoap every minute if present |

## Retire — works, for content only

| Behaviour | Where | Detail |
|---|---|---|
| Library replacement | `serve.rotate_library()` | Publishes new `*.flac` + metadata first, then removes managed stale files per root — atomic per file, no empty window |
| Voice pool pruning | `mario/prune.py` `prune_host_dir` | Keeps the N most recent buckets (`--keep-buckets 1` in compose), deletes whole stale buckets |
| Log truncation | `scripts/mario-refresh.sh` | Keeps the last 500 lines once `mario-refresh.log` passes 1 MiB |

## Sustain — does not work

| Gap | Evidence | Failure it causes |
|---|---|---|
| Docker build cache unbounded | `docker system df`: **21.1 GB**, 17.5 GB reclaimable | Disk fills over months; the failure looks like "renders fail to publish", not "disk full" |
| Journal unbounded | `journald.conf` at defaults; no `SystemMaxUse` | Grows during exactly the incidents you need the journal for |
| Container logs | **fixed 2026-11-13** (`max-size: 10m`, `max-file: 3` in compose) | Was unbounded; `liquidsoap --verbose` is the fastest-growing file on the box |
| Container images | 14 images, 8.5 GB, no `image prune` anywhere | Every deploy that changes a Dockerfile leaves the old image behind |
| `data/indiegen/runs/` history | Never pruned | Small, but it is another thing that only grows |
| `ac1-soak-*.log` | `scripts/ac1-soak.sh` writes a file per run | Diagnostic artefacts accumulate in `data/` |
| `rss-cache` | `data/host/rss-cache` | Bounded by feed count, but nothing states the bound |
| No disk budget in the loop | — | Nothing makes the generator *stop* when disk is low; it will fail mid-rotation instead |

## Recover — partial

| Behaviour | Status |
|---|---|
| Container restart on crash | ✅ `restart: unless-stopped` on all long-lived services |
| Liquidsoap restart after rotation | ✅ signal file + 1-minute cron watcher |
| Detect "stream is silent while Icecast says it is fine" | ❌ nothing checks `total_bytes_read` rate |
| Detect a crash loop | ❌ docker restarts forever; nothing counts |
| Detect that a render failed | ⚠️ written to `data/indiegen/state.json` and the log; nobody reads it |
| Detect that Mario stopped producing | ❌ the station slowly runs out of voice between tracks |
| Restart with a budget | ❌ no watchdog, no backoff, no "stop trying and alert" |
| Degrade instead of die | ❌ no ladder; an OOM is global (proven 2026-11-13) |
| Deploy actually applies | ❌ was silently broken: detached HEAD meant `updateInstead` never moved the worktree. **Fixed 2026-11-13** |

## Coordination — none

The three batch jobs are independent cron entries:

```
* * * * *   restart-on-signal.sh     # every minute
0 * * * *   mario-refresh.sh         # hourly, TTS model load
            indiegen serve loop      # every 6 h from inside the container
```

Nothing prevents them overlapping. Nothing knows that a TTS render, a library
render and an image build are three memory peaks that must not meet. On
2026-11-13 they met, and the kernel picked the victims.

## The honest summary

The station can already produce its own material indefinitely and delete what it
no longer needs. What it cannot do is **manage its own machine**: bound its own
storage, notice its own silence, or decide when it is too hot or too busy to
generate.
