# Fix ML Pipeline: Enable Automatic Training with FX Data

## TL;DR

> **Fix the broken ML pricing pipeline by adding the missing poeninja_snapshot service and correcting a table name mismatch that prevents FX rates from being populated.**
>
> **Deliverables:**
> - Table name fix in `build_fx()` (1 line change)
> - New `poeninja_snapshot` service module with full data pipeline orchestration
> - Updated docker-compose.yml and Makefile to run the service
> - Unit tests for PoeNinjaClient and the new service
> - Documentation updates
>
> **Estimated Effort:** Medium (5-7 commits, well-scoped)
> **Parallel Execution:** NO - sequential dependency chain
> **Critical Path:** Fix table name → Create service → Add orchestration → Wire into compose

---

## Context

### Original Request
"Making the PoE ML Pricer Model actually work, train and improve fully automatically, while via API I can see all the results of recent trainings to figure out, if it improves or not."

### Diagnostic Summary
The ML system is **fully built but broken** due to a **deployment gap**:

**Root Causes Identified:**
1. **Missing orchestration**: `poeninja_snapshot` service is not defined in docker-compose.yml
2. **Table name mismatch**: `build_fx()` reads from `ml_poeninja_currency_snapshot_v1` (non-existent) instead of `raw_poeninja_currency_overview` (where snapshot writes)
3. **Missing dataset rebuild**: `train_loop` doesn't trigger data preparation; expects pre-built dataset
4. **No service registration**: `poeninja_snapshot` not in `SERVICE_NAMES` and no service module exists
5. **Zero test coverage**: PoeNinjaClient and scheduler lack unit tests

**Evidence:**
- Source items: 9.9M rows ✅
- `raw_poeninja_currency_overview`: 0 rows ❌ (FX source empty)
- `ml_fx_hour_v1`: 0 rows ❌ (built from snapshot)
- `ml_price_labels_v1`: 0 rows ❌ (normalization fails without FX)
- `ml_price_dataset_v1`: 0 rows ❌ (no training data)
- Training runs: 5,272 recorded, all `failed_gates` with `hold_no_material_improvement` ❌
- Model registry: 0 promoted models ❌
- Predictions: fallback heuristics only ❌

**Pipeline Flow (Broken):**
```
market_harvester → v_ps_items_enriched (9.9M rows)
                     ↓ (missing)
           poeninja_snapshot (SERVICE NOT RUNNING)
                     ↓
    raw_poeninja_currency_overview (EMPTY)
                     ↓
          build_fx() reads wrong table → ml_fx_hour_v1 (EMPTY)
                     ↓
     normalize_prices() fails → ml_price_labels_v1 (EMPTY)
                     ↓
        build_dataset() → ml_price_dataset_v1 (EMPTY)
                     ↓
     train_loop() → no data → models not trained → fallback predictions
```

### Metis Gap Analysis
Metis identified two additional critical issues:
1. `build_fx()` default `snapshot_table` param points to non-existent table `ml_poeninja_currency_snapshot_v1`
2. `train_loop` does not call data preparation functions; dataset must be built separately

---

## Work Objectives

### Core Objective
Restore the ML pricing pipeline to full functionality by adding the missing currency snapshot service and fixing the table name mismatch, enabling automatic model training and accurate predictions.

### Concrete Deliverables
1. **Bug fix**: Change `build_fx()` default `snapshot_table` from `ml_poeninja_currency_snapshot_v1` to `raw_poeninja_currency_overview`
2. **Service module**: Create `poe_trade/services/poeninja_snapshot.py` with FX fetch + dataset rebuild orchestration
3. **Service registration**: Add `"poeninja_snapshot"` to `SERVICE_NAMES` in `poe_trade/config/constants.py`
4. **Docker orchestration**: Add `poeninja_snapshot` service to `docker-compose.yml` and `docker-compose.qa.yml`
5. **Makefile integration**: Add to `SERVICES` variable in `Makefile`
6. **Unit tests**: Add `tests/unit/test_poeninja_snapshot.py` for client/scheduler and `tests/unit/test_service_poeninja_snapshot.py` for service module
7. **Configuration**: Add environment variables for enable flag, league, and rebuild interval
8. **Documentation**: Update `README.md` with service description and troubleshooting notes

### Definition of Done
- [ ] All unit tests pass (`pytest tests/unit`)
- [ ] CI deterministic gate passes (`make ci-smoke-cli`)
- [ ] `docker compose config` validates without errors
- [ ] Service starts successfully with `docker compose up poeninja_snapshot`
- [ ] FX data populates `raw_poeninja_currency_overview` and `ml_fx_hour_v1`
- [ ] `ml_price_dataset_v1` contains >10,000 rows for Mirage after first rebuild
- [ ] `ml_train_runs` shows subsequent training runs with `status=completed`
- [ ] `ml_model_registry_v1` contains at least one promoted model
- [ ] Predictions return non-fallback values with confidence > 0.4
- [ ] API `/automation/history` returns meaningful metrics (MDAPE < 1.0, coverage > 0.3)

### Must Have
- Table name fix in `build_fx()` is non-negotiable; without it FX data won't flow
- Service must include full dataset rebuild (not just snapshot) to unblock training
- Unit tests for previously-untested PoeNinjaClient are required for coverage
- Docker service must have proper `depends_on` ordering (clickhouse, schema_migrator)

### Must NOT Have
- No OAuth or authentication for poe.ninja (public API)
- No immediate dependency between `poeninja_snapshot` and `ml_trainer` (independent services)
- No infinite retry loops on poe.ninja failures (respect backoff)
- No changes to existing PoeNinjaClient or scheduler classes (only add service wrapper)
- No manual data bootstrap steps required (service should auto-detect and populate)

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest, CI gates, docker-compose)
- **Automated tests**: TDD (tests written alongside implementation)
- **Framework**: pytest (existing)
- **Coverage target**: 80%+ for new service module and PoeNinjaClient

### QA Policy
All tasks include agent-executed verification scenarios using Bash (curl, clickhouse-client, pytest). Evidence captured to `.sisyphus/evidence/`.

---

## Execution Strategy

### Parallel Execution Analysis
This plan is **largely sequential** due to dependencies:
- Table name fix must precede service creation (otherwise service won't work)
- Service module must precede docker-compose changes
- Tests must follow implementation

However, some tasks can be parallelized within commit batches:
- Unit tests can be written alongside implementation
- Documentation updates can happen in parallel with code changes

### Waves

```
Wave 1 (Foundation - core bug fixes)
├── Task 1: Fix build_fx() table name mismatch
└── Task 2: Add poeninja_snapshot to SERVICE_NAMES

Wave 2 (Service implementation)
├── Task 3: Create poeninja_snapshot service module
├── Task 4: Add environment variable configuration
└── Task 5: Implement full pipeline orchestration

Wave 3 (Testing)
├── Task 6: Add unit tests for PoeNinjaClient/scheduler
├── Task 7: Add unit tests for service module
└── Task 8: Verify all unit tests pass

Wave 4 (Infrastructure)
├── Task 9: Add poeninja_snapshot to docker-compose.yml
├── Task 10: Add poeninja_snapshot to docker-compose.qa.yml
├── Task 11: Add to Makefile SERVICES variable
└── Task 12: Update README.md

Wave 5 (Integration verification)
├── Task 13: Verify docker compose config
├── Task 14: Start service and check FX data population
├── Task 15: Verify dataset rebuild triggers
├── Task 16: Check training resumes with data
└── Task 17: Verify predictions improve

Wave FINAL (Independent review)
├── F1: Code quality review (linter, formatting)
├── F2: Test coverage report
└── F3: Scope fidelity check
```

**Critical Path**: Task 1 → Task 3 → Task 9 → Task 14 → Task 15 → Task 16 → Task 17

**Max Parallel**: Waves 1-2 are mostly sequential, but Tasks 6-7 can run in parallel with Task 5.

---

## TODOs

### Wave 1: Foundation

- [x] 1. Fix build_fx() default snapshot_table parameter

  **What to do**:
  - Change `build_fx()` signature line 140 from:
    `snapshot_table: str = "poe_trade.ml_poeninja_currency_snapshot_v1"`
  - To:
    `snapshot_table: str = "poe_trade.raw_poeninja_currency_overview"`
  - This aligns with where `snapshot_poeninja()` actually writes data

  **Must NOT do**:
  - Do not rename the ClickHouse table (migration already created it as `raw_poeninja_currency_overview`)
  - Do not create a view; fix the default parameter directly

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Single-line file modification with high impact
  - **Skills**: None needed beyond basic edit

  **Parallelization**:
  - **Can Run In Parallel**: NO (dependency for Task 3)
  - **Parallel Group**: Wave 1 (only task)
  - **Blocks**: Task 3, Task 9
  - **Blocked By**: None (can start immediately)

  **References**:
  - `poe_trade/ml/workflows.py:140` - the line to change
  - `schema/migrations/0032_ml_pricing_v1.sql:1-14` - shows actual table name is `raw_poeninja_currency_overview`
  - `poe_trade/ml/workflows.py:85-132` - `snapshot_poeninja()` writes to `raw_poeninja_currency_overview`

  **WHY Each Reference Matters**:
  - Workflows.py line 140: The bug location - default parameter must be corrected
  - Migration 0032: Proves the intended table name is `raw_poeninja_currency_overview`
  - snapshot_poeninja function: Shows where data is actually written

  **Acceptance Criteria**:

  **Agent-Executable Verification:**
  - [ ] Verify signature change: `python3 -c "from poe_trade.ml.workflows import build_fx; import inspect; sig = inspect.signature(build_fx); assert sig.parameters['snapshot_table'].default == 'poe_trade.raw_poeninja_currency_overview'"` returns exit code 0

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Verify build_fx() accepts correct default table name
    Tool: Bash (python3 -c)
    Preconditions: Python module importable
    Steps:
      1. Import build_fx from poe_trade.ml.workflows
      2. Inspect the snapshot_table parameter default
      3. Assert it equals 'poe_trade.raw_poeninja_currency_overview'
    Expected Result: Assertion passes, exit code 0
    Failure Indicators: Assertion error, different string value
    Evidence: .sisyphus/evidence/task-1-table-name-check.txt
  ```

  **Evidence to Capture**:
  - [ ] Output of verification command

  **Commit**: YES (standalone bug fix)
  - Message: `fix(ml): correct build_fx default snapshot_table to match actual table name`
  - Files: `poe_trade/ml/workflows.py`
  - Pre-commit: `python3 -c "from poe_trade.ml.workflows import build_fx; import inspect; sig = inspect.signature(build_fx); assert sig.parameters['snapshot_table'].default == 'poe_trade.raw_poeninja_currency_overview'"`

- [x] 2. Add poeninja_snapshot to SERVICE_NAMES in constants.py

  **What to do**:
  - Edit `poe_trade/config/constants.py`
  - Add `"poeninja_snapshot"` to the `SERVICE_NAMES` tuple
  - Keep alphabetical or logical ordering consistent with existing entries

  **Must NOT do**:
  - Do not remove or rename existing services
  - Do not change the constant's name or type

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Single-line edit in constants file
  - **Skills**: None

  **Parallelization**:
  - **Can Run In Parallel**: YES with Task 1 (no dependency)
  - **Parallel Group**: Wave 1
  - **Blocks**: CLI service invocation
  - **Blocked By**: None

  **References**:
  - `poe_trade/config/constants.py:3` - SERVICE_NAMES definition
  - `poe_trade/cli.py:87` - places where SERVICE_NAMES is used for `--name` choices

  **Acceptance Criteria**:
  - [ ] `poe_trade/config/constants.py` contains `"poeninja_snapshot"` in SERVICE_NAMES
  - [ ] CLI command `python -m poe_trade.cli service --name poeninja_snapshot -- --help` succeeds (exit 0)

  **QA Scenarios:**

  ```
  Scenario: Verify poeninja_snapshot in SERVICE_NAMES
    Tool: Bash (python3 -c)
    Steps:
      1. from poe_trade.config.constants import SERVICE_NAMES
      2. assert 'poeninja_snapshot' in SERVICE_NAMES
    Expected Result: Assertion passes, exit code 0
    Evidence: .sisyphus/evidence/task-2-service-names-check.txt
  ```

  ```
  Scenario: Verify CLI accepts poeninja_snapshot service
    Tool: Bash
    Steps:
      1. .venv/bin/python -m poe_trade.cli service --name poeninja_snapshot -- --help
    Expected Result: Exit code 0, help text prints
    Failure Indicators: Exit code 2, "invalid choice" error
    Evidence: .sisyphus/evidence/task-2-cli-help.txt
  ```

  **Commit**: YES
  - Message: `feat(ml): register poeninja_snapshot service in SERVICE_NAMES`
  - Files: `poe_trade/config/constants.py`

---

### Wave 2: Service Implementation

- [x] 3. Create poe_trade/services/poeninja_snapshot.py

  **What to do**:
  Create a new service module following the pattern of `services/market_harvester.py`:
  - Imports: `argparse`, `logging`, `time`, `json`, `ClickHouseClient`, `workflows.snapshot_poeninja`, `workflows.build_fx`, `workflows.normalize_prices`, `workflows.build_listing_events_and_labels`, `workflows.build_dataset`, `workflows.build_comps`, `config.settings`
  - Define `SERVICE_NAME = "poeninja_snapshot"`
  - Implement `_configure_logging()` (copy pattern)
  - Implement `main(argv)` with argparse:
    - `--league` (required or from config)
    - `--snapshot-table` default `poe_trade.raw_poeninja_currency_overview`
    - `--fx-table` default `poe_trade.ml_fx_hour_v1`
    - `--labels-table` default `poe_trade.ml_price_labels_v1`
    - `--dataset-table` default `poe_trade.ml_price_dataset_v1`
    - `--comps-table` default `poe_trade.ml_comps_v1`
    - `--model-dir` default `artifacts/ml/mirage_v1`
    - `--interval-seconds` default from config or 900 (15 min)
    - `--once` flag
  - Load config, check `ml_automation_enabled` (or separate `POE_ENABLE_POENINJA_SNAPSHOT`)
  - In loop:
    1. Call `snapshot_poeninja(client, league=league, output_table=snapshot_table, max_iterations=1)`
    2. Call `build_fx(client, league=league, output_table=fx_table, snapshot_table=snapshot_table)`
    3. Call `normalize_prices(client, league=league, output_table=labels_table, fx_table=fx_table)`
    4. Call `build_listing_events_and_labels(client, league=league)`
    5. Call `build_dataset(client, league=league, as_of_ts=datetime.now(UTC).isoformat(), output_table=dataset_table)`
    6. Optionally: Call `build_comps(client, league=league, dataset_table=dataset_table, output_table=comps_table)`
    7. Log summary rows written from each step
  - Sleep interval between cycles (unless `--once`)
  - Write status to `.sisyphus/state/poeninja_snapshot-last-run.json`

  **Must NOT do**:
  - Do not add OAuth or authentication
  - Do not change the imported workflow function signatures
  - Do not implement custom backoff (PoeNinjaClient handles it)
  - Do not make training decisions (this is data prep only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Boilerplate service structure, straightforward orchestration of existing functions
  - **Skills**: `python`, `logging`, `argparse`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 1 and Task 2)
  - **Parallel Group**: Wave 2 (with Tasks 4-5)
  - **Blocks**: Task 9, Task 14
  - **Blocked By**: Task 1, Task 2

  **References**:
  - `poe_trade/services/market_harvester.py` - service structure pattern
  - `poe_trade/ml/cli.py:242-249` - example of calling `snapshot_poeninja`
  - `poe_trade/ml/workflows.py:135-196` - `build_fx` function
  - `poe_trade/ml/workflows.py:198-248` - `normalize_prices` function
  - `poe_trade/ml/workflows.py:251-318` - `build_listing_events_and_labels`
  - `poe_trade/ml/workflows.py:321-451` - `build_dataset`
  - `poe_trade/ml/workflows.py:545-588` - `build_comps`

  **Acceptance Criteria**:
  - [ ] Module exists at `poe_trade/services/poeninja_snapshot.py`
  - [ ] `main()` function can be invoked via CLI
  - [ ] Service can be started with `docker-compose up poeninja_snapshot`
  - [ ] Status file written to `.sisyphus/state/poeninja_snapshot-last-run.json`

  **QA Scenarios:**

  ```
  Scenario: Service imports without error
    Tool: Bash (python3 -c)
    Steps:
      1. from poe_trade.services import poeninja_snapshot
      2. assert hasattr(poeninja_snapshot, 'main')
    Expected Result: Import succeeds, exit code 0
    Evidence: .sisyphus/evidence/task-3-import-check.txt
  ```

  ```
  Scenario: Service --help displays options
    Tool: Bash
    Steps:
      1. .venv/bin/python -m poe_trade.cli service --name poeninja_snapshot -- --help
    Expected Result: Exit 0, shows --league, --interval-seconds, --once options
    Evidence: .sisyphus/evidence/task-3-help-output.txt
  ```

  **Commit**: YES
  - Message: `feat(ml): add poeninja_snapshot service with full data pipeline orchestration`
  - Files: `poe_trade/services/poeninja_snapshot.py`
  - Pre-commit: `python3 -c "from poe_trade.services import poeninja_snapshot"`

- [x] 4. Add environment variable configuration

  **What to do**:
  - In `poe_trade/config/settings.py`, add:
    - `PoeNinjaSnapshotSettings` dataclass or add fields to existing Settings
    - `poe_enable_poeninja_snapshot: bool` default `True`
    - `poe_poeninja_snapshot_league: str | None` default `None` (falls back to `ml_automation_league`)
    - `poe_ml_dataset_rebuild_interval_seconds: int` default `900` (15 minutes)
  - Ensure these are read from environment with proper aliases
  - Service `main()` should read these settings

  **Must NOT do**:
  - Do not create duplicate configs; integrate with existing Settings pattern
  - Do not hardcode values; make them configurable via env

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Straightforward config addition following established patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES with Task 3
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 9 (service needs config to start)
  - **Blocked By**: None (can edit settings independently)

  **References**:
  - `poe_trade/config/settings.py` - existing Settings class
  - `poe_trade/config/constants.py` - existing service names

  **Acceptance Criteria**:
  - [ ] Settings class includes poeninja_snapshot flags
  - [ ] Environment variables are parsed correctly (test with test_settings)

  **QA Scenarios:**

  ```
  Scenario: Verify default settings values
    Tool: Bash (python3 -c)
    Steps:
      1. from poe_trade.config.settings import get_settings
      2. s = get_settings()
      3. assert s.poe_enable_poeninja_snapshot is True
      4. assert s.poe_ml_dataset_rebuild_interval_seconds == 900
    Expected Result: Defaults set correctly, exit 0
    Evidence: .sisyphus/evidence/task-4-settings-check.txt
  ```

  **Commit**: YES
  - Message: `feat(config): add poeninja_snapshot toggle and rebuild interval settings`
  - Files: `poe_trade/config/settings.py`

- [x] 5. Implement full pipeline orchestration in service

  **What to do**:
  In `poeninja_snapshot.py`, implement the main loop:
  - Parse args: `--league`, `--interval-seconds`, `--once`
  - Load settings, read `poe_enable_poeninja_snapshot`, `poe_poeninja_snapshot_league`, `poe_ml_dataset_rebuild_interval_seconds`
  - Validate: if `raw_poeninja_currency_overview` is empty, log warning but continue (first run will populate)
  - Loop:
    - Log start of cycle
    - `snapshot_poeninja(client, league, snapshot_table, max_iterations=1)`
    - `build_fx(client, league, fx_table, snapshot_table)`
    - `normalize_prices(client, league, labels_table, fx_table)`
    - `build_listing_events_and_labels(client, league)`
    - `build_dataset(client, league, as_of_ts=datetime.now(UTC).isoformat(), output_table=dataset_table)`
    - `build_comps(client, league, dataset_table, comps_table)`
    - Log rows written from each step (query counts from tables)
    - Write status JSON with timestamps and row counts
    - If `--once`: break, else `time.sleep(interval)`

  **Important**: The `build_dataset` function requires `as_of_ts` parameter. Use current timestamp.

  **Must NOT do**:
  - Do not skip any pipeline steps; full rebuild is required
  - Do not call `train_loop()` from here (separation of concerns)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Wiring together existing functions, straightforward control flow

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 3 code structure)
  - **Blocks**: Task 14
  - **Blocked By**: Task 3

  **References**:
  - `poe_trade/services/market_harvester.py` - logging, status file, loop structure
  - All workflow functions listed above

  **Acceptance Criteria**:
  - [ ] Service runs without errors: `python -m poe_trade.cli service --name poeninja_snapshot -- --once --league Mirage`
  - [ ] After run, `raw_poeninja_currency_overview` has rows for Mirage
  - [ ] `ml_fx_hour_v1` has rows
  - [ ] `ml_price_labels_v1` has rows
  - [ ] `ml_price_dataset_v1` has rows (>1,000)

  **QA Scenarios:**

  ```
  Scenario: Run one-shot service and populate all tables
    Tool: Bash
    Preconditions: docker compose up clickhouse, schema_migrator completed
    Steps:
      1. .venv/bin/python -m poe_trade.cli service --name poeninja_snapshot -- --once --league Mirage
    Expected Result: Exit 0, logs show rows written for each step
    Evidence: .sisyphus/evidence/task-5-one-shot-run.txt
  ```

  **Commit**: YES
  - Message: `feat(ml): implement full FX→dataset pipeline orchestration in poeninja_snapshot service`
  - Files: `poe_trade/services/poeninja_snapshot.py`

---

### Wave 3: Testing

- [x] 6. Add unit tests for PoeNinjaClient and PoeNinjaSnapshotScheduler

  **What to do**:
  Create `tests/unit/test_poeninja_snapshot.py` covering:
  - `PoeNinjaClient`:
    - `fetch_currency_overview()` success returns parsed payload
    - Handles 429 rate limit with exponential backoff
    - Handles network errors gracefully
    - Caches responses (if cache logic exists)
    - `_to_float()` and `_to_int()` helpers
  - `PoeNinjaSnapshotScheduler`:
    - League scheduling (multiple leagues)
    - Next run time calculation respects interval
    - Backoff state updates correctly
    - `record_response()` updates pacing state

  Use `unittest.mock` or `pytest-mock` to mock HTTP calls. Test that `response.stale` is set correctly based on cache headers (if applicable).

  **Must NOT do**:
  - Do not test ClickHouse integration (that's integration test, not unit)
  - Do not make real HTTP calls to poe.ninja

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` (test writing requires understanding of tested code)
  - **Reason**: Need to mock HTTP, test error handling, and validate scheduler logic

  **Parallelization**:
  - **Can Run In Parallel**: YES with Task 5 (independent)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: None (but better after client/scheduler code is stable)

  **References**:
  - `poe_trade/ingestion/poeninja_snapshot.py` - the code under test
  - Existing test patterns: `tests/unit/test_ml_*` for structure

  **Acceptance Criteria**:
  - [ ] Test file exists at `tests/unit/test_poeninja_snapshot.py`
  - [ ] `pytest tests/unit/test_poeninja_snapshot.py -v` passes (exit 0)
  - [ ] Coverage report shows >80% coverage for `poeninja_snapshot.py`

  **QA Scenarios:**

  ```
  Scenario: Run PoeNinjaClient unit tests
    Tool: Bash
    Steps:
      1. .venv/bin/pytest tests/unit/test_poeninja_snapshot.py -v
    Expected Result: All tests pass, exit 0
    Evidence: .sisyphus/evidence/task-6-unit-tests.txt
  ```

  **Commit**: YES
  - Message: `test(ml): add unit tests for PoeNinjaClient and PoeNinjaSnapshotScheduler`
  - Files: `tests/unit/test_poeninja_snapshot.py`

- [x] 7. Add unit tests for poeninja_snapshot service module

  **What to do**:
  Create `tests/unit/test_service_poeninja_snapshot.py`:
  - Test `main()` with mocked workflows
  - Verify orchestrator calls all 5 workflow functions in correct order
  - Test `--once` flag exits after one cycle
  - Test settings loading (env vars override defaults)
  - Test that status file is written with expected keys
  - Mock ClickHouse client to simulate row counts

  **Must NOT do**:
  - Do not run actual ClickHouse queries (mock client)
  - Do not test real poe.ninja API

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Reason**: Mocking orchestration flow requires careful test design

  **Parallelization**:
  - **Can Run In Parallel**: YES with Task 6
  - **Parallel Group**: Wave 3
  - **Blocks**: F2 (coverage)
  - **Blocked By**: Task 5 (service module must exist)

  **References**:
  - `tests/unit/test_service_registry.py` - pattern for testing service modules
  - `tests/unit/test_market_harvester.py` - similar service testing approach

  **Acceptance Criteria**:
  - [ ] Test file exists at `tests/unit/test_service_poeninja_snapshot.py`
  - [ ] All tests pass with `pytest -v`
  - [ ] Mock Assertions verify workflow functions called with correct args

  **QA Scenarios:**

  ```
  Scenario: Run service module unit tests
    Tool: Bash
    Steps:
      1. .venv/bin/pytest tests/unit/test_service_poeninja_snapshot.py -v
    Expected Result: Exit 0, all tests pass
    Evidence: .sisyphus/evidence/task-7-service-tests.txt
  ```

  **Commit**: YES
  - Message: `test(ml): add unit tests for poeninja_snapshot service module`
  - Files: `tests/unit/test_service_poeninja_snapshot.py`

- [x] 8. Verify all unit tests pass (including existing suite)

  **What to do**:
  Run full unit test suite to ensure no regressions:
  ```bash
  .venv/bin/pytest tests/unit -v
  ```

  **Must NOT do**:
  - Do not commit if any test fails
  - Do not skip flaky tests; fix them

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Running test suite is straightforward

  **Parallelization**:
  - **Can Run In Parallel**: NO (must wait for Tasks 6-7)
  - **Parallel Group**: Wave 3 (final task)
  - **Blocks**: Wave 4
  - **Blocked By**: Tasks 6, 7

  **Acceptance Criteria**:
  - [ ] `pytest tests/unit` returns exit code 0
  - [ ] No new failures introduced
  - [ ] Existing test coverage maintained

  **QA Scenarios:**

  ```
  Scenario: Run complete unit test suite
    Tool: Bash
    Steps:
      1. .venv/bin/pytest tests/unit --tb=short
    Expected Result: Exit 0, all tests pass
    Evidence: .sisyphus/evidence/task-8-full-test-suite.txt
  ```

  **Commit**: NO (part of verification)
  - No separate commit; this is a gate check

---

### Wave 4: Infrastructure

- [x] 9. Add poeninja_snapshot to docker-compose.yml

  **What to do**:
  Add new service section after `ml_trainer` (following same pattern):
  ```yaml
  poeninja_snapshot:
    build: .
    command: ["service", "--name", "poeninja_snapshot"]
    depends_on:
      clickhouse:
        condition: service_healthy
      schema_migrator:
        condition: service_completed_successfully
    env_file:
      - .env
    environment:
      POE_CLICKHOUSE_URL: ${POE_CLICKHOUSE_URL:-http://clickhouse:8123}
      POE_ML_AUTOMATION_LEAGUE: ${POE_ML_AUTOMATION_LEAGUE:-Mirage}
      POE_ML_DATASET_REBUILD_INTERVAL_SECONDS: ${POE_ML_DATASET_REBUILD_INTERVAL_SECONDS:-900}
    volumes:
      - ./.state:/app/.state
      - ./artifacts:/app/artifacts
    networks:
      - default
  ```

  **Must NOT do**:
  - Do not add ports (no external exposure needed)
  - Do not add OAuth secrets (not needed)
  - Do not make it depend on ml_trainer (independent)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Copy-paste from existing service definition with minor tweaks

  **Parallelization**:
  - **Can Run In Parallel**: YES with Tasks 6-8 (independent)
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 14 (docker deployment)
  - **Blocked By**: Task 1 (code must exist), Task 2 (SERVICE_NAMES)

  **References**:
  - `docker-compose.yml:102-125` (ml_trainer service as template)
  - `poe_trade/config/constants.py` - SERVICE_NAMES must include the service

  **Acceptance Criteria**:
  - [ ] `docker-compose config --services` includes `poeninja_snapshot`
  - [ ] `grep -A12 'poeninja_snapshot:' docker-compose.yml` shows correct depends_on

  **QA Scenarios:**

  ```
  Scenario: Validate docker-compose configuration
    Tool: Bash
    Steps:
      1. docker compose config --services | grep poeninja_snapshot
    Expected Result: Outputs 'poeninja_snapshot' line, exit 0
    Evidence: .sisyphus/evidence/task-9-compose-config.txt
  ```

  **Commit**: YES
  - Message: `feat(infra): add poeninja_snapshot service to docker-compose.yml`
  - Files: `docker-compose.yml`

- [x] 10. Add poeninja_snapshot to docker-compose.qa.yml

  **What to do**:
  Ensure QA override includes the service. Usually QA extends base compose, but verify the service is included when using `-f docker-compose.qa.yml`. May need to add explicit service definition or ensure it inherits from base.

  Check `docker-compose.qa.yml` content and add service if missing, or ensure it's not excluded by overrides.

  **Must NOT do**:
  - Do not change service behavior in QA (use same image, command)
  - Do not add test-only dependencies that don't exist in production

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Reason**: Simple copy/addition

  **Parallelization**:
  - **Can Run In Parallel**: YES with Task 9
  - **Blocked By**: Task 9

  **Acceptance Criteria**:
  - [ ] `docker compose -f docker-compose.yml -f docker-compose.qa.yml config --services | grep poeninja_snapshot` succeeds

  **QA Scenarios:**

  ```
  Scenario: Validate QA docker-compose includes service
    Tool: Bash
    Steps:
      1. docker compose -f docker-compose.yml -f docker-compose.qa.yml config --services | grep poeninja_snapshot
    Expected Result: Service listed, exit 0
    Evidence: .sisyphus/evidence/task-10-qa-compose.txt
  ```

  **Commit**: YES
  - Message: `feat(infra): add poeninja_snapshot to QA docker-compose configuration`
  - Files: `docker-compose.qa.yml`

- [x] 11. Add poeninja_snapshot to Makefile SERVICES variable

  **What to do**:
  Edit `Makefile` (likely line with `SERVICES ?= ...`) to include `poeninja_snapshot` in the list.

  **Must NOT do**:
  - Do not break existing make targets

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES with Tasks 9-10
  - **Blocked By**: Task 2 (SERVICE_NAMES must match)

  **References**:
  - `Makefile:5` - SERVICES variable definition

  **Acceptance Criteria**:
  - [ ] `grep SERVICES Makefile` shows `poeninja_snapshot` in the list

  **QA Scenarios:**

  ```
  Scenario: Verify Makefile includes service
    Tool: Bash (grep)
    Steps:
      1. grep -E 'SERVICES.*poeninja_snapshot' Makefile
    Expected Result: Match found, exit 0
    Evidence: .sisyphus/evidence/task-11-makefile-check.txt
  ```

  **Commit**: YES
  - Message: `feat(infra): add poeninja_snapshot to Makefile SERVICES`
  - Files: `Makefile`

- [x] 12. Update README.md

  **What to do**:
  Add section describing the new service:
  - What it does (FX snapshots + dataset rebuild)
  - Default interval (900s)
  - Environment variables
  - Troubleshooting: Check logs if dataset not populating
  - Update "ML Quick Start" to mention that dataset is now auto-rebuilt

  **Must NOT do**:
  - Do not remove existing documentation
  - Do not document internal implementation details

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Reason**: Documentation requires clear, concise description

  **Parallelization**:
  - **Can Run In Parallel**: YES with Tasks 9-11
  - **Blocked By**: Task 5 (understand service behavior)

  **References**:
  - `README.md` - existing structure
  - `docs/ops-runbook.md` - may also need updates

  **Acceptance Criteria**:
  - [ ] README mentions `poeninja_snapshot` service
  - [ ] Environment variables documented
  - [ ] Service description accurate

  **QA Scenarios:**

  ```
  Scenario: Verify README contains poeninja_snapshot section
    Tool: Bash (grep)
    Steps:
      1. grep -q 'poeninja_snapshot' README.md
    Expected Result: Match found, exit 0
    Evidence: .sisyphus/evidence/task-12-readme-check.txt
  ```

  **Commit**: YES
  - Message: `docs: add poeninja_snapshot service documentation`
  - Files: `README.md`

---

### Wave 5: Integration Verification

- [ ] 13. Verify docker compose configuration

  **What to do**:
  Run:
  ```bash
  docker compose config
  ```
  Check for errors, validate all services defined.

  **Must NOT do**:
  - Do not proceed if config invalid

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: NO (post-deployment)
  - **Blocked By**: Tasks 9-12

  **Acceptance Criteria**:
  - [ ] `docker compose config` exits 0 with no errors

  **QA Scenarios:**

  ```
  Scenario: Validate docker-compose configuration
    Tool: Bash
    Steps:
      1. docker compose config > /dev/null
    Expected Result: Exit 0, no output
    Evidence: .sisyphus/evidence/task-13-docker-config.txt
  ```

  **Commit**: NO

- [ ] 14. Start service and check FX data population

  **What to do**:
  ```bash
  docker compose up -d poeninja_snapshot
  docker compose logs -f poeninja_snapshot  # watch for completion
  ```
  Then query ClickHouse:
  ```bash
  docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.raw_poeninja_currency_overview WHERE league='Mirage'"
  docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.ml_fx_hour_v1 WHERE league='Mirage'"
  ```

  **Expected**: Both queries return >0 rows (at least 1 snapshot, FX rates for multiple currencies)

  **Must NOT do**:
  - Do not proceed if counts are 0

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` (deployment debugging)
  - **Reason**: May need to troubleshoot logs, retry, check network

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocked By**: Task 13

  **Acceptance Criteria**:
  - [ ] `raw_poeninja_currency_overview` count > 0 for Mirage
  - [ ] `ml_fx_hour_v1` count > 0 for Mirage
  - [ ] Service logs show successful completion

  **QA Scenarios:**

  ```
  Scenario: Verify FX data populated after service run
    Tool: Bash
    Steps:
      1. docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.raw_poeninja_currency_overview WHERE league='Mirage' FORMAT TSV"
      2. docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.ml_fx_hour_v1 WHERE league='Mirage' FORMAT TSV"
    Expected Result: Both counts > 0
    Evidence: .sisyphus/evidence/task-14-fx-population.txt
  ```

  **Commit**: NO (verification)

- [ ] 15. Verify dataset rebuild triggers

  **What to do**:
  After FX data is present, service should continue to rebuild dataset. Check:
  ```bash
  docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_labels_v1 WHERE league='Mirage'"
  docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_dataset_v1 WHERE league='Mirage'"
  ```

  **Expected**: Both >10,000 rows (depending on market data volume)

  **Must NOT do**:
  - Do not accept empty tables

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocked By**: Task 14

  **Acceptance Criteria**:
  - [ ] `ml_price_labels_v1` count > 10,000
  - [ ] `ml_price_dataset_v1` count > 10,000
  - [ ] Coverage ratio (supported/total) > 0.5

  **QA Scenarios:**

  ```
  Scenario: Verify dataset rebuilt successfully
    Tool: Bash
    Steps:
      1. docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_dataset_v1 WHERE league='Mirage' FORMAT TSV"
    Expected Result: Count > 10000
    Evidence: .sisyphus/evidence/task-15-dataset-count.txt
  ```

  **Commit**: NO

- [ ] 16. Check training resumes with data

  **What to do**:
  The ml_trainer should now produce successful runs. Check after next cycle:
  ```bash
  docker compose logs ml_trainer | tail -20
  docker compose exec clickhouse clickhouse-client --query "SELECT run_id, status, stop_reason FROM poe_trade.ml_train_runs WHERE league='Mirage' ORDER BY updated_at DESC LIMIT 1 FORMAT JSON"
  ```

  **Expected**: Status should be `completed` or `stopped_budget` (not `failed_gates` or `stopped_no_improvement` due to no data). Stop reason could be `iteration_budget_exhausted` or `wall_clock_budget_exhausted` which are normal completions.

  **Must NOT do**:
  - Do not confuse "completed but no improvement" with "failed due to no data". With data present, models should train and metrics should be finite numbers.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocked By**: Task 15

  **Acceptance Criteria**:
  - [ ] Latest training run status is either `completed` or `stopped_budget`
  - [ ] `ml_eval_runs` contains entries for the run with `mdape` < 1.0 and `sample_count` > 0
  - [ ] No more `failed_gates` due to missing data

  **QA Scenarios:**

  ```
  Scenario: Verify training runs succeed with data
    Tool: Bash
    Steps:
      1. docker compose exec clickhouse clickhouse-client --query "SELECT status, stop_reason FROM poe_trade.ml_train_runs WHERE league='Mirage' ORDER BY updated_at DESC LIMIT 1 FORMAT JSON"
    Expected Result: status in ('completed', 'stopped_budget'), stop_reason meaningful
    Evidence: .sisyphus/evidence/task-16-training-status.txt
  ```

  **Commit**: NO

- [ ] 17. Verify predictions improve

  **What to do**:
  Call prediction API to see if model produces real values:
  ```bash
  curl -H "Authorization: Bearer $TOKEN" -H "Origin: https://poe.lama-lan.ch" -X POST -H "Content-Type: application/json" --data '{"input_format":"poe-clipboard","payload":"Item Class: Maps\nRarity: Rare\nGrim Veil\nCemetery Map"}' https://api.poe.lama-lan.ch/api/v1/ml/leagues/Mirage/predict-one
  ```
  (Use appropriate token from .env)

  Check response:
  - `route` should be one of the trained routes (not `fallback_abstain` if data sufficient)
  - `price_p50` should be a reasonable number (not absurdly high/low)
  - `confidence` should be > 0.2 (non-zero)
  - `fallback_reason` should be empty

  **Must NOT do**:
  - Do not accept fallback predictions as "good enough"

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocked By**: Task 16

  **Acceptance Criteria**:
  - [ ] At least one prediction returns non-fallback route
  - [ ] Confidence > 0.2 for structured/boosted routes
  - [ ] Prices are within plausible PoE economy ranges (1-10000 chaos for maps)

  **QA Scenarios:**

  ```
  Scenario: Verify ML predictions use trained models
    Tool: Bash (curl)
    Preconditions: API running, token available
    Steps:
      1. curl -s -H "Authorization: Bearer $TOKEN" -H "Origin: https://poe.lama-lan.ch" -X POST -H "Content-Type: application/json" --data '{"input_format":"poe-clipboard","payload":"Item Class: Maps\nRarity: Rare\nGrim Veil\nCemetery Map"}' https://api.poe.lama-lan.ch/api/v1/ml/leagues/Mirage/predict-one | python3 -m json.tool
    Expected Result: JSON contains route not equal to 'fallback_abstain', price_p50 is number > 0
    Evidence: .sisyphus/evidence/task-17-prediction-sample.json
  ```

  **Commit**: NO

---

### Wave FINAL: Independent Review

- [x] F1. Code quality review

  **What to do**:
  - Run linter: `.venv/bin/ruff check poe_trade/services/poeninja_snapshot.py`
  - Check formatting: `.venv/bin/black --check poe_trade/services/poeninja_snapshot.py`
  - Verify type hints are present
  - Ensure no `print()` statements (use `logging`)

  **Acceptance**:
  - [ ] Linter passes (exit 0)
  - [ ] Formatting OK
  - [ ] No critical issues

- [x] F2. Test coverage report

  **What to do**:
  Run coverage:
  ```bash
  .venv/bin/pytest tests/unit/test_poeninja_snapshot.py tests/unit/test_service_poeninja_snapshot.py --cov=poe_trade.services.poeninja_snapshot --cov-report=term-missing
  ```
  Verify >80% coverage.

  **Acceptance**:
  - [ ] Coverage report shows >=80% for new module
  - [ ] All lines in critical paths covered

- [x] F3. Scope fidelity check

  **What to do**:
  Verify all "Must Have" deliverables are present in codebase:
  - Table name fix exists in workflows.py
  - Service module exists
  - SERVICE_NAMES updated
  - Docker files updated
  - Tests exist
  - Docs updated

  **Acceptance**:
  - [ ] Every deliverable accounted for
  - [ ] No scope creep (no changes to ml_trainer or other services)

---

## Commit Strategy

1. `fix(ml): correct build_fx default snapshot_table to match actual table name`
   - `poe_trade/ml/workflows.py`

2. `feat(ml): register poeninja_snapshot service in SERVICE_NAMES`
   - `poe_trade/config/constants.py`

3. `feat(ml): add poeninja_snapshot service with full data pipeline orchestration`
   - `poe_trade/services/poeninja_snapshot.py`

4. `feat(config): add poeninja_snapshot toggle and rebuild interval settings`
   - `poe_trade/config/settings.py`

5. `test(ml): add unit tests for PoeNinjaClient and PoeNinjaSnapshotScheduler`
   - `tests/unit/test_poeninja_snapshot.py`

6. `test(ml): add unit tests for poeninja_snapshot service module`
   - `tests/unit/test_service_poeninja_snapshot.py`

7. `feat(infra): add poeninja_snapshot service to docker-compose.yml`
   - `docker-compose.yml`

8. `feat(infra): add poeninja_snapshot to QA docker-compose configuration`
   - `docker-compose.qa.yml`

9. `feat(infra): add poeninja_snapshot to Makefile SERVICES`
   - `Makefile`

10. `docs: add poeninja_snapshot service documentation`
    - `README.md`

---

## Success Criteria

### Verification Commands (ALL must pass)
```bash
# 1. Table name fix
python3 -c "from poe_trade.ml.workflows import build_fx; import inspect; assert inspect.signature(build_fx).parameters['snapshot_table'].default == 'poe_trade.raw_poeninja_currency_overview'"

# 2. Service registration
python3 -c "from poe_trade.config.constants import SERVICE_NAMES; assert 'poeninja_snapshot' in SERVICE_NAMES"

# 3. CLI help
.venv/bin/python -m poe_trade.cli service --name poeninja_snapshot -- --help

# 4. Docker config
docker compose config --services | grep poeninja_snapshot

# 5. QA compose
docker compose -f docker-compose.yml -f docker-compose.qa.yml --env-file .env.qa.example config --services | grep poeninja_snapshot

# 6. Unit tests
.venv/bin/pytest tests/unit/test_poeninja_snapshot.py tests/unit/test_service_poeninja_snapshot.py -v

# 7. Full test suite
.venv/bin/pytest tests/unit --tb=short

# 8. CI smoke
make ci-smoke-cli

# 9. Makefile
grep -q 'poeninja_snapshot' Makefile

# After deployment:
# 10. FX population
docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.raw_poeninja_currency_overview WHERE league='Mirage' FORMAT TSV" | grep -qv '^0$'
docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.ml_fx_hour_v1 WHERE league='Mirage' FORMAT TSV" | grep -qv '^0$'

# 11. Dataset population
docker compose exec clickhouse clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_dataset_v1 WHERE league='Mirage' FORMAT TSV" | grep -q '[1-9][0-9][0-9][0-9]'  # >= 1000

# 12. Training success
docker compose exec clickhouse clickhouse-client --query "SELECT status FROM poe_trade.ml_train_runs WHERE league='Mirage' ORDER BY updated_at DESC LIMIT 1 FORMAT TSV" | grep -E '^(completed|stopped_budget)$'

# 13. Predictions non-fallback
curl -s -H "Authorization: Bearer $TOKEN" -H "Origin: https://poe.lama-lan.ch" -X POST -H "Content-Type: application/json" --data '{"input_format":"poe-clipboard","payload":"Item Class: Maps\nRarity: Rare\nGrim Veil\nCemetery Map"}' https://api.poe.lama-lan.ch/api/v1/ml/leagues/Mirage/predict-one | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('route') != 'fallback_abstain', 'still using fallback'; assert d.get('price_p50',0) > 0, 'no price'"
```

### Final Checklist
- [ ] All code committed and pushed
- [ ] All tests pass locally and in CI
- [ ] Docker config validated
- [ ] Service starts successfully in docker-compose
- [ ] FX data populates within 2 minutes of service start
- [ ] Dataset rebuilds within 5 minutes of FX population
- [ ] Training produces completed runs with valid metrics
- [ ] Model registry shows promoted models
- [ ] API predictions show confidence > 0.2 and non-fallback routes
- [ ] Dashboard displays non-zero metrics for ML performance
