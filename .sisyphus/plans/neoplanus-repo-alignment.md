# NeoPlanus Repo Alignment Plan

## TL;DR
> **Summary**: Align the repo with `NeoPlanus.md` by replacing the current league-scoped, file-checkpointed PSAPI harvester with a unified ClickHouse-native sync daemon, then rebuilding silver/current-state/gold analytics, strategy packs, scanner, journal, and CLI surfaces around official PSAPI/CXAPI constraints.
> **Deliverables**:
> - Unified `market_harvester` daemon with `psapi:<realm>` and `cxapi:<realm>` queues and ClickHouse-only checkpoint state
> - Additive migration set for corrected bronze telemetry/CX storage plus NeoPlanus silver/current-state/gold layers
> - SQL-first refresh/backtest/strategy runtime with strategy packs, scanner, alert suppression, journal, and CLI/reporting flows
> - Updated tests, sanity SQL, `.env.example`, `README.md`, and `docs/ops-runbook.md` matching the shipped runtime
> **Effort**: XL
> **Parallel**: YES - 6 waves
> **Critical Path**: 1 -> 2 -> 7 -> 8/9 -> 11/12/14 -> 15/16/17 -> 18/19/20 -> 21/23/24 -> 26/27/28/29/30

## Context
### Original Request
Create a work plan using `NeoPlanus.md` as the foundation, making sure every part of that document is covered and compared against what already exists in the repo.

### Interview Summary
- No blocking ambiguities remained after repo exploration, so the plan proceeds directly from the documented target architecture plus live repo facts.
- Default test strategy is `tests-after`: reuse the current `pytest` unit suite, add targeted unit coverage for refactors, and require agent-executed CLI/SQL verification after each task.
- Compatibility is preserved only at the operator boundary: keep `poe-ledger-cli service --name market_harvester`, the `market_harvester` console script, and core `--once` / `--dry-run` behaviors, while deliberately replacing legacy runtime semantics that encode the wrong ingest model.

### Metis Review (gaps addressed)
- Treat `schema/migrations/0003_silver.sql`, `schema/migrations/0004_gold.sql`, and related older docs as historical context only; `schema/migrations/0018_cleanup_unused_objects.sql` removed many of those objects, so they are not evidence of shipped capability.
- Separate compatibility cleanup from new capability work so implementers do not assume `bronze_trade_metadata`, dropped views, or old liquidity objects remain part of the new core path.
- Add explicit acceptance gates for clean-install migrations, upgrade-path migrations, restart/resume without checkpoint files, documented API parameter correctness, and docs/sanity sweep.

## Work Objectives
### Core Objective
Transform the repo from an ingestion-focused, threaded PSAPI collector into the private ClickHouse-native trading intelligence engine described in `NeoPlanus.md`, without leaving any runtime or data-contract ambiguity for the implementer.

### Deliverables
- Cutover-safe ingest contract for realm-scoped PSAPI and hourly CXAPI queues
- Updated Python orchestration modules for OAuth, queue scheduling, PSAPI sync, CXAPI sync, refresh execution, strategy runtime, scanner, journal, and reporting
- New SQL assets for silver/current-state/gold/strategy/backtest layers
- Strategy packs covering NeoPlanus priority ladders and advanced follow-on packs
- Updated verification surface: tests, sanity SQL, CLI commands, docs, and dependency cleanup

### Definition of Done (verifiable conditions with commands)
- `poe-migrate --status --dry-run` reports the full migration set without checksum mismatch or pending compatibility surprises on both clean and upgraded databases.
- `.venv/bin/pytest tests/unit` passes with added coverage for scheduler, PSAPI, CXAPI, settings, migrations, strategies, scanner, journal, and CLI surfaces.
- `.venv/bin/python -m poe_trade.cli --help` and `.venv/bin/python -m poe_trade.cli service --name market_harvester -- --help` expose the final CLI surface described in the plan.
- `clickhouse-client --multiquery < schema/sanity/bronze.sql`, `clickhouse-client --multiquery < schema/sanity/silver.sql`, and `clickhouse-client --multiquery < schema/sanity/gold.sql` pass against an upgraded database.
- A restart test proves daemon resume uses ClickHouse checkpoints only and no filesystem cursor state is required.

### Must Have
- One private daemon, one durable store (ClickHouse), CLI-first operation, SQL-first analytics, and official-API-only ingestion
- PSAPI uses documented realm paths with no `league` query parameter; CXAPI normal mode always uses explicit hour ids
- ClickHouse checkpoint history is the only canonical cursor source; file checkpoints are fully removed from runtime semantics
- Silver/current-state and gold layers match NeoPlanus object intent rather than reviving obsolete analytics models
- Strategy logic lives in SQL packs plus small TOML metadata, with optional Python evaluators only for clearly bounded advanced cases

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No Redis, Postgres, Kafka, Airflow, Dagster, dbt, generic ETL layer, web UI, or strategy DSL
- No undocumented `api/trade/data/*` dependency in the core design
- No analytics that treat legacy per-league bronze rows as if they were valid realm-scoped v2 rows after cutover
- No hidden destructive schema rewrites; any required rebuild must be explicit, staged, and documented like `schema/migrations/0021_raw_public_stash_pages_nullable_league.sql`
- No docs, sanity SQL, or tests that keep checkpoint files, dropped views, or obsolete flags alive by accident

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: tests-after + `pytest` unit coverage, CLI verification, and ClickHouse sanity SQL
- QA policy: Every task includes happy-path and failure-path agent-executed scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: ingest contract, telemetry schema, grants/sanity, config, dependency/layout cleanup
Wave 2: OAuth/client/checkpoint adapter/scheduler/PSAPI/CXAPI core
Wave 3: silver/current-state/CX silver/refresh execution
Wave 4: gold marts, strategy runtime, backtests, CLI/report surfaces
Wave 5: strategy packs, scanner, journal, docs/test sweeps
Wave 6: advanced packs, rebuild/retention tooling, SQL CI, final compatibility cleanup

### Dependency Matrix (full, all tasks)
| Task | Depends On |
|---|---|
| 1 | - |
| 2 | 1 |
| 3 | 2 |
| 4 | 1 |
| 5 | 1 |
| 6 | 4 |
| 7 | 2,4 |
| 8 | 6,7 |
| 9 | 6,7 |
| 10 | 2,6,7,8 |
| 11 | 2,9 |
| 12 | 2,9 |
| 13 | 11,12 |
| 14 | 2,10 |
| 15 | 5,11,12,13,14 |
| 16 | 14,15 |
| 17 | 13,15 |
| 18 | 5,15 |
| 19 | 15,16,17,18 |
| 20 | 15,18 |
| 21 | 16,17,18,19,20 |
| 22 | 16,17,18,19,20 |
| 23 | 16,17,18,19,20,21 |
| 24 | 19,20,23 |
| 25 | 21,22,23,24 |
| 26 | 19,21,22,23,24 |
| 27 | 15,16,17,18,19,20,21,22,23,24 |
| 28 | 15,16,17,18,19,20,21,22,23,24 |
| 29 | 27,28 |
| 30 | 25,26,27,28,29 |

### Agent Dispatch Summary
| Wave | Task Count | Categories |
|---|---:|---|
| Wave 1 | 5 | deep, protocol-compat, writing, quick |
| Wave 2 | 5 | deep, unspecified-high, quick |
| Wave 3 | 5 | protocol-compat, deep, quick |
| Wave 4 | 5 | deep, unspecified-high, writing |
| Wave 5 | 5 | deep, unspecified-high, writing |
| Wave 6 | 5 | deep, ultrabrain, writing, quick |

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Lock the v2 ingest contract and legacy cutover boundary

  **What to do**: Add a single shared contract definition for NeoPlanus runtime semantics: `psapi:<realm>` / `cxapi:<realm>` queue keys, `feed_kind`, a hard v2 contract marker, and a bounded legacy-handling rule so pre-cutover per-league rows are never read as valid realm-scoped v2 data. Implement this as shared constants/types plus a documented cutoff strategy used by migrations, sync code, refresh SQL, and tests.
  **Must NOT do**: Do not rely on implicit timestamps, ad hoc string parsing, or comments-only guidance; the contract must be machine-readable and imported by runtime code.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this defines the compatibility boundary for every later task.
  - Skills: [`protocol-compat`] — enforce explicit additive-vs-rebuild thinking for contract evolution.
  - Omitted: [`docs-specialist`] — docs update comes later after code and schema settle.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2,4,7,8,9,11,12,13,14,15,27,28,29,30 | Blocked By: none

  **References**:
  - Pattern: `poe_trade/config/constants.py:3` — current service/runtime constants live here.
  - Pattern: `poe_trade/ingestion/market_harvester.py:146` — current checkpoint key still encodes `realm:league`.
  - Pattern: `poe_trade/ingestion/market_harvester.py:467` — current runtime keying is per-league.
  - Pattern: `NeoPlanus.md:104` — PSAPI must become one queue per realm.
  - Pattern: `NeoPlanus.md:288` — ClickHouse checkpoints are canonical.
  - Pattern: `NeoPlanus.md:679` — queue-key-based checkpoint query is the target contract.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `rg -n "queue_key|feed_kind|contract" poe_trade/config poe_trade/ingestion schema/migrations` shows one shared contract vocabulary reused across code and migrations.
  - [ ] `.venv/bin/pytest tests/unit/test_service_registry.py tests/unit/test_settings_aliases.py` passes with contract-aware defaults and without reintroducing per-league runtime semantics.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path contract resolution
    Tool: Bash
    Steps: Run `rg -n "psapi:|cxapi:|feed_kind|contract" poe_trade/config poe_trade/ingestion schema/migrations`.
    Expected: Results show explicit queue-key/feed-kind constants and no ambiguity about the active ingest contract.
    Evidence: .sisyphus/evidence/task-1-ingest-contract.txt

  Scenario: Failure path legacy ambiguity prevented
    Tool: Bash
    Steps: Run `rg -n "realm:league|POE_LEAGUES.*runtime|CheckpointStore.*canonical" poe_trade tests README.md docs`.
    Expected: No result claims legacy `realm:league` or file checkpoints are the canonical runtime contract after the task changes.
    Evidence: .sisyphus/evidence/task-1-ingest-contract-error.txt
  ```

  **Commit**: YES | Message: `refactor(ingest): codify v2 queue contract` | Files: `poe_trade/config/constants.py`, `poe_trade/ingestion/`, `tests/unit/`

- [ ] 2. Evolve bronze telemetry schema for queue-based ClickHouse state

  **What to do**: Add the next migration(s) to evolve `poe_trade.bronze_ingest_checkpoints`, `poe_trade.bronze_requests`, and `poe_trade.poe_ingest_status` for NeoPlanus by introducing `queue_key`, `feed_kind`, explicit contract versioning, and nullable `league` where needed. If physical layout or nullability changes cannot stay additive, use an explicit shadow-table rebuild pattern and preserve upgrade safety for an existing database.
  **Must NOT do**: Do not mutate historical migration files or hide a rebuild inside a migration that looks additive.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the highest-risk schema cutover in the plan.
  - Skills: [`protocol-compat`] — needed for additive migration discipline and downgrade thinking.
  - Omitted: [`git-master`] — no git work required during implementation.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 3,7,8,9,10,27,28 | Blocked By: 1

  **References**:
  - Pattern: `schema/migrations/0008_bronze_ingest_metadata.sql:1` — current checkpoint schema lacks `queue_key` / `feed_kind`.
  - Pattern: `schema/migrations/0016_ops_reliability_artifacts.sql:33` — current request telemetry schema already tolerates nullable realm/league.
  - Pattern: `schema/migrations/0006_ops.sql:1` — current status table is league-partitioned and ingest-only.
  - Pattern: `schema/migrations/0021_raw_public_stash_pages_nullable_league.sql:4` — explicit rebuild precedent to follow if nullability/order keys force it.
  - Pattern: `NeoPlanus.md:316` — recommended telemetry adjustments include nullable `league` and `queue_key`.
  - Pattern: `NeoPlanus.md:709` — add `queue_key`, nullable `league`, and `feed_kind` to status reporting.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-migrate --status --dry-run` lists the new migration(s) in order with no checksum mismatch.
  - [ ] `rg -n "queue_key|feed_kind|Nullable\(String\)|contract" schema/migrations` shows the new telemetry contract in the migration set.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path migration discovery
    Tool: Bash
    Steps: Run `poe-migrate --status --dry-run`.
    Expected: The next migration numbers are discovered cleanly and describe queue-based telemetry evolution.
    Evidence: .sisyphus/evidence/task-2-telemetry-migrations.txt

  Scenario: Failure path rebuild explicitness
    Tool: Bash
    Steps: Run `rg -n "RENAME TABLE|shadow|backup" schema/migrations`.
    Expected: If a rebuild is required, the migration explicitly uses a shadow/backup flow rather than a silent in-place destructive change.
    Evidence: .sisyphus/evidence/task-2-telemetry-migrations-error.txt
  ```

  **Commit**: YES | Message: `feat(schema): add queue-based ingest telemetry` | Files: `schema/migrations/*.sql`

- [ ] 3. Refresh grants and sanity SQL for the new bronze contract

  **What to do**: Add/update migration grants for any recreated tables/views and rewrite `schema/sanity/*.sql` so they validate the new queue-based bronze state instead of dropped views, legacy checkpoint files, or pre-NeoPlanus assumptions. Include explicit bronze sanity for PSAPI queue freshness, CXAPI queue freshness, request telemetry, and status rows.
  **Must NOT do**: Do not leave grants implicit or let sanity SQL keep querying dropped objects like `v_ops_ingest_health` or `raw_account_stash_snapshot` as core runtime evidence.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: constrained SQL updates once the telemetry schema is settled.
  - Skills: [`protocol-compat`] — keeps grants/data-contract surface safe.
  - Omitted: [`docs-specialist`] — this task is SQL-only.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 27,29 | Blocked By: 2

  **References**:
  - Pattern: `schema/migrations/0007_roles_and_grants.sql:7` — old grants referenced dropped `raw_currency_exchange_hour`.
  - Pattern: `schema/migrations/0018_cleanup_unused_objects.sql:33` — old CX table was dropped.
  - Pattern: `schema/sanity/bronze.sql:10` — current sanity SQL still references legacy objects.
  - Pattern: `docs/ops-runbook.md:11` — runbook still names `v_ops_ingest_health` as live evidence.
  - Pattern: `NeoPlanus.md:305` — bronze schema and telemetry are part of the target architecture.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `clickhouse-client --multiquery < schema/sanity/bronze.sql` is valid against the target schema and no longer relies on dropped objects.
  - [ ] `rg -n "GRANT .*raw_currency_exchange_hour|v_ops_ingest_health|raw_account_stash_snapshot" schema docs README.md` shows only intended compatibility references, not stale core-runtime guidance.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path sanity sweep
    Tool: Bash
    Steps: Run `clickhouse-client --multiquery < schema/sanity/bronze.sql` against the target environment or test fixture DB.
    Expected: The script executes without referencing dropped views/tables as required runtime proof.
    Evidence: .sisyphus/evidence/task-3-bronze-sanity.txt

  Scenario: Failure path stale grant detection
    Tool: Bash
    Steps: Run `rg -n "raw_currency_exchange_hour|v_ops_ingest_health|raw_account_stash_snapshot" schema/migrations schema/sanity README.md docs/ops-runbook.md`.
    Expected: Any remaining references are explicitly compatibility-only or removed from core guidance.
    Evidence: .sisyphus/evidence/task-3-bronze-sanity-error.txt
  ```

  **Commit**: YES | Message: `chore(schema): align grants and sanity checks` | Files: `schema/migrations/*.sql`, `schema/sanity/*.sql`

- [ ] 4. Replace the runtime env/config surface with NeoPlanus controls

  **What to do**: Refactor `Settings` and constants so runtime config pivots from `POE_LEAGUES`, checkpoint directories, and bootstrap flags to NeoPlanus controls: `POE_REALMS`, `POE_ENABLE_PSAPI`, `POE_ENABLE_CXAPI`, PSAPI polling cadence, CX backfill hours/hour offset, refresh cadence, scan cadence, and TTLs. Keep backward-compatible parsing only long enough to emit deprecation warnings or hard failures that prevent legacy variables from silently changing runtime semantics.
  **Must NOT do**: Do not let `POE_LEAGUES`, `POE_CHECKPOINT_DIR`, or bootstrap flags continue to drive daemon behavior.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: config changes affect every service, test, and operator workflow.
  - Skills: [] — no special skill beyond repo-specific context.
  - Omitted: [`protocol-compat`] — schema already handled elsewhere.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6,7,27,29 | Blocked By: 1

  **References**:
  - Pattern: `poe_trade/config/settings.py:167` — current settings still load `POE_LEAGUES`, checkpoint dirs, and bootstrap flags.
  - Pattern: `poe_trade/config/constants.py:7` — current defaults still center on leagues and checkpoint directories.
  - Pattern: `.env.example:6` — example env still exposes file checkpoints and `POE_LEAGUES` as runtime knobs.
  - Pattern: `NeoPlanus.md:1207` — target config surface replaces old ingest settings.
  - Pattern: `NeoPlanus.md:1232` — concrete recommended env variables to adopt.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/pytest tests/unit/test_settings_aliases.py` passes with new defaults/deprecation handling.
  - [ ] `rg -n "POE_LEAGUES|POE_CHECKPOINT_DIR|POE_CURSOR_DIR|POE_STASH_BOOTSTRAP" poe_trade .env.example README.md docs tests` shows only compatibility/deprecation references, not active runtime guidance.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path NeoPlanus env load
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_settings_aliases.py` and inspect settings-related output.
    Expected: Tests confirm the new env surface loads correctly and legacy aliases are handled deliberately.
    Evidence: .sisyphus/evidence/task-4-config-surface.txt

  Scenario: Failure path legacy env misuse blocked
    Tool: Bash
    Steps: Run `rg -n "POE_LEAGUES|POE_CHECKPOINT_DIR|POE_CURSOR_DIR|POE_STASH_BOOTSTRAP" poe_trade .env.example README.md docs tests`.
    Expected: Legacy variables appear only in explicit deprecation/error handling or migration notes.
    Evidence: .sisyphus/evidence/task-4-config-surface-error.txt
  ```

  **Commit**: YES | Message: `refactor(config): adopt queue-based runtime settings` | Files: `poe_trade/config/settings.py`, `poe_trade/config/constants.py`, `tests/unit/test_settings_aliases.py`, `.env.example`

- [ ] 5. Remove non-core web/runtime leftovers and add SQL execution scaffolding

  **What to do**: Remove dead dependencies and stale scaffolding that conflict with NeoPlanus' CLI-first/no-web-ui doctrine, specifically unused FastAPI/uvicorn/httpx footprints if no shipped code needs them. In the same wave, add the minimal package scaffolding for `analytics/`, `strategy/`, and `sql/` execution helpers so later waves can plug in scheduled SQL refreshes without inventing a generic ETL framework.
  **Must NOT do**: Do not introduce a web server replacement, job framework, or abstraction-heavy refresh engine.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: bounded cleanup and scaffolding based on already-proven repo gaps.
  - Skills: [] — local repo cleanup only.
  - Omitted: [`frontend-ui-ux`] — NeoPlanus explicitly deprioritizes UI.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 15,18,19,20,27,29 | Blocked By: 1

  **References**:
  - Pattern: `pyproject.toml:15` — current dependencies still include `fastapi`, `uvicorn`, and `httpx`.
  - Pattern: `tests/unit/__init__.py:16` — tests stub FastAPI even though runtime code does not use it.
  - Pattern: `poe_trade/cli.py:32` — current CLI router is the right thin entry surface to keep.
  - Pattern: `NeoPlanus.md:32` — explicitly forbids ETL frameworks and extra service layers.
  - Pattern: `NeoPlanus.md:1255` — target code layout includes `analytics/`, `strategy/`, and `sql/` assets.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/python -m poe_trade.cli --help` still works after dependency cleanup and scaffolding.
  - [ ] `python3 -m compileall poe_trade` succeeds with the new `analytics/` and `strategy/` scaffolds in place.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path CLI survives cleanup
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli --help`.
    Expected: The CLI still loads successfully with no FastAPI/uvicorn runtime dependency.
    Evidence: .sisyphus/evidence/task-5-runtime-cleanup.txt

  Scenario: Failure path stale web dependency detection
    Tool: Bash
    Steps: Run `rg -n "FastAPI|uvicorn|httpx" poe_trade tests pyproject.toml`.
    Expected: Results are limited to intentional compatibility cleanup or removed entirely from shipped runtime paths.
    Evidence: .sisyphus/evidence/task-5-runtime-cleanup-error.txt
  ```

  **Commit**: YES | Message: `chore(runtime): remove web leftovers and add sql scaffolds` | Files: `pyproject.toml`, `poe_trade/`, `tests/unit/__init__.py`

- [ ] 6. Generalize OAuth and PoE client behavior for the unified daemon

  **What to do**: Update `oauth_client_factory` and `PoeClient` so the daemon can request the correct confidential-client scopes for enabled feeds, preserve the documented `User-Agent` format, and support documented path construction for PSAPI and CXAPI without relying on undocumented query params. Keep retry, `Retry-After`, and dynamic rate-limit handling intact.
  **Must NOT do**: Do not weaken rate-limit behavior, silently accept public-client service scopes, or bake realm handling into query parameters where path segments are required.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: auth and HTTP semantics are central shared dependencies.
  - Skills: [] — repo-local logic with strong test surface.
  - Omitted: [`protocol-compat`] — this is runtime behavior, not schema evolution.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 8,9,10,27 | Blocked By: 4

  **References**:
  - Pattern: `poe_trade/ingestion/market_harvester.py:79` — current OAuth factory hardcodes `service:psapi` validation.
  - Pattern: `poe_trade/ingestion/poe_client.py:168` — URL/path building lives in one place already.
  - Pattern: `poe_trade/config/constants.py:20` — current defaults are the right place for API base URLs and UA defaults.
  - External: `https://www.pathofexile.com/developer/docs/authorization` — confidential clients can use `service:*` scopes; public clients cannot.
  - External: `https://www.pathofexile.com/developer/docs/reference#publicstashes` — PSAPI path shape and cursor rules.
  - External: `https://www.pathofexile.com/developer/docs/reference#currencyexchange` — CXAPI path shape and hourly-id contract.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/pytest tests/unit/test_poe_client.py tests/unit/test_market_harvester_auth.py` passes with PSAPI + CXAPI-capable auth/client behavior.
  - [ ] `rg -n "service:psapi|service:cxapi|User-Agent|public-stash-tabs|currency-exchange" poe_trade/ingestion poe_trade/config tests/unit` shows explicit documented handling for both feeds.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path confidential-client support
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_market_harvester_auth.py tests/unit/test_poe_client.py`.
    Expected: Tests prove the OAuth/client stack supports the unified daemon without regressing retry or token refresh behavior.
    Evidence: .sisyphus/evidence/task-6-oauth-client.txt

  Scenario: Failure path undocumented request shape blocked
    Tool: Bash
    Steps: Run `rg -n "league\s*=|params\[\"realm\"\]|api/trade/data" poe_trade/ingestion tests/unit`.
    Expected: No active PSAPI/CXAPI path construction relies on undocumented league query params or the old trade metadata path.
    Evidence: .sisyphus/evidence/task-6-oauth-client-error.txt
  ```

  **Commit**: YES | Message: `refactor(ingestion): generalize oauth and client paths` | Files: `poe_trade/ingestion/market_harvester.py`, `poe_trade/ingestion/poe_client.py`, `tests/unit/`

- [ ] 7. Replace `CheckpointStore` with ClickHouse-backed sync state

  **What to do**: Introduce `sync_state.py` (or equivalent) that loads and persists the latest PSAPI/CXAPI queue cursor from `poe_trade.bronze_ingest_checkpoints` using `queue_key` and allowed statuses. Remove runtime dependence on filesystem checkpoints from service startup, resume logic, and health calculations.
  **Must NOT do**: Do not keep dual canonical sources or leave restart behavior dependent on `.state/` files.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the core durability cutover.
  - Skills: [`protocol-compat`] — required for safe fallback and upgrade behavior.
  - Omitted: [`docs-specialist`] — docs come after runtime changes land.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 8,9,10,27,29 | Blocked By: 2,4

  **References**:
  - Pattern: `poe_trade/ingestion/checkpoints.py:1` — current file-backed store to remove from runtime semantics.
  - Pattern: `poe_trade/services/market_harvester.py:109` — current service startup still instantiates `CheckpointStore`.
  - Pattern: `poe_trade/ingestion/market_harvester.py:469` — current PSAPI resume still reads filesystem checkpoints.
  - Pattern: `NeoPlanus.md:106` — file checkpoints are redundant because ClickHouse already stores checkpoint history.
  - Pattern: `NeoPlanus.md:683` — target checkpoint query pattern for PSAPI.
  - Pattern: `NeoPlanus.md:692` — target checkpoint query pattern for CXAPI.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/pytest tests/unit/test_market_harvester.py tests/unit/test_market_harvester_service.py` passes with no runtime dependency on `CheckpointStore`.
  - [ ] `rg -n "CheckpointStore|checkpoint_dir|POE_CURSOR_DIR|POE_CHECKPOINT_DIR" poe_trade/tests README.md docs` shows only explicit compatibility/deprecation references after the cutover.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path ClickHouse resume source
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_market_harvester.py tests/unit/test_market_harvester_service.py`.
    Expected: Tests demonstrate restart/resume flows obtain cursors from ClickHouse-backed sync state.
    Evidence: .sisyphus/evidence/task-7-sync-state.txt

  Scenario: Failure path file checkpoint dependency removed
    Tool: Bash
    Steps: Run `rg -n "CheckpointStore|checkpoint lag risk|\.checkpoint" poe_trade tests README.md docs`.
    Expected: No shipped runtime path depends on file checkpoints; any remaining mentions are deprecation/cleanup-only.
    Evidence: .sisyphus/evidence/task-7-sync-state-error.txt
  ```

  **Commit**: YES | Message: `refactor(ingestion): move sync state into clickhouse` | Files: `poe_trade/ingestion/`, `poe_trade/services/market_harvester.py`, `tests/unit/`

- [ ] 8. Split `market_harvester` into a unified scheduler service

  **What to do**: Keep the external service name `market_harvester`, but refactor internals into a single scheduler loop that dispatches `psapi:<realm>`, `cxapi:<realm>`, refresh, and scanner work without a thread pool per league. Add explicit queue due-state calculation and sleep behavior matching NeoPlanus' scheduler doctrine.
  **Must NOT do**: Do not preserve `ThreadPoolExecutor`-driven `realm x league` harvesting or keep scheduler state smeared across private helper branches.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the main runtime architecture rewrite.
  - Skills: [] — current repo patterns plus tests are sufficient.
  - Omitted: [`protocol-compat`] — schema is already defined by earlier tasks.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 9,10,27 | Blocked By: 6,7

  **References**:
  - Pattern: `poe_trade/services/market_harvester.py:32` — keep this service entrypoint thin and backwards compatible.
  - Pattern: `poe_trade/ingestion/market_harvester.py:237` — current threaded runner to replace.
  - Pattern: `poe_trade/cli.py:43` — CLI router already exposes the correct operator entrypoint.
  - Pattern: `NeoPlanus.md:210` — one private daemon with two queue types.
  - Pattern: `NeoPlanus.md:621` — canonical single-threaded scheduler loop sketch.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/pytest tests/unit/test_market_harvester_service.py tests/unit/test_service_registry.py` passes with `market_harvester` still loading through the CLI router.
  - [ ] `rg -n "ThreadPoolExecutor|max_workers|realm x league|sync_psapi_once|sync_cxapi" poe_trade/ingestion poe_trade/services` shows the old threading model is gone and the new scheduler paths are explicit.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path scheduler wiring
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli service --name market_harvester -- --help` and `.venv/bin/pytest tests/unit/test_market_harvester_service.py tests/unit/test_service_registry.py`.
    Expected: CLI wiring remains stable while tests prove the new scheduler is the active runtime path.
    Evidence: .sisyphus/evidence/task-8-scheduler.txt

  Scenario: Failure path threaded runtime removed
    Tool: Bash
    Steps: Run `rg -n "ThreadPoolExecutor|max_workers" poe_trade/ingestion poe_trade/services tests/unit`.
    Expected: No shipped runtime or tests continue to depend on the old per-league thread pool model.
    Evidence: .sisyphus/evidence/task-8-scheduler-error.txt
  ```

  **Commit**: YES | Message: `refactor(service): add unified market scheduler` | Files: `poe_trade/services/market_harvester.py`, `poe_trade/ingestion/`, `tests/unit/`

- [ ] 9. Implement documented PSAPI queue behavior

  **What to do**: Move PSAPI logic into an explicit queue module that requests the documented path only, uses one queue per realm, never sends `league`, filters leagues locally after ingest, writes bronze rows row-by-row, logs requests/checkpoints/status, and handles the empty-`stashes`/unchanged-`next_change_id` idle case exactly as documented. Refresh only fast/current-state models after successful PSAPI batches.
  **Must NOT do**: Do not preserve bootstrap-until-league behavior as a runtime requirement or fetch undocumented trade metadata as part of core PSAPI sync.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: PSAPI is the primary live ingest feed.
  - Skills: [] — strong existing test coverage makes this a focused refactor.
  - Omitted: [`protocol-compat`] — core schema contract already exists.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 11,12,13,27 | Blocked By: 6,7,8

  **References**:
  - Pattern: `poe_trade/ingestion/market_harvester.py:151` — current request params still accept `league` and `realm` as query params.
  - Pattern: `poe_trade/ingestion/market_harvester.py:555` — current row emission already normalizes bronze insert shape.
  - Pattern: `tests/unit/test_market_harvester.py:303` — current success-path tests are the starting point for updated PSAPI coverage.
  - Pattern: `NeoPlanus.md:93` — current multi-league PSAPI topology is wrong and must be replaced.
  - Pattern: `NeoPlanus.md:643` — target PSAPI sync rules.
  - External: `https://www.pathofexile.com/developer/docs/reference#publicstashes` — authoritative PSAPI path/cursor/idle semantics.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/pytest tests/unit/test_market_harvester.py tests/unit/test_market_harvester_auth.py` passes with PSAPI requests omitting `league` and using ClickHouse-backed queue state.
  - [ ] `rg -n "public-stash-tabs|league\]|params\[\"league\"\]|api/trade/data" poe_trade/ingestion tests/unit` confirms documented PSAPI paths and no core metadata-path dependency.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path PSAPI request contract
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_market_harvester.py tests/unit/test_market_harvester_auth.py`.
    Expected: Tests prove PSAPI sync works without `league` query params and preserves OAuth/rate-limit behavior.
    Evidence: .sisyphus/evidence/task-9-psapi-sync.txt

  Scenario: Failure path undocumented metadata dependency removed
    Tool: Bash
    Steps: Run `rg -n "api/trade/data|trade_data_id|bootstrap_until_league" poe_trade/ingestion tests/unit`.
    Expected: No core PSAPI path depends on the old trade metadata or bootstrap runtime behavior.
    Evidence: .sisyphus/evidence/task-9-psapi-sync-error.txt
  ```

  **Commit**: YES | Message: `refactor(psapi): adopt realm-scoped documented sync` | Files: `poe_trade/ingestion/`, `tests/unit/test_market_harvester*.py`

- [ ] 10. Reintroduce corrected CX bronze storage and queue behavior

  **What to do**: Add the corrected `poe_trade.raw_currency_exchange_hour` migration, grants, and queue module so the daemon can backfill and maintain hourly historical CX data per realm with explicit hour ids only. Implement cold-start backfill from `last_completed_hour - backfill_hours`, steady-state hourly catch-up, and post-write refresh hooks for currency references.
  **Must NOT do**: Do not reuse the old `league`-keyed raw CX schema or call CXAPI without an explicit id in daemon mode.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this introduces a new official feed plus corrected bronze storage.
  - Skills: [`protocol-compat`] — migration + runtime contract must stay aligned.
  - Omitted: [`docs-specialist`] — docs update comes later.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 14,16,27 | Blocked By: 6,7,8

  **References**:
  - Pattern: `schema/migrations/0002_bronze.sql:14` — old CX schema was league-keyed and incorrect for NeoPlanus.
  - Pattern: `schema/migrations/0018_cleanup_unused_objects.sql:33` — old CX table was explicitly dropped.
  - Pattern: `NeoPlanus.md:130` — old raw CX design should not be restored as-is.
  - Pattern: `NeoPlanus.md:331` — corrected `raw_currency_exchange_hour` schema.
  - Pattern: `NeoPlanus.md:664` — target CXAPI sync rules.
  - External: `https://www.pathofexile.com/developer/docs/reference#currencyexchange` — authoritative endpoint, payload, and historical-only behavior.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-migrate --status --dry-run` discovers the CX migration(s) and grant updates cleanly.
  - [ ] `.venv/bin/pytest tests/unit` includes new CX queue coverage proving explicit-hour requests and ClickHouse checkpoint resume semantics.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path CX queue catch-up
    Tool: Bash
    Steps: Run `poe-migrate --status --dry-run` and the CX-focused unit tests added in this task.
    Expected: The repo contains the corrected bronze CX schema and tests prove hourly catch-up behavior.
    Evidence: .sisyphus/evidence/task-10-cx-sync.txt

  Scenario: Failure path omitted-id call prevented
    Tool: Bash
    Steps: Run `rg -n "currency-exchange.*\{/<id>\}|currency-exchange\W*$|id is None|no id" poe_trade tests/unit schema/migrations`.
    Expected: Normal daemon code always constructs CX requests with an explicit hour id and never falls back to first-hour-of-history mode.
    Evidence: .sisyphus/evidence/task-10-cx-sync-error.txt
  ```

  **Commit**: YES | Message: `feat(cxapi): add hourly sync queue and bronze table` | Files: `schema/migrations/*.sql`, `poe_trade/ingestion/`, `tests/unit/`

- [ ] 11. Add silver stash-change storage and materialized view

  **What to do**: Implement the NeoPlanus stash-header silver layer by adding `poe_trade.silver_ps_stash_changes` plus `poe_trade.mv_ps_stash_changes`, fed from `raw_public_stash_pages`. Ensure each row represents one stash change, keeps upstream stash/account/public metadata, and retains checkpoint linkage for debugging and current-state derivation.
  **Must NOT do**: Do not keep reusing older `v_bronze_public_stash_items` logic that assumes nested `stashes` arrays inside each bronze row.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the first major silver model and becomes the base for current-state logic.
  - Skills: [`protocol-compat`] — ClickHouse MV/table evolution must stay safe.
  - Omitted: [`docs-specialist`] — docs update is deferred.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 13,15,27 | Blocked By: 2,9

  **References**:
  - Pattern: `schema/migrations/0002_bronze.sql:1` — bronze source table shape.
  - Pattern: `poe_trade/ingestion/market_harvester.py:812` — current bronze insert columns already approximate the target source payload.
  - Pattern: `NeoPlanus.md:351` — target `silver_ps_stash_changes` schema.
  - Pattern: `NeoPlanus.md:377` — target MV projection for stash changes.
  - Pattern: `NeoPlanus.md:504` — current-state views must be stash-driven.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-migrate --status --dry-run` discovers the stash-change silver migration(s).
  - [ ] `rg -n "silver_ps_stash_changes|mv_ps_stash_changes" schema/migrations schema/sanity` shows the new table/MV and related validation coverage.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path stash silver object creation
    Tool: Bash
    Steps: Run `poe-migrate --status --dry-run` and `rg -n "silver_ps_stash_changes|mv_ps_stash_changes" schema/migrations schema/sanity`.
    Expected: The migration set includes the stash-change table and MV, with sanity coverage added.
    Evidence: .sisyphus/evidence/task-11-stash-silver.txt

  Scenario: Failure path legacy nested-stash parser retired
    Tool: Bash
    Steps: Run `rg -n "v_bronze_public_stash_items|JSONExtractRaw\(raw.payload_json, 'stashes'\)" schema poe_trade`.
    Expected: Old nested-stash assumptions are removed from the active silver path.
    Evidence: .sisyphus/evidence/task-11-stash-silver-error.txt
  ```

  **Commit**: YES | Message: `feat(sql): add stash-change silver layer` | Files: `schema/migrations/*.sql`, `schema/sanity/*.sql`

- [ ] 12. Add silver exploded item storage and pricing primitives

  **What to do**: Implement `poe_trade.silver_ps_items_raw` plus `poe_trade.mv_ps_items_raw`, exploding item rows from stash-change payloads and preserving the fields NeoPlanus names as phase-1 essentials: item id, name, type line, base type, rarity, ilvl, stack size, note/forum note, corruption, fractured, synthesised, and raw item JSON. Keep the bronze-to-silver transform in ClickHouse rather than Python.
  **Must NOT do**: Do not rebuild a Python-side normalization loop for item explosion or a complete PoE ontology in this task.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this creates the main analytics grain for PSAPI-driven strategies.
  - Skills: [`protocol-compat`] — SQL object evolution must stay explicit.
  - Omitted: [`ultrabrain`] — problem is large but straightforward.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 13,15,17,21,22 | Blocked By: 2,9

  **References**:
  - Pattern: `schema/migrations/0002_bronze.sql:1` — bronze source data.
  - Pattern: `NeoPlanus.md:395` — target `silver_ps_items_raw` schema.
  - Pattern: `NeoPlanus.md:433` — target MV sketch for exploded items.
  - Pattern: `NeoPlanus.md:464` — effective pricing should derive from `note`, `forum_note`, then stash name.
  - Pattern: `NeoPlanus.md:773` — use ClickHouse JSON/array functions, not Python loops.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-migrate --status --dry-run` discovers the item silver migration(s).
  - [ ] `rg -n "silver_ps_items_raw|mv_ps_items_raw|note|forum_note|stack_size" schema/migrations schema/sanity` shows the new table/MV and pricing primitives.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path item silver object creation
    Tool: Bash
    Steps: Run `poe-migrate --status --dry-run` and `rg -n "silver_ps_items_raw|mv_ps_items_raw" schema/migrations schema/sanity`.
    Expected: The migration set defines the item table and MV exactly once with sanity coverage.
    Evidence: .sisyphus/evidence/task-12-items-silver.txt

  Scenario: Failure path Python normalization avoided
    Tool: Bash
    Steps: Run `rg -n "for .*item|while .*item|normalize.*item" poe_trade/ingestion poe_trade/analytics`.
    Expected: No new Python loop is introduced to explode or normalize millions of PSAPI item rows.
    Evidence: .sisyphus/evidence/task-12-items-silver-error.txt
  ```

  **Commit**: YES | Message: `feat(sql): add psapi item silver layer` | Files: `schema/migrations/*.sql`, `schema/sanity/*.sql`

- [ ] 13. Build enriched and current-state PSAPI views

  **What to do**: Add `v_ps_items_enriched`, `v_ps_current_stashes`, and `v_ps_current_items`, using NeoPlanus' narrow enrichment scope: effective price note, parsed amount/currency, category/subcategory heuristics, and stash-driven current state derived from the latest stash snapshot rather than naive last-seen item rows. Ensure current public items explode only from the latest public stash rows.
  **Must NOT do**: Do not attempt a full item ontology or current-state logic that ignores unlisted/partial stash reappearance behavior.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: current-state semantics are essential for scanner correctness.
  - Skills: [`protocol-compat`] — view contracts must stay query-safe.
  - Omitted: [`docs-specialist`] — docs update is later.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 16,17,19,21,22,23,24,27,28 | Blocked By: 11,12

  **References**:
  - Pattern: `schema/migrations/0012_liquidity_views.sql:1` — current liquidity pipeline is built on obsolete bronze/item assumptions and should not be reused.
  - Pattern: `NeoPlanus.md:466` — enriched views should replace Python transforms for narrow parsing.
  - Pattern: `NeoPlanus.md:481` — target `v_ps_items_enriched` sketch.
  - Pattern: `NeoPlanus.md:504` — current-state views must be stash-driven.
  - Pattern: `NeoPlanus.md:516` — target `v_ps_current_stashes` sketch.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `clickhouse-client --multiquery < schema/sanity/silver.sql` validates the enriched/current-state view set.
  - [ ] `rg -n "v_ps_items_enriched|v_ps_current_stashes|v_ps_current_items|effective_price_note|argMax" schema/migrations schema/sanity` shows the expected view logic.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path current-state validation
    Tool: Bash
    Steps: Run `clickhouse-client --multiquery < schema/sanity/silver.sql`.
    Expected: Silver sanity passes using the new enriched/current-state view set.
    Evidence: .sisyphus/evidence/task-13-current-state.txt

  Scenario: Failure path naive last-seen logic rejected
    Tool: Bash
    Steps: Run `rg -n "last seen item|last_seen|GROUP BY item_id.*max\(|latest item row" schema/migrations poe_trade/sql`.
    Expected: No active current-state object relies on naive last-seen item-row semantics instead of stash-driven `argMax` logic.
    Evidence: .sisyphus/evidence/task-13-current-state-error.txt
  ```

  **Commit**: YES | Message: `feat(sql): add enriched and current-state views` | Files: `schema/migrations/*.sql`, `schema/sanity/silver.sql`

- [ ] 14. Add silver CX market rows and CX enriched views

  **What to do**: Create `poe_trade.silver_cx_markets_hour`, `poe_trade.mv_cx_markets_hour`, and `v_cx_markets_enriched` (or equivalent) from `raw_currency_exchange_hour`, keeping ratio dictionaries raw initially and deriving only stable structural fields such as `league`, `market_id`, `base_code`, and `quote_code`. Avoid inventing mid-rate assumptions until real payloads are available.
  **Must NOT do**: Do not normalize CX markets back into the dropped old `league`-partitioned raw schema or over-model rate math before inspecting real hourly payloads.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: CX silver is a new analytical base for currency normalization and market-making.
  - Skills: [`protocol-compat`] — keep MV/storage contracts safe.
  - Omitted: [`ultrabrain`] — the task is structural, not conceptually novel.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 16,19,22,27 | Blocked By: 2,10

  **References**:
  - Pattern: `NeoPlanus.md:534` — target `silver_cx_markets_hour` schema.
  - Pattern: `NeoPlanus.md:561` — target MV sketch for exploded CX markets.
  - Pattern: `NeoPlanus.md:581` — store ratio dictionaries raw first; do not assume mid-rates too early.
  - Pattern: `NeoPlanus.md:157` — CXAPI is historical hourly data, not live order-book depth.
  - External: `https://www.pathofexile.com/developer/docs/reference#currencyexchange` — authoritative CX response shape.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-migrate --status --dry-run` discovers the CX silver migration(s).
  - [ ] `rg -n "silver_cx_markets_hour|mv_cx_markets_hour|base_code|quote_code|lowest_ratio_json|highest_ratio_json" schema/migrations schema/sanity` shows the correct structural storage.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path CX silver object creation
    Tool: Bash
    Steps: Run `poe-migrate --status --dry-run` and `rg -n "silver_cx_markets_hour|mv_cx_markets_hour" schema/migrations schema/sanity`.
    Expected: CX silver objects are present and keyed by realm/hour/market.
    Evidence: .sisyphus/evidence/task-14-cx-silver.txt

  Scenario: Failure path premature rate assumptions prevented
    Tool: Bash
    Steps: Run `rg -n "mid_rate|weighted_mid|implied_spread" schema/migrations poe_trade/sql`.
    Expected: No early-stage CX silver object bakes in assumed rate math before payload inspection.
    Evidence: .sisyphus/evidence/task-14-cx-silver-error.txt
  ```

  **Commit**: YES | Message: `feat(sql): add cx silver market views` | Files: `schema/migrations/*.sql`, `schema/sanity/*.sql`

- [ ] 15. Add SQL refresh/rebuild execution for silver and gold groups

  **What to do**: Implement the lightweight SQL execution helpers and command wiring needed to run scheduled refreshes and rebuilds for NeoPlanus groups (`silver`, `gold refs`, `gold strategies`, full rebuilds). The execution layer must stay intentionally small: read ordered SQL assets, execute them through ClickHouse, and expose incremental vs full rebuild entrypoints without introducing a workflow engine.
  **Must NOT do**: Do not add a DAG/orchestrator abstraction, plugin system, or Python data-processing layer that competes with ClickHouse SQL.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: later gold/strategy tasks depend on a shared execution path.
  - Skills: [] — repo-local execution wiring only.
  - Omitted: [`protocol-compat`] — no new persisted schema beyond later tasks.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 16,17,18,19,20,26,27,28,29,30 | Blocked By: 5,11,12,13,14

  **References**:
  - Pattern: `poe_trade/db/clickhouse.py:1` — existing ClickHouse execution client to reuse.
  - Pattern: `poe_trade/cli.py:32` — current CLI router can host refresh/rebuild commands.
  - Pattern: `NeoPlanus.md:719` — bronze-to-silver/current/gold transform lifecycle.
  - Pattern: `NeoPlanus.md:755` — every gold model supports incremental refresh and full rebuild.
  - Pattern: `NeoPlanus.md:766` — suggested refresh/rebuild commands.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/python -m poe_trade.cli --help` exposes refresh/rebuild subcommands or equivalent routing.
  - [ ] `python3 -m compileall poe_trade` succeeds with the new analytics/strategy execution modules.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path refresh command exposure
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli --help` and inspect the command list.
    Expected: Refresh/rebuild command groups for silver and gold are visible through the CLI.
    Evidence: .sisyphus/evidence/task-15-refresh-engine.txt

  Scenario: Failure path orchestration bloat avoided
    Tool: Bash
    Steps: Run `rg -n "airflow|dagster|dbt|workflow engine|scheduler framework|plugin manager" poe_trade pyproject.toml`.
    Expected: No ETL/orchestrator dependency or abstraction is introduced.
    Evidence: .sisyphus/evidence/task-15-refresh-engine-error.txt
  ```

  **Commit**: YES | Message: `feat(cli): add sql refresh and rebuild execution` | Files: `poe_trade/cli.py`, `poe_trade/analytics/`, `poe_trade/strategy/`, `poe_trade/sql/`

- [ ] 16. Build CX-driven currency reference marts

  **What to do**: Add `gold_currency_ref_hour` and its refresh SQL using CX hourly markets as the core normalization source for exchange-eligible pairs. Start with durable measures only: nearest completed-hour rates, pair coverage, sample counts, and regime-ready metadata needed by later strategies and joins.
  **Must NOT do**: Do not introduce external pricing as a core dependency or pretend CX data is live current-hour depth.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: currency normalization is foundational for pricing, backtests, and scanner ranking.
  - Skills: [] — all logic is repo-local SQL.
  - Omitted: [`protocol-compat`] — schema primitives already exist from prior tasks.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 19,21,22,23 | Blocked By: 14,15

  **References**:
  - Pattern: `schema/migrations/0003_silver.sql:43` — historical `currency_rates` table is obsolete context, not the target design.
  - Pattern: `NeoPlanus.md:157` — CXAPI is hourly historical only.
  - Pattern: `NeoPlanus.md:587` — `gold_currency_ref_hour` is one of the few gold marts to keep.
  - Pattern: `NeoPlanus.md:745` — gold refreshes should cover price references.
  - Pattern: `NeoPlanus.md:785` — `ASOF JOIN` is a recommended ClickHouse pattern for attaching currency refs by time.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `clickhouse-client --multiquery < schema/sanity/gold.sql` validates the presence and freshness of `gold_currency_ref_hour`.
  - [ ] `rg -n "gold_currency_ref_hour|ASOF JOIN|currency_ref" poe_trade/sql schema/migrations schema/sanity` shows the mart and its refresh path.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path currency reference refresh
    Tool: Bash
    Steps: Run `poe-ledger-cli refresh gold --group refs`, then `clickhouse-client --multiquery < schema/sanity/gold.sql`.
    Expected: `gold_currency_ref_hour` is populated from CX data and visible to sanity checks.
    Evidence: .sisyphus/evidence/task-16-currency-ref.txt

  Scenario: Failure path external pricing dependency absent
    Tool: Bash
    Steps: Run `rg -n "poe\.ninja|external pricing|third-party price" poe_trade/sql poe_trade/analytics README.md docs`.
    Expected: No core gold currency ref path depends on third-party pricing sources.
    Evidence: .sisyphus/evidence/task-16-currency-ref-error.txt
  ```

  **Commit**: YES | Message: `feat(gold): add cx-driven currency references` | Files: `poe_trade/sql/gold/`, `schema/migrations/*.sql`, `schema/sanity/gold.sql`

- [ ] 17. Build listing, liquidity, bulk, and set reference marts

  **What to do**: Add `gold_listing_ref_hour`, `gold_liquidity_ref_hour`, `gold_bulk_premium_hour`, and `gold_set_ref_hour`, all refreshed from PSAPI silver/current-state plus CX normalization where needed. Encode fair current price, likely time to sell, bulk premium, and set-assembly value as explicit marts instead of reviving the dropped legacy gold tables.
  **Must NOT do**: Do not bring back `price_stats_1h`, `flip_opportunities`, `craft_opportunities`, or the old `v_liquidity` design as if they were the final NeoPlanus architecture.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: these marts make the scanner and backtests possible.
  - Skills: [] — SQL-first work with existing ClickHouse client/runner.
  - Omitted: [`protocol-compat`] — object layout is already governed by earlier tasks.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 19,21,22,23,24 | Blocked By: 13,15

  **References**:
  - Pattern: `schema/migrations/0004_gold.sql:1` — old gold tables are historical and should not be restored as-is.
  - Pattern: `schema/migrations/0012_liquidity_views.sql:88` — old liquidity view relies on obsolete bronze metadata assumptions.
  - Pattern: `NeoPlanus.md:583` — gold marts should stay few and high-value.
  - Pattern: `NeoPlanus.md:1426` — phase-3 gold reference scope and exit criteria.
  - Pattern: `NeoPlanus.md:1446` — target questions the system must answer.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `clickhouse-client --multiquery < schema/sanity/gold.sql` validates all four reference marts.
  - [ ] `rg -n "gold_listing_ref_hour|gold_liquidity_ref_hour|gold_bulk_premium_hour|gold_set_ref_hour" poe_trade/sql schema/migrations schema/sanity` shows the full NeoPlanus mart set.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path gold mart refresh
    Tool: Bash
    Steps: Run `poe-ledger-cli refresh gold --group refs`, then `clickhouse-client --multiquery < schema/sanity/gold.sql`.
    Expected: Gold sanity proves the four reference marts exist and answer the intended pricing/liquidity questions.
    Evidence: .sisyphus/evidence/task-17-gold-refs.txt

  Scenario: Failure path legacy gold resurrection prevented
    Tool: Bash
    Steps: Run `rg -n "price_stats_1h|flip_opportunities|craft_opportunities|v_liquidity\b" schema poe_trade/sql`.
    Expected: Legacy gold/liquidity objects are not reused as the new authoritative marts.
    Evidence: .sisyphus/evidence/task-17-gold-refs-error.txt
  ```

  **Commit**: YES | Message: `feat(gold): add listing liquidity bulk and set marts` | Files: `poe_trade/sql/gold/`, `schema/migrations/*.sql`, `schema/sanity/gold.sql`

- [ ] 18. Add strategy-pack runtime and metadata registry

  **What to do**: Implement the SQL-pack strategy runtime that loads `strategies/<id>/strategy.toml` metadata, maps each strategy to `poe_trade/sql/strategy/<id>/discover.sql` and `backtest.sql`, and supports optional bounded `eval.py` hooks only for advanced stochastic strategies. Include registry, enable/disable state, and execution-venue metadata as first-class concepts.
  **Must NOT do**: Do not invent a custom DSL, YAML metadata layer, or opaque plugin registry.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this defines the long-term strategy authoring model.
  - Skills: [] — local Python + TOML + SQL wiring.
  - Omitted: [`protocol-compat`] — not a migration-heavy task.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 19,20,21,22,23,24,26,27,28 | Blocked By: 5,15

  **References**:
  - Pattern: `NeoPlanus.md:47` — no custom DSL in v1.
  - Pattern: `NeoPlanus.md:794` — strategy-pack format and rationale.
  - Pattern: `NeoPlanus.md:828` — example `strategy.toml` structure.
  - Pattern: `NeoPlanus.md:849` — SQL files are the real strategy logic.
  - Pattern: `NeoPlanus.md:1255` — target layout splits SQL assets and metadata directories.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-ledger-cli strategy list` executes and loads pack metadata through the strategy runtime.
  - [ ] `python3 -m compileall poe_trade` succeeds with `strategy/` registry/runner modules and `strategies/` metadata packs present.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path strategy registry load
    Tool: Bash
    Steps: Run `poe-ledger-cli strategy list` and inspect the loaded pack metadata.
    Expected: Strategies are discovered from TOML + SQL assets without a custom DSL.
    Evidence: .sisyphus/evidence/task-18-strategy-runtime.txt

  Scenario: Failure path DSL creep blocked
    Tool: Bash
    Steps: Run `rg -n "yaml|dsl|parser generator|custom language" poe_trade/strategy strategies pyproject.toml`.
    Expected: No strategy runtime introduces a custom DSL or YAML dependency.
    Evidence: .sisyphus/evidence/task-18-strategy-runtime-error.txt
  ```

  **Commit**: YES | Message: `feat(strategy): add sql-pack registry and runner` | Files: `poe_trade/strategy/`, `poe_trade/sql/strategy/`, `strategies/`

- [ ] 19. Implement SQL-first backtest storage and execution flows

  **What to do**: Add `research_backtest_runs` and `research_backtest_results`, plus the runtime needed to execute strategy `backtest.sql` over historical windows using `t0`-frozen references, future-window exit estimates, and the NeoPlanus fill-truth hierarchy. Classify strategies by backtest reliability (Class A/B/C) and store predicted vs proxy-realized outcomes.
  **Must NOT do**: Do not claim direct fill truth from PSAPI or treat high-dimensional rare-item strategies as equally reliable to commodity/set strategies.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: backtesting touches gold refs, strategy runtime, and truth modeling.
  - Skills: [] — repo-local SQL/runtime design.
  - Omitted: [`ultrabrain`] — complexity is large but already bounded by NeoPlanus.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: 21,22,24,26,27,28 | Blocked By: 15,16,17,18

  **References**:
  - Pattern: `NeoPlanus.md:1063` — SQL-first backtesting workflow.
  - Pattern: `NeoPlanus.md:1077` — fill-truth hierarchy.
  - Pattern: `NeoPlanus.md:1087` — Class A/B/C backtest classes.
  - Pattern: `NeoPlanus.md:592` — backtest run/result tables belong in the initial gold/research set.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-ledger-cli research backtest --strategy bulk_essence --league Mirage --days 14` executes and persists rows into `research_backtest_runs` and `research_backtest_results`.
  - [ ] `rg -n "research_backtest_runs|research_backtest_results|Class A|Class B|Class C|predicted vs" poe_trade schema poe_trade/sql` shows the intended storage and classification logic.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path historical backtest run
    Tool: Bash
    Steps: Run `poe-ledger-cli research backtest --strategy bulk_essence --league Mirage --days 14`.
    Expected: A run record and result rows are written with t0-only inputs and future-window outputs.
    Evidence: .sisyphus/evidence/task-19-backtests.txt

  Scenario: Failure path fake fill truth prevented
    Tool: Bash
    Steps: Run `rg -n "executed fill|actual fill|guaranteed sale" poe_trade/sql poe_trade/strategy docs README.md`.
    Expected: No backtest path claims direct fill truth from PSAPI; heuristics and journal truth are clearly separated.
    Evidence: .sisyphus/evidence/task-19-backtests-error.txt
  ```

  **Commit**: YES | Message: `feat(research): add sql-first backtesting` | Files: `poe_trade/strategy/`, `poe_trade/sql/strategy/`, `schema/migrations/*.sql`

- [ ] 20. Expand the CLI and reporting surface for sync, research, and refs

  **What to do**: Grow `poe-ledger-cli` beyond `service --name` so it exposes NeoPlanus-aligned sync, refresh, research, strategy, and report commands, with markdown/JSON output modes where appropriate. Keep the CLI the primary interface layer and defer any TUI/browser work to later optional tasks.
  **Must NOT do**: Do not reintroduce a web UI or bury business logic inside `cli.py` instead of service/runtime modules.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: command surface shapes the operator workflow and later automation.
  - Skills: [] — existing router patterns are enough.
  - Omitted: [`frontend-ui-ux`] — CLI-first task only.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 23,24,27,29 | Blocked By: 15,18

  **References**:
  - Pattern: `poe_trade/cli.py:35` — current router is intentionally thin and should stay that way.
  - Pattern: `README.md:22` — current CLI docs are limited to service routing and migrations.
  - Pattern: `NeoPlanus.md:75` — CLI first, TUI second.
  - Pattern: `NeoPlanus.md:1167` — suggested command surface.
  - Pattern: `NeoPlanus.md:244` — user-facing tool should read from gold views/tables and emit clear actions.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/python -m poe_trade.cli --help` shows sync/refresh/strategy/research/report command groups.
  - [ ] `.venv/bin/python -m poe_trade.cli service --name market_harvester -- --help` still works for backwards compatibility.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path CLI command discovery
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli --help` and capture the command tree.
    Expected: The CLI exposes the new command surface while preserving the service entrypoint.
    Evidence: .sisyphus/evidence/task-20-cli-surface.txt

  Scenario: Failure path thin-router rule preserved
    Tool: Bash
    Steps: Run `rg -n "ClickHouse|SQL|strategy logic|scanner logic" poe_trade/cli.py`.
    Expected: `cli.py` remains a router, not the home for business logic.
    Evidence: .sisyphus/evidence/task-20-cli-surface-error.txt
  ```

  **Commit**: YES | Message: `feat(cli): add sync research and report commands` | Files: `poe_trade/cli.py`, `poe_trade/services/`, `README.md`

- [ ] 21. Implement the Priority-1 strategy pack set

  **What to do**: Ship the first NeoPlanus strategy family as SQL packs plus TOML metadata and notes: bulk essences, bulk fossils, fragment sets, flask crafting, cluster crafting, and map/logbook package premium. Each pack must include `strategy.toml`, `discover.sql`, `backtest.sql`, human-readable notes, and explicit execution-venue metadata.
  **Must NOT do**: Do not start with Watcher's Eye, high-dimensional rare-item, or corruption-ladder strategies before the boring strategies are working.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: multiple strategy packs must share one clean runtime pattern.
  - Skills: [] — SQL-pack infrastructure already exists from earlier tasks.
  - Omitted: [`ultrabrain`] — these are intentionally high-confidence, low-ambiguity packs.

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 23,24,25,26,27,28 | Blocked By: 16,17,18,19,20

  **References**:
  - Pattern: `NeoPlanus.md:930` — Priority-1 strategy ladder.
  - Pattern: `NeoPlanus.md:936` — bulk convenience targets.
  - Pattern: `NeoPlanus.md:959` — fragment/set assembly rationale.
  - Pattern: `NeoPlanus.md:974` — flask crafting rationale.
  - Pattern: `NeoPlanus.md:985` — cluster crafting rationale.
  - Pattern: `NeoPlanus.md:995` — map/logbook package premium rationale.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-ledger-cli strategy list` shows all Priority-1 packs as loadable/enabled candidates with venue metadata.
  - [ ] Each pack has `strategies/<id>/strategy.toml`, `strategies/<id>/notes.md`, `poe_trade/sql/strategy/<id>/discover.sql`, and `poe_trade/sql/strategy/<id>/backtest.sql` present.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path priority-pack discovery
    Tool: Bash
    Steps: Run `poe-ledger-cli strategy list` and `rg -n "bulk_essence|bulk_fossil|fragment_sets|flask|cluster|logbook" strategies poe_trade/sql/strategy`.
    Expected: All Priority-1 packs are present and loadable through the strategy runtime.
    Evidence: .sisyphus/evidence/task-21-priority-strategies.txt

  Scenario: Failure path advanced-pack creep blocked
    Tool: Bash
    Steps: Run `rg -n "watcher|double corrupt|high-dimensional|forbidden pair" strategies poe_trade/sql/strategy`.
    Expected: Advanced pack work has not leaked into the Priority-1 implementation task.
    Evidence: .sisyphus/evidence/task-21-priority-strategies-error.txt
  ```

  **Commit**: YES | Message: `feat(strategy): add priority one packs` | Files: `strategies/`, `poe_trade/sql/strategy/`

- [ ] 22. Implement the Priority-2 strategy pack set

  **What to do**: Add the second NeoPlanus strategy family: Rog valuation, scarab reroll/vendor-loop arbitrage, CX market making and cross-rate dislocations, dump-tab and half-finished item repricing, and fossil-scarcity tracking. Use the gold marts and CX/PS current-state layers already built; only add `eval.py` where the pack truly needs bounded stochastic logic.
  **Must NOT do**: Do not bypass the strategy-pack runtime or skip venue-aware logic for CX/manual trade differences.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: these packs are more context-sensitive and capital-aware.
  - Skills: [] — prior strategy scaffolding is sufficient.
  - Omitted: [`frontend-ui-ux`] — strategy logic only.

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 23,24,25,26,27,28 | Blocked By: 16,17,18,19,20

  **References**:
  - Pattern: `NeoPlanus.md:1005` — Priority-2 strategy ladder.
  - Pattern: `NeoPlanus.md:1007` — Rog engine rationale.
  - Pattern: `NeoPlanus.md:1017` — scarab reroll rationale.
  - Pattern: `NeoPlanus.md:1028` — CX market-making rationale.
  - Pattern: `NeoPlanus.md:1039` — dump-tab repricing rationale.
  - Pattern: `NeoPlanus.md:189` — 3.28 supply shifts affecting fossils and cluster valuation.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-ledger-cli strategy list` shows all Priority-2 packs with correct venue/latency metadata.
  - [ ] Backtest and discover SQL exist for each Priority-2 pack, with optional `eval.py` only where bounded advanced logic is justified.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path priority-two pack discovery
    Tool: Bash
    Steps: Run `poe-ledger-cli strategy list` and `rg -n "rog|scarab|cx|dump_tab|fossil" strategies poe_trade/sql/strategy`.
    Expected: All Priority-2 packs are present and registered with the runtime.
    Evidence: .sisyphus/evidence/task-22-priority-two-strategies.txt

  Scenario: Failure path venue metadata missing
    Tool: Bash
    Steps: Run `rg -n "execution_venue|latency_class|capital_tier" strategies/*/strategy.toml`.
    Expected: Every Priority-2 pack declares venue/latency/capital metadata explicitly.
    Evidence: .sisyphus/evidence/task-22-priority-two-strategies-error.txt
  ```

  **Commit**: YES | Message: `feat(strategy): add priority two packs` | Files: `strategies/`, `poe_trade/sql/strategy/`, `poe_trade/strategy/`

- [ ] 23. Build scanner recommendations, alert suppression, and output modes

  **What to do**: Implement `scanner_recommendations`, `scanner_alert_log`, continuous and one-shot scan flows, and the suppression model described in NeoPlanus: thresholds, fill probability, cooldowns, max alerts per run, capital budgets, venue filters, and stale-candidate dedupe. Emit delayed recommendation outputs as the core mode, with markdown/JSON/terminal formats first and any browser-search plugin isolated as optional/non-core.
  **Must NOT do**: Do not make unsupported browser/trade-site behavior a dependency for scanner usefulness.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the first operator-facing decision engine.
  - Skills: [] — current CLI/report/runtime layers are enough.
  - Omitted: [`playwright`] — no browser automation should be required for the core scanner path.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: 25,26,27,28,29 | Blocked By: 16,17,18,19,20,21

  **References**:
  - Pattern: `NeoPlanus.md:1097` — scanner/output shape.
  - Pattern: `NeoPlanus.md:1120` — alert suppression requirements.
  - Pattern: `NeoPlanus.md:1139` — delayed recommendation mode vs optional browser-search mode.
  - Pattern: `NeoPlanus.md:1518` — scanner deliverables and exit criteria.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-ledger-cli scan once --league Mirage`, `poe-ledger-cli scan watch --league Mirage`, `poe-ledger-cli alerts list`, and `poe-ledger-cli alerts ack --id sample-alert` run through the CLI and write `scanner_recommendations` / `scanner_alert_log`.
  - [ ] Recommendation rows include the full NeoPlanus output shape: strategy id, why it fired, buy/transform/exit plan, venue, profit, ROI, hold time, confidence, and evidence snapshot.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path scanner emission
    Tool: Bash
    Steps: Run `poe-ledger-cli scan once --league Mirage`, then `poe-ledger-cli alerts list` and inspect the resulting recommendation and alert rows.
    Expected: The scanner emits actionable delayed recommendations and suppression controls behave as configured.
    Evidence: .sisyphus/evidence/task-23-scanner.txt

  Scenario: Failure path unsupported browser dependency absent
    Tool: Bash
    Steps: Run `rg -n "browser search|trade site|selenium|playwright" poe_trade/strategy poe_trade/analytics README.md docs`.
    Expected: Any browser-search path is clearly optional and not required for the scanner to function.
    Evidence: .sisyphus/evidence/task-23-scanner-error.txt
  ```

  **Commit**: YES | Message: `feat(scanner): add recommendations and alert suppression` | Files: `poe_trade/strategy/`, `poe_trade/analytics/`, `schema/migrations/*.sql`, `README.md`

- [ ] 24. Add journal tables, manual execution flows, and the truth loop

  **What to do**: Implement `journal_events`, `journal_positions`, and the CLI commands needed to record buy/sell/craft/corrupt/list actions, attach scanner recommendations to actual actions, compute realized PnL, and compare realized vs predicted outcomes. If a `Client.txt` importer is added, keep it fully optional, explicit opt-in, and isolated from the core architecture.
  **Must NOT do**: Do not make log-file ingestion mandatory, automatic, or hidden from the operator.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this closes the loop between recommendations, backtests, and reality.
  - Skills: [] — current runtime plus CLI/reporting layers suffice.
  - Omitted: [`playwright`] — no browser dependency.

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 25,26,27,28,29 | Blocked By: 19,20,23

  **References**:
  - Pattern: `NeoPlanus.md:1483` — journal and truth-loop phase.
  - Pattern: `NeoPlanus.md:1497` — target journal deliverables.
  - Pattern: `NeoPlanus.md:1079` — journal is the eventual source of truth in the fill hierarchy.
  - External: `https://www.pathofexile.com/developer/docs/index#guidelines` — log reading is allowed only when the user is aware of it.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-ledger-cli journal buy --strategy bulk_essence --league Mirage --item-or-market-key sample-1 --price-chaos 100 --quantity 20` and `poe-ledger-cli journal sell --strategy bulk_essence --league Mirage --item-or-market-key sample-1 --price-chaos 145 --quantity 20` persist events/positions, and `poe-ledger-cli report daily --league Mirage` produces realized-vs-predicted output.
  - [ ] `rg -n "journal_events|journal_positions|realized|predicted|Client.txt" poe_trade schema README.md docs` shows opt-in truth-loop support with no hidden log-ingest path.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path journal round-trip
    Tool: Bash
    Steps: Run `poe-ledger-cli journal buy --strategy bulk_essence --league Mirage --item-or-market-key sample-1 --price-chaos 100 --quantity 20`, `poe-ledger-cli journal sell --strategy bulk_essence --league Mirage --item-or-market-key sample-1 --price-chaos 145 --quantity 20`, then `poe-ledger-cli report daily --league Mirage`.
    Expected: Journal data writes successfully and the report links paper expectations to realized outcome.
    Evidence: .sisyphus/evidence/task-24-journal.txt

  Scenario: Failure path hidden log ingestion blocked
    Tool: Bash
    Steps: Run `rg -n "Client.txt|tail -f|watch file|automatic import" poe_trade README.md docs`.
    Expected: Any log-file importer is explicitly opt-in and non-core.
    Evidence: .sisyphus/evidence/task-24-journal-error.txt
  ```

  **Commit**: YES | Message: `feat(journal): add execution truth loop` | Files: `poe_trade/strategy/`, `schema/migrations/*.sql`, `README.md`, `docs/ops-runbook.md`

- [ ] 25. Align docs, examples, and the test suite with the shipped runtime

  **What to do**: Update `README.md`, `docs/ops-runbook.md`, `.env.example`, and the unit suite so they describe and verify the new queue-based daemon, CX support, refresh/research/scan/journal commands, ClickHouse-only checkpoints, and gold/silver sanity flow. Add or rewrite tests for scheduler, CXAPI, strategy runtime, scanner, journal, and CLI routing until the verification surface matches the shipped architecture.
  **Must NOT do**: Do not leave ingestion-only, checkpoint-file, or dropped-view guidance in place after the code moves on.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: this task is primarily documentation and verification alignment after code work stabilizes.
  - Skills: [`docs-specialist`] — needed for terse, accurate operational docs.
  - Omitted: [`protocol-compat`] — schema work is already complete here.

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 29,30 | Blocked By: 21,22,23,24

  **References**:
  - Pattern: `README.md:3` — current docs still present an ingestion-pack-only runtime.
  - Pattern: `docs/ops-runbook.md:17` — current failure recovery still references checkpoint files.
  - Pattern: `.env.example:6` — current example env still uses checkpoint dirs and `POE_LEAGUES`.
  - Pattern: `tests/AGENTS.md:7` — current suite focus areas to expand.
  - Pattern: `NeoPlanus.md:1535` — later phases still require reliable operator flow and verification.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/pytest tests/unit` passes after the test surface is expanded.
  - [ ] `rg -n "POE_CHECKPOINT_DIR|POE_CURSOR_DIR|POE_LEAGUES|v_ops_ingest_health|api/trade/data" README.md docs .env.example tests` shows no stale core-runtime guidance.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path full repo verification
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit`, `.venv/bin/python -m poe_trade.cli --help`, and the bronze/silver/gold sanity SQL commands.
    Expected: Tests, CLI help, and sanity SQL all align with the shipped runtime and documentation.
    Evidence: .sisyphus/evidence/task-25-docs-tests.txt

  Scenario: Failure path stale docs sweep
    Tool: Bash
    Steps: Run `rg -n "POE_CHECKPOINT_DIR|POE_CURSOR_DIR|POE_LEAGUES|v_ops_ingest_health|api/trade/data" README.md docs .env.example tests`.
    Expected: Stale checkpoint-file, dropped-view, or undocumented-endpoint guidance is removed from operator-facing docs/tests.
    Evidence: .sisyphus/evidence/task-25-docs-tests-error.txt
  ```

  **Commit**: YES | Message: `test(docs): align verification and runtime guides` | Files: `README.md`, `docs/ops-runbook.md`, `.env.example`, `tests/unit/`

- [ ] 26. Add the advanced strategy pack with explicit confidence gating

  **What to do**: Implement the advanced NeoPlanus pack only after the boring packs, scanner, and journal are stable: corruption EV ladders, Watcher's Eye / high-dimensional jewels, forbidden pair matching, double-corrupt targets, and advanced rare finishing. Gate each pack behind stricter confidence thresholds, capital requirements, and journal-backed truth requirements so hype does not outrun evidence.
  **Must NOT do**: Do not surface advanced strategies as equal-confidence recommendations before journal calibration and backtest evidence exist.

  **Recommended Agent Profile**:
  - Category: `ultrabrain` — Reason: these are the highest-variance, highest-complexity strategies in the roadmap.
  - Skills: [] — existing runtime is sufficient; the challenge is evaluation discipline.
  - Omitted: [`frontend-ui-ux`] — strategy logic only.

  **Parallelization**: Can Parallel: YES | Wave 6 | Blocks: 30 | Blocked By: 19,21,22,23,24

  **References**:
  - Pattern: `NeoPlanus.md:1047` — Priority-3 advanced strategy ladder.
  - Pattern: `NeoPlanus.md:1093` — do not overstate Class C reliability before journal data exists.
  - Pattern: `NeoPlanus.md:1553` — phase-8 advanced pack and hardening scope.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `poe-ledger-cli strategy list` marks advanced packs as gated or disabled until their confidence requirements are met.
  - [ ] Advanced packs include explicit notes/evaluators describing why journal or higher-confidence evidence is required.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path advanced-pack registration
    Tool: Bash
    Steps: Run `poe-ledger-cli strategy list` and inspect metadata for the advanced packs.
    Expected: Advanced packs exist but are clearly gated behind stricter confidence/journal requirements.
    Evidence: .sisyphus/evidence/task-26-advanced-pack.txt

  Scenario: Failure path overconfident ranking blocked
    Tool: Bash
    Steps: Run `rg -n "confidence|journal|required|capital_tier" strategies/*/strategy.toml strategies/*/notes.md`.
    Expected: Advanced packs do not present themselves as default safe strategies without explicit gating.
    Evidence: .sisyphus/evidence/task-26-advanced-pack-error.txt
  ```

  **Commit**: YES | Message: `feat(strategy): add advanced gated packs` | Files: `strategies/`, `poe_trade/sql/strategy/`, `poe_trade/strategy/`

- [ ] 27. Add rebuild tooling, retention tuning, and data-lifecycle controls

  **What to do**: Finish the NeoPlanus hardening story by implementing reliable silver/gold rebuild commands, retention/TTL tuning for bronze/silver/CX data, and explicit rebuild-from-cutover support when logic changes materially. Make rebuild and retention behavior visible in config and operational docs, with separate defaults for raw PS, raw CX, and silver retention windows.
  **Must NOT do**: Do not leave data-lifecycle behavior implicit or tie rebuilds to destructive manual SQL steps.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: rebuild reliability and data retention directly affect operator trust.
  - Skills: [`protocol-compat`] — TTL/rebuild changes touch persistent data contracts.
  - Omitted: [`docs-specialist`] — docs are updated downstream.

  **Parallelization**: Can Parallel: YES | Wave 6 | Blocks: 29,30 | Blocked By: 15,16,17,18,19,20,21,22,23,24

  **References**:
  - Pattern: `.env.example:1` — current env example has no NeoPlanus retention controls.
  - Pattern: `NeoPlanus.md:755` — rebuild philosophy.
  - Pattern: `NeoPlanus.md:1246` — recommended retention variables.
  - Pattern: `NeoPlanus.md:1561` — phase-8 performance/rebuild/retention scope.

  **Acceptance Criteria** (agent-executable only):
  - [ ] The CLI exposes bounded rebuild commands for silver and gold, including cutover-aware rebuild entrypoints.
  - [ ] Config/docs expose separate retention knobs for raw PS, raw CX, and silver data.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path rebuild command exposure
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli --help` and inspect rebuild-related commands and options.
    Expected: Silver/gold rebuild commands are visible and aligned with the retention/config model.
    Evidence: .sisyphus/evidence/task-27-rebuild-retention.txt

  Scenario: Failure path hidden destructive rebuild avoided
    Tool: Bash
    Steps: Run `rg -n "DROP TABLE|TRUNCATE|manual sql step|hard reset" poe_trade README.md docs schema`.
    Expected: No rebuild path depends on undocumented destructive operator steps.
    Evidence: .sisyphus/evidence/task-27-rebuild-retention-error.txt
  ```

  **Commit**: YES | Message: `feat(ops): add rebuild and retention controls` | Files: `poe_trade/cli.py`, `poe_trade/analytics/`, `.env.example`, `README.md`, `docs/ops-runbook.md`

- [ ] 28. Add SQL/model CI and full migration verification harness

  **What to do**: Implement CI or repo-local validation that catches broken migrations and SQL models before release, including clean-install migration, upgrade-path migration from the current repo state, sanity SQL execution, and representative CLI smoke checks. Make the verification harness fast enough for routine use and strict enough to stop broken SQL or stale docs from landing.
  **Must NOT do**: Do not stop at unit tests only or assume SQL correctness without executing the actual assets.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this hardens the whole architecture against regression.
  - Skills: [`protocol-compat`] — migration verification is a contract problem.
  - Omitted: [`docs-specialist`] — docs are only supporting artifacts here.

  **Parallelization**: Can Parallel: YES | Wave 6 | Blocks: 29,30 | Blocked By: 15,16,17,18,19,20,21,22,23,24

  **References**:
  - Pattern: `tests/unit/test_migrations.py:133` — current migration test surface is useful but incomplete.
  - Pattern: `README.md:45` — current migration workflow is already documented and can be expanded.
  - Pattern: `NeoPlanus.md:1564` — CI for SQL models is part of phase 8.
  - Pattern: `NeoPlanus.md:1578` — whole-project acceptance criteria require repeatable automated verification.

  **Acceptance Criteria** (agent-executable only):
  - [ ] The repo contains an executable validation path that runs migrations, sanity SQL, and CLI smoke checks in one automated flow.
  - [ ] `.venv/bin/pytest tests/unit/test_migrations.py` still passes and the new harness covers clean-install plus upgrade-path behavior.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path full validation harness
    Tool: Bash
    Steps: Run the SQL/model validation workflow introduced in this task.
    Expected: Clean-install, upgrade-path, sanity SQL, and CLI smoke checks all pass in one automated sequence.
    Evidence: .sisyphus/evidence/task-28-sql-ci.txt

  Scenario: Failure path broken SQL caught early
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_migrations.py` and the new validation workflow against a deliberately stale or missing object set if supported.
    Expected: The harness fails fast when migrations or SQL models are inconsistent.
    Evidence: .sisyphus/evidence/task-28-sql-ci-error.txt
  ```

  **Commit**: YES | Message: `test(ci): add sql and migration validation harness` | Files: `tests/unit/`, `schema/sanity/`, CI/workflow config, `README.md`

- [ ] 29. Remove deprecated compatibility surfaces and freeze legacy artifacts

  **What to do**: After all core functionality is migrated, delete or hard-error the deprecated runtime surfaces that would otherwise keep the old model alive: file-checkpoint runtime, `POE_LEAGUES` daemon behavior, bootstrap-only ingestion flags, old trade-metadata core path, and stale operator guidance. Leave legacy tables readable only where the plan explicitly calls for compatibility, and mark them as frozen/non-core.
  **Must NOT do**: Do not keep silent compatibility shims that still affect runtime semantics.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: by this point the task is cleanup with explicit removal criteria.
  - Skills: [] — straightforward repo cleanup.
  - Omitted: [`protocol-compat`] — only frozen/read-only legacy artifacts remain.

  **Parallelization**: Can Parallel: NO | Wave 6 | Blocks: 30 | Blocked By: 27,28

  **References**:
  - Pattern: `poe_trade/ingestion/checkpoints.py:1` — legacy file-checkpoint module.
  - Pattern: `poe_trade/services/market_harvester.py:37` — legacy CLI flags still present today.
  - Pattern: `.env.example:6` — deprecated env surface to finish removing.
  - Pattern: `NeoPlanus.md:1593` — final doctrine rules for coding agents and runtime shape.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `rg -n "CheckpointStore|POE_LEAGUES|POE_CHECKPOINT_DIR|POE_CURSOR_DIR|bootstrap_until_league|api/trade/data" poe_trade README.md docs tests` returns only explicit frozen-legacy notes or no matches.
  - [ ] `.venv/bin/python -m poe_trade.cli --help` still exposes the supported command surface without deprecated runtime controls.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path deprecated-surface removal
    Tool: Bash
    Steps: Run the repo-wide `rg` sweep for deprecated env flags, file checkpoints, and the old metadata path.
    Expected: Deprecated runtime surfaces are gone or hard-failed, not silently supported.
    Evidence: .sisyphus/evidence/task-29-compat-cleanup.txt

  Scenario: Failure path stale shim detection
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli --help` and inspect for legacy runtime flags.
    Expected: The help output does not advertise deprecated queue-breaking behavior.
    Evidence: .sisyphus/evidence/task-29-compat-cleanup-error.txt
  ```

  **Commit**: YES | Message: `chore(runtime): remove deprecated compatibility shims` | Files: `poe_trade/`, `.env.example`, `README.md`, `docs/ops-runbook.md`, `tests/unit/`

- [ ] 30. Add the optional TUI/report polish gate without making it core

  **What to do**: If and only if all core CLI/scanner/journal/ref flows are stable, add the optional `poe-ledger-cli tui` or richer terminal output layer using `rich`/`textual` semantics, keeping it as a thin presentation shell over the existing gold/scanner/journal queries. If the repo is not yet stable enough, implement only the command/feature flag and document it as deferred so the optional interface does not distort the core architecture.
  **Must NOT do**: Do not promote the TUI into a required dependency for operating the platform or let it block core verification/release readiness.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: optional but cross-cutting operator polish work.
  - Skills: [] — terminal-only presentation layer.
  - Omitted: [`frontend-ui-ux`] — this is still CLI/TUI, not web UI.

  **Parallelization**: Can Parallel: NO | Wave 6 | Blocks: Final verification wave only | Blocked By: 25,26,27,28,29

  **References**:
  - Pattern: `NeoPlanus.md:75` — CLI first, TUI second.
  - Pattern: `NeoPlanus.md:1199` — optional later `poe-ledger-cli tui` command.
  - Pattern: `NeoPlanus.md:1509` — scanner and optional TUI phase.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/python -m poe_trade.cli --help` either exposes `tui` as an optional command or clearly omits it with documented deferment.
  - [ ] The core scanner/report/journal commands remain fully usable without the TUI enabled.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```text
  Scenario: Happy path optional TUI gate
    Tool: Bash
    Steps: Run `.venv/bin/python -m poe_trade.cli --help` and, if implemented, run `poe-ledger-cli tui --help`.
    Expected: The TUI is clearly optional and layered on top of existing CLI functionality.
    Evidence: .sisyphus/evidence/task-30-tui-gate.txt

  Scenario: Failure path core dependency regression prevented
    Tool: Bash
    Steps: Run scanner/report/journal commands without enabling the TUI.
    Expected: Core terminal workflows continue to operate without the TUI path.
    Evidence: .sisyphus/evidence/task-30-tui-gate-error.txt
  ```

  **Commit**: YES | Message: `feat(cli): add optional tui gate` | Files: `poe_trade/cli.py`, `poe_trade/analytics/`, `README.md`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Use atomic commits per task unless a wave-specific pair of tightly coupled tasks must land together.
- Keep migration commits isolated from Python/runtime commits when possible.
- Never amend previously pushed commits; if hooks auto-modify files during execution, create a new commit unless the executor explicitly owns the immediately preceding unpublished commit.

## Success Criteria
- One daemon continuously syncs PSAPI and CXAPI without manual cursor handling.
- ClickHouse is the only persistent state store for core runtime behavior.
- Core transforms are expressed as ClickHouse MVs, views, and scheduled SQL refreshes.
- Strategies are SQL packs with TOML metadata and bounded optional Python evaluators.
- Scanner output is actionable, backtests are rerunnable, journal data closes the loop, and optional browser/TUI paths are non-core add-ons.
- No undocumented PoE endpoint or obsolete repo artifact is required for the shipped architecture.
