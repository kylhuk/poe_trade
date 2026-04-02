# Stash Scan + Valuation Routing Rework

## TL;DR
> **Summary**: Rework the stash API into canonical start/status/result routes for Account Stash scan and valuation, while preserving the current aliases and updating `apispec.yml` to match. The backend logic stays the same; this is a routing/contract reshuffle with tests and docs brought back into sync.
> **Deliverables**: canonical stash lifecycle routes, preserved legacy aliases, ops route-map updates, OpenAPI path/schema updates, focused contract/regression tests.
> **Effort**: Large
> **Parallel**: YES - 2 waves
> **Critical Path**: route map/handler aliases → OpenAPI contract → regression verification

## Context
### Original Request
The API needs rework in the area of `/api/v1/stash/scan/valuations` so it can expose:
- Start an Account Stash scan
- Get status of an Account Stash scan
- Get result of an Account Stash scan (all items and stashes)
- Start valuation of all items in all stashes
- Check valuation status
- Get valuation result (price estimates, historical prices, etc.)

The user also asked to update `apispec.yml`, and the functionality is expected to already exist — only routing/contracts need to move.

### Interview Summary
- Current route handlers live in `poe_trade/api/app.py` and are already split by responsibility:
  - `_stash_scan_start` → `/api/v1/stash/scan` and `/api/v1/stash/scan/start`
  - `_stash_scan_status` → `/api/v1/stash/scan/status`
  - `_stash_status` → `/api/v1/stash/status`
  - `_stash_tabs` → `/api/v1/stash/tabs`
  - `_stash_scan_valuations` → `/api/v1/stash/scan/valuations`
  - `_stash_item_history` → `/api/v1/stash/items/{fingerprint}/history`
- Payload builders already exist in `poe_trade/api/stash.py` and `poe_trade/api/valuation.py`.
- `apispec.yml` already documents the current scan start/status/valuations paths and the legacy `/api/v1/stash/scan` alias.
- Existing tests cover scan status, stash status, and the valuations POST route.
- External long-running-operation guidance favors explicit start/status/result resources, stable job identifiers, and preserved polling semantics.
- Decision for this plan: **preserve current aliases** and add canonical lifecycle routes under the stash scan/valuation families instead of breaking existing clients.

### Metis Review (gaps addressed)
- Preserve legacy aliases; do not break the current `/api/v1/stash/scan`, `/api/v1/stash/tabs`, or `/api/v1/stash/scan/valuations` callers.
- Keep scan and valuation lifecycle responsibilities separate; no pricing-engine rewrite.
- Make the canonical public shape resource-like: `start` / `status` / `result` for scan and valuation.
- Resolve naming ambiguity up front: canonical result routes will live under `/api/v1/stash/scan/result` and `/api/v1/stash/scan/valuations/result` while legacy aliases remain available.
- Scope creep guardrails: no new schema migrations, no auth/session redesign, no frontend changes, no valuation math changes.

## Work Objectives
### Core Objective
Expose a clean, documented, backward-compatible lifecycle for stash scan and valuation operations using the routes already implied by the backend helpers.

### Deliverables
- Canonical stash scan routes for start, status, and result.
- Canonical valuation lifecycle routes for start, status, and result.
- Legacy aliases retained for current consumers.
- `ops` contract route map updated to include canonical and deprecated route names.
- `apispec.yml` updated with the new route layout and schema references.
- Focused tests proving canonical route behavior and alias compatibility.

### Definition of Done (verifiable conditions with commands)
- `.venv/bin/pytest tests/unit/test_api_ops_routes.py tests/unit/test_api_stash.py tests/unit/test_api_stash_valuations.py` passes.
- `make ci-api-contract` passes.
- Any new OpenAPI contract/snapshot test for `apispec.yml` passes.
- The route map in `poe_trade/api/ops.py` exposes canonical and legacy stash keys consistently.

### Must Have
- Preserve the existing alias paths during the transition.
- Keep response payload shapes stable for the current endpoints.
- Add canonical result routes instead of overloading the current status endpoints.
- Use the existing payload builders; do not change valuation algorithms or ClickHouse schema.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No pricing/median/fallback algorithm rewrite.
- No DB schema or migration work.
- No auth/session flow changes.
- No frontend changes.
- No undocumented route rename that breaks current clients.

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: **tests-first / contract-first** for route and spec changes.
- QA policy: every task includes agent-executed happy-path and failure-path scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.md` for success and `.sisyphus/evidence/task-{N}-{slug}-error.md` for failure.

## Execution Strategy
### Parallel Execution Waves
> Target: 2 waves. Wave 1 establishes the canonical route map; Wave 2 can run spec and regression coverage in parallel once the route names are fixed.

Wave 1: canonical stash route map + handler aliases

Wave 2: OpenAPI/spec update + regression/contract tests

### Dependency Matrix (full, all tasks)
- Task 1 blocks Tasks 2 and 3.
- Task 2 and Task 3 can run in parallel after Task 1.

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 1 task → unspecified-high
- Wave 2 → 2 tasks → writing, quick

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. `poe_trade/api/app.py` + `poe_trade/api/stash.py` + `poe_trade/api/valuation.py` + `poe_trade/api/ops.py`: rework the stash route map into canonical lifecycle endpoints and keep the current aliases

  **What to do**: Add the canonical stash lifecycle route set in `ApiApp._register_routes()` and wire the handlers to the existing payload builders. Preserve current aliases while introducing the canonical paths:
  - `POST /api/v1/stash/scan/start` and legacy `POST /api/v1/stash/scan`
  - `GET /api/v1/stash/scan/status`
  - `GET /api/v1/stash/scan/result` and legacy `GET /api/v1/stash/tabs`
  - `POST /api/v1/stash/scan/valuations/start`
  - `GET /api/v1/stash/scan/valuations/status`
  - `GET /api/v1/stash/scan/valuations/result` and legacy `POST /api/v1/stash/scan/valuations`

  Keep `/_stash_account_scope` and existing session/auth gating behavior intact. If a tiny shared parser is needed so the legacy POST route and the canonical GET result route reuse the same validation, add it in the stash/valuation helper layer rather than duplicating request parsing in the handler methods.

  **Must NOT do**: Do not change scan/valuation algorithms, do not add new DB tables, do not alter auth semantics, and do not remove old paths.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: multiple route handlers, aliasing, and contract payload updates across API modules.
  - Skills: `[]` — no special skill injection needed.
  - Omitted: `visual-engineering` — not a UI task.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [2, 3] | Blocked By: []

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `poe_trade/api/app.py:516-545` — current stash route registration block and alias style.
  - Pattern: `poe_trade/api/app.py:1120-1419` — current stash handlers and auth/session gating.
  - Pattern: `poe_trade/api/stash.py:25-291` — status/result payload builders already used by the handlers.
  - Pattern: `poe_trade/api/valuation.py:108-457` — valuation result builder and current response fields.
  - Pattern: `poe_trade/api/ops.py:40-82` — route contract map that must reflect canonical and legacy paths.
  - Pattern: `tests/unit/test_api_ops_routes.py:105-124` — current contract assertions for stash routes.
  - Pattern: `tests/unit/test_api_stash.py:93-240` — status/published-scan payload expectations.
  - Pattern: `tests/unit/test_api_stash_valuations.py:66-335` — valuation POST route, validation, and response shape.
  - External: [Google Cloud long-running operations](https://docs.cloud.google.com/document-ai/docs/long-running-operations) — explicit start/status/result job-resource pattern.
  - External: [OpenREST long-running operations](https://openrest.krotscheck.net/advanced/long-running-operations/) — 202/Retry-After/Location guidance for deferred work.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `ApiApp._register_routes()` exposes the canonical stash lifecycle paths and keeps the legacy aliases mapped to the same handlers.
  - [ ] The ops route contract includes canonical route keys for scan result and valuation start/status/result, plus the old legacy keys.
  - [ ] Canonical scan result returns the same published tabs/items payload currently served by `/api/v1/stash/tabs`.
  - [ ] Canonical valuation result returns the same payload currently served by `/api/v1/stash/scan/valuations`.
  - [ ] No auth/session status codes change for existing stash endpoints.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Canonical scan aliases resolve
    Tool: Bash
    Steps: Run the focused route tests for stash scan and ensure both `/api/v1/stash/scan/start` and `/api/v1/stash/scan` still dispatch to the same handler, while `/api/v1/stash/scan/result` returns the published tabs/items payload.
    Expected: The new canonical route exists and the legacy aliases still pass unchanged.
    Evidence: .sisyphus/evidence/task-1-stash-route-map.md

  Scenario: Canonical valuation lifecycle resolves
    Tool: Bash
    Steps: Run the focused valuation route tests, including the new result path and legacy POST alias.
    Expected: The canonical valuation result path and the legacy POST alias both return the same payload shape; invalid input still yields 400/404 as before.
    Evidence: .sisyphus/evidence/task-1-stash-route-map-error.md
  ```

  **Commit**: NO | Message: none | Files: [poe_trade/api/app.py, poe_trade/api/stash.py, poe_trade/api/valuation.py, poe_trade/api/ops.py, tests/unit/test_api_ops_routes.py, tests/unit/test_api_stash.py, tests/unit/test_api_stash_valuations.py]

- [ ] 2. `apispec.yml`: document the canonical stash lifecycle routes, keep deprecated aliases, and align schemas/response codes with the new route shape

  **What to do**: Update the OpenAPI spec so it reflects the new canonical lifecycle endpoints and the kept legacy aliases. Reuse the current stash auth/parameter patterns (`sessionCookie`, `LeagueQuery`, `Realm`) and keep the response codes aligned with the handler behavior.

  Concretely:
  - add canonical paths for scan start/status/result and valuation start/status/result;
  - keep the old paths documented as deprecated aliases;
  - reuse `StashTabsResponse` for scan result and `StashScanValuationsResponse` for valuation result unless a new explicit job envelope schema is required;
  - add new lightweight schemas for valuation start/status if the route contract needs explicit fields;
  - document 202 / 200 / 401 / 404 / 503 behavior and any `Location` / `Retry-After` headers used by the lifecycle routes.

  **Must NOT do**: Do not change runtime behavior in the spec task; do not invent new data fields beyond the handler contract; do not remove the deprecated aliases from the document.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: OpenAPI documentation and schema alignment.
  - Skills: `[]` — no special skill injection needed.
  - Omitted: `visual-engineering` — not a UI task.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [] | Blocked By: [1]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `apispec.yml:316-474` — current stash path grouping and schema style.
  - Pattern: `apispec.yml:858-944` — current stash response/request schemas.
  - Pattern: `poe_trade/api/stash.py:25-291` — field names emitted by the current payload helpers.
  - Pattern: `poe_trade/api/valuation.py:108-457` — valuation response fields and request validation semantics.
  - Pattern: `tests/unit/test_api_stash.py:93-240` — status payload expectations used to keep schema fields accurate.
  - Pattern: `tests/unit/test_api_stash_valuations.py:66-335` — valuation route request/response shape that the spec must describe.
  - External: [Google Cloud long-running operations](https://docs.cloud.google.com/document-ai/docs/long-running-operations) — canonical job-resource/status/result guidance.
  - External: [OpenREST long-running operations](https://openrest.krotscheck.net/advanced/long-running-operations/) — 202/Retry-After/Location pattern for deferred endpoints.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `apispec.yml` contains the canonical route entries and marks the legacy aliases as deprecated.
  - [ ] The documented response schemas match the actual route payloads and status codes.
  - [ ] If new valuation start/status schemas are introduced, they are fully documented and referenced by the new paths.
  - [ ] The route naming in the spec matches the canonical route map from Task 1.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: OpenAPI document exposes canonical lifecycle paths
    Tool: Bash
    Steps: Run the OpenAPI/spec validation or snapshot test after updating apispec.yml.
    Expected: The new canonical routes appear with the expected methods, security, and schema refs; deprecated aliases remain documented.
    Evidence: .sisyphus/evidence/task-2-openapi-spec.md

  Scenario: OpenAPI contract remains parseable
    Tool: Bash
    Steps: Run the contract target (`make ci-api-contract`) or the repo's spec-check test after the YAML update.
    Expected: The API contract check passes without changing any unrelated ops/api route behavior.
    Evidence: .sisyphus/evidence/task-2-openapi-spec-error.md
  ```

  **Commit**: NO | Message: none | Files: [apispec.yml, tests/unit/test_apispec_contract.py (if needed)]

- [ ] 3. `tests/unit/test_api_ops_routes.py` + `tests/unit/test_api_stash.py` + `tests/unit/test_api_stash_valuations.py` (and any small new contract file if needed): expand regression coverage for the new canonical routes and preserved aliases

  **What to do**: Add or adjust the route and payload tests so they prove the canonical routes, legacy aliases, and error/status semantics all line up with the new routing plan.

  Coverage should include:
  - canonical scan start/status/result paths;
  - canonical valuation start/status/result paths;
  - legacy alias coverage for `/api/v1/stash/scan`, `/api/v1/stash/tabs`, and `/api/v1/stash/scan/valuations`;
  - preserved 400/401/404/503 behavior;
  - the ops contract route map exposing the new keys.

  If the repo has no existing OpenAPI snapshot/contract test, add a small focused contract test file instead of inventing a new broad framework.

  **Must NOT do**: Do not test business logic that didn’t change; do not introduce live ClickHouse or network dependencies; do not weaken the existing negative-path assertions.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: focused regression tests and route assertions.
  - Skills: `[]` — no special skill injection needed.
  - Omitted: `visual-engineering` — not a UI task.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [] | Blocked By: [1]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `tests/unit/test_api_ops_routes.py:105-124` — route-map assertions for stash aliases.
  - Pattern: `tests/unit/test_api_stash.py:93-240` — scan status and published-scan payload coverage.
  - Pattern: `tests/unit/test_api_stash_valuations.py:66-335` — valuations request validation and error mapping.
  - Pattern: `poe_trade/api/app.py:1120-1419` — handler behavior and status codes that the tests must preserve.
  - Pattern: `Makefile:65-67` — `make ci-api-contract` target for contract verification.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Tests prove the new canonical stash routes resolve to the correct payload builders.
  - [ ] Tests prove the old aliases still behave exactly as before.
  - [ ] Tests prove invalid valuation input and missing session behavior remain unchanged.
  - [ ] The route contract assertions include the new canonical keys.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Canonical route regression passes
    Tool: Bash
    Steps: Run the focused unit test modules after the routing changes.
    Expected: The canonical and alias route tests pass, including status/result assertions.
    Evidence: .sisyphus/evidence/task-3-route-regressions.md

  Scenario: Contract assertions stay stable
    Tool: Bash
    Steps: Run `make ci-api-contract` after the route/test updates.
    Expected: The API contract target passes and the stash route keys appear exactly as planned.
    Evidence: .sisyphus/evidence/task-3-route-regressions-error.md
  ```

  **Commit**: NO | Message: none | Files: [tests/unit/test_api_ops_routes.py, tests/unit/test_api_stash.py, tests/unit/test_api_stash_valuations.py, tests/unit/test_apispec_contract.py (if needed)]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Keep the implementation in two atomic waves if commits are used at all: route/handler work first, then OpenAPI/docs/tests.
- Do not commit during planning; only commit if/when the user explicitly asks during execution.

## Success Criteria
- The API exposes canonical stash lifecycle routes for scan and valuation without breaking current clients.
- The legacy aliases remain functional and documented as deprecated where appropriate.
- `apispec.yml` matches the runtime route map and payload schemas.
- Route regression tests and `make ci-api-contract` pass.
- No valuation algorithm or storage-layer behavior changed as part of the routing rework.
