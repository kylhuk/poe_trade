# Protected ML API Foundation

## TL;DR
> **Summary**: Add a new in-repo, operator-token protected HTTP service that exposes a narrow ML-only API foundation for a separate-domain React frontend, without reusing CLI stdout or exposing mutating ML workflows.
> **Deliverables**:
> - new `poe_trade/api/` package plus `poe_trade/services/api.py` service entrypoint
> - explicit inbound API settings for bind host/port, operator token, CORS origins, request limits, and league allowlist
> - versioned `/api/v1` ML read/predict routes with stable DTOs and sanitized JSON errors
> - strict bearer-token auth and separate-domain CORS policy
> - pytest coverage, curl-based verification, and operator docs for local/dev startup
> **Effort**: Medium
> **Parallel**: YES - 3 waves
> **Critical Path**: Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7 -> Task 8

## Context
### Original Request
- Create a protected API foundation so this backend can later integrate with a likely React frontend built elsewhere.
- Lay out the foundation first, then shape the final frontend-specific API contract later once the frontend is available.
- Expose various backend measures through the API.

### Interview Summary
- User wants planning only at this stage.
- Protection model chosen: operator-token auth for phase 1.
- First-wave scope chosen: ML only.
- Deployment assumption chosen: frontend and API are on separate domains.
- Default applied: phase 1 is an operator/internal foundation, not a browser-direct public SPA auth solution.

### Metis Review (gaps addressed)
- Keep inbound API auth fully separate from existing outbound `POE_OAUTH_*` PoE credentials.
- Do not expose CLI entrypoints or mutating ML workflows as HTTP routes.
- Freeze a DTO boundary instead of returning raw internal workflow dicts unchanged.
- Add strict CORS allowlisting and fail-closed auth; no wildcard origin and no credentialed cookie flow.
- Plan around test injection and settings singleton reset behavior so HTTP tests stay deterministic.

### Oracle Review (architecture guardrails applied)
- Use a small stdlib HTTP service for the foundation instead of introducing a full web framework in v1.
- Add a dedicated `poe_trade/api/` package and a thin `poe_trade/services/api.py` entrypoint aligned with existing service patterns.
- Keep v1 route scope to `healthz`, ML contract, ML status, and ML predict-one only.
- Keep TLS and external ingress outside the app; the service only binds host/port.

## Work Objectives
### Core Objective
Create a decision-complete, protected ML API foundation that a later frontend integration can safely consume without forcing any redesign of auth boundaries, CORS policy, or core response contracts.

### Deliverables
- `poe_trade/api/` package with app factory, routing, auth, DTO mapping, error mapping, and HTTP helpers
- `poe_trade/services/api.py` startup entrypoint registered through the existing service router
- additive inbound API settings parsed through `poe_trade.config.settings.Settings`
- versioned endpoints:
  - `GET /healthz`
  - `GET /api/v1/ml/contract`
  - `GET /api/v1/ml/leagues/{league}/status`
  - `POST /api/v1/ml/leagues/{league}/predict-one`
- unit tests for settings, auth, CORS, routing, status, and predict-one
- README/operator guidance with exact env vars and curl verification flow

### Definition of Done (verifiable conditions with commands)
- `.venv/bin/python -m poe_trade.cli service --name api -- --help` succeeds and shows bind/auth-related flags.
- `curl -i http://127.0.0.1:8080/healthz` returns `200` with JSON body containing `status` and `service`.
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ml/leagues/Mirage/status` returns `200` with JSON body containing `league`, `status`, `active_model_version`, and `candidate_vs_incumbent`.
- `curl -i -X POST -H "Authorization: Bearer phase1-token" -H "Content-Type: application/json" --data @.sisyphus/evidence/predict-one-request.json http://127.0.0.1:8080/api/v1/ml/leagues/Mirage/predict-one` returns `200` with JSON body containing `route`, `price_p50`, and `confidence_percent`.
- `curl -i -H "Origin: https://evil.example.com" -H "Authorization: Bearer phase1-token" http://127.0.0.1:8080/api/v1/ml/leagues/Mirage/status` does not return an allow-origin header for the denied origin.
- `.venv/bin/pytest tests/unit/test_api_settings.py tests/unit/test_api_auth.py tests/unit/test_api_cors.py tests/unit/test_api_ml_routes.py tests/unit/test_api_service.py -q` passes.

### Must Have
- inbound API settings use new `POE_API_*` names and never reuse `POE_OAUTH_*` or `POE_STASH_TRIGGER_TOKEN`
- all `/api/v1/ml/*` routes require bearer-token auth
- public contract is versioned and DTO-backed
- CORS is explicit, allowlist-based, and compatible with separate frontend/API domains
- phase 1 is ML-only and excludes long-running/mutating ML routes
- errors are sanitized and JSON-shaped consistently

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- no FastAPI/Flask introduction in phase 1
- no browser-stored long-lived operator token as the intended production usage model
- no wildcard CORS origin or `allow_credentials=true`
- no direct shelling out to `poe-ml` or reuse of CLI stdout as API responses
- no `train-loop`, `evaluate`, `report`, `predict-batch`, migration, scanner, or ingestion-control routes in phase 1
- no TLS termination logic inside the Python app

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: `tests-after` using `pytest`, direct HTTP curl checks, and service startup verification
- QA policy: Every task includes agent-executed happy-path and failure-path scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: service foundation, inbound settings, transport/error primitives (`deep`, `quick`)
Wave 2: security and ML endpoint vertical slices (`deep`, `unspecified-high`)
Wave 3: tests, docs, and end-to-end verification (`writing`, `deep`)

### Dependency Matrix (full, all tasks)
- `1` blocks `2,3,4,5,6,7,8`
- `2` blocks `3,4,5,6,7,8`
- `3` blocks `4,5,6,7,8`
- `4` blocks `5,6,7,8`
- `5` blocks `7,8`
- `6` blocks `7,8`
- `7` blocks `8`

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 3 tasks -> `deep`, `quick`
- Wave 2 -> 3 tasks -> `deep`, `unspecified-high`
- Wave 3 -> 2 tasks -> `writing`, `deep`

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Add the API package and service registration foundation

  **What to do**: Create a new `poe_trade/api/` package with these exact modules: `__init__.py`, `app.py`, `routes.py`, `auth.py`, `responses.py`, and `ml.py`. Add a thin `poe_trade/services/api.py` entrypoint that parses exactly `--host` and `--port`, falling back to `POE_API_BIND_HOST` and `POE_API_BIND_PORT`, then starts the HTTP server. Register the new service through the existing service/router pattern so operators can start it with `poe_trade.cli service --name api -- --host 127.0.0.1 --port 8080`.
  **Must NOT do**: Do not add a new standalone console script in phase 1. Do not embed ML business logic inside the service entrypoint.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this establishes the backend boundary and startup pattern every later task depends on.
  - Skills: [] — why needed: repo-native service patterns are sufficient.
  - Omitted: [`frontend-ui-ux`] — why not needed: no frontend work.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: `2,3,4,5,6,7,8` | Blocked By: none

  **References**:
  - Pattern: `poe_trade/cli.py` — existing CLI router and service-dispatch entrypoint to extend.
  - Pattern: `poe_trade/config/constants.py` — `SERVICE_NAMES` registration pattern.
  - Pattern: `poe_trade/services/market_harvester.py` — existing service entrypoint shape to mirror.
  - Pattern: `poe_trade/services/_runner.py` — helper location and service startup conventions.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe_trade.cli` can resolve `service --name api` without import errors.
  - [ ] `poe_trade/services/api.py` is transport-only and delegates request handling into `poe_trade/api/`.
  - [ ] API startup path does not import `poe_trade.ml.cli`.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Service help renders for the new API service
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli service --name api -- --help`.
    Expected: Command exits 0 and prints API bind flag help for `--host` and `--port`.
    Evidence: .sisyphus/evidence/task-1-api-service-help.txt

  Scenario: Unknown service handling still works predictably
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli service --name not-a-real-service`.
    Expected: Command exits non-zero with the existing unknown-service error behavior; adding `api` does not weaken service validation.
    Evidence: .sisyphus/evidence/task-1-api-service-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add service foundation` | Files: `poe_trade/cli.py`, `poe_trade/config/constants.py`, `poe_trade/services/api.py`, `poe_trade/api/*`, `tests/unit/test_api_service.py`

- [ ] 2. Add inbound API settings with explicit names and validation rules

  **What to do**: Extend `Settings` with dedicated inbound API config values and parsing helpers: `POE_API_BIND_HOST`, `POE_API_BIND_PORT`, `POE_API_OPERATOR_TOKEN`, `POE_API_CORS_ORIGINS`, `POE_API_MAX_BODY_BYTES`, and `POE_API_LEAGUE_ALLOWLIST`. Define exact defaults: bind host `127.0.0.1`, bind port `8080`, no default operator token, empty CORS origins tuple, max body bytes `32768`, and league allowlist defaulting to `Mirage` only.
  **Must NOT do**: Do not reuse `POE_OAUTH_*` or `POE_STASH_TRIGGER_TOKEN` for inbound auth. Do not add alias env names beyond the exact list above.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: auth/CORS config is part of the long-term contract and must stay consistent with existing settings patterns.
  - Skills: [] — why needed: repo-native env parsing and alias tests cover the pattern.
  - Omitted: [`protocol-compat`] — why not needed: no schema evolution here.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: `3,4,5,6,7,8` | Blocked By: `1`

  **References**:
  - Pattern: `poe_trade/config/settings.py` — existing `Settings` dataclass and parsing helpers.
  - Pattern: `poe_trade/config/constants.py` — default constant location.
  - Test: `tests/unit/test_settings_aliases.py` — config parsing and alias coverage style.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Missing `POE_API_OPERATOR_TOKEN` causes API app creation/startup to fail closed with a clear error in non-test startup paths.
  - [ ] `POE_API_CORS_ORIGINS` parses into a tuple of exact origins, preserving order and trimming whitespace.
  - [ ] `POE_API_LEAGUE_ALLOWLIST` defaults to `("Mirage",)` and is used by route validation.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Settings parse valid API env values
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_api_settings.py -q`.
    Expected: Tests pass and verify host, port, token, origins, body limit, and league allowlist parsing.
    Evidence: .sisyphus/evidence/task-2-api-settings.txt

  Scenario: Missing operator token fails closed
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_api_settings.py -q -k missing_token`.
    Expected: Test passes and proves startup raises a stable config error instead of silently allowing unauthenticated access.
    Evidence: .sisyphus/evidence/task-2-api-settings-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add inbound settings` | Files: `poe_trade/config/constants.py`, `poe_trade/config/settings.py`, `tests/unit/test_api_settings.py`

- [ ] 3. Build the stdlib HTTP transport, route table, and JSON envelope primitives

  **What to do**: Implement an in-process stdlib HTTP server in `poe_trade/api/` using a request handler plus app factory. Freeze the exact route table now: `GET /healthz`, `GET /api/v1/ml/contract`, `GET /api/v1/ml/leagues/{league}/status`, `POST /api/v1/ml/leagues/{league}/predict-one`, plus `OPTIONS` support for preflight on those same paths only. Define one shared JSON response helper and one shared JSON error envelope shape: `{ "error": { "code": str, "message": str, "details": object | null } }`. Use exactly these error codes across the service: `route_not_found`, `method_not_allowed`, `auth_required`, `auth_invalid`, `origin_denied`, `league_not_allowed`, `invalid_json`, `invalid_input`, `request_too_large`, `backend_unavailable`, and `internal_error`.
  **Must NOT do**: Do not use `http.server` ad hoc per-route branching without a reusable route registry. Do not leave error bodies inconsistent across handlers.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: transport and route contracts must be locked before auth and endpoint wiring.
  - Skills: [] — why needed: stdlib-only implementation is the chosen architecture.
  - Omitted: [`artistry`] — why not needed: conventional service design.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: `4,5,6,7,8` | Blocked By: `1,2`

  **References**:
  - Pattern: `poe_trade/cli.py` — thin public entrypoint style.
  - Pattern: `poe_trade/db/clickhouse.py` — existing exception surface to wrap later.
  - External: `https://docs.python.org/3/library/http.server.html` — stdlib transport reference.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `GET /healthz` returns deterministic JSON `{ "status": "ok", "service": "api", "version": "v1" }` without requiring auth.
  - [ ] Unknown routes return `404` using the shared JSON error envelope.
  - [ ] Wrong methods on known routes return `405` using the shared JSON error envelope.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Health endpoint is live and JSON-shaped
    Tool: Bash
    Steps: Start the API service in a background shell, then run `curl -i http://127.0.0.1:8080/healthz`.
    Expected: Response is `200`, content type is JSON, and body contains `status` and `service`.
    Evidence: .sisyphus/evidence/task-3-healthz.txt

  Scenario: Unknown route returns stable error JSON
    Tool: Bash
    Steps: Start the API service and run `curl -i http://127.0.0.1:8080/api/v1/does-not-exist`.
    Expected: Response is `404` and body matches the shared error envelope.
    Evidence: .sisyphus/evidence/task-3-route-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add transport primitives` | Files: `poe_trade/api/*`, `tests/unit/test_api_routes.py`, `tests/unit/test_api_service.py`

- [ ] 4. Implement bearer-token auth, strict CORS, and request-size protection

  **What to do**: Add auth and CORS middleware/helpers to the transport layer. Require `Authorization: Bearer <token>` on every `/api/v1/ml/*` route, validate with constant-time comparison, and implement origin allowlisting from `POE_API_CORS_ORIGINS` with explicit support for `GET`, `POST`, and `OPTIONS`. Enforce `POE_API_MAX_BODY_BYTES` before reading request bodies.
  **Must NOT do**: Do not allow query-string tokens. Do not set `Access-Control-Allow-Origin: *`. Do not set `Access-Control-Allow-Credentials: true`.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: security policy and preflight behavior need careful precision but stay scoped.
  - Skills: [] — why needed: stdlib + settings-based approach is enough.
  - Omitted: [`frontend-ui-ux`] — why not needed: no UI work.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: `5,6,7,8` | Blocked By: `3`

  **References**:
  - Pattern: `poe_trade/config/settings.py` — env-backed settings access.
  - Test: `tests/unit/test_market_harvester_auth.py` — auth-related negative-path coverage style.
  - External: `https://docs.python.org/3/library/hmac.html#hmac.compare_digest` — constant-time token comparison reference.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Missing token returns `401` on ML routes.
  - [ ] Invalid token returns `401` on ML routes.
  - [ ] Allowed origin receives a specific `access-control-allow-origin` header, while denied origin does not.
  - [ ] Oversized request body returns `413` before workflow execution.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Valid auth and allowed origin pass preflight and request checks
    Tool: Bash
    Steps: Start the API service, run an `OPTIONS` preflight with `Origin: https://app.example.com`, then run an authenticated `GET` against the ML status route.
    Expected: Preflight returns allow-origin for `https://app.example.com`; authenticated request returns non-401.
    Evidence: .sisyphus/evidence/task-4-auth-cors.txt

  Scenario: Missing token and denied origin both fail safely
    Tool: Bash
    Steps: Start the API service, request ML status without `Authorization`, then repeat with `Origin: https://evil.example.com`.
    Expected: First response is `401`; second response includes no allowed-origin header for the denied origin.
    Evidence: .sisyphus/evidence/task-4-auth-cors-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add auth and cors guards` | Files: `poe_trade/api/*`, `tests/unit/test_api_auth.py`, `tests/unit/test_api_cors.py`

- [ ] 5. Add the ML contract and ML status endpoints with stable DTO mapping

  **What to do**: Implement `GET /api/v1/ml/contract` and `GET /api/v1/ml/leagues/{league}/status`. `contract` must expose exactly these top-level keys: `version`, `auth_mode`, `allowed_leagues`, `routes`, and `non_goals`. `status` must call the existing ML status workflow directly from `poe_trade.ml.workflows`, validate league against `POE_API_LEAGUE_ALLOWLIST`, and map the internal payload into a stable DTO with exactly these top-level keys: `league`, `run`, `status`, `promotion_verdict`, `stop_reason`, `active_model_version`, `latest_avg_mdape`, `latest_avg_interval_coverage`, `candidate_vs_incumbent`, and `route_hotspots`. When the underlying workflow returns `no_runs`, the DTO must still include all of those keys, using `null` for scalar values and `{}` or `[]` defaults for structured fields so the frontend contract remains stable even on empty environments.
  **Must NOT do**: Do not expose raw workflow dicts without field filtering. Do not call `poe_trade.ml.cli.main` or parse CLI stdout.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the first true business endpoint and locks the DTO boundary for frontend integration.
  - Skills: [] — why needed: existing workflow return shapes already exist in-repo.
  - Omitted: [`docs-specialist`] — why not needed: endpoint implementation first.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `7,8` | Blocked By: `4`

  **References**:
  - Pattern: `poe_trade/ml/workflows.py` — ML status workflow and related response fields.
  - Pattern: `poe_trade/ml/contract.py` — ML contract constants that can inform the API contract response.
  - Pattern: `poe_trade/ml/cli.py` — confirms which ML surfaces are currently public/operator-visible.
  - Test: `tests/unit/test_ml_tuning.py` — status payload keys and ML contract behavior patterns.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `GET /api/v1/ml/contract` returns `200` with a stable JSON contract document.
  - [ ] `GET /api/v1/ml/leagues/Mirage/status` returns only the agreed DTO fields and no extra internal-only keys, even when no ML runs exist yet.
  - [ ] Requesting a league outside the allowlist returns `400` with the shared JSON error envelope.
  - [ ] ClickHouse/workflow failures are translated to sanitized `503` responses.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Contract and status endpoints succeed for Mirage
    Tool: Bash
    Steps: Start the API service, call `GET /api/v1/ml/contract`, then call authenticated `GET /api/v1/ml/leagues/Mirage/status`.
    Expected: Contract route returns route/auth metadata; status route returns the agreed ML status DTO with `candidate_vs_incumbent` and `route_hotspots`, using null/empty defaults if the environment has no prior ML runs.
    Evidence: .sisyphus/evidence/task-5-ml-status.txt

  Scenario: Invalid league fails with stable client error
    Tool: Bash
    Steps: Start the API service and call authenticated `GET /api/v1/ml/leagues/Standard/status`.
    Expected: Response is `400` with a sanitized JSON error body explaining the unsupported league.
    Evidence: .sisyphus/evidence/task-5-ml-status-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add ml status routes` | Files: `poe_trade/api/*`, `tests/unit/test_api_ml_routes.py`

- [ ] 6. Add the ML predict-one endpoint with exact request validation and sanitized workflow integration

  **What to do**: Implement `POST /api/v1/ml/leagues/{league}/predict-one` as the only phase-1 write-like inference endpoint. Accept a JSON request body with exact fields: `input_format` (`poe-clipboard` only in v1), `payload` (string), and optional `output_mode` (`json` only in v1). Convert this request into the existing `predict_one` workflow invocation, then map the result into a stable response DTO with exactly these top-level keys: `league`, `route`, `price_p10`, `price_p50`, `price_p90`, `confidence_percent`, `sale_probability_percent`, `price_recommendation_eligible`, and `fallback_reason`.
  **Must NOT do**: Do not support clipboard/file/stdin transport flags over HTTP. Do not expose internal traceback or raw ClickHouse error strings.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: request validation, workflow adaptation, and public DTO behavior must be exact.
  - Skills: [] — why needed: existing workflow is already in repo.
  - Omitted: [`playwright`] — why not needed: backend-only API work.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `7,8` | Blocked By: `4`

  **References**:
  - Pattern: `poe_trade/ml/workflows.py` — `predict_one` behavior and output vocabulary.
  - Pattern: `poe_trade/ml/cli.py` — current predict-one CLI arguments to translate into HTTP request fields.
  - Test: `tests/fixtures/ml/sample_clipboard_item.txt` — canonical sample payload input.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Authenticated Mirage request with the sample clipboard payload returns `200` and the exact response DTO keys.
  - [ ] Unsupported `input_format` returns `400` before workflow execution.
  - [ ] Oversized or malformed JSON body returns `400` or `413` with the shared error envelope.
  - [ ] Workflow/backend failures map to sanitized `503` instead of leaking internals.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Predict-one succeeds for the canonical sample input
    Tool: Bash
    Steps: Start the API service, build `predict-one-request.json` from `tests/fixtures/ml/sample_clipboard_item.txt`, and call authenticated `POST /api/v1/ml/leagues/Mirage/predict-one`.
    Expected: Response is `200` and includes `route`, `price_p50`, `confidence_percent`, and `price_recommendation_eligible`.
    Evidence: .sisyphus/evidence/task-6-predict-one.txt

  Scenario: Unsupported input format is rejected
    Tool: Bash
    Steps: Start the API service and call authenticated `POST /api/v1/ml/leagues/Mirage/predict-one` with `{"input_format":"unknown","payload":"x"}`.
    Expected: Response is `400` with a stable validation error envelope.
    Evidence: .sisyphus/evidence/task-6-predict-one-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add ml predict-one route` | Files: `poe_trade/api/*`, `tests/unit/test_api_ml_routes.py`, `tests/fixtures/ml/*`

- [ ] 7. Add focused unit and service-startup coverage for the protected API foundation

  **What to do**: Add new API-focused test modules: `test_api_service.py`, `test_api_settings.py`, `test_api_auth.py`, `test_api_cors.py`, and `test_api_ml_routes.py`. Use the repo’s existing monkeypatch style to inject `Settings`, fake `ClickHouseClient`, and stub workflow returns. Include startup-path tests through the CLI service router so the API foundation is verified the same way other services are verified.
  **Must NOT do**: Do not rely on live ClickHouse or a real frontend for test coverage. Do not use manual-only verification in place of deterministic unit tests.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this task locks correctness and prevents auth/CORS drift.
  - Skills: [] — why needed: existing pytest/monkeypatch patterns are sufficient.
  - Omitted: [`protocol-compat`] — why not needed: no schema changes here.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: `8` | Blocked By: `5,6`

  **References**:
  - Test: `tests/unit/test_ml_cli.py` — CLI/service monkeypatch style.
  - Test: `tests/unit/test_market_harvester_service.py` — service startup/wiring tests.
  - Test: `tests/unit/test_settings_aliases.py` — settings parsing assertions.
  - Test: `tests/unit/test_poe_client.py` — isolated mocking of external IO.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/pytest tests/unit/test_api_settings.py tests/unit/test_api_auth.py tests/unit/test_api_cors.py tests/unit/test_api_ml_routes.py tests/unit/test_api_service.py -q` passes.
  - [ ] Tests cover happy path, missing token, wrong token, denied origin, invalid league, unsupported input format, and sanitized backend failure.
  - [ ] Service startup tests verify the CLI router can resolve the new `api` service.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Full API test suite passes
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_api_settings.py tests/unit/test_api_auth.py tests/unit/test_api_cors.py tests/unit/test_api_ml_routes.py tests/unit/test_api_service.py -q`.
    Expected: All tests pass.
    Evidence: .sisyphus/evidence/task-7-api-pytest.txt

  Scenario: Negative-path auth/CORS tests prove fail-closed behavior
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_api_auth.py tests/unit/test_api_cors.py -q`.
    Expected: Tests pass and explicitly cover missing token, wrong token, allowed origin, and denied origin cases.
    Evidence: .sisyphus/evidence/task-7-api-negative-tests.txt
  ```

  **Commit**: YES | Message: `test(api): verify protected ml api foundation` | Files: `tests/unit/test_api_*`, `poe_trade/api/*`, `poe_trade/services/api.py`

- [ ] 8. Document env vars, startup flow, and curl verification for the API foundation

  **What to do**: Update `README.md` with a short API foundation section covering exact env vars, startup command, and curl examples for `healthz`, `ml/contract`, `ml/status`, and `ml/predict-one`. Document the phase-1 non-goals explicitly so later frontend work does not assume training/report endpoints already exist.
  **Must NOT do**: Do not document browser-direct long-lived token storage as the intended production pattern. Do not claim user-auth or frontend integration is complete.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: foundation docs must be exact and operational.
  - Skills: [`docs-specialist`] — why needed: concise README diff aligned to real commands.
  - Omitted: [`frontend-ui-ux`] — why not needed: backend-only docs.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: none | Blocked By: `7`

  **References**:
  - Pattern: `README.md` — current operational command style.
  - Pattern: `poe_trade/cli.py` — service startup command surface.
  - Pattern: `poe_trade/ml/cli.py` — ML route semantics to mirror accurately.

  **Acceptance Criteria** (agent-executable only):
  - [ ] README includes the exact `POE_API_*` env vars introduced for v1.
  - [ ] README includes copy-pasteable startup and curl commands that match the implemented route table.
  - [ ] README explicitly states that phase 1 excludes training, report generation, and broad non-ML API scope.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: README API commands run as documented
    Tool: Bash
    Steps: Execute the documented API startup and curl verification commands in order.
    Expected: Commands succeed and return the documented route behavior.
    Evidence: .sisyphus/evidence/task-8-readme-api-flow.txt

  Scenario: README does not overclaim frontend readiness
    Tool: Bash
    Steps: Grep the README API section for user-auth, training-endpoint, or wildcard-CORS claims.
    Expected: Wording matches the implemented phase-1 foundation only.
    Evidence: .sisyphus/evidence/task-8-readme-api-claims.txt
  ```

  **Commit**: YES | Message: `docs(api): explain protected ml api foundation` | Files: `README.md`
## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
  - Tool: `task(subagent_type="oracle")`
  - Steps: Review implemented API files, tests, and README against this plan only.
  - Expected: Confirms route table, auth mode, CORS policy, DTO keys, and non-goals all match the plan with no omitted phase-1 guardrails.
- [ ] F2. Code Quality Review — unspecified-high
  - Tool: `task(category="unspecified-high")`
  - Steps: Review transport code, settings parsing, auth handling, and error mapping for unnecessary complexity, duplication, and unsafe branching.
  - Expected: Approves maintainability and confirms the implementation stays thin, stdlib-based, and in-process.
- [ ] F3. Real Manual QA — unspecified-high
  - Tool: `task(category="unspecified-high")`
  - Steps: Start the API service, run the documented curl checks for `healthz`, `ml/contract`, `ml/status`, and `ml/predict-one`, then run denied-auth and denied-origin checks.
  - Expected: Every documented happy path and failure path matches the plan’s HTTP contract exactly.
- [ ] F4. Scope Fidelity Check — deep
  - Tool: `task(category="deep")`
  - Steps: Inspect changed files and route table for accidental scope expansion.
  - Expected: Confirms no non-ML endpoints, no training/report endpoints, no user-auth system, no TLS in-app logic, and no framework expansion beyond the planned stdlib service.

## Commit Strategy
- Commit 1: add API service registration and inbound settings surface
- Commit 2: add HTTP transport, auth, CORS, and shared JSON/error helpers
- Commit 3: add ML contract/status endpoint vertical slice
- Commit 4: add ML predict-one endpoint vertical slice
- Commit 5: add docs and verification coverage

## Success Criteria
- The repo gains a protected API foundation without introducing a frontend dependency or broad API sprawl.
- Separate-domain frontend integration is technically viable through explicit bearer-token auth and strict CORS.
- ML API consumers receive stable DTOs instead of internal workflow payload leakage.
- The first release is safe by default because mutating and long-running ML routes remain out of scope.
