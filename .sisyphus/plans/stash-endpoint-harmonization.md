# Stash Endpoint Harmonization

## TL;DR
> **Summary**: Consolidate the Account Stash flow behind one canonical snapshot-style endpoint, preserve the current JSON contract, and remove duplicate fetch/finalization paths that currently make scan/valuate/tab-switch behavior slow and inconsistent.
> **Deliverables**:
> - One canonical stash snapshot endpoint with legacy routes removed
> - Shared backend payload builder that serves status/result/tab views from one source of truth
> - Scan lifecycle fix for duplicate finalization and redundant reads
> - Edge/proxy path tuned for bounded fan-out, timeouts, and stable JSON envelopes
> - Contract/regression tests proving frontend-compatible payloads and no tab-switch refetch churn
> **Effort**: Large
> **Parallel**: YES - 2 waves
> **Critical Path**: contract lock → canonical snapshot builder → scan lifecycle/perf fix → proxy/consumer parity → regression verification

## Context
### Original Request
User reported that Account Stash fetching/display is broken, the Supabase `api-proxy` is slow and unclear, tab switches appear to refetch unnecessarily, and multiple legacy stash endpoints are causing confusion. They want one new endpoint that covers previous functionality and returns the same format as today, but all old/legacy endpoints should be removed so stale callers fail loudly instead of silently falling back.

### Interview Summary
- Backend currently exposes overlapping stash routes (`/stash/tabs`, `/stash/status`, `/stash/scan/*`) plus legacy aliases.
- Backend status/result paths read the full published stash payload; scan finalization appears to run twice on the success path.
- Frontend `StashViewerTab` and `EconomyTab` each fetch stash data independently, and internal stash-tab clicks also trigger fresh network calls.
- Frontend already normalizes both `stashTabs` and `stash/tabs/items` response families, but the migration policy now requires stale callers to fail fast instead of relying on compatibility bridges.
- Supabase guidance points to one fat proxy, bounded concurrency, timeouts, `waitUntil` for post-response work, and stable JSON envelopes.
- Oracle/Metis both flagged this as a contract + orchestration change that needs explicit contract, freshness, and failure semantics.

### Metis Review (gaps addressed)
- Contract authority, freshness semantics, and failure envelope were made explicit.
- Acceptance criteria now include exactly-once finalization, no extra tab-switch fetches, and payload parity checks.

### Contract Lock Artifact
- Canonical snapshot fields: `scanId`, `publishedAt`, `isStale`, `scanStatus`, `numTabs`, `tabsMeta`, `tabs`, `items`, `stashTabs`, `stash`.
- Canonical field semantics: `numTabs` must equal `len(tabs)` and `tabsMeta` must remain stable and ordered by tab index.
- Final public read surface: `POST /api/v1/stash/scan/start`, `GET /api/v1/stash/scan/status`, and `GET /api/v1/stash/scan/snapshot`.
- Lifecycle route table: `POST /api/v1/stash/scan/start` and `GET /api/v1/stash/scan/status` remain; `/api/v1/stash/scan`, `/api/v1/stash/tabs`, `/api/v1/stash/status`, `/api/v1/stash/scan/result`, and `/api/v1/stash/scan/valuations*` are tombstoned.
- Removed routes and expected status: `/api/v1/stash/scan` → `410 Gone`, `/api/v1/stash/tabs` → `410 Gone`, `/api/v1/stash/status` → `410 Gone`, `/api/v1/stash/scan/result` → `410 Gone`, `/api/v1/stash/scan/valuations*` → `410 Gone`.
- Failure envelope for removed routes: deterministic JSON error body with `error.code = route_gone`, `error.message`, and `error.details`, not a silent redirect or compatibility fallback.
- Tombstone handlers must be explicit 410 responders; unregistering routes is not sufficient because it yields a generic 404.
- Ops contract must stop advertising removed routes; route-map assertions should only expose the canonical snapshot flow.
- Ops contract key removals must include `stash_scan_legacy` and every related read alias.
- Canonical snapshot fixture: `.sisyphus/evidence/task-1-canonical-snapshot.json` becomes the authority for backend and frontend normalization tests.
- Error envelope parity must be field/value-identical across backend, proxy, and removed-route tombstones.
- Canonical snapshot must carry the valuation overlay that used to live behind `/scan/valuations*`; the public valuation routes are not retained.
- Backend error allowlist must add `route_gone` so 410 tombstones have a deterministic code.
- Tombstone rollout flag: `STASH_HARD_FAIL_LEGACY_ROUTES` gates 410 responses in shared/staging until the canonical consumer smoke passes.

## Work Objectives
### Core Objective
Replace the current stash route maze with one canonical snapshot endpoint and shared payload builder while forcing stale consumers to fail loudly until they are migrated.

### Deliverables
- Canonical stash snapshot endpoint with legacy routes removed
- Unified backend builder for tabs/status/result/valuation views
- Fixed scan lifecycle with exactly-once finalization
- Proxy/edge handler that minimizes latency and fan-out
- Frontend stash API fallbacks removed so stale callers fail loudly
- Golden tests proving JSON parity and no duplicate tab-switch fetches

### Definition of Done (verifiable conditions with commands)
- `.venv/bin/pytest tests/unit/test_api_stash.py tests/unit/test_api_stash_valuations.py tests/unit/test_api_ops_routes.py tests/unit/test_stash_scan.py tests/unit/test_account_stash_harvester.py` passes
- Frontend contract checks confirm stash data shape still satisfies `../poe-frontend/src/services/api.ts` normalization expectations
- Canonical endpoint responses match preserved snapshot fixtures for success, in-progress, and error cases
- Tab-switch path no longer triggers redundant stash refetches in the verified flow
- Scan completion writes occur exactly once per scan id

### Must Have
- Canonical snapshot JSON shape remains stable
- Legacy routes removed and stale callers forced to fail loudly
- No duplicate finalization
- No extra network fetches on fresh tab switches
- Explicit timeout/error mapping for proxy calls

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No frontend UI redesign in this step
- No backend contract drift hidden behind “compatible enough” behavior
- No new function-to-function hop chains in the proxy path
- No broad stash-domain redesign or valuation algorithm rewrite
- No silent retention of removed legacy routes or soft fallback shims

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: **tests-after** using focused unit/contract/regression coverage
- QA policy: Every task includes agent-executed happy-path and failure-path scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> This migration is dependency-heavy; the practical split is 2 / 2 / 1 waves.
> Extract shared dependencies early, but do not force fake parallelism across blocking contract changes.

Wave 1: Task 1 (contract lock) → Task 3 (scan lifecycle/perf fix)
Wave 2: Task 2 (backend snapshot builder) + Task 4 (edge proxy path)
Wave 3: Task 5 (contract/regression verification)

### Dependency Matrix (full, all tasks)
- 1 → 2, 4, 5
- 3 → 2, 5
- 2 → 5
- 4 → 5
- 5 → final verification only

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 2 tasks → deep, ultrabrain
- Wave 2 → 2 tasks → deep, deep
- Wave 3 → 1 task → unspecified-high

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Lock canonical stash snapshot contract

  **What to do**: Define the canonical read endpoint as `GET /api/v1/stash/scan/snapshot`, freeze the authoritative response schema, and replace every legacy stash route (`/scan`, `/tabs`, `/status`, `/scan/result`, `/scan/valuations*`) with an explicit 410 tombstone handler. Update OpenAPI/ops metadata so the old entries disappear from the public contract and stale callers hit a deterministic `route_gone` failure instead of a compatibility facade.
  **Must NOT do**: Do not change consumer-visible JSON keys, do not preserve any legacy alias behavior, and do not touch frontend UI behavior.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is a contract-definition and routing decision task that sets the foundation for the rest of the work.
  - Skills: `[]` — no extra specialization needed.
  - Omitted: `quick` — this spans multiple files and contracts.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2, 4, 5 | Blocked By: none

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `poe_trade/api/app.py` — route registration, tombstone handlers, and stash handler wiring.
  - Pattern: `apispec.yml` — canonical snapshot schema, removed-route tombstones, and response envelopes.
  - Pattern: `poe_trade/api/ops.py` — ops contract payload names and route metadata.
  - Pattern: `poe_trade/api/responses.py` — error-code allowlist and tombstone envelope codes.
  - Test: `tests/unit/test_api_ops_routes.py` — route contract expectations.
  - Test: `tests/unit/test_apispec_contract.py` — OpenAPI/schema parity expectations.
  - External: `../poe-frontend/src/services/api.ts` — current normalization behavior for old/new stash payload families.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `GET /api/v1/stash/scan/snapshot` is registered and returns the canonical stash snapshot shape.
  - [ ] Existing stash aliases are removed from the public route surface and return `410 Gone` with `error.code = route_gone` for stale callers.
  - [ ] Contract tests pass for the canonical response, prove the removed routes fail as expected, and verify `poe_trade/api/app.py`, `poe_trade/api/ops.py`, and `apispec.yml` all reflect the new route map while `poe_trade/api/responses.py` includes `route_gone`.
  - [ ] No JSON key renames or envelope changes leak into current consumer payloads.
  - [ ] Tombstone rollout is gated by `STASH_HARD_FAIL_LEGACY_ROUTES` so shared/staging environments only flip to 410 after the canonical consumer smoke passes.
  - [ ] `numTabs` equals `len(tabs)` and `tabsMeta` remains stable and ordered by tab index.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Canonical snapshot returns preserved shape
    Tool: Bash
    Steps: Start a private stash scan, wait until published, then run `curl -sS "$API_BASE/api/v1/stash/scan/snapshot" | jq '.stash, .tabs, .items, .stashTabs'` and save the body to `.sisyphus/evidence/task-1-canonical-snapshot.json`.
    Expected: The canonical route returns the full stash data and still satisfies the existing frontend normalization families.
    Evidence: .sisyphus/evidence/task-1-canonical-snapshot.json

  Scenario: Legacy alias hard-fails
    Tool: Bash
    Steps: Call the legacy stash routes (`/api/v1/stash/scan`, `/api/v1/stash/tabs`, `/api/v1/stash/scan/result`, and `/api/v1/stash/scan/valuations/start`) against the same published scan and record the HTTP status/body to `.sisyphus/evidence/task-1-legacy-alias-hardfail.json`.
    Expected: Legacy aliases are gone and stale callers fail loudly with `410 Gone` and `error.code = route_gone`.
    Evidence: .sisyphus/evidence/task-1-legacy-alias-hardfail.json
  ```

  **Commit**: NO | Message: n/a | Files: [poe_trade/api/app.py, poe_trade/api/ops.py, apispec.yml, tests/unit/test_api_ops_routes.py, tests/unit/test_apispec_contract.py]

- [ ] 2. Unify backend stash payload builders

  **What to do**: Refactor the backend read path so the canonical snapshot endpoint is the only public read surface and all internal status/result/tab sections are produced by one shared snapshot builder. Treat valuation assembly as an internal dependency of that canonical snapshot only; `stash_status_payload` must stop depending on `fetch_stash_tabs` full-payload reads and instead use metadata-only reads (`published scan id`, latest run, optional counts) unless a full snapshot is explicitly requested.
  **Must NOT do**: Do not introduce a second payload assembly path, do not expand the response shape, and do not reintroduce public tab-specific fetch branches on the backend.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the core orchestration refactor that removes duplicated reads.
  - Skills: `[]` — no extra specialization needed.
  - Omitted: `quick` — too many coupled files and contracts.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 5 | Blocked By: 1, 3

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `poe_trade/stash_scan.py` — published snapshot builder and stash tab/item assembly.
  - Pattern: `poe_trade/api/stash.py` — status/result payload helpers and canonical snapshot helpers.
  - Pattern: `poe_trade/api/valuation.py` — valuation merge behavior that must stay shape-compatible.
  - Test: `tests/unit/test_api_stash.py` — stash status/result/tab behavior.
  - Test: `tests/unit/test_stash_scan.py` — scan publication and snapshot reading.
  - External: `../poe-frontend/src/services/api.ts` — the frontend’s accepted payload families and normalization rules.

  **Acceptance Criteria** (agent-executable only):
  - [ ] The canonical snapshot endpoint and its internal sections come from one shared builder path.
  - [ ] Status reads stay metadata-light and no longer force a full snapshot rebuild on every poll (at most one metadata lookup, zero full item/tab reads).
  - [ ] `stash_status_payload` no longer depends on the full `fetch_stash_tabs` path.
  - [ ] Snapshot sections remain JSON-equivalent to the canonical snapshot contract.
  - [ ] Unit tests prove the read-path no longer duplicates full payload assembly.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Status poll stays lightweight
    Tool: Bash
    Steps: Run the focused stash tests (`.venv/bin/pytest tests/unit/test_api_stash.py tests/unit/test_stash_scan.py`) and capture a baseline of query/read counts for a status-only request.
    Expected: Status polling returns the correct metadata without forcing a second full snapshot build.
    Evidence: .sisyphus/evidence/task-2-status-lightweight.txt

  Scenario: Snapshot sections share the same source
    Tool: Bash
    Steps: Call the canonical snapshot endpoint once for a published scan, extract the `tabs`, `items`, `tabsMeta`, and `stashTabs` sections, and save normalized output to `.sisyphus/evidence/task-2-shared-source.json`.
    Expected: The canonical snapshot data is assembled once and all internal sections stay consistent with one source of truth.
    Evidence: .sisyphus/evidence/task-2-shared-source.json
  ```

  **Commit**: NO | Message: n/a | Files: [poe_trade/stash_scan.py, poe_trade/api/stash.py, poe_trade/api/valuation.py, tests/unit/test_api_stash.py, tests/unit/test_stash_scan.py]

- [ ] 3. Fix scan finalization and valuation cost

  **What to do**: Remove the duplicate scan-finalization call in the successful scan path, enforce exactly-once state transitions for publish/completion, and reduce valuation fan-out where possible so the scan/valuate pipeline stops paying N+1 costs on every item. The valuation overlay must be assembled into the canonical snapshot payload; do not preserve public valuation routes. Keep the current response contract intact while tightening the lifecycle and performance budget.
  **Must NOT do**: Do not alter scan-visible item data, do not change league/account scoping, and do not introduce a new storage schema in this task.

  **Recommended Agent Profile**:
  - Category: `ultrabrain` — Reason: this is the most logic-heavy part of the flow and needs careful lifecycle reasoning.
  - Skills: `[]` — no extra specialization needed.
  - Omitted: `quick` — too much cross-file state handling.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 2, 5 | Blocked By: 1

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `poe_trade/ingestion/account_stash_harvester.py` — scan execution and finalization path.
  - Pattern: `poe_trade/api/valuation.py` — per-item valuation behavior and query fan-out.
  - Test: `tests/unit/test_account_stash_harvester.py` — scan lifecycle expectations.
  - Test: `tests/unit/test_valuation_helpers.py` — valuation query-count and merge expectations.
  - External: Supabase Edge Functions docs (`architecture`, `limits`, `status-codes`, `background-tasks`) — for downstream proxy timing constraints and error envelope alignment.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Scan completion/finalization is executed exactly once per scan id on the success path.
  - [ ] Retry or exception paths do not duplicate publish/finalize writes; terminal write assertions cover both the scan-run row and the published marker.
  - [ ] Valuation query fan-out is reduced or capped relative to the current baseline measurement.
  - [ ] Lifecycle and valuation tests pass without contract drift.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Successful scan finalizes once
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_account_stash_harvester.py` and save the finalization/assertion output to `.sisyphus/evidence/task-3-finalize-once.txt`.
    Expected: The success path produces one finalization/publish sequence only.
    Evidence: .sisyphus/evidence/task-3-finalize-once.txt

  Scenario: Failure path does not double-write
    Tool: Bash
    Steps: Run the failure-path scan test or inject a controlled exception in the focused harvester test and verify active/published state remains consistent.
    Expected: The scan fails cleanly without duplicate finalize writes or half-published state.
    Evidence: .sisyphus/evidence/task-3-failure-path.txt
  ```

  **Commit**: NO | Message: n/a | Files: [poe_trade/ingestion/account_stash_harvester.py, poe_trade/api/valuation.py, tests/unit/test_account_stash_harvester.py, tests/unit/test_valuation_helpers.py]

- [ ] 4. Harden the edge proxy path

  **What to do**: Locate the Supabase `api-proxy` edge function in `../poe-frontend`, make it a single bounded proxy to the canonical stash snapshot endpoint, and tune it for low latency: batch where possible, avoid function-to-function hops, use request timeouts, and keep any post-response work off the critical path. Preserve the existing JSON envelope and make cache/revalidation behavior explicit.
  **Must NOT do**: Do not introduce new UI logic, do not add extra proxy hops, do not add fallback calls to removed legacy routes, and do not change the client-facing response shape.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this spans proxy architecture, latency control, and contract preservation.
  - Skills: `[]` — no extra specialization needed.
  - Omitted: `quick` — path discovery and proxy behavior tuning are multi-step.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 5 | Blocked By: 1

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `../poe-frontend/src/services/api.ts` — current normalization and stash API consumer behavior.
  - Pattern: `../poe-frontend/supabase/functions/api-proxy/index.ts` — current proxy error envelope and path forwarding behavior.
  - External: Supabase Edge Functions docs (`architecture`, `regional-invocation`, `limits`, `status-codes`, `development-tips`, `background-tasks`, `dependencies`, `recursive-functions`) — proxy performance and envelope guidance.
  - External: the repo’s `api-proxy` edge function entrypoint (locate by name in `../poe-frontend`) — the actual handler to tune.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Proxy calls route to the canonical stash snapshot endpoint with no extra function-to-function hop chain.
  - [ ] The proxy preserves `410 Gone` tombstones for removed routes with `error.code = route_gone`, enforces an 8s hard timeout, maps timeout/error cases to the preserved backend-style JSON envelope (`error.code`, `error.message`, `error.details`), and keeps stash auth policy no broader than today.
  - [ ] Canonical-proxy smoke meets the agreed latency budget (P95 at or below 2s over 20 measured requests after 3 warm-up calls in the baseline environment).
  - [ ] Cache/revalidation behavior is explicit and does not break the canonical consumer path.
  - [ ] Latency-sensitive post-processing is offloaded from the user-facing critical path.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Proxy returns canonical snapshot quickly
    Tool: Bash
    Steps: Call the proxy endpoint end-to-end with `curl -sS -D-` and save the body/headers to `.sisyphus/evidence/task-4-proxy-happy.json`.
    Expected: The proxy returns the canonical stash snapshot envelope, with stable headers and no unexpected extra hop behavior.
    Evidence: .sisyphus/evidence/task-4-proxy-happy.json

  Scenario: Upstream timeout is mapped cleanly
    Tool: Bash
    Steps: Force an upstream timeout or 5xx in the proxy path and capture the response body/status to `.sisyphus/evidence/task-4-proxy-timeout.json`.
    Expected: The proxy returns the documented `route_gone`/timeout error envelope without hanging or crashing.
    Evidence: .sisyphus/evidence/task-4-proxy-timeout.json
  ```

  **Commit**: NO | Message: n/a | Files: [edge proxy entrypoint in ../poe-frontend, ../poe-frontend/src/services/api.ts]

- [ ] 5. Add contract and regression verification

  **What to do**: Add or update golden fixtures and regression tests so the canonical snapshot, removed legacy aliases, frontend normalization family, in-progress states, and failure envelopes are all verified automatically. Remove the legacy fallback logic in `../poe-frontend/src/services/api.ts`, switch `StashViewerTab` and `stashCache` to the canonical snapshot endpoint, remove `StashViewerTab`’s valuation endpoint callers (`getStashValuationsStart/Status/Result`) in favor of snapshot-derived valuations, and move `EconomyTab`’s connected/disconnected status source to `GET /api/v1/stash/scan/status` so stale callers fail loudly while the canonical path keeps working.
  **Must NOT do**: Do not widen scope into UI redesign or unrelated stash-domain features.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: this is a multi-file verification pass with cross-repo contract checks.
  - Skills: `[]` — no extra specialization needed.
  - Omitted: `quick` — the verification surface is larger than a trivial test update.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: none | Blocked By: 1, 2, 3, 4

  **References** (executor has NO interview context — be exhaustive):
  - Test: `tests/unit/test_apispec_contract.py` — OpenAPI/schema parity checks.
  - Test: `tests/unit/test_api_ops_routes.py` — route contract coverage.
  - Test: `tests/unit/test_api_stash.py` — stash route behavior.
  - Test: `tests/unit/test_api_stash_valuations.py` — valuation contract coverage.
  - External: `../poe-frontend/src/services/api.ts` — frontend normalization expectations for `stashTabs` and `stash/tabs/items`.
  - External: `../poe-frontend/src/services/stashCache.ts` — caching/stash loading behavior.
  - External: `../poe-frontend/src/components/tabs/StashViewerTab.tsx`, `../poe-frontend/src/components/tabs/EconomyTab.tsx` — consumer flows to validate against.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Golden fixtures cover success, in-progress, stale, and error responses for the canonical snapshot route.
  - [ ] Legacy aliases (including valuation routes) are absent from the public surface and regression tests prove stale calls fail loudly.
  - [ ] Regression coverage proves the frontend normalization path still accepts the delivered payload.
  - [ ] `StashViewerTab` no longer calls valuation endpoints; valuation data comes from the canonical snapshot payload.
  - [ ] Legacy fallback logic is removed from `../poe-frontend/src/services/api.ts`, `StashViewerTab`/`stashCache` use the canonical snapshot endpoint, and `EconomyTab` uses `GET /api/v1/stash/scan/status` for connection state.
  - [ ] Fresh tab switches do not trigger a redundant stash refetch in the verified flow.
  - [ ] The tab-switch smoke harness asserts request counts deterministically so duplicate fetches are caught automatically.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Canonical fixture parity
    Tool: Bash
    Steps: Run the focused API contract tests (`.venv/bin/pytest tests/unit/test_apispec_contract.py tests/unit/test_api_ops_routes.py tests/unit/test_api_stash.py tests/unit/test_api_stash_valuations.py`) and save the output to `.sisyphus/evidence/task-5-contract-parity.txt`.
    Expected: The canonical endpoint matches the golden contract expectations and the removed legacy aliases fail as expected.
    Evidence: .sisyphus/evidence/task-5-contract-parity.txt

  Scenario: Frontend normalization still accepts payload
    Tool: Bash
    Steps: Validate the saved snapshot against the frontend normalization rules in `../poe-frontend/src/services/api.ts` and write the result to `.sisyphus/evidence/task-5-frontend-normalization.txt`.
    Expected: The delivered payload remains consumable by the existing frontend normalization family.
    Evidence: .sisyphus/evidence/task-5-frontend-normalization.txt

  Scenario: Stale frontend routes fail loudly
    Tool: Bash
    Steps: Run the current frontend stash fetch smoke against removed legacy routes (including valuation routes) after the `api.ts` fallback removal and capture the failure/status to `.sisyphus/evidence/task-5-stale-frontend-fail.txt`.
    Expected: The stale route usage fails loudly with `410 Gone` and `error.code = route_gone` so any un-migrated caller is immediately visible.
    Evidence: .sisyphus/evidence/task-5-stale-frontend-fail.txt
  ```

  **Commit**: NO | Message: n/a | Files: [tests/unit/test_apispec_contract.py, tests/unit/test_api_ops_routes.py, tests/unit/test_api_stash.py, tests/unit/test_api_stash_valuations.py, new regression fixtures]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep
## Commit Strategy
No commits unless the user explicitly asks for them. If the implementation team later decides to checkpoint work, commit only after the matching task’s tests pass and keep each commit scoped to one wave’s completed change set.

## Success Criteria
1. Canonical stash snapshot endpoint exists and preserves the current JSON contract.
2. Legacy stash aliases are removed and stale callers fail loudly.
3. Status/result/tab reads share one backend source of truth.
4. Scan completion is exactly-once and valuation fan-out is reduced.
5. The edge proxy path is bounded, timeout-safe, and envelope-stable.
6. Contract/regression tests prove frontend normalization still accepts the delivered payload.
