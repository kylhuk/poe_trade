# Frontend/Backend Ops Dashboard and Stash Pricing Integration

## TL;DR
> **Summary**: Replace the mock-backed React dashboard data path with a live backend-for-frontend rooted in the existing Python API service, expose real repo telemetry and safe runtime controls, and add a new private-stash pricing pipeline/API without changing frontend aesthetics.
> **Deliverables**:
> - live data and explicit unavailable states for the existing top-level tabs in `frontend/`
> - guarded service visibility plus `start`/`stop`/`restart` for approved runtime targets only
> - read-only analytics, health, messages, reports, scanner, and ML surfaces backed by repo truth
> - additive private stash sync/pricing storage and read-only `stashTabs` JSON delivery
> **Effort**: XL
> **Parallel**: YES - 3 waves
> **Critical Path**: T1 -> T2 -> T3 -> T6 -> T7 -> T8 -> T9 -> T10/T11/T12 -> T13

## Context
### Original Request
- Build a major plan to marry the frontend in `frontend/` with the backend via API so the frontend can visualize repo services, outputs, controls, healthchecks, and a new stash tab pricing capability.
- Keep the current frontend look and feel intact; functionality may change, aesthetics may not.

### Interview Summary
- Preserve the current top-level tab shell in `frontend/src/pages/Index.tsx`.
- Keep web mutations limited to service lifecycle `start`, `stop`, and `restart`.
- Assume backend-managed auth or same-origin proxying; do not store long-lived operator tokens in the browser.
- Treat Docker Compose as the primary runtime control target.
- Support plain Python process control only for real long-running daemons; one-shot jobs remain visible/read-only.
- Use tests-after with agent-executed QA on every task.
- Deliver private stash pricing as a backend feature that eventually emits the `stashTabs` wrapper shape already documented in `frontend/src/components/tabs/StashViewerTab.tsx`.

### Metis Review (gaps addressed)
- Lock the internal architecture to one Python API/BFF, not multiple backends.
- Split endpoint families into read-only ops/status, guarded service actions, and stash-domain reads.
- Explicitly remap inner analytics content to real repo capabilities instead of trying to preserve mock semantics.
- Add guardrails for unavailable, degraded, stale, and empty states so the UI never falls back to fake data.
- Keep ClickHouse evolution additive-only and preserve backward/forward read safety for stash pricing storage.
- Exclude one-shot job launching, arbitrary CLI execution, and dangerous service mutations from the first rollout.

## Work Objectives
### Core Objective
- Make every existing top-level frontend tab useful against real backend data, repo runtime truth, or explicit unavailable state, while keeping the existing visual system and adding a new private stash pricing backend/API.

### Deliverables
- Versioned API/BFF expansion in `poe_trade/api/` for ops contract, service inventory, service actions, dashboard/messages, analytics read models, and stash reads.
- Runtime registry/control adapter for Docker Compose services plus future-compatible long-running process targets.
- Additive stash pricing backend: config, OAuth-aware client, storage, harvester/service, serializer, and frontend-facing read endpoint.
- Frontend HTTP client/bootstrap layer that replaces mocks in `frontend/src/services/api.ts`.
- Live tab wiring for Dashboard, Services, Analytics, Price Check, Stash Viewer, and Messages.
- Updated operator/developer documentation for deployment, auth transport expectations, runtime control guardrails, and verification steps.

### Definition of Done (verifiable conditions with commands)
- `curl -i http://127.0.0.1:8080/healthz` returns `200` and the expected JSON health shape.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/contract` returns `200` and lists ops/action/stash families.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/services` returns service DTOs with control metadata.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/messages` returns live or empty-state messages without mock-only placeholders.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" "http://127.0.0.1:8080/api/v1/stash/tabs?league=Mirage&realm=pc"` returns the `stashTabs` wrapper contract.
- `.venv/bin/pytest tests/unit` passes.
- `npm run test` passes in `frontend/`.
- `npm run build` passes in `frontend/`.
- `npx playwright test` passes in `frontend/`.

### Must Have
- Live frontend data must flow only through the API/BFF boundary; no browser ClickHouse access.
- Top-level tabs remain `Dashboard`, `Services`, `Analytics`, `Price Check`, `Stash Viewer`, and `Messages`.
- Service controls are whitelist-driven and reject non-approved targets.
- `frontend/src/services/api.ts` becomes the only frontend data transport seam; mock data is removed from active runtime flow.
- Stash pricing storage and API changes are additive and downgrade-tolerant.
- Every live panel shows one of: data, empty, stale/degraded, or unavailable.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No theme/color/aesthetic redesign in `frontend/`.
- No wildcard CORS or browser-held long-lived operator token.
- No fake mock fallback when a backend request fails.
- No UI controls for migrations, alert acknowledgements, journal writes, strategy toggles, arbitrary CLI jobs, or schema apply/rebuild operations.
- No self-stop or self-restart action for the serving `api` process.
- No lifecycle controls for `schema_migrator` or other one-shot jobs.
- No destructive ClickHouse migrations, column drops, or incompatible contract rewrites.
- No direct browser calls to PoE private stash endpoints.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after using backend `pytest`, frontend `vitest`, and Playwright browser verification.
- QA policy: every task includes at least one happy-path and one failure-path scenario, with explicit selectors, request shapes, or commands.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: API/BFF foundation, runtime control model, service read/actions, dashboard/messages, analytics read models
Wave 2: private stash storage/client/harvester/API backend
Wave 3: frontend live transport, tab rewiring, docs, and browser verification

### Dependency Matrix (full, all tasks)
- T1: none
- T2: T1
- T3: T1, T2
- T4: T1, T3
- T5: T1
- T6: T1
- T7: T6
- T8: T1, T6, T7
- T9: T1, T3, T4, T5, T8
- T10: T9, T3, T4
- T11: T9, T5
- T12: T9, T8
- T13: T3, T4, T5, T8, T10, T11, T12

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 5 tasks -> `deep` x1, `unspecified-high` x3, `quick` x1
- Wave 2 -> 3 tasks -> `deep` x2, `unspecified-high` x1
- Wave 3 -> 5 tasks -> `visual-engineering` x4, `writing` x1

## TODOs

- [ ] T1. Codify the live API contract and protected namespaces

  **What to do**: Extend `poe_trade/api/app.py` so protected-path handling covers `/api/v1/ops/`, `/api/v1/actions/`, and `/api/v1/stash/` in addition to the existing ML routes, while keeping `/healthz` public. Add `GET /api/v1/ops/contract` as the bootstrap contract for the frontend; it must publish `version`, `auth_mode`, `allowed_leagues`, `primary_league`, endpoint families, visible service ids, controllable service ids, and the approved top-level tab mapping. Keep existing ML route shapes intact and reuse the current router/auth/CORS patterns instead of adding a second auth system.
  **Must NOT do**: Do not add browser login UX, cookie/session invention, wildcard CORS, or a parallel API framework.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: this task locks the contract and auth shape every downstream task depends on.
  - Skills: `[]` - no extra skill required; existing API patterns are already in-repo.
  - Omitted: `protocol-compat` - no schema change belongs here.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: T2, T3, T5, T6, T9 | Blocked By: none

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `poe_trade/api/app.py` - current route registration, auth gating, CORS handling, and JSON error semantics.
  - Pattern: `poe_trade/api/routes.py` - path-template routing pattern to preserve.
  - Pattern: `poe_trade/api/ml.py` - current contract payload style and allowlisted league handling.
  - API/Type: `frontend/src/services/api.ts` - current frontend bootstrap seam to replace.
  - API/Type: `frontend/src/types/api.ts` - frontend DTO inventory and current service/price/stash types.
  - Test: `tests/unit/test_api_auth.py` - bearer token expectations.
  - Test: `tests/unit/test_api_cors.py` - allowed/denied origin behavior.
  - Test: `tests/unit/test_api_ml_routes.py` - stable route/error-shape expectations.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `GET /api/v1/ops/contract` is authenticated, CORS-protected, and returns a stable JSON contract with `primary_league` and endpoint families.
  - [ ] `/healthz` remains unauthenticated and unchanged.
  - [ ] Unauthorized and denied-origin requests to the new namespaces fail closed with stable JSON errors.
  - [ ] `.venv/bin/pytest tests/unit -k "api or cors or auth or service"` passes.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Ops contract bootstrap succeeds
    Tool: Bash
    Steps: Start the API locally with test env vars; run curl with Authorization and allowed Origin against /api/v1/ops/contract.
    Expected: HTTP 200 and JSON keys include version, auth_mode, allowed_leagues, primary_league, routes/families, visible_service_ids, controllable_service_ids.
    Evidence: .sisyphus/evidence/task-T1-ops-contract.txt

  Scenario: New protected namespace fails closed
    Tool: Bash
    Steps: Run curl against /api/v1/ops/contract once without Authorization and once with denied Origin.
    Expected: Missing auth returns 401 auth_required; denied Origin returns 403 origin_denied.
    Evidence: .sisyphus/evidence/task-T1-ops-contract-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add ops contract bootstrap` | Files: `poe_trade/api/app.py`, `poe_trade/api/ml.py`, `poe_trade/api/routes.py`, `tests/unit/`

- [ ] T2. Introduce a runtime service registry and control adapter

  **What to do**: Add a backend registry abstraction that separates visible runtime targets from controllable ones and records runtime kind per target. Initial visible targets must be `clickhouse`, `schema_migrator`, `market_harvester`, and `api`; the registry shape must already support future `process` entries such as `account_stash_harvester`, but no one-shot ML/CLI job may be represented as a restartable service. Initial controllable whitelist must exclude `clickhouse`, `schema_migrator`, and `api`, and must be designed so T7 can safely register `account_stash_harvester` later without changing the frontend contract again.
  **Must NOT do**: Do not shell out directly from route handlers, do not infer service ids from arbitrary user input, and do not treat one-shot commands like `poe-ml report` or `poe-ledger-cli scan plan` as services.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: this is cross-cutting runtime plumbing with guardrails, not just a single-file tweak.
  - Skills: `[]` - existing runtime/service patterns are enough.
  - Omitted: `playwright` - no browser work belongs in this backend task.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: T3 | Blocked By: T1

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `poe_trade/config/constants.py` - current service registry and runtime constants.
  - Pattern: `poe_trade/services/market_harvester.py` - service entry-point shape and runtime settings usage.
  - Pattern: `poe_trade/services/api.py` - service entry-point pattern for the API.
  - Pattern: `docker-compose.yml` - current Compose-managed topology.
  - Test: `tests/unit/test_service_registry.py` - existing registry expectation surface.
  - Test: `tests/unit/test_market_harvester_service.py` - service/runtime startup behavior patterns.
  - API/Type: `frontend/src/types/api.ts` - current service DTO that downstream UI consumes.

  **Acceptance Criteria** (agent-executable only):
  - [ ] A single registry source defines visible services, runtime kind, control eligibility, and display metadata.
  - [ ] Non-controllable targets are explicitly marked and can be rejected before any runtime mutation attempt.
  - [ ] No one-shot CLI workflow is representable as a `start`/`stop`/`restart` target.
  - [ ] `.venv/bin/pytest tests/unit -k "service_registry or market_harvester_service"` passes.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Registry exposes only approved service inventory
    Tool: Bash
    Steps: Run the targeted pytest subset covering the service registry and inspect the serialized visible ids in test assertions/log output.
    Expected: Visible ids include clickhouse, schema_migrator, market_harvester, api; controllable ids exclude api and schema_migrator.
    Evidence: .sisyphus/evidence/task-T2-service-registry.txt

  Scenario: One-shot jobs are rejected as services
    Tool: Bash
    Steps: Add/update unit coverage that attempts to register or resolve a one-shot CLI target as restartable, then run the targeted pytest subset.
    Expected: The test suite proves the registry rejects or never exposes one-shot jobs as controllable services.
    Evidence: .sisyphus/evidence/task-T2-service-registry-error.txt
  ```

  **Commit**: NO | Message: `grouped into T3` | Files: `poe_trade/config/constants.py`, `poe_trade/services/`, `tests/unit/`

- [ ] T3. Expose live service inventory and guarded lifecycle actions

  **What to do**: Build `GET /api/v1/ops/services` and `POST /api/v1/actions/services/{service_id}/{verb}` using the registry from T2. Extend the service DTO so the frontend can see allowed actions per service instead of assuming all buttons are valid. Enrich service responses with runtime status plus freshness metadata from ClickHouse when available, and return stable rejection codes for unknown service ids, forbidden targets, and unsupported verbs. After an allowed action, re-read and return the updated service state instead of assuming success.
  **Must NOT do**: Do not allow `api` self-stop/self-restart, do not allow lifecycle mutation for `schema_migrator`, and do not return optimistic fake running/stopped status before verifying the adapter result.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: backend runtime mutation and state reconciliation are safety-sensitive.
  - Skills: `[]` - no extra skill required.
  - Omitted: `protocol-compat` - no schema evolution belongs in this task.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: T4, T9, T10, T13 | Blocked By: T1, T2

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `poe_trade/api/app.py` - protected-route plumbing and JSON error behavior.
  - Pattern: `poe_trade/cli.py` - current service command dispatch and sync status behavior.
  - Pattern: `poe_trade/ingestion/status.py` - source of ingestion freshness metadata.
  - Pattern: `frontend/src/components/tabs/ServicesTab.tsx` - current UX assumptions for action buttons and loading state.
  - API/Type: `frontend/src/types/api.ts` - current `Service` DTO to extend deliberately.
  - Test: `tests/unit/test_api_service.py` - service routing tests to extend.
  - Test: `tests/unit/test_service_registry.py` - registry expectations.
  - Doc: `docs/ops-runbook.md` - operational meaning of service freshness and ingestion health.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `GET /api/v1/ops/services` returns stable DTOs for all visible services and includes action eligibility for each target.
  - [ ] `POST /api/v1/actions/services/market_harvester/restart` uses the adapter path and returns refreshed service state or a stable action error.
  - [ ] `POST` against `api`, `schema_migrator`, `clickhouse`, or an unknown id fails closed with a stable JSON error.
  - [ ] `.venv/bin/pytest tests/unit -k "api_service or service_registry or market_harvester_service"` passes.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Services inventory exposes live action metadata
    Tool: Bash
    Steps: Start the API with test env vars and curl /api/v1/ops/services with Authorization and allowed Origin.
    Expected: HTTP 200; market_harvester shows allowed start/stop/restart flags; api and schema_migrator are visible but not action-enabled.
    Evidence: .sisyphus/evidence/task-T3-services.txt

  Scenario: Forbidden control action fails closed
    Tool: Bash
    Steps: Curl POST /api/v1/actions/services/api/stop and /api/v1/actions/services/schema_migrator/restart.
    Expected: Stable non-2xx JSON error with a dedicated rejection code; no optimistic status flip is returned.
    Evidence: .sisyphus/evidence/task-T3-services-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add guarded service controls` | Files: `poe_trade/api/app.py`, `poe_trade/cli.py`, `poe_trade/services/`, `frontend/src/types/api.ts`, `tests/unit/`

- [ ] T4. Add dashboard summary and message aggregation endpoints

  **What to do**: Create read-only ops endpoints for the existing `Dashboard` and `Messages` tabs. `GET /api/v1/ops/dashboard` must expose the summary numbers and top-opportunity data the tab needs, while `GET /api/v1/ops/messages` must aggregate scanner alerts, ingestion degradation, and service/runtime anomalies into the `AppMessage`-style feed. Severity must be deterministic: `critical` for action-blocking service or alert failures, `warning` for stale/rate-limited/degraded state, and `info` for non-blocking operational notes.
  **Must NOT do**: Do not invent placeholder messages when underlying sources are empty, do not duplicate the raw CLI output format directly into the browser, and do not hide stale/unavailable conditions behind success-looking summaries.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: this is mostly read-model composition over existing sources once the contract and service inventory exist.
  - Skills: `[]` - no extra skill required.
  - Omitted: `playwright` - backend aggregation first, browser verification later.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T10, T13 | Blocked By: T1, T3

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/src/components/tabs/DashboardTab.tsx` - current summary-card, health-strip, and top-opportunity expectations.
  - Pattern: `frontend/src/components/tabs/MessagesTab.tsx` - current alert/message feed expectations.
  - Pattern: `poe_trade/strategy/alerts.py` - existing alert listing source.
  - Pattern: `poe_trade/ingestion/status.py` - ingestion status source contract.
  - Pattern: `poe_trade/cli.py` - sync status query and alert/report command surfaces.
  - Doc: `docs/ops-runbook.md` - operational severity meaning for stale ingestion, rate limits, and SLOs.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `GET /api/v1/ops/dashboard` returns stable summary keys and top-opportunity content derived from real repo sources.
  - [ ] `GET /api/v1/ops/messages` returns empty arrays, stale warnings, and critical failures correctly without mock filler.
  - [ ] Service/runtime degradation and scanner alerts map to deterministic severities.
  - [ ] `.venv/bin/pytest tests/unit -k "api and (alerts or dashboard or messages or service)"` passes.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Dashboard and messages read models load
    Tool: Bash
    Steps: Curl /api/v1/ops/dashboard and /api/v1/ops/messages with Authorization and allowed Origin.
    Expected: Both endpoints return 200 with stable keys; empty-source environments return zeros/[] rather than mock demo content.
    Evidence: .sisyphus/evidence/task-T4-dashboard-messages.txt

  Scenario: Degraded source becomes warning/critical output
    Tool: Bash
    Steps: Run targeted pytest coverage that feeds a degraded ingest or alert source into the aggregation layer.
    Expected: The read model emits warning/critical severities deterministically and the tests pass.
    Evidence: .sisyphus/evidence/task-T4-dashboard-messages-error.txt
  ```

  **Commit**: NO | Message: `grouped into T5` | Files: `poe_trade/api/`, `poe_trade/strategy/alerts.py`, `frontend/src/components/tabs/DashboardTab.tsx`, `frontend/src/components/tabs/MessagesTab.tsx`, `tests/unit/`

- [ ] T5. Replace mock analytics semantics with real repo read models

  **What to do**: Redefine the inner `Analytics` tab content around real repo capabilities rather than the current mock concept names. Use backend read-only endpoints under `/api/v1/ops/analytics/` for `ingestion`, `scanner`, `alerts`, `backtests`, `ml`, and `report`, with DTOs shaped for the frontend rather than raw CLI text dumps. Reuse existing backend truth where it already exists (`poe_ingest_status`, `scanner_alert_log`, `research_backtest_summary`, `analytics.reports`, ML status workflow) and return explicit unavailable or empty states when a source has no rows.
  **Must NOT do**: Do not preserve fake mock panel semantics just because they exist today, do not add action endpoints under analytics, and do not hide backend/source failures behind hard-coded sample cards.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: this task turns a broad mock analytics surface into a stable BFF read-model family.
  - Skills: `[]` - in-repo API and analytics patterns are sufficient.
  - Omitted: `protocol-compat` - no schema change is required in this task.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T9, T11, T13 | Blocked By: T1

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/src/components/tabs/AnalyticsTab.tsx` - current nested-tab UX shell to preserve stylistically while remapping content.
  - Pattern: `poe_trade/api/ml.py` - current ML status shaping and backend-unavailable behavior.
  - Pattern: `poe_trade/analytics/reports.py` - daily report source.
  - Pattern: `poe_trade/cli.py` - scanner, alerts, report, and backtest command/query surfaces.
  - Doc: `docs/ops-runtime-ui-upgrade-plan.md` - operator-facing health/alert layout principles to respect functionally.
  - Doc: `docs/ops-runbook.md` - ingestion/SLO semantics for warning and critical thresholds.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `/api/v1/ops/analytics/ingestion`, `/scanner`, `/alerts`, `/backtests`, `/ml`, and `/report` expose stable JSON read models or explicit unavailable/empty responses.
  - [ ] The new analytics DTOs map only to real repo capabilities and source tables/workflows.
  - [ ] Backend-unavailable and no-data cases are distinguishable in tests and HTTP responses.
  - [ ] `.venv/bin/pytest tests/unit -k "api or ml or alerts or backtest or report"` passes.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Analytics read models load against real sources
    Tool: Bash
    Steps: Curl each /api/v1/ops/analytics/* endpoint with Authorization and allowed Origin.
    Expected: Each endpoint returns 200 with stable keys, or a documented unavailable/empty response when source data is absent.
    Evidence: .sisyphus/evidence/task-T5-analytics.txt

  Scenario: Analytics unavailable state is explicit
    Tool: Bash
    Steps: Run targeted pytest coverage that injects ClickHouse/backend failures into the analytics read-model layer.
    Expected: The API returns stable unavailable/error semantics; no mock fallback payload appears.
    Evidence: .sisyphus/evidence/task-T5-analytics-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add ops analytics read models` | Files: `poe_trade/api/`, `poe_trade/analytics/reports.py`, `poe_trade/cli.py`, `frontend/src/components/tabs/AnalyticsTab.tsx`, `tests/unit/`

- [ ] T6. Add additive stash pricing storage, config, and private-stash client foundation

  **What to do**: Add the backend foundation for private stash pricing with additive-only ClickHouse evolution. Extend settings/config for private stash enablement, realm/league targeting, polling interval, and OAuth scope expectations. Implement a dedicated private-stash client that follows the official stash endpoints, backend-only OAuth `account:stashes`, explicit User-Agent requirements, and dynamic rate-limit parsing. Add migrations for raw stash snapshots plus a flattened priced read model, preserving backward/forward read safety and leaving existing readers untouched.
  **Must NOT do**: Do not mutate existing public-stash tables in place, do not drop or rename existing columns, do not call PoE private stash endpoints from the browser, and do not assume cache-only storage for the first rollout.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: this task spans config, upstream auth/rate-limit correctness, and additive ClickHouse contracts.
  - Skills: `protocol-compat` - required to keep schema/data-contract evolution additive and downgrade-safe.
  - Omitted: `playwright` - no browser automation belongs in this backend foundation task.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: T7, T8 | Blocked By: T1

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `poe_trade/config/settings.py` - env parsing and API/runtime settings conventions.
  - Pattern: `poe_trade/config/constants.py` - default values and service constants.
  - Pattern: `poe_trade/ingestion/market_harvester.py` - upstream client, rate-limit, checkpoint, and status-reporting patterns.
  - Pattern: `poe_trade/ingestion/poe_client.py` - existing upstream request wrapper and metadata capture pattern.
  - Test: `tests/unit/test_market_harvester_auth.py` - OAuth failure-path expectations to mirror.
  - External: `https://www.pathofexile.com/developer/docs/reference#stashes` - official private stash endpoint reference.
  - External: `https://www.pathofexile.com/developer/docs/authorization` - official OAuth requirements.
  - External: `https://www.pathofexile.com/developer/docs/index#ratelimits` - official rate-limit contract.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Config parsing supports private stash feature flags/settings without regressing existing env behavior.
  - [ ] Additive migrations create raw and priced stash tables without altering existing public-stash or ML contracts.
  - [ ] The private-stash client handles missing credentials, denied scope, and 429/retry-after behavior deterministically.
  - [ ] `poe-migrate --status --dry-run` shows only additive pending work for the stash feature.
  - [ ] `.venv/bin/pytest tests/unit -k "settings or auth or rate_limit or poe_client"` passes.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Additive stash migrations are visible and safe
    Tool: Bash
    Steps: Run poe-migrate --status --dry-run after adding the stash migrations.
    Expected: Pending migrations are additive-only; no existing table drops or incompatible rewrites appear.
    Evidence: .sisyphus/evidence/task-T6-stash-migrations.txt

  Scenario: Private-stash auth or rate-limit failure is handled cleanly
    Tool: Bash
    Steps: Run targeted pytest coverage for missing OAuth config, denied scope, and 429 retry-after behavior in the private-stash client.
    Expected: Tests prove deterministic failure handling and no browser-facing secret leakage.
    Evidence: .sisyphus/evidence/task-T6-stash-client-error.txt
  ```

  **Commit**: NO | Message: `grouped into T8` | Files: `poe_trade/config/settings.py`, `poe_trade/config/constants.py`, `poe_trade/ingestion/`, `schema/migrations/`, `tests/unit/`

- [ ] T7. Build the account stash harvester service and runtime registration

  **What to do**: Implement a dedicated `account_stash_harvester` service using the repo’s existing service-entrypoint pattern. The service must poll one configured operator account/league/realm, fetch tab metadata and tab item contents server-side, write raw snapshots and priced rows to ClickHouse, and report health through `StatusReporter`. Register it in the service/runtime inventory so it becomes a real controllable daemon, and add a Compose entry for containerized deployment.
  **Must NOT do**: Do not bolt private-stash polling into `market_harvester`, do not make it a one-shot CLI job, and do not emit pretend prices when no estimator can support the item.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: this task creates a new long-running ingestion/pricing service with runtime implications.
  - Skills: `protocol-compat` - the service writes to new additive storage and must remain contract-safe.
  - Omitted: `docs-specialist` - documentation follows after the service is working.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: T8, T9, T12, T13 | Blocked By: T6

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `poe_trade/services/market_harvester.py` - service entry-point, logging, settings, and scheduler wiring pattern.
  - Pattern: `poe_trade/ingestion/status.py` - health/status reporting contract to reuse.
  - Pattern: `poe_trade/ingestion/sync_state.py` - latest-state/checkpoint lookup patterns.
  - Pattern: `poe_trade/ingestion/cxapi_sync.py` - dedicated feed sync class structure.
  - Test: `tests/unit/test_market_harvester_service.py` - service startup and OAuth precheck patterns.
  - Doc: `docker-compose.yml` - current runtime topology to extend.
  - Doc: `docs/ops-runbook.md` - expected operational observability and restart guidance.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `account_stash_harvester` exists as a real service entry point and appears in runtime/service inventory.
  - [ ] The service records health/status through existing status telemetry patterns.
  - [ ] Price rows persist explicit confidence/fallback semantics instead of invented precision.
  - [ ] `.venv/bin/pytest tests/unit -k "harvester or service"` passes for the new service and its startup/auth paths.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Account stash harvester starts as a managed service
    Tool: Bash
    Steps: Run the targeted pytest subset for the new service entry point and registry integration; if a local compose service is available, inspect the services endpoint afterward.
    Expected: The service can be resolved, started through its adapter path, and reported through the runtime inventory.
    Evidence: .sisyphus/evidence/task-T7-stash-harvester.txt

  Scenario: Unsupported or unpriceable item path is explicit
    Tool: Bash
    Steps: Run targeted unit tests that feed an item without a supported estimator or price note into the pricing pipeline.
    Expected: The pipeline records zero-confidence fallback semantics instead of fabricating a confident price.
    Evidence: .sisyphus/evidence/task-T7-stash-harvester-error.txt
  ```

  **Commit**: NO | Message: `grouped into T8` | Files: `poe_trade/services/`, `poe_trade/ingestion/`, `docker-compose.yml`, `tests/unit/`

- [ ] T8. Expose the read-only stash API in the documented wrapper contract

  **What to do**: Add `GET /api/v1/stash/tabs?league=<league>&realm=<realm>` that reads the latest synced stash snapshot and returns exactly the wrapper shape expected by the frontend documentation: `{ "stashTabs": [...] }`. The serializer must map tab metadata, item coordinates, listed price parsing, estimated price, confidence, delta fields, evaluation enum, and `iconUrl`. When the feature is configured but the stash is empty, return `200` with an empty `stashTabs` array; when the feature is disabled or unconfigured, return an explicit unavailable error instead of mock data.
  **Must NOT do**: Do not return raw upstream stash payloads to the browser, do not invent unsupported enum values, and do not bypass the stored snapshot/read model by calling PoE directly during the request.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: this task is the public-facing serialization boundary for the new stash domain.
  - Skills: `protocol-compat` - read-model stability matters because the frontend will bind directly to this wrapper.
  - Omitted: `playwright` - backend serializer first; UI verification follows in T12.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: T9, T12, T13 | Blocked By: T1, T6, T7

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/src/components/tabs/StashViewerTab.tsx` - exact wrapper contract currently documented in the UI.
  - API/Type: `frontend/src/types/api.ts` - current stash item/tab typing expectations.
  - Pattern: `frontend/src/services/api.ts` - current frontend stash call seam.
  - Pattern: `poe_trade/api/app.py` - route registration and JSON response style.
  - Test: `tests/unit/test_api_ml_routes.py` - route/JSON-shape and backend-unavailable testing pattern.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `GET /api/v1/stash/tabs` returns the documented `stashTabs` wrapper with stable field names and enums.
  - [ ] Configured-but-empty and feature-unavailable states are distinguishable.
  - [ ] Item serializer emits explicit zero-confidence fallback values when an estimate is unavailable.
  - [ ] `.venv/bin/pytest tests/unit -k "api or stash"` passes.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Stash tabs wrapper loads for the frontend
    Tool: Bash
    Steps: Curl /api/v1/stash/tabs with Authorization, allowed Origin, and configured league/realm query parameters.
    Expected: HTTP 200 and JSON root contains stashTabs; each returned tab/item matches the documented field names.
    Evidence: .sisyphus/evidence/task-T8-stash-api.txt

  Scenario: Unconfigured stash feature is explicit
    Tool: Bash
    Steps: Run the same curl or targeted pytest path with stash config disabled/missing.
    Expected: Stable unavailable/error response; no mock or stale wrapper is returned.
    Evidence: .sisyphus/evidence/task-T8-stash-api-error.txt
  ```

  **Commit**: YES | Message: `feat(stash): add account stash sync and api` | Files: `poe_trade/api/`, `poe_trade/services/`, `poe_trade/ingestion/`, `poe_trade/config/settings.py`, `schema/migrations/`, `docker-compose.yml`, `tests/unit/`

- [ ] T9. Replace the frontend mock transport with a live same-origin API client

  **What to do**: Rewrite `frontend/src/services/api.ts` so it stops importing mock data and instead uses `fetch` against the same-origin API. Bootstrap the frontend with `GET /api/v1/ops/contract`, cache `primary_league`, and centralize JSON parsing, HTTP error handling, unavailable-state mapping, and request helpers there. Keep the Promise-based service interface so the current component architecture can be migrated without a visual rewrite, and add local development proxying in `frontend/vite.config.ts` rather than exposing operator tokens in browser code.
  **Must NOT do**: Do not leave mock runtime data in the active code path, do not hard-code secrets into the frontend bundle, and do not silently swallow 401/403/503 responses.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: this is frontend integration plumbing that touches app bootstrap and shared data flow without redesigning UI.
  - Skills: `[]` - in-repo React/Vite patterns are enough.
  - Omitted: `playwright` - this task should land the transport first; browser flow verification comes in later tasks.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: T10, T11, T12, T13 | Blocked By: T1, T3, T4, T5, T8

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/src/services/api.ts` - current mock seam to replace.
  - Pattern: `frontend/src/App.tsx` - app bootstrap already wraps QueryClientProvider and router.
  - Pattern: `frontend/src/main.tsx` - frontend bootstrap entry.
  - Pattern: `frontend/package.json` - available scripts and test/build tooling.
  - Pattern: `frontend/playwright.config.ts` - browser test harness entry.
  - Test: `frontend/src/test/example.test.ts` - current Vitest wiring baseline.
  - API/Type: `frontend/src/types/api.ts` - DTOs and service interface to evolve deliberately.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `frontend/src/services/api.ts` no longer imports or returns `mockData` at runtime.
  - [ ] The frontend can bootstrap `primary_league` and protected endpoint families from `/api/v1/ops/contract`.
  - [ ] HTTP 401/403/503 conditions are surfaced to callers as explicit UI states instead of hidden failures.
  - [ ] `npm run test` and `npm run build` pass in `frontend/`.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Frontend API client loads live contract data
    Tool: Bash
    Steps: Run frontend unit tests covering the fetch client/bootstrap helpers and then run npm run build.
    Expected: Contract bootstrap and JSON parsing tests pass; the production build contains no active mock-data dependency.
    Evidence: .sisyphus/evidence/task-T9-frontend-client.txt

  Scenario: HTTP failure becomes explicit unavailable state
    Tool: Bash
    Steps: Run targeted Vitest coverage with mocked 401/403/503 fetch responses from the API helper layer.
    Expected: The helper rejects with typed/unavailable errors that downstream tabs can render explicitly.
    Evidence: .sisyphus/evidence/task-T9-frontend-client-error.txt
  ```

  **Commit**: YES | Message: `feat(frontend): add live api client` | Files: `frontend/src/services/api.ts`, `frontend/src/types/api.ts`, `frontend/vite.config.ts`, `frontend/src/test/`

- [ ] T10. Wire Dashboard, Services, and Messages to live backend data

  **What to do**: Replace the current tab-local mock loading in `DashboardTab`, `ServicesTab`, and `MessagesTab` with live calls through the new API client. The `Services` tab must honor backend action metadata, disable or hide invalid buttons, and only let `Start All`/`Stop All` operate on action-enabled services. The `Dashboard` tab must use the new summary/read models rather than deriving business meaning from demo data, and all three tabs must show explicit loading, empty, stale/degraded, and unavailable states.
  **Must NOT do**: Do not keep the current optimistic local status flip in `ServicesTab`, do not render demo opportunities/messages after a fetch failure, and do not expose buttons for disallowed service actions.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: this is functional tab wiring with state/error handling inside the existing UI shell.
  - Skills: [`playwright`] - browser verification is important because action/button state changes are UI-visible.
  - Omitted: `protocol-compat` - no schema work belongs in this frontend task.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: T13 | Blocked By: T9, T3, T4

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/src/components/tabs/DashboardTab.tsx` - current summary and health-strip layout to preserve visually.
  - Pattern: `frontend/src/components/tabs/ServicesTab.tsx` - current action/button UX and current optimistic status flip to remove.
  - Pattern: `frontend/src/components/tabs/MessagesTab.tsx` - current filter UX and message-card shell.
  - Pattern: `frontend/src/components/shared/StatusIndicators.tsx` - status/freshness badge behavior to reuse.
  - Pattern: `frontend/src/pages/Index.tsx` - current top-level tab shell that must remain intact.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Dashboard summary, health strip, and top-opportunity cards render live backend data or explicit unavailable state.
  - [ ] Services buttons only appear enabled for backend-approved lifecycle actions.
  - [ ] Messages filtering still works on live data and handles empty/unavailable cases.
  - [ ] `npm run test` and targeted Playwright coverage for these tabs pass.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Live dashboard/services/messages flow works
    Tool: Playwright
    Steps: Open `/`; use `getByRole('tab', { name: 'Dashboard' })`, `getByRole('tab', { name: 'Services' })`, and `getByRole('tab', { name: 'Messages' })`; verify a service card title renders, then click the `critical`, `warning`, and `info` message filter buttons.
    Expected: Tabs render live content or explicit state messaging; Services buttons reflect backend action eligibility.
    Evidence: .sisyphus/evidence/task-T10-dashboard-services-messages.txt

  Scenario: Disallowed service control is not clickable
    Tool: Playwright
    Steps: Open `Services`; locate the card for `api` or `schema_migrator`; inspect the `Start`, `Stop`, and `Restart` buttons within that card.
    Expected: Stop/restart/start controls for disallowed targets are hidden or disabled, and no optimistic status flip occurs.
    Evidence: .sisyphus/evidence/task-T10-dashboard-services-messages-error.txt
  ```

  **Commit**: NO | Message: `grouped into T13` | Files: `frontend/src/components/tabs/DashboardTab.tsx`, `frontend/src/components/tabs/ServicesTab.tsx`, `frontend/src/components/tabs/MessagesTab.tsx`, `frontend/src/components/shared/StatusIndicators.tsx`, `frontend/src/types/api.ts`, `frontend/src/test/`

- [ ] T11. Remap Analytics and Price Check to real repo capabilities

  **What to do**: Rebuild the inner `Analytics` tab set around the backend read models from T5 while preserving the current nested-tab visual pattern. Use real capability names and data sources (`Ingestion`, `Scanner`, `Alerts`, `Backtests`, `ML`, `Reports`) instead of the current mock-only labels. For `Price Check`, stop expecting the old mock comparable-card DTO; call the existing ML predict-one route using the bootstrap `primary_league`, and render the real ML semantics: `price_p50` as the primary value, `price_p10`/`price_p90` interval, `confidence_percent`, `sale_probability_percent`, `price_recommendation_eligible`, and `fallback_reason`.
  **Must NOT do**: Do not preserve fake mock analytics cards, do not invent comparables if the backend does not provide them, and do not hide low-confidence or fallback ML outputs.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: this is frontend semantic remapping inside an existing visual structure.
  - Skills: [`playwright`] - browser verification is required because nested tabs and prediction output are UI-visible.
  - Omitted: `protocol-compat` - no schema work belongs here.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: T13 | Blocked By: T9, T5

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/src/components/tabs/AnalyticsTab.tsx` - nested-tab shell and card layout patterns to keep stylistically.
  - Pattern: `frontend/src/components/tabs/PriceCheckTab.tsx` - current prediction form shell to preserve while changing semantics.
  - Pattern: `frontend/src/components/shared/StatusIndicators.tsx` - confidence and currency display helpers.
  - Pattern: `poe_trade/api/ml.py` - actual ML status and predict-one response fields.
  - Test: `tests/unit/test_api_ml_routes.py` - predict-one and status behavior to align with.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Analytics nested tabs represent real repo capabilities and load from the new analytics endpoints.
  - [ ] Price Check uses the real ML prediction semantics and no longer depends on mock comparables.
  - [ ] ML fallback/low-confidence cases are visible in the UI rather than hidden.
  - [ ] `npm run test` and targeted Playwright coverage for Analytics + Price Check pass.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Analytics panels map to live repo capabilities
    Tool: Playwright
    Steps: Open `Analytics`; use `getByRole('tab', { name: 'Ingestion' })`, `Scanner`, `Alerts`, `Backtests`, `ML`, and `Reports`; verify each tab swap changes the visible heading/card copy.
    Expected: Each panel renders live or explicit unavailable/empty state content tied to the real backend capability names.
    Evidence: .sisyphus/evidence/task-T11-analytics-pricecheck.txt

  Scenario: Price Check shows real ML fallback semantics
    Tool: Playwright
    Steps: Open `Price Check`; fill the textarea with `Item Class: Maps\nRarity: Rare\nGrim Veil\nCemetery Map`; click the `Price Check` button once with a successful prediction fixture and once with a fallback/low-confidence fixture.
    Expected: The UI renders interval/confidence/eligibility/fallback fields accurately and does not expect comparables when none exist.
    Evidence: .sisyphus/evidence/task-T11-analytics-pricecheck-error.txt
  ```

  **Commit**: NO | Message: `grouped into T13` | Files: `frontend/src/components/tabs/AnalyticsTab.tsx`, `frontend/src/components/tabs/PriceCheckTab.tsx`, `frontend/src/types/api.ts`, `frontend/src/test/`

- [ ] T12. Wire the Stash Viewer to the live stash API without changing the UI style

  **What to do**: Update the stash viewer flow so `frontend/src/services/api.ts` reads the backend wrapper from `/api/v1/stash/tabs`, unwraps `stashTabs`, and feeds the existing grid/hover-card UI. Keep the tab bar, grid layout, hover card styling, and schema disclosure visual treatment intact. Add explicit UI states for `stash unavailable`, `stash empty`, and `stale last snapshot`, and make sure the schema text shown in the collapsible matches the real delivered contract exactly.
  **Must NOT do**: Do not keep mock stash tabs in the runtime path, do not fetch PoE directly from the browser, and do not change the stash viewer’s visual language to work around missing data.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: this is live-data wiring inside a visually sensitive existing panel.
  - Skills: [`playwright`] - browser verification is required because grid rendering and hover behavior are central.
  - Omitted: `protocol-compat` - serializer/storage work is already handled in T6-T8.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: T13 | Blocked By: T9, T8

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/src/components/tabs/StashViewerTab.tsx` - existing stash grid, hover card, and schema disclosure behavior.
  - API/Type: `frontend/src/types/api.ts` - stash item and tab types to keep aligned with the backend wrapper.
  - Pattern: `frontend/src/services/api.ts` - stash API call seam.
  - Pattern: `frontend/src/lib/utils.ts` - class name composition helper already used in the view.

  **Acceptance Criteria** (agent-executable only):
  - [ ] The stash viewer renders live stash tabs/items from the backend wrapper and no longer loads mock stash data at runtime.
  - [ ] Empty, unavailable, and stale states are visible and do not break the grid layout.
  - [ ] The displayed schema text matches the actual backend contract.
  - [ ] `npm run test` and targeted Playwright coverage for the stash viewer pass.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Live stash viewer renders backend tabs
    Tool: Playwright
    Steps: Open `Stash Viewer`; use `getByRole('tab', { name: 'Stash Viewer' })`; click two rendered stash-tab buttons such as `Trade 1` and `Quad Dump` when present; hover the first visible `.stash-item-cell`.
    Expected: Grid cells, item hover details, and schema text all reflect live backend data without visual redesign.
    Evidence: .sisyphus/evidence/task-T12-stash-viewer.txt

  Scenario: Unavailable stash feature is explicit in the UI
    Tool: Playwright
    Steps: Load `Stash Viewer` with the stash endpoint returning either a feature-unavailable error or `{ "stashTabs": [] }`.
    Expected: The UI shows explicit unavailable or empty state messaging instead of mock tabs or broken layout.
    Evidence: .sisyphus/evidence/task-T12-stash-viewer-error.txt
  ```

  **Commit**: NO | Message: `grouped into T13` | Files: `frontend/src/components/tabs/StashViewerTab.tsx`, `frontend/src/services/api.ts`, `frontend/src/types/api.ts`, `frontend/src/test/`

- [ ] T13. Update deployment/docs and land the cross-tab verification suite

  **What to do**: Update the operator and developer documentation to reflect the new frontend/backend integration model. Document the same-origin/backend-managed auth assumption, local frontend proxying, allowed/disallowed service controls, private stash prerequisites, and the exact verification commands for API, frontend tests, and Playwright. Add or strengthen the cross-tab Playwright suite so all six top-level tabs are covered by one browser smoke path plus targeted failure cases.
  **Must NOT do**: Do not document browser-held token flows, do not claim unsupported controls exist, and do not record unrun commands as successful evidence.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: this is documentation plus verification-surface tightening after implementation settles.
  - Skills: [`docs-specialist`, `playwright`] - docs need accurate minimal diffs; browser verification needs stable coverage.
  - Omitted: `protocol-compat` - schema details should already be finalized before docs are updated.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: final verification wave only | Blocked By: T3, T4, T5, T8, T10, T11, T12

  **References** (executor has NO interview context - be exhaustive):
  - Doc: `README.md` - API startup, verification, and environment-variable guidance to update.
  - Doc: `docs/ops-runbook.md` - operator runtime and service-control guidance to update.
  - Pattern: `frontend/package.json` - frontend verification commands.
  - Pattern: `frontend/playwright.config.ts` - browser suite entry.
  - Pattern: `frontend/src/pages/Index.tsx` - tab inventory to cover in the smoke suite.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Docs explain same-origin/backend-managed auth, allowed service controls, stash prerequisites, and exact verification commands.
  - [ ] A Playwright smoke suite covers all six top-level tabs plus at least one unavailable/failure state.
  - [ ] `npm run build`, `npm run test`, `npx playwright test`, and `.venv/bin/pytest tests/unit` all pass after the full integration lands.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Full top-level tab smoke passes
    Tool: Playwright
    Steps: Open `/`; visit `Dashboard`, `Services`, `Analytics`, `Price Check`, `Stash Viewer`, and `Messages` using top-level tab role selectors; capture one screenshot or trace for the run.
    Expected: Every tab loads live content or explicit unavailable state, and no tab falls back to mock data.
    Evidence: .sisyphus/evidence/task-T13-full-smoke.txt

  Scenario: Verification bundle fails if docs or tests drift
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit && npm run test && npm run build && npx playwright test` and compare the docs commands to what actually ran.
    Expected: The command bundle is green and the docs reflect the real verification path exactly.
    Evidence: .sisyphus/evidence/task-T13-full-smoke-error.txt
  ```

  **Commit**: YES | Message: `feat(frontend): wire live dashboard tabs` | Files: `frontend/src/components/tabs/`, `frontend/src/services/api.ts`, `frontend/src/types/api.ts`, `frontend/src/test/`, `frontend/playwright.config.ts`, `README.md`, `docs/ops-runbook.md`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit - oracle
- [ ] F2. Code Quality Review - unspecified-high
- [ ] F3. Real Manual QA - unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check - deep

## Commit Strategy
- Commit 1: API contract and protected namespace foundation.
- Commit 2: Guarded runtime registry plus live service inventory/actions.
- Commit 3: Ops read-model endpoints for dashboard, messages, and analytics.
- Commit 4: Additive stash pricing schema/client/harvester/API.
- Commit 5: Frontend live transport/bootstrap layer.
- Commit 6: Frontend tab rewiring, docs, and verification updates.
- Each commit must be independently green for `pytest`/`vitest` scope touched before moving to the next commit.

## Success Criteria
- The frontend no longer renders mock-backed runtime data in production flow.
- The UI can show repo runtime state and outputs even when some subsystems are stale or unavailable.
- Only approved lifecycle targets are controllable, and dangerous/self-destructive actions fail closed.
- Private stash data is acquired server-side only, stored additively, priced with explicit confidence/fallback semantics, and returned in the documented wrapper contract.
- Browser verification proves all six top-level tabs load live data or explicit unavailable states without aesthetic regressions.
