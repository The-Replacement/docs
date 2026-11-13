# 0001 — Migrating the radio ecosystem into The-Replacement

**Date:** 2026-11-13
**Status:** applied, with two open items (Cloudflare Pages, host hardware)

## Context

The radio system lived across personal repositories under `juanmanueldaza` and
one production host, `mainframe` (`192.168.100.148`), that ran the radio stack
plus Jellyfin and other unrelated workloads. The host overheated and hit memory
limits, and was powered off.

The goal of the migration: every repository, reference, integration and gate in
the organisation, self-contained, with no dependency on the host being online.

## Decisions

### D1 — `mainframe` is a separate git remote, not a second push URL

**Before:** `origin` had two push URLs (GitHub, then the host).

**Why it was wrong:** git pushes to every push URL and fails the command if any
one fails. Whenever the host was down, `git push origin master` exited non-zero
*after* GitHub had already accepted the commit — so the exit code lied about the
state of the world, which is the one thing a gate must never do.

**Now:** `git push origin master` publishes; `git push mainframe master` deploys.
Two intents, two commands.

**Cost:** deploying is now a second command. That is the point.

### D2 — Branch rulesets require a PR and the CI checks

`protect-master` on `radio` (requires `test`, `shellcheck`) and on
`indiegenerator` (requires `gate`). Organisation admins can bypass.

**Deliberately excluded:** `indiegenerator`'s `sweep` job. It is red on master
(gate 6 fails on two seeds, issue #43), and a required check that already fails
blocks every merge — it would stop work instead of protecting it. It gets added
as soon as it is green.

**Cost:** direct pushes to `master` are no longer the path. A docs-only change
goes through a PR like anything else.

### D3 — The SDD board is `The-Replacement Roadmap`, project **1**

The pipeline instructions pointed at project 2 with field IDs from a project
that did not exist in this organisation. The org had no projects at all.

Created: project 1, `Status` (Todo / In Progress / Done, unchanged IDs) and
`Phase` (Todo, Explore, Propose, Spec, Design, Tasks, Apply, Verify, Done).
The five open migration issues are on the board as Todo.

**Cost:** the hardcoded IDs in `AGENTS.md` and in the agent prompt are stale
until edited; the local `.opencode` skill copies were updated, but `.opencode/`
is untracked in every repository — which is precisely why the harness needs a
single home (see D5).

### D4 — Documentation: code-coupled stays, explanation moves

`radio/docs/` is not a knowledge base: its files are measured. `docs.sh` renders
their Mermaid diagrams, `claims.sh` greps the tree for hand-written domains,
`tests/test_playout_contract.py` asserts `PLAYOUT-CONTRACT.md`, and
`HARDENING.md` / `SDD-65-SPLIT-LAYOUT.md` describe code paths that exist today.

Moving those to a separate repository would leave the gates measuring fewer
files while reporting green — the exact failure mode they exist to prevent.

**Split:** code-coupled documents stay in their repository; research, plans and
org-level explanation live here in `docs`; anything executable lives in `infra`.

### D5 — `n3rv` is standalone, not a fork

`n3rv-thereplacement` was a GitHub fork of a personal repository: issues
disabled by default, no private visibility, upstream as the default PR target.
Requiring `has_issues=true` to be patched on by hand is a smell.

Created `The-Replacement/n3rv` with the full history (all branches, all tags,
`main` at `64db2af`), and archived the fork rather than deleting it — links
written elsewhere keep resolving, and the decision stays reversible.

### D6 — Cloudflare Pages: the working route is to re-link, the durable one is CI

The Pages project `radio` still records `owner: juanmanueldaza`; its GitHub App
installation lost access when the repository moved, and deployments stopped
without an error anyone would see. The last published build predates the
transfer.

Two routes, in `infra/runbooks/cloudflare-pages.md`: re-link in the dashboard
(two minutes, keeps the same fragility), or deploy from GitHub Actions with a
scoped API token (one more secret, deploys that appear in the repository's own
history and cannot be severed by an ownership change).

**Status:** open. A human must complete either route; neither can be done from
the API with the credentials available here.

### D7 — The host is treated as an appliance, not a server

Research in `appliance/` argues for a single-purpose box. The shortest version:
the stack has zero resource caps in `docker-compose.yml`, and the deploy hook
runs `docker compose build` **on the production host** after every code push. A
box that runs Jellyfin, transcodes, builds images and encodes audio has no way to
tell you which of those caused the OOM. Isolating one purpose is what makes the
next failure diagnosable.
