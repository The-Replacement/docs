# The-Replacement docs

The organisation's knowledge base: architecture, decisions, and research.

## What goes here, and what does not

| Repository | Holds |
|---|---|
| `radio`, `indiegenerator`, `n3rv` | Code **and** the documents its own gates measure (`docs.sh` renders their Mermaid, `claims.sh` greps them, tests assert their content) |
| [`infra`](https://github.com/The-Replacement/infra) | Things that **run**: scripts, environment templates, systemd units, dashboards, alert rules, runbooks |
| `docs` (here) | Things that **explain**: architecture, decisions, research, plans |

The rule of thumb: if a document would be wrong when the code changes, it belongs
next to the code. If it explains *why the shape is what it is*, it belongs here.

## Contents

- [appliance/](appliance/README.md) — repurposing the production host as a
  radio-dedicated appliance: workload audit, resource budget, thermal and memory
  analysis, monitoring architecture, alert catalog, hardening, topology,
  migration plan for unrelated services, and access control.
- [decisions/](decisions/0001-org-migration.md) — the decisions taken during the
  migration to this organisation, and what each one cost.

## Evidence discipline

Every number in these documents carries one of three labels:

- **MEASURED** — produced by a command whose output is quoted, on a named host.
- **ESTIMATED** — derived from a measurement plus a stated assumption.
- **UNKNOWN** — nobody has looked, and no decision should rest on it.

A document that says UNKNOWN is more useful than one that quietly guesses. The
host this research is about was offline when most of it was written; where that
matters, the document says so instead of inventing numbers.
