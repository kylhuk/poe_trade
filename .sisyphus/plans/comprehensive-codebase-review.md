# Comprehensive Codebase Review And Remediation

## TL;DR
> **Summary**: Audit the full maintained codebase, prove behavior across local disposable QA and `https://poe.lama-lan.ch`, remediate verified defects with TDD discipline, and finish with evidence-backed approval across backend, frontend, schema, docs, CI, and ML persistence/governance.
> **Deliverables**:
> - full subsystem inventory and coverage map
> - dual-target E2E evidence bundle for local QA and live
> - defect register with reproductions, fixes, and rerun proof
> - ML learning-without-forgetting verification bundle
> - opportunity-centric product-layer contract covering scanner, homepage, alerts, journal, diagnostics, and ML surfaces
> - docs/CI alignment for all proven behavior changes
> **Effort**: XL
> **Parallel**: YES - 4 waves
> **Critical Path**: 1 -> 2 -> 4A -> 5 -> 8 -> 11 -> 14 -> F1-F4

## Context
### Original Request
Create a comprehensive plan that guides other agents through the whole code base so everything is tested, measured, and fixed, with heavy focus on end-to-end behavior, the hosted frontend at `https://poe.lama-lan.ch`, and ML learning/persistence behavior.

### Interview Summary
- Authoritative E2E target policy: local disposable QA and live site are equal-weight targets.
- Safety policy: user selected full production exercise.
- Coverage accounting: maintained source, tests, schema, configs, docs, and workflows only; exclude generated/vendor/build outputs.
- Hard guardrail: never delete or modify crawled public stash data in the database.
- Operational allowance: services may be restarted at any point.

### Execution Prerequisites
- QA prerequisites: `.env.qa`, disposable Docker services, QA operator token from `docker-compose.qa.yml`, and local browser/runtime dependencies.
- Live readonly prerequisites: reachability to `https://poe.lama-lan.ch` and `https://api.poe.lama-lan.ch` plus any public/live-safe selectors and routes.
- Live auth/session prerequisites: a valid live `poeSessionId` bootstrap credential for `POST /api/v1/auth/session` per `poe_trade/api/app.py:663` and `frontend/src/services/auth.tsx:72`.
- Live protected-route prerequisites: a valid live operator bearer token for protected `/api/v1/ops/*`, `/api/v1/ml/*`, `/api/v1/stash/*`, and `/api/v1/actions/services/*` routes as described in `README.md` and enforced in `poe_trade/api/app.py`.
- If live credentials are unavailable at execution time, live credential-gated tasks must close as `blocked_by_credentials` with captured evidence instead of guessed execution.

### Metis Review (gaps addressed)
- Added explicit live mutation allowlist and immutable-data policy.
- Added TDD-first remediation requirement per defect cluster.
- Added exact scenario labels for `qa-only`, `live-readonly`, and `live-allowlisted-mutation` execution.
- Added explicit environment pinning so frontend runs cannot silently hit the wrong API target.
- Added ML persistence and promotion-gate verification beyond aggregate metrics.
- Added atomic commit strategy by verified defect cluster.

## Work Objectives
### Core Objective
Produce a zero-guesswork execution program that verifies every maintained subsystem, proves whether the product works as intended on both QA and live targets, fixes only evidence-backed defects, and preserves immutable crawled public stash data throughout execution.

### Deliverables
- repo-wide subsystem inventory and ownership map
- verification matrix covering backend, frontend, schema, docs, CI, and ML lifecycle
- evidence bundle under `.sisyphus/evidence/` for every task
- defect register with reproducible failures and validated fixes
- updated automated checks and documentation for all confirmed changes

### Definition of Done (verifiable conditions with commands)
- `.venv/bin/pytest tests/unit` passes after all backend changes.
- `npm --prefix frontend run test` passes after frontend changes.
- `npm --prefix frontend run build` succeeds.
- `npm --prefix frontend run test:inventory` succeeds.
- `npx --prefix frontend playwright test` passes against the local QA target.
- `docker compose -f docker-compose.yml -f docker-compose.qa.yml --env-file .env.qa config` succeeds.
- `.venv/bin/poe-migrate --status --dry-run` succeeds without introducing destructive schema actions.
- all live verification tasks produce evidence and do not mutate crawled public stash data.

### Must Have
- Dual-target E2E parity matrix across local QA and live.
- TDD-oriented remediation for every verified defect.
- Exact evidence path per task.
- Explicit live-vs-QA safety labels per scenario.
- ML checks for restart persistence, candidate-vs-incumbent gates, and non-forgetting evidence.
- Documentation and CI verification aligned to proven behavior.
- A canonical opportunity contract that defines homepage/opportunities/scanner/journal/diagnostics/ML field semantics.
- Homepage and primary navigation that surface actionable trade opportunities before passive alerts.
- Stable opportunity identity across reruns unless semantic identity fields change.
- Strategy runtime enforcement of declared `strategy.toml` metadata and non-placeholder candidate semantics.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No deletion, overwrite, replay reset, truncation, or mutation of crawled public stash data or canonical persisted public-stash history.
- No destructive live DB experiments, migration rehearsal, or bulk data rewrites against the public environment.
- No fixing issues before reproducing them with a failing automated or scripted check.
- No treating mocked frontend success as equivalent to real backend/live success.
- No undocumented target switching between QA and live.
- No splitting this work into multiple plans.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: TDD for remediation tasks; tests-first or reproducer-first before code change, then targeted rerun, then subsystem rerun, then full gate rerun.
- QA policy: Every task includes agent-executed happy-path and failure/edge-case scenarios.
- Evidence: `.sisyphus/evidence/review/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. Extract shared dependencies first.

Wave 1: environment contract, inventory, target pinning, and baseline verification
Wave 2: opportunity-contract definition, backend/schema/data-contract review, and local QA harness hardening
Wave 3: frontend/live parity, auth/stash/service-action flows, and ML governance
Wave 4: remediation completion, docs/CI alignment, and final end-to-end replay

### Product Layer: Opportunity-Centric Experience
- Canonical product flow: source market rows -> strategy SQL -> runtime filtering/identity -> scanner recommendation -> API payload -> homepage/scanner UI -> alerting/journal/diagnostics -> ML augmentation.
- P0: define the canonical opportunity contract and stable identity rules before UI/API/runtime remediation.
- P1: make homepage and navigation opportunity-first, stabilize IDs, enrich API payloads, and enforce strategy metadata/runtime semantics.
- P2: add journal and diagnostics surfaces and expose ML-backed opportunity signals through the same recommendation contract.
- Owner surfaces: `UI`, `API`, `runtime`, `SQL`, `observability`, `ML`.

### Dependency Matrix (full, all tasks)
- 1 blocks 2, 3, 4, 4A, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
- 2 blocks 4A, 5, 6, 7, 8, 9, 10, 11, 12, 13
- 3 blocks 8, 9, 10, 13
- 4 blocks 4A, 8, 9, 10, 14
- 4A blocks 5, 6, 8, 9, 10, 11, 13, 14, 16
- 5 blocks 14
- 6 blocks 14
- 7 blocks 14
- 8 blocks 14
- 9 blocks 14
- 10 blocks 14
- 11 blocks 14
- 13 blocks 14
- 14 blocks 12 and 15
- 12 blocks 16
- 15 blocks 16
- 16 blocks final verification

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 4 tasks -> `deep`, `unspecified-high`, `quick`
- Wave 2 -> 5 tasks -> `deep`, `unspecified-high`, `visual-engineering`
- Wave 3 -> 4 tasks -> `visual-engineering`, `deep`, `unspecified-high`
- Wave 4 -> 4 tasks -> `unspecified-high`, `writing`, `deep`

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Establish audit contract, safety matrix, and immutable-data guardrails

  **What to do**: Create the execution-time audit contract covering targets, credentials, evidence naming, allowed mutations, forbidden data actions, and restart policy. Define exact labels for every scenario: `qa-only`, `live-readonly`, `live-allowlisted-mutation`. Explicitly prohibit any delete/overwrite/replay-reset/truncate action against crawled public stash data and canonical persisted public-stash history. Name the exact live mutation allowlist at the endpoint/action level: only explicit service restart actions approved in the matrix may mutate live state; all other live mutations are forbidden.
  **Must NOT do**: Do not start code changes, migration rewrites, or live destructive checks before this contract is written into the execution notes/evidence bundle.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: establishes cross-system safety policy that all later tasks depend on.
  - Skills: [`protocol-compat`] - needed for ClickHouse/data-contract safety rules.
  - Omitted: [`docs-specialist`] - documentation polish is secondary to safety definition here.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16 | Blocked By: none

  **References**:
  - Pattern: `README.md` - existing operator and QA command surface.
  - Pattern: `docker-compose.qa.yml` - QA-only runtime ports, trusted-origin bypass, seeded operator token.
  - Pattern: `Makefile` - qa-up, qa-seed, fault injectors, qa-verify-product entrypoints.
  - Pattern: `poe_trade/api/app.py` - routes whose live behaviors must be safety-classified.
  - External: `https://poe.lama-lan.ch` - live frontend target named by the user.

  **Acceptance Criteria**:
  - [ ] Scenario classification matrix exists for all major flows and names which target(s) each flow may hit.
  - [ ] Live mutation allowlist names exact approved restart endpoints/actions and states that all other live mutations are forbidden.
  - [ ] Forbidden live data actions explicitly name crawled public stash data and canonical history tables/stores.
  - [ ] Restart policy is defined as allowed on live and QA, with evidence requirements before and after restart.
  - [ ] Evidence path convention is fixed for all downstream tasks.

  **QA Scenarios**:
  ```text
  Scenario: Safety matrix complete
    Tool: Bash
    Steps: verify referenced commands exist in README/Makefile and list final scenario classes in task evidence
    Expected: every major route/service family has one of qa-only/live-readonly/live-allowlisted-mutation
    Evidence: .sisyphus/evidence/review/task-1-audit-contract.json

  Scenario: Immutable-data policy check
    Tool: Bash
    Steps: search plan notes for forbidden verbs and public stash data targets
    Expected: policy explicitly forbids delete/overwrite/truncate/replay-reset against crawled public stash data
    Evidence: .sisyphus/evidence/review/task-1-immutable-data.json
  ```

  **Commit**: NO | Message: `docs(review): define audit contract` | Files: `.sisyphus/evidence/review/*`

- [x] 2. Build maintained-code coverage map and subsystem ownership inventory

  **What to do**: Enumerate all maintained source areas across `poe_trade/`, `frontend/src/`, `tests/unit/`, `schema/`, `.github/workflows/`, key docs, and strategy/config surfaces. Record for each area: purpose, runtime entrypoints, current automated checks, live dependency level, and whether it is already covered by QA inventory or still untested.
  **Must NOT do**: Do not count generated/vendor/build outputs (`frontend/dist`, `frontend/node_modules`, Playwright outputs, lockfiles, existing evidence blobs) toward coverage completion.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: broad repo inventory and coverage accounting.
  - Skills: []
  - Omitted: [`protocol-compat`] - schema safety is addressed in task 6.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 5, 6, 7, 8, 9, 10, 11, 12, 13 | Blocked By: 1

  **References**:
  - Pattern: `AGENTS.md` - top-level maintained-scope guidance.
  - Pattern: `poe_trade/AGENTS.md` - package boundaries and conventions.
  - Pattern: `tests/AGENTS.md` - test surface guidance.
  - Pattern: `frontend/src/services/api.ts` - frontend API dependencies and stubbed feature surface.
  - Pattern: `.github/workflows/python-ci.yml` - current CI verification coverage.

  **Acceptance Criteria**:
  - [ ] Inventory covers every maintained directory and marks excluded generated/vendor paths explicitly.
  - [ ] Each subsystem lists runtime entrypoint(s), test files, and review owner task(s).
  - [ ] Inventory identifies gaps where no automated or scripted verification currently exists.

  **QA Scenarios**:
  ```text
  Scenario: Maintained-scope accounting
    Tool: Bash
    Steps: enumerate maintained paths from AGENTS/readme guidance and compare against coverage inventory output
    Expected: no maintained source directory is missing from the inventory
    Evidence: .sisyphus/evidence/review/task-2-coverage-map.json

  Scenario: Exclusion precision
    Tool: Bash
    Steps: verify exclusion list includes dist/node_modules/locks/generated evidence/build outputs and excludes only those classes
    Expected: coverage accounting excludes generated/vendor/build outputs but not maintained source/docs/tests/schema
    Evidence: .sisyphus/evidence/review/task-2-exclusions.json
  ```

  **Commit**: NO | Message: `docs(review): map maintained coverage` | Files: `.sisyphus/evidence/review/*`

- [x] 3. Pin environment targets and prevent accidental QA/live crossover

  **What to do**: Define exact execution commands and environment variables for QA-target frontend/backend runs versus live-target read/live-target mutation flows. Prove which commands hit `http://127.0.0.1:18080`, which hit `https://api.poe.lama-lan.ch`, and how frontend runs avoid silently using the wrong default API base.
  **Must NOT do**: Do not allow any browser or CLI execution without explicit target pinning in the command or environment file.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: focused target matrix and command pinning.
  - Skills: []
  - Omitted: [`docs-specialist`] - this is execution control, not narrative docs work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 8, 9, 10, 13 | Blocked By: 1

  **References**:
  - Pattern: `frontend/src/services/config.ts` - frontend default API base.
  - Pattern: `frontend/package.json` - `qa:dev` command pins `VITE_API_BASE_URL=http://127.0.0.1:18080`.
  - Pattern: `frontend/playwright.config.ts` - local QA browser target.
  - Pattern: `docker-compose.qa.yml` - QA API port mapping and trusted-origin bypass.

  **Acceptance Criteria**:
  - [ ] Every execution command in the plan names its target environment explicitly.
  - [ ] QA frontend/browser commands are pinned to `127.0.0.1:4173` -> `127.0.0.1:18080`.
  - [ ] Live browser/API commands are pinned to the live host and recorded separately from QA evidence.

  **QA Scenarios**:
  ```text
  Scenario: QA target pinning
    Tool: Bash
    Steps: inspect frontend/package.json and Playwright config; record final QA command matrix
    Expected: local frontend runs cannot accidentally hit live API when using QA commands
    Evidence: .sisyphus/evidence/review/task-3-qa-targets.json

  Scenario: Live target pinning
    Tool: Bash
    Steps: inspect config defaults and live command list; record explicit live base URLs
    Expected: live checks are separated and never rely on implicit defaults
    Evidence: .sisyphus/evidence/review/task-3-live-targets.json
  ```

  **Commit**: NO | Message: `test(review): pin audit targets` | Files: `.sisyphus/evidence/review/*`

- [x] 4. Capture deterministic baseline across unit, build, CLI, and migration dry-run surfaces

  **What to do**: Run the cheapest deterministic checks first and capture failures before any remediation: backend unit tests, frontend unit tests, frontend build, scenario inventory validation, CLI smoke commands, compose config validation, and migration dry-run/status checks. Produce one baseline matrix with pass/fail and failing command output excerpts.
  **Must NOT do**: Do not start fixing defects until the failing baseline is captured and grouped by subsystem.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: broad deterministic baseline across multiple runtimes.
  - Skills: []
  - Omitted: [`playwright`] - browser work starts in later tasks.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 8, 9, 10, 14 | Blocked By: 1

  **References**:
  - Pattern: `.github/workflows/python-ci.yml` - current backend/CLI baseline.
  - Pattern: `Makefile` - `qa-verify-product` aggregate command.
  - Pattern: `README.md` - bootstrap, CLI, migration, and sanity command list.
  - Test: `tests/unit/test_ml_runtime.py`
  - Test: `frontend/src/test/scenarioInventory.test.ts`

  **Acceptance Criteria**:
  - [ ] Baseline matrix records status for pytest, vitest, build, inventory validation, playwright dependency readiness, compose config, and migration dry-run.
  - [ ] Each failure includes command, exit code, and first relevant error lines.
  - [ ] No remediation begins without a captured failing baseline or explicit all-green baseline proof.

  **QA Scenarios**:
  ```text
  Scenario: Deterministic baseline run
    Tool: Bash
    Steps: run unit/build/cli/migration dry-run commands and collect statuses
    Expected: a complete baseline matrix is produced with pass/fail by subsystem
    Evidence: .sisyphus/evidence/review/task-4-baseline.json

  Scenario: Failure grouping
    Tool: Bash
    Steps: cluster any failing commands by backend/frontend/schema/ci/ml category
    Expected: no failure remains unassigned to a later remediation task
    Evidence: .sisyphus/evidence/review/task-4-failure-groups.json
  ```

  **Commit**: NO | Message: `test(review): capture deterministic baseline` | Files: `.sisyphus/evidence/review/*`

- [x] 4A. Define the canonical opportunity contract and product flow

  **What to do**: Define the opportunity-centric product contract that every later product-layer task must follow. Specify the canonical scanner/homepage/opportunities/journal/diagnostics/ML flow, the stable identity rule for an opportunity, the minimum recommendation schema, the minimum API payload, the rule that homepage “top opportunities” come from scanner recommendations rather than alerts, and the exact producer/consumer mapping for `UI`, `API`, `runtime`, `SQL`, `observability`, and `ML`. This task must also classify which current fields are placeholders or missing and which additive API/schema changes are allowed. Produce a versioned contract artifact and deterministic fixture examples so later tasks can replay identity behavior without guessing.
  **Must NOT do**: Do not let later tasks invent their own opportunity shape, alert semantics, homepage semantics, or stable-ID rules independently.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: this is the contract and dependency anchor for the entire product-layer workstream.
  - Skills: [`protocol-compat`] - additive API/schema evolution rules may be required.
  - Omitted: [`docs-specialist`] - this is execution-contract design, not final docs polish.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 5, 6, 8, 9, 10, 11, 13, 14, 16 | Blocked By: 1, 2, 4

  **References**:
  - Pattern: `poe_trade/api/ops.py` - dashboard/contract/scanner payload semantics.
  - Pattern: `frontend/src/components/tabs/DashboardTab.tsx` - current homepage opportunity rendering.
  - Pattern: `frontend/src/services/api.ts` - frontend consumers and missing product fields.
  - Pattern: `poe_trade/strategy/scanner.py` - current recommendation/alert identity generation.
  - Pattern: `poe_trade/strategy/registry.py` - current runtime metadata model.
  - Pattern: `poe_trade/sql/strategy/*/*.sql` - producer surfaces for recommendations/backtests.

  **Acceptance Criteria**:
  - [ ] Canonical opportunity schema is defined with required fields including `semantic_key`, `search_hint`, `item_name`, `why_it_fired`, `buy_plan`, `max_buy`, `transform_plan`, `exit_plan`, `expected_profit_chaos`, `expected_roi`, `expected_hold_minutes`, `confidence`, `liquidity_score`, `freshness_minutes`, `gold_cost`, and `evidence_snapshot` or structured evidence.
  - [ ] Stable-ID rule is defined so identical underlying opportunities map to the same semantic identity across reruns unless identity fields change.
  - [ ] A versioned JSON fixture/schema artifact exists for the contract and includes replayable seeded examples.
  - [ ] Homepage, scanner/opportunities tab, alerts, journal loop, diagnostics, and ML augmentation are all mapped to this same contract.
  - [ ] Explicit non-goals are recorded for anything that remains outside current authority or current backend support.

  **QA Scenarios**:
  ```text
  Scenario: Opportunity contract completeness
    Tool: Bash
    Steps: compare contract output against current UI/API/runtime/SQL surfaces and record required fields, producers, and consumers
    Expected: one canonical contract exists and every downstream product-layer task can reference it without ambiguity
    Evidence: .sisyphus/evidence/review/task-4a-opportunity-contract.json

  Scenario: Stable identity rule check
    Tool: Bash
    Steps: compare current scanner alert/recommendation identity logic against proposed semantic identity fields and replay seeded fixtures with same vs changed semantic keys
    Expected: the contract explicitly replaces run-scoped IDs with stable semantic identity rules; identical seeded inputs preserve IDs and semantic-key changes force ID changes
    Evidence: .sisyphus/evidence/review/task-4a-opportunity-identity.json
  ```

  **Commit**: NO | Message: `docs(review): define opportunity contract` | Files: `.sisyphus/evidence/review/*`

- [x] 5. Audit backend API contracts, auth boundaries, and opportunity-product payload behavior

  **What to do**: Review and test the backend API surface for route registration, auth requirements, CORS/trusted-origin bypass, session behavior, service action guards, payload validation, and negative-path responses. Reconcile actual route behavior with README claims, frontend assumptions, and the canonical opportunity contract from task 4A. This task must explicitly verify dashboard-vs-scanner semantics, scanner/opportunities discoverability in the ops contract, recommendation sorting/filtering richness, evidence/search-hint exposure, summary diagnostics, journal route exposure, price-check comparables semantics, and the internal dashboard artifact’s fetch/error behavior.
  **Must NOT do**: Do not treat QA trusted-origin bypass behavior as proof that live bearer-token behavior is correct.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: core backend contract correctness with auth and control-flow edge cases.
  - Skills: []
  - Omitted: [`protocol-compat`] - no schema evolution focus in this task.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 14 | Blocked By: 1, 2, 4A

  **References**:
  - Pattern: `poe_trade/api/app.py` - full route registration and auth gating.
  - Pattern: `poe_trade/api/ml.py` - ML route contracts and request validation.
  - Pattern: `poe_trade/api/ops.py` - ops payload composition and service action surface.
  - Pattern: `dashboard/internal/app.js` - internal dashboard fetch path and fallback behavior.
  - Test: `tests/unit/test_api_auth.py`
  - Test: `tests/unit/test_api_auth_oauth.py`
  - Test: `tests/unit/test_api_ml_routes.py`
  - Test: `tests/unit/test_api_ops_routes.py`

  **Acceptance Criteria**:
  - [ ] All documented API routes have passing positive and negative automated coverage.
  - [ ] Auth/session/trusted-origin behavior differs between QA and live only where explicitly intended and documented.
  - [ ] Service action routes are tested for allowed, forbidden, invalid, and unavailable cases.
  - [ ] `/api/v1/ops/dashboard` and the homepage contract expose opportunities separately from alerts; alerts are not mislabeled as top trade opportunities.
  - [ ] `/api/v1/ops/scanner/recommendations` supports contract-approved sorting/filtering and returns enough evidence/search-hint data for the UI without fallback guesswork.
  - [ ] `/api/v1/ops/scanner/summary` distinguishes empty/no-data/no-opportunity/freshness states well enough for the UI to avoid silent emptiness.
  - [ ] Journal API exposure is either implemented additively or the plan explicitly gates `requires_journal` strategies from frontend availability.
  - [ ] `price_check_payload()` either returns real comparables or the frontend/UI contract stops pretending that comparables are available.
  - [ ] Exact request examples are captured for `/api/v1/ops/dashboard`, `/api/v1/ops/scanner/summary`, `/api/v1/ops/scanner/recommendations`, `/api/v1/ops/leagues/{league}/price-check`, and any additive `/api/v1/journal/*` routes, including expected status codes and payload keys.
  - [ ] Any README/contract mismatch is either fixed in code/tests or documented as intentional.

  **QA Scenarios**:
  ```text
  Scenario: Protected route happy path
    Tool: Bash
    Steps: GET `/healthz`, `/api/v1/ops/contract`, `/api/v1/ops/dashboard`, `/api/v1/ops/scanner/summary`, `/api/v1/ops/scanner/recommendations?sort=expected_profit_chaos&min_confidence=0.65`, `/api/v1/ml/contract`; POST `/api/v1/ops/leagues/Mirage/price-check` with a fixture item; if implemented, exercise `/api/v1/journal/open` and journal POST routes with valid QA credentials or cookie session
    Expected: healthz=200, contract/dashboard/scanner routes return 200 with expected top-level keys, scanner payloads expose opportunity fields rather than alert-only fields, and price-check/journal behavior matches the contract
    Evidence: .sisyphus/evidence/review/task-5-api-happy.json

  Scenario: Protected route failure matrix
    Tool: Bash
    Steps: repeat selected routes with missing bearer, invalid bearer, denied origin, invalid league, invalid price-check body, unsupported sort/filter params, and nonexistent service/action
    Expected: correct 4xx/5xx codes, stable error payloads, and no silent fallback telemetry/product masking
    Evidence: .sisyphus/evidence/review/task-5-api-failure.json
  ```

  **Commit**: YES | Message: `test(api): harden opportunity route contracts` | Files: `poe_trade/api/*`, `dashboard/internal/*`, `tests/unit/test_api_*.py`, `README.md`

- [x] 6. Audit schema, migrations, ClickHouse compatibility, and immutable-data safety

  **What to do**: Review `schema/`, migration ordering, sanity queries, ClickHouse read/write assumptions, and downstream contracts. Verify migration dry-run behavior, additive-safety expectations, restart/retry tolerance, and data-integrity checks without mutating crawled public stash history. This task must explicitly assess whether current gold marts are too coarse for the named strategies, whether additive candidate marts or diagnostics marts/endpoints are required, and whether league/null handling at the gold layer can explain zero-row backtests. If schema or query defects are found, add targeted verification and fix using additive-safe patterns only.
  **Must NOT do**: Do not drop tables, reorder columns destructively, issue mass deletes, or mutate crawled public stash data.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: ClickHouse schema/data-contract and recovery reasoning.
  - Skills: [`protocol-compat`] - required for additive-safe migration review.
  - Omitted: [`docs-specialist`] - docs follow only after verified schema behavior.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 14 | Blocked By: 1, 2, 4A

  **References**:
  - Pattern: `schema/migrations/` - migration chain.
  - Pattern: `schema/sanity/bronze.sql`
  - Pattern: `schema/sanity/silver.sql`
  - Pattern: `schema/sanity/gold.sql`
  - Pattern: `poe_trade/sql/gold/110_listing_ref_hour.sql`
  - Pattern: `poe_trade/sql/gold/120_liquidity_ref_hour.sql`
  - Pattern: `poe_trade/sql/gold/130_bulk_premium_hour.sql`
  - Pattern: `poe_trade/sql/gold/140_set_ref_hour.sql`
  - Pattern: `poe_trade/db/migrations.py` - migration runner behavior.
  - Pattern: `poe_trade/analytics/reports.py` - current mart row-count reporting.
  - Pattern: `README.md` - migration and sanity-query commands.
  - Test: `tests/unit/test_migrations.py`

  **Acceptance Criteria**:
  - [ ] Migration review records whether every planned fix remains additive-safe or is escalated as incompatible.
  - [ ] Dry-run and sanity-query surfaces are exercised and evidence captured.
  - [ ] Immutable crawled public stash data safety is explicitly preserved in all schema/data tasks.
  - [ ] The plan explicitly classifies current gold marts as monitoring/coarse-market-state marts versus candidate-generation marts, with any new candidate marts defined additively.
  - [ ] League/data-coverage diagnostics exist or are planned additively for `max(time_bucket)`, row counts, distinct leagues, and null/blank league counts per relevant mart.
  - [ ] Each zero-row strategy is resolved to one of: `no_data`, `coarse_mart_gap`, `league_nulls`, `thresholded_out`, `runtime_metadata_ignored`, or another explicitly named root cause.
  - [ ] At least one seeded QA strategy either produces a non-placeholder candidate/backtest row after remediation or is explicitly classified as blocked by a named root cause.
  - [ ] Any new marts or diagnostics preserve backward/forward safety for existing readers.
  - [ ] Any required schema/code change includes targeted regression coverage.

  **QA Scenarios**:
  ```text
  Scenario: Migration and sanity preflight
    Tool: Bash
    Steps: run poe-migrate --status --dry-run and applicable sanity queries against QA ClickHouse; compare current gold mart schemas to strategy requirements
    Expected: output captured; destructive migration actions are absent or explicitly escalated; granularity gaps are documented precisely
    Evidence: .sisyphus/evidence/review/task-6-schema-preflight.json

  Scenario: Immutable-data guard check
    Tool: Bash
    Steps: inspect planned SQL/code changes and executed queries for forbidden delete/truncate/reset verbs against public stash data stores and for additive candidate-mart/diagnostic evolution
    Expected: no forbidden mutation exists and all new data contracts are additive-safe
    Evidence: .sisyphus/evidence/review/task-6-immutable-check.json
  ```

  **Commit**: YES | Message: `fix(schema): preserve compatibility and audit migrations` | Files: `schema/**`, `poe_trade/db/*`, `tests/unit/test_migrations.py`, `README.md`

- [x] 7. Validate ingestion, checkpoint recovery, scanner, and long-running service resilience

  **What to do**: Audit the ingestion and service layer for startup behavior, checkpoint recovery, duplicate/out-of-order handling, scanner runs, rate-limit/backoff paths, and restart resilience. Use QA fixtures and safe service restarts to prove behavior before and after any fixes. This task must also verify service-registry semantics for disabled optional services, one-shot jobs, denominator accuracy on the homepage, freshness/status inference so that the dashboard does not mislead operators about the actual trading path, and scanner runtime behavior such as strategy metadata enforcement, stable alert identity, and duplicate-alert cooldown/novelty handling.
  **Must NOT do**: Do not reset or delete canonical crawled public stash data to force a scenario; use QA fixtures, faults, or safe restart-based reproductions only.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: long-running operational behavior and failure recovery.
  - Skills: []
  - Omitted: [`protocol-compat`] - schema compatibility is covered elsewhere.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 14 | Blocked By: 1, 2

  **References**:
  - Pattern: `poe_trade/ingestion/market_harvester.py`
  - Pattern: `poe_trade/ingestion/status.py`
  - Pattern: `poe_trade/api/service_control.py`
  - Pattern: `poe_trade/strategy/registry.py`
  - Pattern: `poe_trade/strategy/scanner.py`
  - Pattern: `poe_trade/strategy/backtest.py`
  - Pattern: `Makefile` - fault injectors and restart-friendly QA commands.
  - Test: `tests/unit/test_market_harvester.py`
  - Test: `tests/unit/test_market_harvester_auth.py`
  - Test: `tests/unit/test_rate_limit.py`
  - Test: `tests/unit/test_scheduler.py`

  **Acceptance Criteria**:
  - [ ] Restart, retry, degraded dependency, and scanner-fault behavior are proven with deterministic evidence.
  - [ ] Checkpoint and recovery logic has automated coverage for failure paths relevant to discovered defects.
  - [ ] Service-control operations capture pre-restart baseline and post-restart health proof.
  - [ ] Service health/reporting semantics distinguish disabled optional services, one-shot jobs, stale workers, and always-on services without misleading the primary trading dashboard.
  - [ ] Scanner runtime either enforces declared strategy metadata (`minima`, `params`, `cooldown_minutes`, `requires_journal`, `min_sample_count`) or records an explicit remediation requirement with failing reproducers.
  - [ ] Alert identity and cooldown behavior are stable across reruns and do not generate run-scoped duplicate-alert spam for semantically identical opportunities.

  **QA Scenarios**:
  ```text
  Scenario: QA long-running service recovery
    Tool: Bash
    Steps: run qa-up, qa-seed, inject scanner/api/service-action faults, restart affected services, then capture status and logs
    Expected: services recover or fail with stable, documented signals; post-restart health is provable
    Evidence: .sisyphus/evidence/review/task-7-service-recovery.json

  Scenario: Failure-path determinism
    Tool: Bash
    Steps: trigger degraded/failure modes and rerun targeted unit or script reproducers
    Expected: each discovered defect has a deterministic failing reproducer before any fix
    Evidence: .sisyphus/evidence/review/task-7-failure-repro.json
  ```

  **Commit**: YES | Message: `fix(ingestion): harden recovery and service resilience` | Files: `poe_trade/ingestion/*`, `poe_trade/services/*`, `tests/unit/test_*harvester*.py`, `tests/unit/test_rate_limit.py`, `tests/unit/test_scheduler.py`

- [x] 8. Verify and extend local full-stack E2E against disposable QA

  **What to do**: Use the disposable QA stack as the mutation-friendly full-stack test bed. Reconcile `frontend/src/test/scenario-inventory.json` with actual client behavior, expand Playwright where gaps exist, run the browser against the real QA backend, and prove dashboard, opportunities/scanner, services, analytics, messages, stash, pricecheck, auth/session, journal-aware states, diagnostics, and ML automation flows end to end. This task must explicitly verify that the homepage and any dedicated opportunities view consume scanner recommendations rather than alert summaries.
  **Must NOT do**: Do not rely on mocks when the real QA backend is available. Do not treat current scenario inventory as authoritative until reconciled with `frontend/src/services/api.ts`.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: UI behavior plus real-stack Playwright flows.
  - Skills: [`playwright`] - required for browser-based verification.
  - Omitted: [`docs-specialist`] - behavior proof precedes docs.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 14 | Blocked By: 1, 2, 3, 4, 4A

  **References**:
  - Pattern: `frontend/src/test/playwright/inventory.spec.ts` - current scenario runner.
  - Pattern: `frontend/src/test/scenario-inventory.json` - declared scenario inventory.
  - Pattern: `frontend/src/services/api.ts` - actual route usage and stubbed methods.
  - Pattern: `frontend/src/components/tabs/DashboardTab.tsx` - current alert-driven opportunity rendering.
  - Pattern: `frontend/playwright.config.ts` - QA browser target.
  - Pattern: `Makefile` - `qa-frontend`, `qa-verify-product`.

  **Acceptance Criteria**:
  - [ ] Scenario inventory matches actual implemented frontend flows and backend routes.
  - [ ] Homepage renders opportunity-first content from scanner recommendations and keeps alerts visually separate.
  - [ ] Scanner/opportunities is reachable as a first-class product surface if the canonical contract requires it.
  - [ ] The QA browser suite asserts exact selectors and network calls for opportunity rendering, including `data-testid="panel-dashboard-root"`, a dedicated opportunities/scanner tab selector, and opportunity-card selectors added by remediation.
  - [ ] Playwright passes on the real QA stack for all supported tabs and interactions.
  - [ ] Any unsupported/stubbed feature path is explicitly classified and not mislabeled as passing product behavior.
  - [ ] Each failing QA browser defect has a reproducer before remediation.

  **QA Scenarios**:
  ```text
  Scenario: Full QA browser happy path
    Tool: Playwright
    Steps: launch QA frontend, click `data-testid="tab-dashboard"`, `data-testid="tab-opportunities"` when present, and other primary tabs; assert `data-testid="panel-dashboard-root"`, `data-testid="panel-opportunities"`, and opportunity-card selectors after remediation; inspect network calls for `/api/v1/ops/scanner/recommendations` and ensure dashboard top-opportunity content is scanner-backed
    Expected: visible panels, successful API-backed renders, scanner-backed opportunities, and captured evidence for each supported flow
    Evidence: .sisyphus/evidence/review/task-8-qa-happy.json

  Scenario: Full QA browser degraded path
    Tool: Playwright
    Steps: activate QA fault profiles, repeat selected flows, and capture resulting UI/API behavior
    Expected: graceful degraded states and stable error affordances; no silent hangs or uncaught crashes
    Evidence: .sisyphus/evidence/review/task-8-qa-degraded.json
  ```

  **Commit**: YES | Message: `test(frontend): expand QA e2e coverage` | Files: `frontend/src/**`, `frontend/src/test/**`, `Makefile`, `README.md`

- [x] 9. Verify live frontend and API parity against `https://poe.lama-lan.ch`

  **What to do**: Exercise the hosted frontend and its live API integration with an explicit parity matrix against QA results. Confirm which flows work identically, which intentionally differ, and which regress only on live. Capture console/network evidence, selectors, HTTP statuses, payload-shape differences, homepage opportunity semantics, service denominator semantics, and scanner/opportunities discoverability. Fix only after a deterministic live-vs-QA mismatch is reproduced and classified.
  **Must NOT do**: Do not run hidden destructive DB actions on live. Do not click service-control buttons or mutation flows on live unless they are explicitly classified as `live-allowlisted-mutation` by task 1.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: browser-driven live parity audit.
  - Skills: [`playwright`] - required for live browser evidence.
  - Omitted: [`protocol-compat`] - live parity is UI/API behavior, not schema design.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 14 | Blocked By: 1, 2, 3, 4A

  **References**:
  - External: `https://poe.lama-lan.ch` - live frontend target.
  - Pattern: `frontend/src/services/config.ts` - default live API base behavior.
  - Pattern: `frontend/src/services/api.ts` - expected route surface.
  - Pattern: `frontend/src/test/playwright/inventory.spec.ts` - scenario structure to adapt for live-safe replay.

  **Acceptance Criteria**:
  - [ ] Each major supported flow has QA evidence and live evidence side by side.
  - [ ] Live homepage does not present alert summaries as trade opportunities after remediation.
  - [ ] Live service-health messaging does not mislead the user about optional/one-shot services versus real opportunity availability.
  - [ ] Live browser verification uses explicit selector and request assertions for dashboard/opportunities semantics rather than visual spot checks only.
  - [ ] Every live mismatch is classified as bug, intentional environment difference, or blocked credential dependency.
  - [ ] No live mutation occurs outside the allowlisted set established in task 1.

  **QA Scenarios**:
  ```text
  Scenario: Live parity happy path
    Tool: Playwright
    Steps: open `https://poe.lama-lan.ch`, assert `data-testid="panel-dashboard-root"`, attempt `data-testid="tab-opportunities"` or equivalent first-class opportunities navigation after remediation, inspect network calls for `/api/v1/ops/dashboard` and `/api/v1/ops/scanner/recommendations`, and compare selectors/network behavior against QA evidence
    Expected: parity matrix clearly marks match/mismatch for each flow, including opportunity-versus-alert semantics
    Evidence: .sisyphus/evidence/review/task-9-live-parity.json

  Scenario: Live parity failure classification
    Tool: Playwright
    Steps: capture any failed or blocked live flow with console/network traces and compare to QA equivalent
    Expected: each mismatch has an explicit classification and next-action owner
    Evidence: .sisyphus/evidence/review/task-9-live-mismatches.json
  ```

  **Commit**: YES | Message: `fix(frontend): align live parity regressions` | Files: `frontend/src/**`, `poe_trade/api/**`, `tests/unit/**`, `frontend/src/test/**`

- [x] 10. Verify authenticated flows, stash behavior, and live allowlisted service actions

  **What to do**: Exercise credential-gated auth/session/stash flows and the minimal allowlisted live mutation surface. Validate login, callback/session refresh, logout, stash status/tabs, and only those live service restarts explicitly allowed by task 1. Use pre-action baseline capture, bounded restart health polling, and post-action parity checks. Respect the immutable public-stash-data rule at all times.
  **Must NOT do**: Do not perform live destructive actions beyond allowlisted restarts. Do not modify, delete, or replay-reset crawled public stash data.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: credentialed flows, state transitions, and operational safety.
  - Skills: [`playwright`] - browser auth/session evidence may be required.
  - Omitted: [`docs-specialist`] - execution proof first.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 14 | Blocked By: 1, 2, 3, 4

  **References**:
  - Pattern: `poe_trade/api/app.py` - auth/session/stash/service-control routes.
  - Pattern: `frontend/src/services/auth.tsx` - frontend auth/session behavior.
  - Pattern: `frontend/src/services/api.ts` - stash and service action callers.
  - Test: `tests/unit/test_api_auth.py`
  - Test: `tests/unit/test_auth_session.py`
  - Test: `tests/unit/test_account_stash_service.py`

  **Acceptance Criteria**:
  - [ ] Live credential prerequisites are checked up front: live `poeSessionId` bootstrap credential and live operator bearer token.
  - [ ] Auth/session, stash, and allowlisted restart flows have deterministic reproducers and post-action evidence.
  - [ ] Live restart actions, if used, record baseline, action, bounded polling, and healthy post-state.
  - [ ] No stash-data mutation occurs during any verification or remediation.
  - [ ] Missing live credentials close the affected live tasks as `blocked_by_credentials` with evidence rather than implicit failure.

  **QA Scenarios**:
  ```text
  Scenario: Credentialed happy path
    Tool: Playwright
    Steps: execute login/session refresh/logout and stash status/tabs flows on QA and live as allowed by credentials and target matrix
    Expected: stable session indicators, stash payloads, and post-login behavior
    Evidence: .sisyphus/evidence/review/task-10-auth-stash-happy.json

  Scenario: Allowlisted restart path
    Tool: Bash
    Steps: capture service baseline, invoke approved restart, poll health endpoints/status payloads, then compare post-state
    Expected: service returns healthy without manual intervention and without stash-data mutation
    Evidence: .sisyphus/evidence/review/task-10-restart-proof.json
  ```

  **Commit**: YES | Message: `fix(auth): harden session stash and restart flows` | Files: `poe_trade/api/**`, `poe_trade/services/**`, `frontend/src/**`, `tests/unit/**`, `frontend/src/test/**`

- [x] 11. Prove ML training, persistence, and learning-without-forgetting behavior

  **What to do**: Audit the ML pipeline end to end: training loop, status/history/report surfaces, runtime profile persistence, artifact writes, active model version selection, candidate-vs-incumbent evaluation, protected cohort regression blocking, warm start behavior, resume semantics, and restart/reload persistence. Define concrete evidence for “learning without forgetting”: incumbent protection, cohort non-regression, temporal holdout integrity, model version persistence across restart, and rollback-safe promotion behavior. This task must also verify whether ML outputs currently feed the scanner recommendation product layer at all and, if not, plan/add the additive integration path for ML-backed opportunity families using the canonical opportunity contract.
  **Must NOT do**: Do not equate aggregate metric improvement with safe promotion. Do not overwrite incumbent artifacts without preserving verifiable version lineage and evaluation evidence.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: cross-cutting ML governance and persistence behavior.
  - Skills: []
  - Omitted: [`protocol-compat`] - data-contract rules matter, but this task centers on model governance/runtime behavior.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 14 | Blocked By: 1, 2, 4A

  **References**:
  - Pattern: `poe_trade/ml/workflows.py` - train loop, promotion logic, active model version, warm start, resume.
  - Pattern: `poe_trade/ml/runtime.py` - runtime profile detection and persistence.
  - Pattern: `poe_trade/services/ml_trainer.py` - autonomous training service loop.
  - Pattern: `poe_trade/api/ml.py` - ML status and automation history mapping.
  - Test: `tests/unit/test_ml_tuning.py`
  - Test: `tests/unit/test_ml_runtime.py`
  - Test: `tests/unit/test_ml_cli.py`

  **Acceptance Criteria**:
  - [ ] Evidence proves active model version survives service restart or process reload.
  - [ ] Candidate-vs-incumbent history, verdicts, and stop reasons are queryable and consistent with status/report outputs.
  - [ ] Protected cohort regression blocks promotion when expected.
  - [ ] The plan explicitly proves whether ML signals are or are not surfaced as scanner opportunities, and remediates that gap if required.
  - [ ] Any ML-backed strategy family writes into the same normalized scanner recommendation contract and degrades cleanly when ML signals are absent.
  - [ ] Any change that lets ML affect recommendation ranking includes before/after QA comparison, a feature-gated rollout or rollback rule, and evidence that scanner quality did not silently regress.
  - [ ] Any ML fix includes failing reproducer/tests first and preserves artifact lineage.

  **QA Scenarios**:
  ```text
  Scenario: ML persistence and promotion happy path
    Tool: Bash
    Steps: run bounded train-loop/status/report flows, capture automation history, restart trainer or dependent service, then re-query active model version and verdict lineage; verify whether scanner-facing opportunity payloads can consume ML signals
    Expected: active model version and history remain consistent across restart, only promoted models become active, and ML-to-opportunity wiring status is explicit
    Evidence: .sisyphus/evidence/review/task-11-ml-persistence.json

  Scenario: Non-forgetting guard path
    Tool: Bash
    Steps: run targeted reproducers/tests for protected cohort regression, no-improvement patience, resume semantics, and hold verdict conditions
    Expected: promotion is blocked on regression or insufficient improvement and evidence is persisted
    Evidence: .sisyphus/evidence/review/task-11-ml-nonforgetting.json
  ```

  **Commit**: YES | Message: `fix(ml): preserve model lineage and promotion safety` | Files: `poe_trade/ml/**`, `poe_trade/services/ml_trainer.py`, `tests/unit/test_ml_*.py`, `README.md`

- [x] 12. Audit documentation, runbooks, and operator guidance against verified behavior

  **What to do**: Compare README, runbooks, QA instructions, and any shipped operational docs with verified behavior from tasks 4-11. Update stale commands, missing prerequisites, target distinctions, non-goals, ML behavior descriptions, opportunity/scanner/homepage semantics, journal availability, diagnostics availability, and live-vs-QA warnings only after behavior is proven. Ensure docs never claim unverified success.
  **Must NOT do**: Do not document planned commands/features as if they already work. Do not copy secrets into docs.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: evidence-backed documentation reconciliation.
  - Skills: [`docs-specialist`] - needed for precise minimal diffs.
  - Omitted: [`playwright`] - browser execution is upstream evidence, not part of doc editing.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 16 | Blocked By: 14

  **References**:
  - Pattern: `README.md`
  - Pattern: `docs/ops-runbook.md`
  - Pattern: `Makefile`
  - Pattern: `.github/workflows/python-ci.yml`
  - Pattern: `frontend/README.md`

  **Acceptance Criteria**:
  - [ ] Every changed doc statement is backed by evidence from a completed verification task.
  - [ ] README and ops docs distinguish QA-only, live-readonly, and live-allowlisted-mutation flows.
  - [ ] Product-layer docs no longer imply that alerts are opportunities, that placeholder comparables are real, or that journal-backed strategies are web-complete when journal APIs are absent.
  - [ ] Frontend README no longer misleads operators about the shipped app/runtime if inaccuracies are confirmed.

  **QA Scenarios**:
  ```text
  Scenario: Documentation truth audit
    Tool: Bash
    Steps: compare documented commands/routes/behaviors against evidence from prior tasks
    Expected: each doc discrepancy is resolved or listed as an explicit defect
    Evidence: .sisyphus/evidence/review/task-12-doc-truth.json

  Scenario: Unsafe-doc regression check
    Tool: Bash
    Steps: search changed docs for secrets, false success claims, or missing live-vs-QA warnings
    Expected: docs remain operational, terse, and evidence-backed
    Evidence: .sisyphus/evidence/review/task-12-doc-safety.json
  ```

  **Commit**: YES | Message: `docs(ops): align runbooks with verified behavior` | Files: `README.md`, `docs/**`, `frontend/README.md`

- [x] 13. Close frontend feature stubs, unsupported paths, and parity blind spots

  **What to do**: Review the frontend for stubbed or placeholder behaviors uncovered by the coverage map and parity tasks, especially methods in `frontend/src/services/api.ts` that currently return hardcoded placeholders. Decide per feature whether to implement, hide, or document as out of scope based on existing backend support and user-visible product expectations. This task must explicitly cover a first-class scanner/opportunities view, homepage opportunity-first rendering, truthful price-check comparables behavior, and the broken `dashboard/internal` fallback artifact. Add unit and E2E coverage for every resolved path.
  **Must NOT do**: Do not leave placeholder success states that mask missing backend support. Do not claim parity for unsupported features.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: frontend UX plus contract alignment.
  - Skills: [`playwright`] - needed for post-fix E2E proof.
  - Omitted: [`protocol-compat`] - not schema-focused.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 14 | Blocked By: 1, 2, 3, 4A

  **References**:
  - Pattern: `frontend/src/services/api.ts` - placeholder return paths.
  - Pattern: `frontend/src/types/api.ts` - frontend API contracts.
  - Pattern: `frontend/src/components/tabs/DashboardTab.tsx`
  - Pattern: `frontend/src/components/tabs/AnalyticsTab.tsx`
  - Pattern: `frontend/src/components/tabs/StashViewerTab.tsx`
  - Pattern: `frontend/src/components/tabs/PriceCheckTab.tsx`
  - Pattern: `dashboard/internal/app.js`
  - Test: `frontend/src/test/**/*.test.ts*`

  **Acceptance Criteria**:
  - [ ] Every user-visible stub/placeholder path is implemented, hidden, or explicitly documented as unsupported.
  - [ ] The main product surface includes a first-class opportunities/scanner view if required by the canonical contract.
  - [ ] Homepage “Top Opportunity/Top Opportunities” content is sourced from scanner opportunities, not critical alerts.
  - [ ] The internal dashboard artifact either uses the correct API path with explicit degraded/error states or is clearly quarantined from production use.
  - [ ] Frontend unit tests and E2E coverage exist for resolved paths.
  - [ ] No tab or feature reports fake success using hardcoded placeholder business data.

  **QA Scenarios**:
  ```text
  Scenario: Resolved frontend path happy flow
    Tool: Playwright
    Steps: open each previously stubbed or placeholder-backed UI path, including dashboard/opportunities/price-check/internal dashboard views, and exercise it against the intended backend or explicit unsupported state
    Expected: real data is shown or a truthful unsupported/degraded state is rendered; opportunities are scanner-backed rather than alert-backed
    Evidence: .sisyphus/evidence/review/task-13-frontend-resolved.json

  Scenario: Placeholder regression check
    Tool: Bash
    Steps: grep frontend API/service layer for hardcoded placeholder returns and compare against allowed unsupported list
    Expected: no unauthorized placeholder success paths remain
    Evidence: .sisyphus/evidence/review/task-13-placeholder-regression.json
  ```

  **Commit**: YES | Message: `fix(frontend): remove placeholder parity gaps` | Files: `frontend/src/**`, `frontend/src/test/**`

- [x] 14. Remediate verified defects by subsystem cluster with TDD and rerun gates

  **What to do**: Execute the actual fixes discovered in tasks 4-13. Group defects into atomic clusters: opportunity contract/API, schema/data-integrity and candidate marts, ingestion/service resilience, frontend/parity and scanner UX, journal/diagnostics surfaces, and ML governance/integration. For each cluster: capture failing reproducer or test first, implement the minimal fix, rerun targeted checks, rerun subsystem checks, then rerun the relevant dual-target E2E subset. Preserve immutable public-stash data and live mutation rules throughout.
  **Must NOT do**: Do not batch unrelated fixes into one change. Do not skip the failing-reproducer step. Do not close a defect without rerun evidence.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: cross-subsystem remediation with strict gating.
  - Skills: []
  - Omitted: [`docs-specialist`] - docs alignment follows after behavior is fixed.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: 12, 15 | Blocked By: 5, 6, 7, 8, 9, 10, 11, 13

  **References**:
  - Pattern: `tests/unit/` - backend failing-first coverage targets.
  - Pattern: `frontend/src/test/` - frontend unit/inventory/playwright checks.
  - Pattern: `.github/workflows/python-ci.yml` - minimum deterministic CI gate.
  - Pattern: `Makefile` - product verification command path.
  - Pattern: `README.md` - user-facing command truth to preserve.

  **Acceptance Criteria**:
  - [ ] Every fix links back to a specific failing reproducer/test and a matching passing rerun.
  - [ ] Each defect cluster has its own atomic commit.
  - [ ] Relevant dual-target parity checks are rerun after each cluster.
  - [ ] Product-layer fixes preserve additive API/schema compatibility unless an explicit compatibility task says otherwise.
  - [ ] No fix violates immutable-data or live mutation guardrails.

  **QA Scenarios**:
  ```text
  Scenario: TDD remediation loop
    Tool: Bash
    Steps: for each defect cluster, run failing reproducer, apply fix, rerun targeted tests, rerun subsystem suite, then rerun affected QA/live checks
    Expected: red -> green transition is documented for every cluster
    Evidence: .sisyphus/evidence/review/task-14-remediation-loop.json

  Scenario: Guardrail regression check
    Tool: Bash
    Steps: inspect changed code/queries/commands for forbidden public-stash mutations and unclassified live mutations
    Expected: no remediation violates safety policy
    Evidence: .sisyphus/evidence/review/task-14-guardrail-regression.json
  ```

  **Commit**: YES | Message: `fix(review): resolve verified defects by cluster` | Files: `repo-wide, limited to verified defect clusters`

- [x] 15. Align CI and deterministic automation with the proven review gates

  **What to do**: Update CI and local automation so deterministic checks reflect the verified product surface without importing unsafe live-site checks into default CI. Add or refine unit, frontend, inventory, build, QA-safe smoke, product-contract, strategy-runtime, and opportunity-payload checks needed to prevent regression of fixed defects. Keep live verification out of default CI unless explicitly gated.
  **Must NOT do**: Do not add scheduled or default live-site synthetics to standard CI without an explicit separate gate.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: build/test workflow alignment across stacks.
  - Skills: []
  - Omitted: [`playwright`] - CI design is primary; browser tests are already proven upstream.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 16 | Blocked By: 14

  **References**:
  - Pattern: `.github/workflows/python-ci.yml`
  - Pattern: `Makefile`
  - Pattern: `frontend/package.json`
  - Test: `tests/unit/**`
  - Test: `frontend/src/test/**`

  **Acceptance Criteria**:
  - [ ] CI reflects deterministic verified gates for backend and frontend.
  - [ ] Live verification is excluded from default CI and documented as operator-run or gated automation.
  - [ ] Any new regression test added for fixes is reachable from local and CI workflows.

  **QA Scenarios**:
  ```text
  Scenario: CI gate replay
    Tool: Bash
    Steps: run the final deterministic command set exactly as CI expects
    Expected: command set passes locally and matches workflow definitions
    Evidence: .sisyphus/evidence/review/task-15-ci-replay.json

  Scenario: Unsafe CI scope check
    Tool: Bash
    Steps: inspect workflow files for live URLs, live creds, or ungated destructive steps
    Expected: default CI remains deterministic and QA-safe
    Evidence: .sisyphus/evidence/review/task-15-ci-safety.json
  ```

  **Commit**: YES | Message: `ci(test): align workflows with proven gates` | Files: `.github/workflows/**`, `Makefile`, `frontend/package.json`, `README.md`

- [x] 16. Run final dual-target verification, evidence bundling, and defect closeout

  **What to do**: Execute the full final verification stack: deterministic backend/frontend/CI gates, full QA browser suite, selected live parity suite, auth/stash/restart checks per allowlist, ML governance replay, opportunity-contract replay from raw strategy output to homepage/scanner UI, and docs truth audit. Assemble the final evidence bundle and unresolved-risk register. Any remaining failure must be explicitly classified as fixed later, blocked by credentials, or intentional environment difference.
  **Must NOT do**: Do not claim completion without both QA and live evidence. Do not close open mismatches without classification.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: broad final verification and evidence synthesis.
  - Skills: [`evidence-bundle`] - useful for the final verification package.
  - Omitted: [`docs-specialist`] - docs should already be settled before this wave.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: final verification | Blocked By: 12, 15

  **References**:
  - Pattern: `Makefile` - `qa-verify-product` baseline product command.
  - Pattern: `.sisyphus/evidence/product/` - prior evidence layout examples.
  - Pattern: `README.md` - final command truth.
  - Pattern: `frontend/src/test/playwright/*.spec.ts` - browser verification surface.
  - Pattern: `tests/unit/test_ml_*.py` - ML proof surface.

  **Acceptance Criteria**:
  - [ ] Final evidence bundle includes deterministic, QA, live, ML, docs, and CI proof.
  - [ ] Every open issue is classified as resolved, blocked, intentional, or follow-up work.
  - [ ] Final report names exactly what was tested, what was fixed, and what remains outside current authority or credentials.
  - [ ] Any missing live credential-gated proof is explicitly labeled `blocked_by_credentials` and linked to prerequisite checks.
  - [ ] At least one end-to-end trace proves raw strategy metadata/SQL -> scanner recommendation -> API payload -> homepage/opportunities rendering -> alert/journal/diagnostic behavior.

  **QA Scenarios**:
  ```text
  Scenario: Final full verification
    Tool: Bash
    Steps: rerun final deterministic commands, QA suite, selected live suite, and ML replay checks; then assemble evidence bundle
    Expected: final status is evidence-backed and matches the resolved defect register
    Evidence: .sisyphus/evidence/review/task-16-final-verification.json

  Scenario: Unresolved risk closeout
    Tool: Bash
    Steps: compare original failure register, parity matrix, and final reruns
    Expected: no unclassified failure remains
    Evidence: .sisyphus/evidence/review/task-16-risk-closeout.json
  ```

  **Commit**: YES | Message: `chore(review): finalize verification evidence` | Files: `.sisyphus/evidence/**`, `README.md`, `docs/**`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [x] F1. Plan Compliance Audit - oracle

  **What to do**: Verify that execution outputs followed this plan exactly: wave ordering, safety labels, immutable-data guardrails, TDD remediation loop, evidence naming, and credential-blocked handling.
  **Tooling**: oracle
  **Expected Result**: PASS only if no executed step violated plan structure or safety rules.
  **References**: `.sisyphus/plans/comprehensive-codebase-review.md`, `.sisyphus/evidence/review/`
  **QA Scenario**:
  ```text
  Scenario: Plan conformance audit
    Tool: Bash
    Steps: compare completed evidence/tasks against plan requirements, wave dependencies, and safety clauses
    Expected: every completed task maps cleanly to the plan with no unauthorized execution
    Evidence: .sisyphus/evidence/review/f1-plan-compliance.json
  ```

- [x] F2. Code Quality Review - unspecified-high

  **What to do**: Review all changed code and tests for minimal diffs, defect-cluster isolation, regression-test quality, and absence of placeholder logic or undocumented shortcuts.
  **Tooling**: unspecified-high
  **Expected Result**: PASS only if every fix is evidence-backed, test-backed, and scoped to verified defects.
  **References**: changed source files, `tests/unit/`, `frontend/src/test/`, `.github/workflows/python-ci.yml`
  **QA Scenario**:
  ```text
  Scenario: Code quality gate
    Tool: Bash
    Steps: inspect changed files and rerun targeted tests for each defect cluster
    Expected: no low-signal fixes, no missing tests, no scope creep
    Evidence: .sisyphus/evidence/review/f2-code-quality.json
  ```

- [x] F3. Real Browser QA - unspecified-high (+ playwright if UI)

  **What to do**: Re-run a final browser-led product pass on QA and the live site using the completed parity matrix, including auth/stash/service-action subsets allowed by credentials and safety labels.
  **Tooling**: unspecified-high with Playwright
  **Expected Result**: PASS only if QA and live outcomes match their final classifications and no unclassified browser failure remains.
  **References**: `frontend/src/test/playwright/*.spec.ts`, `frontend/src/test/scenario-inventory.json`, `.sisyphus/evidence/review/task-8-*.json`, `.sisyphus/evidence/review/task-9-*.json`, `.sisyphus/evidence/review/task-10-*.json`
  **QA Scenario**:
  ```text
  Scenario: Final browser parity replay
    Tool: Playwright
    Steps: replay approved QA and live scenario sets, capture screenshots/network traces, compare against final parity classifications
    Expected: all browser-visible outcomes are either passing or explicitly classified as blocked/intended
    Evidence: .sisyphus/evidence/review/f3-browser-qa.json
  ```

- [x] F4. Scope Fidelity Check - deep

  **What to do**: Confirm the run covered every maintained source area from the coverage map and did not silently skip backend, frontend, schema, docs, CI, or ML surfaces.
  **Tooling**: deep
  **Expected Result**: PASS only if the final evidence and defect register cover the maintained-code inventory with explicit outcomes for each area.
  **References**: coverage inventory from task 2, final evidence bundle from task 16
  **QA Scenario**:
  ```text
  Scenario: Scope coverage reconciliation
    Tool: Bash
    Steps: compare the maintained-code inventory against completed evidence and final classifications
    Expected: no maintained subsystem lacks an outcome or owner
    Evidence: .sisyphus/evidence/review/f4-scope-fidelity.json
  ```

## Commit Strategy
- Use atomic commits by verified defect cluster only.
- Tasks 5-13 do not get their own commit unless the task fully completes one atomic defect cluster with failing reproducer/test, minimal fix, and passing rerun evidence; pure audit/findings work stays uncommitted and rolls into task 14 clusters.
- Commit order:
  1. test/evidence harness and safety-policy corrections
  2. backend/schema/data-integrity fixes with tests
  3. frontend/E2E/live-parity fixes with tests
  4. ML governance/persistence fixes with tests and evidence
  5. docs/CI alignment after behavior is proven
- Commit only after the relevant task acceptance criteria and evidence are complete.

## Success Criteria
- Every maintained source area has an explicit review owner, verification result, and evidence artifact.
- Local QA and live target differences are either fixed, documented as intentional, or escalated as explicit blocking defects.
- All verified fixes are covered by automated tests or deterministic scripted reproducers.
- Live verification completes without mutating crawled public stash data.
- ML automation proves persistence, non-forgetting guardrails, and safe promotion behavior across restart/reload boundaries.
- Homepage and primary navigation surface real scanner-backed opportunities rather than alert summaries.
- Strategy metadata, strategy SQL, recommendation payloads, journal availability, diagnostics, and ML opportunity integration all conform to the canonical opportunity contract.
