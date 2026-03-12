# DOCS GUIDE

## OVERVIEW

`docs/` holds both live operator docs and planning/supporting material; keep it obvious which pages reflect shipped behavior versus analysis or future work.

## STRUCTURE

```text
docs/
|- ops-runbook.md          # live operational procedures
|- clickhouse/             # storage design notes
|- requirements/           # gap analysis and requirement audits
|- research/               # upstream constraints and source research
`- evidence/               # proof bundles and validation notes
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Update operator workflow | `ops-runbook.md` | Startup, monitoring, recovery commands |
| Update planning context | `v2-implementation-plan.md`, `v2-gap-matrix.md`, `v2-v3-feature-triage.md` | Context only; do not present as shipped behavior |
| Record source constraints | `research/` | Upstream API, rate-limit, and recovery evidence |
| Track implementation gaps | `requirements/` | Audits tied to real code/schema behavior |
| Capture proof | `evidence/` | Only write commands/results you actually ran |

## CONVENTIONS

- Prefer command-first, evidence-backed prose over long narrative.
- Use exact module, CLI, table, and view names from the codebase.
- When docs mention validation, include the exact command and observed result or label it `not run`.
- Separate live runbooks from planning docs with explicit wording like `implemented`, `planned`, or `research`.
- Keep Path of Exile and ClickHouse terminology consistent with `README.md` and runtime logs.

## ANTI-PATTERNS

- Do not describe planned services or dashboards as live unless code or evidence exists.
- Do not drift from current entry-point names (`poe-ledger-cli`, `market_harvester`, `poe-migrate`).
- Do not duplicate large chunks of root planning markdown when a short cross-reference is enough.

## VERIFICATION

```bash
rg -n "poe-ledger-cli|market_harvester|poe-migrate" README.md docs/ poe_trade/
```
