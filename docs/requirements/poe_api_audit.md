# PoE API Markdown Audit

## Scope
Document the tracked markdown that supports API ingestion planning, ensuring official references are visible alongside the repo inventory.

## Sources
- https://www.pathofexile.com/developer/docs (accessed 2026-02-23)
- https://www.pathofexile.com/developer/docs/reference (accessed 2026-02-23)

## Exclusions
- `docs/ops-runtime-ui-upgrade-plan.md` (untracked draft; reviewed but intentionally out of scope for the committed inventory)
- `docs/requirements/poe_api_audit.md` (tracked once this audit is finalized; excluded from the published inventory while still in draft)

## Inventory Summary
- Total inventory: 33 git-tracked markdown files.
- Files with documented requirements: 33.
- Files without actionable requirements: 0.

## Requirements
### File: .opencode/agents/devops.md
Status: requirements
- Requirement ID: REQ-001
  Requirement: Document every ClickHouse/Python pipeline change with minimal diffs, bake in safety/risk rationale, and log command outputs when executing builds or migrations.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/agents/docs.md
Status: requirements
- Requirement ID: REQ-002
  Requirement: Preserve the existing voice, keep terminology aligned with Path of Exile tooling, and avoid claiming commands/tests without output when updating documentation.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/agents/go-fast.md
Status: requirements
- Requirement ID: REQ-003
  Requirement: Apply Python-focused changes with minimal diffs, honor idiomatic styling, guard ClickHouse writes, run repo formatters on touched files, and capture each command output.
  Official: no official match
  Ingestion stage: store
  Data contract impact: none

### File: .opencode/agents/go-tests.md
Status: requirements
- Requirement ID: REQ-004
  Requirement: Confine edits to Python test files/fixtures, use pytest idioms for determinism, and route production behavior shifts back to the implementation builder.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/agents/planner.md
Status: requirements
- Requirement ID: REQ-005
  Requirement: Decompose objectives into todos that include a one-sentence objective, acceptance criteria, evidence commands, and dependencies before kicking off implementation.
  Official: no official match
  Ingestion stage: discover
  Data contract impact: none

### File: .opencode/agents/proj-lead.md
Status: requirements
- Requirement ID: REQ-006
  Requirement: Run the todo-read/refine/implement/verify loop, delegate to the appropriate subagent, and only close tasks when recorded evidence meets acceptance criteria.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/agents/proto-engineer.md
Status: requirements
- Requirement ID: REQ-007
  Requirement: Prefer additive ClickHouse migrations, document backward/forward compatibility for leagues/items, and annotate downstream impacts whenever schema or SQL assets change.
  Official: no official match
  Ingestion stage: store
  Data contract impact: requires explicit additive risk note

### File: .opencode/agents/review.md
Status: requirements
- Requirement ID: REQ-008
  Requirement: Audit Python/ClickHouse work for correctness, ClickHouse safety, Path of Exile domain accuracy, and missing tests or evidence before signing off.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/agents/runner.md
Status: requirements
- Requirement ID: REQ-009
  Requirement: Execute the requested commands, return the exact command text with trimmed output, and label each run as pass/fail/N/A for ingestion verifications.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/commands/pr-ready-quick.md
Status: requirements
- Requirement ID: REQ-010
  Requirement: Run quick PR-readiness checks (git status/diff plus Go tests/lint if available), interpret outputs, and craft a summary with testing commands.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/commands/pr-ready.md
Status: requirements
- Requirement ID: REQ-011
  Requirement: Outline scope, risk areas, command checklist, and a structured PR description that highlights what changed, how to test, and any missing docs/tests.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/commands/proto-safe-change.md
Status: requirements
- Requirement ID: REQ-012
  Requirement: Keep protobuf edits additive, reserve removed fields/tags, run buf lint/breaking/generation, and summarize wire-compat implications.
  Official: no official match
  Ingestion stage: store
  Data contract impact: requires explicit additive risk note

### File: .opencode/commands/speed-perfect.md
Status: requirements
- Requirement ID: REQ-013
  Requirement: Follow the speed-perfect workflow (plan, delegate to go-fast/go-tests, gather runner/review evidence) and return a compact evidence bundle per change.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/rules/core.md
Status: requirements
- Requirement ID: REQ-014
  Requirement: Always capture proof for commands/tests, keep changes minimal/Python-first, and treat ClickHouse schema work as additive unless explicitly approved otherwise.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/skills/docs-specialist/SKILL.md
Status: requirements
- Requirement ID: REQ-015
  Requirement: Update documentation with minimal diffs, preserve style, prioritize copy/pastable examples, and call out ClickHouse terminology/constraints.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/skills/evidence-bundle/SKILL.md
Status: requirements
- Requirement ID: REQ-016
  Requirement: Produce a verification bundle listing changed files plus formatter/lint/test/type-check/ClickHouse commands and their exact outputs.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: .opencode/skills/protocol-compat/SKILL.md
Status: requirements
- Requirement ID: REQ-017
  Requirement: Apply additive schema changes, test backwards/forwards safety (clickhouse-local or CLI), and document migration intent/impact for every contract change.
  Official: no official match
  Ingestion stage: store
  Data contract impact: requires explicit additive risk note

### File: 00-ecosystem-overview.md
Status: requirements
- Requirement ID: REQ-018
  Requirement: Treat ClickHouse as the source of truth, route all analysis through Ledger API, and derive deterministic pricing/ranking outputs before exposing them to downstream tools.
  Official: no official match
  Ingestion stage: discover
  Data contract impact: none

### File: 01-architecture.md
Status: requirements
- Requirement ID: REQ-019
  Requirement: Deploy the listed services, bronze/silver/gold tables, partitioning policies, and PoE-aware guardrails so ingestion adheres to the architecture blueprint.
  Official: no official match
  Ingestion stage: store
  Data contract impact: none

### File: 02-implementation-tasklist.md
Status: requirements
- Requirement ID: REQ-020
  Requirement: Execute the epics in order (Docker baseline through release), honor thresholds (e.g., >=10c stash pricer), and mark DoDs with concrete verification steps.
  Official: no official match
  Ingestion stage: fetch
  Data contract impact: none

### File: 03-strategy-registry.md
Status: requirements
- Requirement ID: REQ-021
  Requirement: Register player strategies with required inputs/KPIs/detectors, then validate them against your own market/session data before scaling suggestions.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: 04-exilelens-linux-item-capture.md
Status: requirements
- Requirement ID: REQ-022
  Requirement: Default to clipboard-first capture, fall back to OCR, and POST the parsed text to `POST /v1/item/analyze` so the backend returns price/craft signals.
  Official: no official match
  Ingestion stage: fetch
  Data contract impact: none

### File: 05-buildatlas-pob-intelligence.md
Status: requirements
- Requirement ID: REQ-023
  Requirement: Integrate BuildAtlas with Ledger pricing outputs, enforce structured randomness/surge to avoid meta-crowding, and persist genome/cost tables in ClickHouse.
  Official: no official match
  Ingestion stage: normalize
  Data contract impact: none

### File: 06-db-etl-roadmap.md
Status: requirements
- Requirement ID: REQ-024
  Requirement: Enforce the PoE ingestion contract (rate-limit headers, Retry-After, User-Agent, checkpoint persistence) while feeding bronze→silver→gold layers with documented SLOs.
  Official: https://www.pathofexile.com/developer/docs
  Ingestion stage: fetch
  Data contract impact: none

### File: 07-exilelens-overlay-plan.md
Status: requirements
- Requirement ID: REQ-025
  Requirement: Use stash payload coordinates to draw full-footprint highlights, dim masks, and a cached selection map while capping renders at ~50 simultaneous selections.
  Official: no official match
  Ingestion stage: normalize
  Data contract impact: none

### File: 08-questing-companion-plan.md
Status: requirements
- Requirement ID: REQ-026
  Requirement: Build the quest companion around an act/zone FSM, runtime detection, reward heuristics, and manual override guardrails so players always see the next objective and relevant loot.
  Official: no official match
  Ingestion stage: discover
  Data contract impact: none

### File: 09-dynamic-item-filter-plan.md
Status: requirements
- Requirement ID: REQ-027
  Requirement: Emit NeverSink-compatible filters with delta rules tied to build state, enforce manual-trigger validations, run dry-run safety checks, and support rollbacks when PoE validation fails.
  Official: https://www.pathofexile.com/item-filter/about
  Ingestion stage: operate
  Data contract impact: none

### File: 10-comprehensive-feature-backlog.md
Status: requirements
- Requirement ID: REQ-028
  Requirement: Operate under the multi-agent control plane, manual-trigger proof guardrails, and policy compliance checklist while completing phased backlog tasks.
  Official: https://www.pathofexile.com/developer/docs
  Ingestion stage: operate
  Data contract impact: none

### File: 11-poe-domain-research-dossier.md
Status: requirements
- Requirement ID: REQ-029
  Requirement: Anchor assumptions on official PoE docs, annotate community-sourced confidence, and normalize filter/quest/freshness models according to those validated findings.
  Official: https://www.pathofexile.com/developer/docs
  Ingestion stage: operate
  Data contract impact: none

### File: AGENTS.md
Status: requirements
- Requirement ID: REQ-030
  Requirement: Follow the repo playbook of speed with proof, scope discipline, ClickHouse safety, and documentation/evidence rigor before touching ingestion assets.
  Official: https://www.pathofexile.com/developer/docs
  Ingestion stage: operate
  Data contract impact: none

### File: README.md
Status: requirements
- Requirement ID: REQ-031
  Requirement: Bootstrap the stack via ledger UI, verify Ops & Runtime health, run CLI help commands, and monitor container logs before trusting ingestion data.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: ask_user.md
Status: requirements
- Requirement ID: REQ-032
  Requirement: Clarify which ClickHouse tables/streams populate `/v1/ops/dashboard`, define checkpoint drift automation vs operator-only handling, and decide dashboard authentication/embedding strategy.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

### File: docs/ops-runbook.md
Status: requirements
- Requirement ID: REQ-033
  Requirement: Execute the listed launch checks, adhere to the freshness/alert SLOs, follow failure recovery steps, and escalate with dashboards/logs when multiple ingestion panels alert.
  Official: no official match
  Ingestion stage: operate
  Data contract impact: none

## Gaps
- `/v1/ops/dashboard` still lacks a definitive mapping of ClickHouse tables/streams and the metrics it must surface before ingestion automation can be certified (see `ask_user.md`).
- Decision-making around checkpoint drift alert automation versus operator-only responses, plus dash auth/embedding, remains outstanding and blocks the ops runbook’s execution plan (`ask_user.md`).
- Manual-trigger proof instrumentation for integration flows (filter reloads, overlay quests, telemetry) still needs explicit verification targets before policy-compliant ingestion can ship (`10-comprehensive-feature-backlog.md`).
