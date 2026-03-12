# Backtest Results Summary Contract

## TL;DR
> **Summary**: Replace the current raw-row, SQL-first backtest output with a shared typed summary contract that enforces `league` and `lookback_days`, prints human-readable CLI results, and preserves optional drill-down detail for all strategy packs.
> **Deliverables**:
> - Shared backtest summary contract and run outcome taxonomy
> - Additive ClickHouse storage for typed summary/detail rows
> - Refactored backtest runner with explicit filter semantics and failure handling
> - Updated `research backtest` and `research backtest-all` CLI output
> - Strategy SQL updates for all registered packs
> - Pytest coverage plus agent-executed DB/CLI QA evidence
> **Effort**: Large
> **Parallel**: YES - 2 waves
> **Critical Path**: 1 -> 2 -> 3 -> 7 -> 8

## Context
### Original Request
Backtesting the strategies still does not give proper results. Confirm whether that is correct and produce a work plan to fix it.

### Interview Summary
- Current behavior is not acceptable for the stated goal.
- User wants human-readable backtest results, not raw stored rows.
- Scope covers all strategies, not a pilot-only implementation.
- Test strategy is tests-after with existing pytest coverage.

### Metis Review (gaps addressed)
- Lock the summary contract before implementation.
- Keep schema evolution additive; do not repurpose old ClickHouse history in place.
- Separate summary rows from drill-down detail.
- Distinguish `no_data`, `no_opportunities`, `completed`, and `failed` outcomes.
- Avoid scope creep into scanner redesign or execution simulation.

## Work Objectives
### Core Objective
Make every strategy backtest produce consistent, human-readable, league/window-scoped output in both CLI and persisted ClickHouse records.

### Deliverables
- Shared typed summary contract used by all strategy backtests.
- Shared detail contract for optional drill-down rows.
- Backtest runner that applies explicit league/window semantics and run status handling.
- CLI output for `research backtest` and `research backtest-all` that prints readable tabular summaries instead of bare run ids and row counts.
- Updated `backtest.sql` files for every strategy pack to conform to the shared contract.
- Unit coverage for runner behavior, storage semantics, zero-result handling, and CLI output.

### Definition of Done (verifiable conditions with commands)
- `.venv/bin/pytest tests/unit/test_strategy_backtest.py tests/unit/test_cli_research.py` passes with assertions for summary output, outcome status, and filter semantics.
- `.venv/bin/python -m poe_trade.cli research backtest --strategy bulk_essence --league Mirage --days 14` prints a tabular summary with the header `run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary`.
- `.venv/bin/python -m poe_trade.cli research backtest-all --league Mirage --days 14 --enabled-only` prints one summary row per enabled strategy using the same header and does not print only `result_rows` counts.
- `clickhouse-client --query "SELECT status, count() FROM poe_trade.research_backtest_summary WHERE run_id = '<run_id>' GROUP BY status ORDER BY status"` returns explicit typed statuses rather than opaque JSON-only rows.
- Running the same strategy with a different league or lookback window changes persisted summary/detail results or returns explicit `no_data`/`no_opportunities` status.

### Must Have
- Shared summary schema for all strategies.
- Shared outcome taxonomy: `completed`, `no_data`, `no_opportunities`, `failed`.
- Universal enforcement of `league` and `lookback_days` in backtest execution.
- Human-readable CLI output for single and bulk backtests.
- Additive persistence for summaries and optional detail rows.
- Tests and evidence for zero-data and failure cases.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- No scanner redesign, no journal-truth redesign, no fill simulator.
- No per-strategy bespoke summary schemas.
- No destructive migration of existing `research_backtest_results` history.
- No success criteria based solely on non-zero row counts.
- No manual-only verification.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after with `pytest`
- QA policy: every task includes agent-executed happy-path and failure/edge-path scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. Extract shared dependencies early so later work can parallelize safely.

Wave 1: contract and foundation tasks - 1, 2, 3, 4, 5
Wave 2: implementation and verification tasks - 6, 7, 8, 9, 10

### Dependency Matrix (full, all tasks)
| Task | Depends On |
| --- | --- |
| 1 | - |
| 2 | 1 |
| 3 | 1, 2 |
| 4 | 1 |
| 5 | 1 |
| 6 | 1, 3, 4 |
| 7 | 1, 3, 5 |
| 8 | 3, 4, 6, 7 |
| 9 | 6, 7, 8 |
| 10 | 6, 7, 8, 9 |

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 5 tasks -> `deep`, `quick`, `unspecified-high`
- Wave 2 -> 5 tasks -> `deep`, `quick`, `writing`, `unspecified-high`

## TODOs
> Implementation + Test = ONE task. Never separate.
> Every task must include Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Define the shared backtest summary and detail contract

  **What to do**: Introduce one canonical column contract for backtest summaries and one optional detail contract, then centralize the ordered column/header list in Python so runner and CLI use the same schema. Use this exact summary column order for both single and bulk backtest CLI output: `run_id`, `strategy_id`, `league`, `lookback_days`, `status`, `opportunity_count`, `expected_profit_chaos`, `expected_roi`, `confidence`, `summary`. Define detail rows as drill-down only, not the primary operator surface.
  **Must NOT do**: Do not let each strategy choose its own summary shape. Do not store opaque JSON as the only human-readable output.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: this task fixes the core contract every other task depends on.
  - Skills: [`protocol-compat`] - Reason: storage and schema decisions must stay additive and compatibility-safe.
  - Omitted: [`docs-specialist`] - Reason: contract must be encoded in code/tests first, not optimized as prose.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2, 3, 4, 5, 6, 7 | Blocked By: none

  **References**:
  - Pattern: `poe_trade/cli.py:429` - Existing tabular CLI output shape to mirror for readable results.
  - Pattern: `NeoPlanus.md:1099` - Existing recommendation vocabulary to reuse where fields overlap.
  - API/Type: `poe_trade/strategy/backtest.py:19` - Current runner entry point that needs a typed contract.
  - API/Type: `schema/migrations/0028_research_backtests.sql:13` - Current raw-results storage that lacks typed summary fields.
  - Test: `tests/unit/test_strategy_backtest.py:21` - Existing backtest test module to expand.
  - Test: `tests/unit/test_cli_research.py:61` - Existing CLI research test module to expand.

  **Acceptance Criteria**:
  - [ ] `.venv/bin/pytest tests/unit/test_strategy_backtest.py -k "summary or contract or status"` passes and asserts the shared summary contract.
  - [ ] `grep -R "run_id\\tstrategy_id\\tleague\\tlookback_days\\tstatus\\topportunity_count\\texpected_profit_chaos\\texpected_roi\\tconfidence\\tsummary" poe_trade tests/unit` returns at least one code/test reference using the canonical header.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Shared contract is encoded once
    Tool: Bash
    Steps: Run `grep -R "opportunity_count.*expected_profit_chaos.*expected_roi.*confidence.*summary" poe_trade tests/unit`
    Expected: One shared constant/helper definition is referenced by runner and CLI tests; no per-strategy alternate headers appear.
    Evidence: .sisyphus/evidence/task-1-contract.txt

  Scenario: Status taxonomy is explicit
    Tool: Bash
    Steps: Run `grep -R "no_data\|no_opportunities\|completed\|failed" poe_trade/strategy tests/unit`
    Expected: All four statuses are present in code/tests and referenced by the backtest path.
    Evidence: .sisyphus/evidence/task-1-statuses.txt
  ```

  **Commit**: NO | Message: `feat(backtest): define shared summary contract` | Files: `poe_trade/strategy/*`, `tests/unit/*`

- [ ] 2. Add additive ClickHouse storage for summary and detail backtest rows

  **What to do**: Create a new migration that preserves `research_backtest_runs` and raw-history compatibility while adding typed storage for summary rows and optional detail rows. Use additive tables such as `poe_trade.research_backtest_summary` and `poe_trade.research_backtest_detail`; keep `run_id`, `strategy_id`, `league`, `lookback_days`, `status`, and summary metrics typed in the summary table.
  **Must NOT do**: Do not edit `schema/migrations/0028_research_backtests.sql`. Do not drop or repurpose `poe_trade.research_backtest_results` in place.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: ClickHouse contract evolution must be correct on the first pass.
  - Skills: [`protocol-compat`] - Reason: additive schema discipline is mandatory.
  - Omitted: [`docs-specialist`] - Reason: migration correctness matters before documentation.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 3, 8, 10 | Blocked By: 1

  **References**:
  - Pattern: `schema/migrations/0028_research_backtests.sql:1` - Existing run/results storage to preserve.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:1` - Gold mart typing patterns and table conventions.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:43` - Example typed numeric columns for summary metrics.
  - External: `AGENTS.md` - Project rule: additive ClickHouse changes only.

  **Acceptance Criteria**:
  - [ ] `poe-migrate --status --dry-run` shows exactly one new pending additive migration for backtest summary/detail storage.
  - [ ] `grep -R "CREATE TABLE IF NOT EXISTS poe_trade.research_backtest_summary\|CREATE TABLE IF NOT EXISTS poe_trade.research_backtest_detail" schema/migrations` returns the new table DDL.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Migration is additive and discoverable
    Tool: Bash
    Steps: Run `poe-migrate --status --dry-run`
    Expected: Output lists the new migration as pending without modifying existing migrations.
    Evidence: .sisyphus/evidence/task-2-migrate-status.txt

  Scenario: Legacy storage remains untouched
    Tool: Bash
    Steps: Run `grep -R "research_backtest_results" schema/migrations && grep -R "research_backtest_summary\|research_backtest_detail" schema/migrations`
    Expected: Existing raw-results table still exists in old migration; new summary/detail tables are introduced separately.
    Evidence: .sisyphus/evidence/task-2-storage.txt
  ```

  **Commit**: NO | Message: `feat(schema): add typed backtest summary storage` | Files: `schema/migrations/*`

- [ ] 3. Refactor the backtest runner to enforce filters, statuses, and typed inserts

  **What to do**: Update `run_backtest()` to (a) inject `league` and `lookback_days` semantics into backtest execution, (b) write explicit summary/detail rows instead of only raw JSON blobs, and (c) persist `failed` status when any insert/query step errors. Use one universal wrapper around strategy SQL so all strategies receive the same filter variables and output contract.
  **Must NOT do**: Do not leave filter application to caller convention. Do not mark runs `completed` if summary/detail insertion fails.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: this is the behavioral center of the backtest pipeline.
  - Skills: [] - Reason: repo-native patterns are enough once the contract is fixed.
  - Omitted: [`protocol-compat`] - Reason: schema decisions are handled in Task 2; this task consumes them.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 6, 7, 8, 9 | Blocked By: 1, 2

  **References**:
  - Pattern: `poe_trade/strategy/backtest.py:31` - Current verbatim SQL read.
  - Pattern: `poe_trade/strategy/backtest.py:36` - Current run insert before result execution.
  - Pattern: `poe_trade/strategy/backtest.py:43` - Current raw results insert.
  - Pattern: `poe_trade/strategy/backtest.py:54` - Current unconditional completed status write.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:2` - Time bucket column used for lookback filters.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:4` - League column available for filter enforcement.

  **Acceptance Criteria**:
  - [ ] `.venv/bin/pytest tests/unit/test_strategy_backtest.py -k "run_backtest or status or filter"` passes with assertions that changing `league`/`days` changes the emitted SQL or status.
  - [ ] A forced query failure in tests results in a persisted `failed` run status instead of a false `completed` row.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: League and lookback are applied universally
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_strategy_backtest.py -k "league or lookback or filter" -q`
    Expected: Tests prove the runner applies both filters to the generated execution path.
    Evidence: .sisyphus/evidence/task-3-filters.txt

  Scenario: Failure state is explicit
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_strategy_backtest.py -k "failed" -q`
    Expected: Tests prove failed inserts/queries write `failed` status and do not emit a completed summary row.
    Evidence: .sisyphus/evidence/task-3-failed.txt
  ```

  **Commit**: NO | Message: `feat(backtest): enforce filter-aware run semantics` | Files: `poe_trade/strategy/backtest.py`, `tests/unit/test_strategy_backtest.py`

- [ ] 4. Rewrite listing-backed strategy backtests to emit the shared summary/detail shape

  **What to do**: Update the `backtest.sql` files backed by `gold_listing_ref_hour` so each query returns the shared contract fields expected by Task 1 and supports the universal wrapper from Task 3. Include at least `advanced_rare_finish`, `corruption_ev`, `flask_basic`, and `high_dim_jewels`; preserve category/base-type intent while replacing `SELECT *` output with explicit summary/detail columns.
  **Must NOT do**: Do not keep wildcard `SELECT *` outputs. Do not omit strategy-specific `summary` text that explains what the row means.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: multiple SQL assets need coordinated but bounded edits.
  - Skills: [`protocol-compat`] - Reason: result-shape changes must stay compatible with additive storage.
  - Omitted: [`docs-specialist`] - Reason: this is SQL contract work, not prose.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 8, 10 | Blocked By: 1

  **References**:
  - Pattern: `poe_trade/sql/strategy/advanced_rare_finish/backtest.sql:1` - Current listing-backed wildcard query.
  - Pattern: `poe_trade/sql/strategy/high_dim_jewels/backtest.sql:1` - Current listing-backed category filter.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:16` - Source mart columns available for listing strategies.
  - Test: `backtest_latest_results_mirage_14d.tsv:2` - Evidence that current strategy runs produce zero useful rows.

  **Acceptance Criteria**:
  - [ ] `grep -R "SELECT \*" poe_trade/sql/strategy/advanced_rare_finish poe_trade/sql/strategy/corruption_ev poe_trade/sql/strategy/flask_basic poe_trade/sql/strategy/high_dim_jewels` returns no matches.
  - [ ] Each listing-backed `backtest.sql` contains explicit references to `league` and `time_bucket` semantics through the shared wrapper contract or explicit predicates.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Listing-backed SQL is explicit
    Tool: Bash
    Steps: Run `grep -R "SELECT \*" poe_trade/sql/strategy/advanced_rare_finish poe_trade/sql/strategy/corruption_ev poe_trade/sql/strategy/flask_basic poe_trade/sql/strategy/high_dim_jewels`
    Expected: No wildcard selects remain.
    Evidence: .sisyphus/evidence/task-4-no-wildcards.txt

  Scenario: Listing-backed SQL supports filtering
    Tool: Bash
    Steps: Run `grep -R "league\|time_bucket" poe_trade/sql/strategy/advanced_rare_finish poe_trade/sql/strategy/corruption_ev poe_trade/sql/strategy/flask_basic poe_trade/sql/strategy/high_dim_jewels`
    Expected: Each strategy SQL references league/time semantics directly or via the chosen shared filter wrapper pattern.
    Evidence: .sisyphus/evidence/task-4-filters.txt
  ```

  **Commit**: NO | Message: `feat(backtest): normalize listing strategy summaries` | Files: `poe_trade/sql/strategy/advanced_rare_finish/backtest.sql`, `poe_trade/sql/strategy/corruption_ev/backtest.sql`, `poe_trade/sql/strategy/flask_basic/backtest.sql`, `poe_trade/sql/strategy/high_dim_jewels/backtest.sql`

- [ ] 5. Rewrite non-listing strategy backtests to emit the shared summary/detail shape

  **What to do**: Update the remaining `backtest.sql` files backed by `gold_bulk_premium_hour`, `gold_currency_ref_hour`, and `gold_set_ref_hour` so all enabled strategies emit the shared contract. Cover `bulk_essence`, `bulk_fossils`, `cluster_basic`, `cx_market_making`, `dump_tab_reprice`, `fossil_scarcity`, `fragment_sets`, `map_logbook_packages`, `rog_basic`, and `scarab_reroll`.
  **Must NOT do**: Do not special-case output columns by strategy. Do not rely on row-count-only success.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: many SQL assets need the same contract retrofit.
  - Skills: [`protocol-compat`] - Reason: shared output shape must remain storage-compatible.
  - Omitted: [`docs-specialist`] - Reason: SQL implementation work only.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 8, 10 | Blocked By: 1

  **References**:
  - Pattern: `poe_trade/sql/strategy/bulk_essence/backtest.sql:1` - Current bulk-premium wildcard query.
  - Pattern: `poe_trade/sql/strategy/cx_market_making/backtest.sql:1` - Current currency mart wildcard query.
  - Pattern: `poe_trade/sql/strategy/fragment_sets/backtest.sql:1` - Current set mart wildcard query.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:1` - Currency mart columns.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:43` - Bulk premium mart columns.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:58` - Set mart columns.

  **Acceptance Criteria**:
  - [ ] `grep -R "SELECT \*" poe_trade/sql/strategy/*/backtest.sql` returns no matches across all non-listing strategies after the retrofit.
  - [ ] All non-listing strategies emit the shared summary/detail columns expected by the runner and CLI tests.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Non-listing SQL is explicit
    Tool: Bash
    Steps: Run `grep -R "SELECT \*" poe_trade/sql/strategy/*/backtest.sql`
    Expected: No wildcard backtest queries remain anywhere in the strategy SQL tree.
    Evidence: .sisyphus/evidence/task-5-no-wildcards.txt

  Scenario: All strategies target the common contract
    Tool: Bash
    Steps: Run `grep -R "expected_profit_chaos\|expected_roi\|confidence\|summary" poe_trade/sql/strategy/*/backtest.sql`
    Expected: Every strategy backtest SQL includes the shared summary fields or aliases required by the contract.
    Evidence: .sisyphus/evidence/task-5-contract.txt
  ```

  **Commit**: NO | Message: `feat(backtest): normalize remaining strategy summaries` | Files: `poe_trade/sql/strategy/*/backtest.sql`

- [ ] 6. Render human-readable output for single-strategy backtests

  **What to do**: Change `poe_trade.cli research backtest` so it prints the shared summary header and one or more readable summary lines for the selected run, instead of only printing `run_id`. Keep `run_id` in the output as the first column for traceability, and print explicit `status` values for zero-result windows.
  **Must NOT do**: Do not hide the run identifier. Do not print a bare UUID as the only success output.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: one CLI path with a clear target output shape.
  - Skills: [] - Reason: existing CLI patterns are sufficient.
  - Omitted: [`docs-specialist`] - Reason: behavior first, docs later.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 9, 10 | Blocked By: 1, 3, 4

  **References**:
  - Pattern: `poe_trade/cli.py:335` - Current single-backtest command branch.
  - Pattern: `poe_trade/cli.py:347` - Current bare `run_id` print behavior.
  - Pattern: `poe_trade/cli.py:429` - Existing readable table rendering pattern from scanner output.
  - Test: `tests/unit/test_cli_research.py:20` - Existing single-backtest CLI test entry point.

  **Acceptance Criteria**:
  - [ ] `.venv/bin/pytest tests/unit/test_cli_research.py -k "research_backtest_command"` passes with assertions that stdout starts with the canonical header instead of a bare run id.
  - [ ] `.venv/bin/python -m poe_trade.cli research backtest --strategy bulk_essence --league Mirage --days 14 --dry-run` still behaves safely in dry-run mode and does not attempt summary queries against ClickHouse.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Single backtest prints a readable summary
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_cli_research.py -k "research_backtest_command" -q`
    Expected: Test proves stdout contains the canonical header and a readable summary line.
    Evidence: .sisyphus/evidence/task-6-cli-single.txt

  Scenario: Dry-run remains side-effect free
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_cli_research.py -k "dry_run" -q`
    Expected: Dry-run tests prove the command avoids ClickHouse summary reads/writes beyond the intended no-op path.
    Evidence: .sisyphus/evidence/task-6-dry-run.txt
  ```

  **Commit**: NO | Message: `feat(cli): print readable backtest summary` | Files: `poe_trade/cli.py`, `tests/unit/test_cli_research.py`

- [ ] 7. Render ranked human-readable output for bulk backtests

  **What to do**: Change `poe_trade.cli research backtest-all` so it prints the same canonical header and one summary row per strategy, sorted by status quality and expected profit. Use explicit rows for `no_data` and `no_opportunities` instead of silent zero counts.
  **Must NOT do**: Do not keep the current `strategy_id\trun_id\tresult_rows` contract. Do not suppress failed strategies from the table.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: one CLI branch with a fixed output contract.
  - Skills: [] - Reason: local repo patterns are enough.
  - Omitted: [`docs-specialist`] - Reason: CLI behavior first.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 9, 10 | Blocked By: 1, 3, 5

  **References**:
  - Pattern: `poe_trade/cli.py:349` - Current bulk-backtest branch.
  - Pattern: `poe_trade/cli.py:358` - Current `result_rows` header to replace.
  - Pattern: `poe_trade/cli.py:369` - Current per-run row-count query logic.
  - Test: `tests/unit/test_cli_research.py:61` - Existing bulk-backtest CLI tests.
  - Test: `backtest_run_ids_all.tsv:2` - Current sample output only tracks status/run ids.

  **Acceptance Criteria**:
  - [ ] `.venv/bin/pytest tests/unit/test_cli_research.py -k "backtest_all"` passes with assertions that stdout uses the canonical header and one readable row per strategy.
  - [ ] A failing or zero-result strategy still appears in output with explicit `status` and `summary` text.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Bulk backtest prints a full summary table
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_cli_research.py -k "backtest_all" -q`
    Expected: Tests prove stdout uses the canonical header and includes one row per strategy.
    Evidence: .sisyphus/evidence/task-7-cli-all.txt

  Scenario: Zero-result strategies stay visible
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_cli_research.py -k "no_opportunities or no_data or failed" -q`
    Expected: Tests prove non-success outcomes remain visible with explicit statuses and summaries.
    Evidence: .sisyphus/evidence/task-7-statuses.txt
  ```

  **Commit**: NO | Message: `feat(cli): summarize all backtest strategies` | Files: `poe_trade/cli.py`, `tests/unit/test_cli_research.py`

- [ ] 8. Add end-to-end unit coverage for runner, storage, and strategy contract conformance

  **What to do**: Expand the test suite so it verifies typed summary/detail inserts, explicit statuses, filter semantics, and strategy contract conformance. Add contract-level tests that iterate discovered strategy packs from the registry and assert every `backtest.sql` conforms to the shared column requirements.
  **Must NOT do**: Do not add live ClickHouse dependencies. Do not leave strategy conformance implicit.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: broad but deterministic test coverage across runner and strategy contracts.
  - Skills: [] - Reason: existing pytest patterns are sufficient.
  - Omitted: [`protocol-compat`] - Reason: this task verifies existing decisions rather than making schema changes.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 9, 10 | Blocked By: 3, 4, 5, 6, 7

  **References**:
  - Pattern: `poe_trade/strategy/registry.py:28` - Registry iteration needed to enforce all-strategy coverage.
  - Test: `tests/unit/test_strategy_backtest.py:21` - Existing runner tests to expand.
  - Test: `tests/unit/test_strategy_registry.py` - Existing registry-oriented test patterns.
  - Test: `tests/unit/test_cli_research.py:117` - Existing result-row test to replace with summary assertions.

  **Acceptance Criteria**:
  - [ ] `.venv/bin/pytest tests/unit/test_strategy_backtest.py tests/unit/test_cli_research.py tests/unit/test_strategy_registry.py` passes.
  - [ ] The test suite contains at least one assertion that iterates all discovered strategy packs and fails if any pack still emits wildcard or contract-mismatched SQL.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: All strategy packs conform
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_strategy_registry.py tests/unit/test_strategy_backtest.py -q`
    Expected: Tests verify every discovered strategy pack participates in the shared backtest contract.
    Evidence: .sisyphus/evidence/task-8-contract-tests.txt

  Scenario: No live DB dependency leaked into tests
    Tool: Bash
    Steps: Run `.venv/bin/pytest tests/unit/test_strategy_backtest.py tests/unit/test_cli_research.py -q`
    Expected: Tests pass with local doubles/stubs only.
    Evidence: .sisyphus/evidence/task-8-local.txt
  ```

  **Commit**: NO | Message: `test(backtest): cover summary output semantics` | Files: `tests/unit/test_strategy_backtest.py`, `tests/unit/test_cli_research.py`, `tests/unit/test_strategy_registry.py`

- [ ] 9. Capture command-first verification evidence for CLI and ClickHouse behavior

  **What to do**: Add or refresh command-first evidence showing single and bulk backtests producing readable results, plus DB queries proving typed summary storage and explicit statuses. Store evidence in `.sisyphus/evidence/` during implementation, not in repo docs unless the docs task updates them.
  **Must NOT do**: Do not claim success without command output. Do not use screenshots where plain-text command evidence is sufficient.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: this is evidence packaging and verification capture.
  - Skills: [`evidence-bundle`] - Reason: produce concise, review-ready proof.
  - Omitted: [`docs-specialist`] - Reason: this is verification evidence, not long-form docs.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 10 | Blocked By: 6, 7, 8

  **References**:
  - Pattern: `README.md:29` - Existing CLI backtest commands to exercise.
  - Pattern: `README.md:30` - Existing bulk backtest command to exercise.
  - API/Type: `schema/migrations/0028_research_backtests.sql:13` - Legacy storage being superseded by typed summary/detail evidence.

  **Acceptance Criteria**:
  - [ ] Evidence files exist for single-run CLI, bulk-run CLI, summary-table DB query, and zero-result/failure status verification.
  - [ ] Every evidence bundle names the exact command run and the key output lines.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: CLI evidence is reproducible
    Tool: Bash
    Steps: Run the final single and bulk backtest commands and save stdout/stderr to `.sisyphus/evidence/`
    Expected: Evidence files show canonical headers and readable summary rows.
    Evidence: .sisyphus/evidence/task-9-cli.txt

  Scenario: DB evidence is reproducible
    Tool: Bash
    Steps: Run `clickhouse-client` queries against `poe_trade.research_backtest_summary` for a captured run id and save output.
    Expected: Evidence shows typed rows with explicit status values.
    Evidence: .sisyphus/evidence/task-9-db.txt
  ```

  **Commit**: NO | Message: `chore(backtest): capture verification evidence` | Files: `.sisyphus/evidence/*`

- [ ] 10. Update operator-facing docs to match the new backtest contract

  **What to do**: Refresh the CLI/help documentation in `README.md` and any affected operational doc so operators know that backtests now emit human-readable summary rows with explicit statuses, not only run ids or row counts. Document the canonical header, the meaning of `no_data` vs `no_opportunities`, and at least one verification query against the typed summary table.
  **Must NOT do**: Do not document behavior before it exists. Do not copy raw evidence dumps into docs.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: concise operator-facing documentation refresh.
  - Skills: [`docs-specialist`] - Reason: minimal, accurate diffs in docs.
  - Omitted: [`evidence-bundle`] - Reason: docs should summarize behavior, not embed full evidence logs.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: none | Blocked By: 2, 6, 7, 8, 9

  **References**:
  - Pattern: `README.md:29` - Existing single-backtest command documentation.
  - Pattern: `README.md:30` - Existing bulk-backtest command documentation.
  - Pattern: `docs/ops-runbook.md` - Operator troubleshooting and query conventions.
  - Test: `AGENTS.md` - Project rule: docs must be terse, operational, and evidence-backed.

  **Acceptance Criteria**:
  - [ ] `grep -n "research backtest" README.md docs/ops-runbook.md` shows updated command descriptions and verification guidance.
  - [ ] Docs mention the canonical summary header and the explicit `no_data` / `no_opportunities` status meanings.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: README matches CLI contract
    Tool: Bash
    Steps: Run `grep -n "research backtest\|backtest-all\|no_data\|no_opportunities" README.md`
    Expected: README documents the new summary output and explicit statuses.
    Evidence: .sisyphus/evidence/task-10-readme.txt

  Scenario: Ops docs include a typed verification query
    Tool: Bash
    Steps: Run `grep -n "research_backtest_summary\|clickhouse-client" docs/ops-runbook.md`
    Expected: Ops doc includes a query against the typed summary table and explains how to interpret statuses.
    Evidence: .sisyphus/evidence/task-10-ops.txt
  ```

  **Commit**: NO | Message: `docs(backtest): explain summary output contract` | Files: `README.md`, `docs/ops-runbook.md`

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit - oracle
- [ ] F2. Code Quality Review - unspecified-high
- [ ] F3. Real Manual QA - unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check - deep

## Commit Strategy
- Commit after Wave 1 foundation lands: `feat(backtest): define typed summary contract`
- Commit after Wave 2 implementation and verification land: `feat(backtest): render human-readable strategy summaries`
- Do not combine schema, runner, CLI, and tests into one unreviewable commit if the implementer can keep them atomic.

## Success Criteria
- All strategies emit readable summary output with a shared schema.
- League and lookback filters materially affect output semantics.
- Zero-result cases are explicit and distinguishable from failures.
- Persisted backtest records are queryable without decoding opaque JSON blobs.
- CLI output is decision-ready for operators.
