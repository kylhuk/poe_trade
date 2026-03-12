# PoE1 Mirage Execution-Aware Pricing ML

## TL;DR
> **Summary**: Build an offline-first pricing tool inside this repo, isolated under its own package/console script, that estimates execution-aware item prices with routed model paths, calibrated confidence, league-parameterized training, clipboard-text item parsing, and time-safe validation.
> **Deliverables**:
> - isolated `poe-ml` subtool inside the repo with its own console script and package
> - additive ML dataset + label pipeline in ClickHouse/CLI
> - routed pricing stack for fungible, structured, and sparse item families
> - execution-aware saleability/confidence outputs
> - single-item prediction from PoE clipboard text plus continuous retraining command
> - rolling evaluation and evidence artifacts for Mirage
> **Effort**: XL
> **Parallel**: YES - 3 waves
> **Critical Path**: Task 1 -> Task 2 -> Task 4 -> Task 5 -> Tasks 6/7/8 -> Task 10 -> Task 11 -> Task 12 -> Task 14

## Context
### Original Request
Create the most suitable ML setup to accurately estimate Path of Exile 1 item prices, Mirage league first, with time-aware handling for seasonality/inflation/external drift. Web serving is explicitly out of scope.

### Interview Summary
- User selected `execution-aware price` rather than raw listed-price fitting.
- User wants `all item families` in v1, but accepts routed confidence-aware handling instead of one universal model.
- Reasonable defaults applied where the repo could answer the question better than further interviewing: tests-after, offline-first, additive ClickHouse evolution, and no deep-learning v1.

### Metis Review (gaps addressed)
- Locked v1 to offline-first dataset/training/evaluation instead of drifting into serving.
- Added explicit label-audit, routing, abstention/fallback, and no-leakage requirements.
- Reused existing research/backtest storage patterns instead of inventing a separate experiment plane.
- Treated saleability/liquidity as a separate head and prerequisite data contract, not something to hide inside price features.

## Work Objectives
### Core Objective
Produce an isolated in-repo pricing tool that can train per league, parse PoE clipboard item text, and return a point estimate, interval, route, confidence, and fallback reason for any PoE1 item using time-safe market data.

### Deliverables
- additive ClickHouse tables/views for ML-ready labels, features, routing metadata, evaluation runs, and prediction outputs
- standalone console script `poe-ml` with commands for dataset build, training, endless retraining, status/progress, single-item prediction, evaluation, and batch prediction
- routed pricing logic:
  - fungible/reference path for stackable/liquid families
  - family-specific boosted-tree path for structured items
  - retrieval-plus-residual path for rares and high-dimensional jewels
- separate saleability/liquidity model and confidence policy
- persisted mod catalog / normalized mod-token surfaces for observed priced-item modifiers; a full canonical game-wide mod corpus is explicitly NOT required for v1
- training runtime manager with hardware-aware backend selection, worker/memory budgeting, resume checkpoints, and safe model promotion
- automated Mirage rolling-backtest reports with per-route coverage and error metrics

### Definition of Done (verifiable conditions with commands)
- `.venv/bin/poe-ml dataset build --league Mirage --as-of 2026-03-12T00:00:00Z --output-table poe_trade.ml_price_dataset_v1` completes and writes a table with non-zero rows.
- `.venv/bin/poe-ml train --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1` writes route-specific artifacts and metadata.
- `.venv/bin/poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --max-iterations 1` completes one full rebuild/train/evaluate cycle; removing `--max-iterations` runs endlessly.
- `.venv/bin/poe-ml status --league Mirage --run latest` shows current stage, route progress, backend, workers, memory budget, and active model version.
- `.venv/bin/poe-ml evaluate --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --split rolling` writes evaluation rows with per-route `coverage`, `mdape`, `wape`, `abstain_rate`, and interval coverage.
- `.venv/bin/poe-ml predict-one --league Mirage --input-format poe-clipboard --stdin < tests/fixtures/ml/sample_clipboard_item.txt` writes a structured estimate containing `route`, `price_p10`, `price_p50`, `price_p90`, `sale_probability`, `sale_probability_percent`, `confidence`, `confidence_percent`, and `fallback_reason`.
- `.venv/bin/poe-ml predict-batch --league Mirage --model-dir artifacts/ml/mirage_v1 --source latest --output-table poe_trade.ml_price_predictions_v1` writes predictions containing `route`, `price_chaos`, `price_p10`, `price_p50`, `price_p90`, `sale_probability`, `confidence`, and `fallback_reason`.
- `clickhouse-client --query "SELECT route, count() FROM poe_trade.ml_price_predictions_v1 WHERE league='Mirage' GROUP BY route ORDER BY route"` returns rows for every configured route.

### Must Have
- league-parameterized training and inference, with Mirage as the initial accepted/validated league and no cross-league leakage in final metrics
- every train/predict command accepts `--league`; Mirage is the initial validated league, not a hard-coded constant
- additive schema only; no destructive migration assumptions
- isolated implementation: all ML logic lives under its own package/tool surface; shared repo changes are limited to console-script registration, shared settings/client reuse, additive schema, and tests
- automatic retraining with persisted run state, resume-on-restart behavior, and atomic model promotion only when evaluation gates pass
- operator-visible progress and health via `poe-ml status` and persisted run bookkeeping
- hardware-aware execution policy that auto-detects available CPU/GPU support, sets safe worker counts, and enforces a memory budget
- time-safe feature snapshots and forward-only rolling evaluation
- routed coverage for every item family with explicit fallback/abstain behavior
- uncertainty/confidence outputs for every prediction
- `predict-one` output must show confidence in percent at minimum; when saleability is available it must also show sale probability in percent
- saleability/liquidity tracked separately from price estimation
- PoE clipboard text format is a first-class inference input
- poe.ninja currency snapshots are the primary FX normalization source for non-chaos listings, with timestamp-safe fallback only when snapshots are missing
- robust training-data cleaning with explicit outlier quarantine for fake anchor listings, mispriced junk rows, and malformed price signals

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- no web service, dashboard, or online API work
- no broad rewrites of unrelated ingestion or strategy code; this remains a separate tool inside the repo
- no assumption that GPU acceleration exists or is stable; CPU-first fallback must always work
- no single universal model claiming equal accuracy across commodities, uniques, rares, and jewels
- no random train/test split, shuffled K-fold, or any validation leaking future data
- no hidden dependence on unavailable Mirage sale-truth tables
- no destructive ClickHouse changes, column reorders, or table drops
- no deep-learning first pass; revisit only after richer labels and broader evidence exist
- no requirement to ingest a full game-wide canonical mod universe before v1; observed priced-item modifiers are sufficient if the tool reports that scope honestly
- no training on unpriced rows or quarantined outlier rows as if they were trustworthy labels
- no auto-promotion of a newly trained model when evaluation gates fail, training aborts, or artifacts are incomplete
- no full in-memory local copy of the raw corpus when ClickHouse-side aggregation/chunking can keep runtime within the machine budget

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Command surface: use standalone `.venv/bin/poe-ml ...` commands; older `python -m poe_trade.cli ml ...` examples are superseded by the separate tool requirement.
- Test decision: `tests-after` using `pytest` plus ClickHouse-backed CLI/evaluation checks
- QA policy: Every task includes agent-executed happy-path and failure-path scenarios
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: tool contract + label/normalization foundation (`deep`, `unspecified-high`)
Wave 2: dataset + routing + model routes + saleability head (`deep`, `ultrabrain`, `unspecified-high`, `quick`)
Wave 3: inference orchestration + evaluation/reporting + current-item batch scoring (`deep`, `writing`, `quick`)

### Dependency Matrix (full, all tasks)
- `1` blocks `2-5`
- `2` blocks `4,10,11,12,14`
- `3` blocks `4,6,7,8,9,14`
- `4` blocks `5,6,7,8,9,10,11,12,14`
- `5` blocks `6,7,8,9,11,14`
- `6` blocks `11,12,14`
- `7` blocks `11,12,14`
- `8` blocks `9,11,12,14`
- `9` blocks `11,12,14`
- `10` blocks `11,12,14`
- `11` blocks `12,14`
- `12` blocks `13,14`
- `13` blocks `14`

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 4 tasks -> `deep`, `unspecified-high`
- Wave 2 -> 6 tasks -> `deep`, `ultrabrain`, `unspecified-high`, `quick`
- Wave 3 -> 4 tasks -> `deep`, `writing`, `quick`

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Create the isolated `poe-ml` tool surface and lock the target contract

  **What to do**: Create a separate in-repo tool with its own package and console script, `poe-ml`, instead of extending the main repo CLI as the primary operator surface. Keep all new ML orchestration, parsers, and training logic under the tool package; only reuse shared settings and the ClickHouse client. Implement `poe-ml audit-data --league <league>` that prints and optionally stores a JSON report covering row counts, priced-row counts, currency cleanliness, category mix, base-type cardinality, market-context coverage, observed priced-mod coverage, outlier diagnostics, and presence/absence of sale-proxy sources. In the same task, implement runtime/hardware detection that records CPU cores, available RAM, GPU/backend availability, chosen training backend, default worker count, and default memory budget, and persist those defaults for the current machine. Codify the v1 target contract as `execution-aware league price in chaos` with the following default semantics: `recommended executable ask price expected to clear within 24h when sale_probability >= 0.5`, and require every later task to emit `label_source`, `label_quality`, `as_of_ts`, `league`, and `outlier_status` so the contract is auditable.
  **Must NOT do**: Do not spread ML business logic through unrelated services or strategy code. Do not train models, create prediction tables, or mix leagues unless the command explicitly requests that league. Do not declare a full canonical mod corpus as a prerequisite for v1.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: establishes the canonical contract that every downstream task depends on.
  - Skills: [`protocol-compat`] — why needed: new ClickHouse tables/views and additive contracts must be staged safely.
  - Omitted: [`evidence-bundle`] — why not needed: evidence packaging belongs after executable features exist.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: `2,3,4,5` | Blocked By: none

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `pyproject.toml` — add a dedicated console script entry for the isolated tool.
  - Pattern: `poe_trade/cli.py` — reference only if a thin compatibility shim is needed; do not use it as the primary ML surface.
  - Pattern: `poe_trade/db/clickhouse.py:43` — shared ClickHouse execution path; reuse instead of adding another client.
  - Pattern: `poe_trade/strategy/backtest.py:43` — existing offline research command shape and result-writing pattern.
  - Pattern: `04-exilelens-linux-item-capture.md:14` — repo context already assumes PoE clipboard copy format is a primary input surface.
  - API/Type: `schema/migrations/0025_psapi_silver_current_views.sql:90` — current enriched listing surface with parsed note fields.
  - API/Type: `schema/migrations/0026_cx_silver_views.sql:1` — hourly currency-exchange inputs for chaos normalization.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:16` — existing gold marts are references, not ML-ready datasets.
  - External: `https://catboost.ai/docs/en/references/training-parameters/common#has_time` — time-respecting training constraint to keep in the contract notes.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml audit-data --league Mirage --output .sisyphus/evidence/task-1-audit-data.json` completes and writes a JSON file.
  - [ ] The audit JSON includes `priced_rows`, `clean_currency_rows`, `base_type_count`, `category_breakdown`, `mod_storage_breakdown`, `poeninja_snapshot_rows`, `sale_proxy_rows`, `outlier_summary`, `hardware_profile`, `chosen_backend`, `default_workers`, `memory_budget_gb`, and `target_contract` keys.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_audit_runs WHERE league='Mirage'"` returns `> 0` if a run table is introduced; otherwise the CLI must print the same fields deterministically.
  - [ ] The target contract is defined in one shared Python module and imported by later ML commands rather than duplicated.
  - [ ] On this machine, the runtime profile chooses a CPU-safe default path and does not require GPU presence to proceed.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Mirage data audit succeeds
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml audit-data --league Mirage --output .sisyphus/evidence/task-1-audit-data.json`.
    Expected: Exit code 0; JSON report exists and includes non-zero `priced_rows`, explicit `target_contract` text, and runtime defaults such as backend/workers/memory budget.
    Evidence: .sisyphus/evidence/task-1-audit-data.json

  Scenario: Unsupported league is rejected
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml audit-data --league Standard` before Standard is explicitly validated.
    Expected: Either a successful parameterized audit with `league='Standard'`, or a clear error stating that only Mirage has validated acceptance criteria so far; it must not silently substitute Mirage.
    Evidence: .sisyphus/evidence/task-1-audit-data-error.txt
  ```

  **Commit**: YES | Message: `feat(ml): add isolated pricing tool contract` | Files: `pyproject.toml`, `poe_trade/ml/*`, `tests/unit/*`, `schema/migrations/*`

- [ ] 2. Rebuild additive sale-proxy and label-provenance surfaces

  **What to do**: Add new additive ML-specific listing-event tables/views instead of reviving the deleted legacy liquidity views by name. Build an `ml_listing_events_v1` surface that deduplicates listing observations into stable listing chains, tracks note edits/relist events, and records whether each event has metadata-backed timestamps or heuristic-only evidence. Build an `ml_execution_labels_v1` surface that emits `sale_probability_label`, `time_to_exit_label`, `label_source`, `label_quality`, and `is_censored`; when `bronze_trade_metadata` is empty, populate only heuristic labels and mark them low-quality rather than fabricating sale truth.
  **Must NOT do**: Do not recreate `v_liquidity`, `v_liquidity_timeline`, or `v_bronze_public_stash_items` under the old names. Do not equate disappearance with a sale unless provenance says so.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: requires careful label semantics, additive schema design, and time-safe event logic.
  - Skills: [`protocol-compat`] — why needed: additive ClickHouse evolution and compatibility-safe view/table design.
  - Omitted: [`git-master`] — why not needed: no git work is part of the task itself.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: `4,10,11,12,14` | Blocked By: `1`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0012_liquidity_views.sql:60` — prior liquidity timeline logic worth mining for event semantics, but not for object names.
  - Pattern: `schema/migrations/0010_bronze_trade_metadata_dedup_view.sql:1` — metadata dedup pattern for listing/delist timestamps.
  - Pattern: `schema/migrations/0018_cleanup_unused_objects.sql:6` — legacy liquidity objects were intentionally dropped; replace with ML-specific names only.
  - API/Type: `schema/migrations/0025_psapi_silver_current_views.sql:33` — raw item listing source keyed by `observed_at`, `stash_id`, and `item_id`.
  - API/Type: `schema/migrations/0030_journal_tables.sql` — future realized truth loop exists and should be join-compatible.
  - Test: `tests/unit/test_strategy_backtest.py` — repo pattern for deterministic offline result handling.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/python -m poe_trade.services.migrator --status --dry-run` shows the new migration(s) cleanly.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_listing_events_v1 WHERE league='Mirage'"` returns `> 0` after dataset refresh.
  - [ ] `clickhouse-client --query "SELECT label_source, label_quality, count() FROM poe_trade.ml_execution_labels_v1 WHERE league='Mirage' GROUP BY label_source, label_quality ORDER BY label_source, label_quality"` returns rows and does not mislabel heuristic-only data as high-quality.
  - [ ] Listings without metadata-backed execution evidence remain `is_censored=1` or low-quality rather than being silently treated as sold.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Label surfaces populate with provenance
    Tool: Bash
    Steps: Run the migration/app refresh path, then query `poe_trade.ml_execution_labels_v1` grouped by `label_source,label_quality` for `league='Mirage'`.
    Expected: Rows exist; sources differentiate metadata-backed vs heuristic labels; no heuristic rows claim high-quality truth.
    Evidence: .sisyphus/evidence/task-2-label-provenance.txt

  Scenario: Empty metadata degrades safely
    Tool: Bash
    Steps: Run a query that filters `label_source='trade_metadata'` for `league='Mirage'`.
    Expected: Zero rows or explicit empty result; downstream views still materialize with heuristic/censored labels instead of failing.
    Evidence: .sisyphus/evidence/task-2-label-empty-metadata.txt
  ```

  **Commit**: YES | Message: `feat(ml): add mirage sale proxy labels` | Files: `schema/migrations/*`, `poe_trade/sql/ml/*`, `poe_trade/ml/*`, `tests/unit/*`

- [ ] 3. Replace coarse price parsing with chaos-normalized label cleaning

  **What to do**: Implement an ML-focused price parsing and normalization layer that upgrades the current regex-based note extraction into a deterministic parser with explicit normalization outcomes. Persist league-scoped poe.ninja currency snapshots as the primary FX source for normalization, including `sample_time_utc`, `chaosEquivalent`, `listing_count`, `stale`, and provenance fields, then build normalized label tables from those snapshots. Emit `parsed_amount`, `parsed_currency`, `price_parse_status`, `normalized_price_chaos`, `normalization_source`, `fx_hour`, `fx_source`, and `unit_price_chaos` for stackables. On top of normalization, add a robust outlier-screening pass that computes family/base-type aware low/high anomaly bands using recent quantiles plus robust spread metrics (for example MAD or IQR on log-price) and flags rows as `trainable`, `quarantined_low_anchor`, `quarantined_high_anchor`, `stale_fx`, or `parse_failure`. Use the freshest poe.ninja snapshot at or before the listing `as_of_ts`; use internal CX only as a timestamp-safe fallback/cross-check when poe.ninja is missing.
  **Must NOT do**: Do not train on raw `price_currency` strings from `v_ps_items_enriched` without normalization. Do not use future FX buckets when normalizing a historical listing. Do not hard-delete suspicious rows; preserve them with explicit outlier status for auditability.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: parsing, normalization, and temporal FX joins need careful but bounded implementation.
  - Skills: [`protocol-compat`] — why needed: additive marts/views for normalized labels.
  - Omitted: [`docs-specialist`] — why not needed: implementation and tests matter more than prose here.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: `4,6,7,8,9,14` | Blocked By: `1`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:93` — current effective price-note extraction entry point.
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:94` — current price amount regex is too coarse for ML labels.
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:95` — current price currency parsing leaks noisy labels like `chaos 2`.
  - Pattern: `poe_trade/ingestion/poeninja_snapshot.py:54` — existing league-scoped poe.ninja currency-overview fetch entry point.
  - Pattern: `docs/research/poe-data-sources.md:49` — repo research notes on approved poe.ninja endpoints and `sample_time_utc`.
  - Pattern: `schema/migrations/0026_cx_silver_views.sql:36` — enriched CX hour source for FX derivation.
  - Pattern: `poe_trade/sql/gold/100_currency_ref_hour.sql:1` — existing hourly FX/reference aggregation style.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:1` — existing gold currency mart storage pattern.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml snapshot-poeninja --league Mirage --output-table poe_trade.ml_poeninja_currency_snapshot_v1 --max-iterations 1` completes and writes rows.
  - [ ] `.venv/bin/poe-ml build-fx --league Mirage --output-table poe_trade.ml_fx_hour_v1` completes and writes rows with `fx_source='poeninja'` where snapshots exist.
  - [ ] `.venv/bin/poe-ml normalize-prices --league Mirage --output-table poe_trade.ml_price_labels_v1` completes and writes `normalized_price_chaos`, parse-status columns, and outlier-status columns.
  - [ ] `clickhouse-client --query "SELECT price_parse_status, count() FROM poe_trade.ml_price_labels_v1 WHERE league='Mirage' GROUP BY price_parse_status ORDER BY price_parse_status"` returns rows for both success and handled-failure states.
  - [ ] `clickhouse-client --query "SELECT outlier_status, count() FROM poe_trade.ml_price_labels_v1 WHERE league='Mirage' GROUP BY outlier_status ORDER BY outlier_status"` returns rows including a `trainable` bucket and at least one quarantined bucket if anomalies exist.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_labels_v1 WHERE league='Mirage' AND normalized_price_chaos IS NOT NULL"` returns `> 0` and never exceeds the priced-row count.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Clean chaos-normalized labels build successfully
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml snapshot-poeninja --league Mirage --output-table poe_trade.ml_poeninja_currency_snapshot_v1 --max-iterations 1`, then `.venv/bin/poe-ml build-fx --league Mirage --output-table poe_trade.ml_fx_hour_v1`, then `.venv/bin/poe-ml normalize-prices --league Mirage --output-table poe_trade.ml_price_labels_v1`.
    Expected: Commands succeed; output table includes non-null `normalized_price_chaos`, `normalization_source`, `fx_hour`, `fx_source`, and `outlier_status`, with poe.ninja used when available.
    Evidence: .sisyphus/evidence/task-3-normalize-success.txt

  Scenario: Suspicious anchor prices are quarantined
    Tool: Bash
    Steps: Run normalization against a fixture/query slice containing malformed notes and implausibly low/high listings for the same family/base-type cohort.
    Expected: Rows are retained with explicit failure or quarantine statuses and are excluded from trainable labels unless the parser marks them recoverable and non-outlier.
    Evidence: .sisyphus/evidence/task-3-normalize-failure.txt
  ```

  **Commit**: YES | Message: `feat(ml): normalize mirage prices to chaos` | Files: `poe_trade/ml/*`, `poe_trade/sql/ml/*`, `schema/migrations/*`, `tests/unit/*`

- [ ] 4. Build the canonical as-of feature dataset for Mirage listings

  **What to do**: Create `ml_price_dataset_v1` as the single training/evaluation source for pricing tasks. Each row must represent one deduplicated listing snapshot at one `as_of_ts`, with only time-safe features available then: base/slot/category, rarity, ilvl, stack size, sockets/links/grid size, influence/corruption flags, parsed mod arrays and normalized roll values, observed mod tokens, route candidate, normalized price labels from Task 3, execution labels from Task 2, and joined market context from the `gold_*` marts plus FX freshness fields. Build and persist `ml_mod_catalog_v1` and `ml_item_mod_tokens_v1` from observed priced listings so modifiers are stored outside raw JSON; a full canonical game-wide mod corpus is optional and must not block v1. Build both a full audited label table and a trainable subset where `outlier_status='trainable'` and the label is priced/normalized.
  **Must NOT do**: Do not use `v_ps_current_items` as the primary source because the live view is currently unreliable. Do not include any feature that depends on future relists, future CX hours, or future evaluation outcomes. Do not let quarantined rows into the trainable subset.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this is the central data contract tying listing, label, and context surfaces together.
  - Skills: [`protocol-compat`] — why needed: additive schema and dataset stability are mandatory.
  - Omitted: [`frontend-ui-ux`] — why not needed: there is no UI scope.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: `6,7,8,9,10,11,12,14` | Blocked By: `2,3`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:33` — raw listing/item grain and base fields.
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:124` — current-item view intent; use it only as a validation reference, not the dataset source.
  - Pattern: `schema/migrations/0027_gold_reference_marts.sql:16` — listing reference mart join pattern.
  - Pattern: `schema/migrations/0027_gold_reference_marts.sql:30` — liquidity reference mart shape.
  - Pattern: `schema/migrations/0028_research_backtests.sql:1` — existing offline run bookkeeping pattern.
  - Pattern: `poe_trade/strategy/backtest.py:240` — existing league/time filtering pattern for offline evaluation windows.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml dataset build --league Mirage --as-of 2026-03-12T00:00:00Z --output-table poe_trade.ml_price_dataset_v1` completes successfully.
  - [ ] `clickhouse-client --query "SELECT count(), min(as_of_ts), max(as_of_ts) FROM poe_trade.ml_price_dataset_v1 WHERE league='Mirage'"` returns non-zero rows and bounded timestamps.
  - [ ] `clickhouse-client --query "DESCRIBE TABLE poe_trade.ml_price_dataset_v1"` includes `normalized_price_chaos`, `sale_probability_label`, `label_quality`, `route_candidate`, `fx_freshness_minutes`, `as_of_ts`, and mod-token feature columns.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_mod_catalog_v1"` returns `> 0` and persists observed priced-item modifiers outside raw item JSON.
  - [ ] The dataset build report explicitly states that the mod catalog is `observed-priced-only` unless a canonical source is later added.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_dataset_v1 WHERE league='Mirage' AND outlier_status != 'trainable'"` returns `0` for the trainable dataset.
  - [ ] A no-leakage audit command/report proves every joined context field is drawn from `<= as_of_ts`.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Canonical dataset builds for a fixed cutoff
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml dataset build --league Mirage --as-of 2026-03-12T00:00:00Z --output-table poe_trade.ml_price_dataset_v1` and inspect table schema/counts.
    Expected: Dataset exists with non-zero rows and all required label/context columns.
    Evidence: .sisyphus/evidence/task-4-dataset-build.txt

  Scenario: Leakage audit catches future joins
    Tool: Bash
    Steps: Run the no-leakage audit against `poe_trade.ml_price_dataset_v1`.
    Expected: Exit code 0 with zero violating rows; if a violation is introduced, the audit fails loudly.
    Evidence: .sisyphus/evidence/task-4-leakage-audit.txt
  ```

  **Commit**: YES | Message: `feat(ml): add mirage pricing dataset builder` | Files: `schema/migrations/*`, `poe_trade/sql/ml/*`, `poe_trade/ml/*`, `pyproject.toml`, `tests/unit/*`

- [ ] 5. Add deterministic routing taxonomy and support thresholds

  **What to do**: Implement a deterministic router that assigns each row/item into one of the v1 pricing paths: `fungible_reference`, `structured_boosted`, `sparse_retrieval`, or `fallback_abstain`. The router must use item-family rules grounded in actual fields (`category`, `base_type`, rarity, stackability, mod density, support counts) and emit `route`, `route_reason`, `support_count_recent`, `support_bucket`, and `fallback_parent_route`. Define explicit support thresholds so thin families back off to a parent route instead of forcing a specialist model. Routing and support counts must be computed from the cleaned trainable subset rather than raw noisy listings.
  **Must NOT do**: Do not leave rares/high-dimensional jewels inside the giant `other` bucket without a route reason. Do not let one implicit catch-all rule silently own most of the corpus.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: routing semantics decide model scope, fallback behavior, and coverage claims.
  - Skills: [] — why needed: none beyond repo exploration and disciplined implementation.
  - Omitted: [`protocol-compat`] — why not needed: primarily Python/SQL rules, not a sensitive schema redesign.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `6,7,8,9,11,14` | Blocked By: `1,4`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:96` — current coarse category bucketing that is insufficient for v1 routing.
  - Pattern: `poe_trade/sql/strategy/high_dim_jewels/discover.sql:1` — existing repo treats cluster jewels as a special strategy family already.
  - Pattern: `poe_trade/sql/strategy/dump_tab_reprice/discover.sql:1` — existing repo sends broad `other` items into a coarse fallback path.
  - API/Type: `schema/migrations/0025_psapi_silver_current_views.sql:48` — rarity and base-type inputs available for routing.
  - External: `https://catboost.ai/docs/en/concepts/algorithm-main-stages_categorical-features` — supports keeping high-cardinality families separate rather than flattening them too early.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml route-preview --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --limit 1000` prints route assignments with reasons.
  - [ ] `clickhouse-client --query "SELECT route, count() FROM poe_trade.ml_route_candidates_v1 WHERE league='Mirage' GROUP BY route ORDER BY route"` returns all configured routes.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_route_candidates_v1 WHERE league='Mirage' AND route_reason = ''"` returns `0`.
  - [ ] Recent-support thresholds are encoded centrally and covered by unit tests.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Routed preview covers every configured path
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml route-preview --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --limit 1000` and aggregate route counts.
    Expected: Output includes the configured routes with non-empty reasons and support buckets.
    Evidence: .sisyphus/evidence/task-5-route-preview.txt

  Scenario: Thin-support item falls back safely
    Tool: Bash
    Steps: Run route preview or a targeted fixture through the router for a sparse rare/influenced item.
    Expected: Route resolves to `sparse_retrieval` or `fallback_abstain` with explicit `fallback_parent_route`, not a silent misclassification.
    Evidence: .sisyphus/evidence/task-5-route-fallback.txt
  ```

  **Commit**: YES | Message: `feat(ml): add mirage pricing router` | Files: `poe_trade/ml/*`, `poe_trade/sql/ml/*`, `pyproject.toml`, `tests/unit/*`

- [ ] 6. Implement the fungible/reference pricing route

  **What to do**: Build the `fungible_reference` route for stackable and liquid families (currency-like items, essences, scarabs, fossils, maps/logbooks when appropriate). Use robust time-bucketed reference pricing and quantiles rather than a learned model: per-unit chaos normalization, recent-window medians, spread bands, sample counts, volatility, and stale-data handling. Return a distribution (`p10/p50/p90`) plus sample-size and freshness metadata.
  **Must NOT do**: Do not train CatBoost/XGBoost for obviously fungible families where robust stats are more stable. Do not emit a price without sample-count and freshness fields.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: the route is mostly deterministic SQL and CLI wiring once the dataset exists.
  - Skills: [`protocol-compat`] — why needed: likely adds route output tables/views.
  - Omitted: [`ultrabrain`] — why not needed: this route should stay simple and robust.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `11,12,14` | Blocked By: `3,4,5`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `poe_trade/sql/gold/110_listing_ref_hour.sql:1` — existing hourly listing reference aggregation.
  - Pattern: `poe_trade/sql/gold/120_liquidity_ref_hour.sql:1` — sample-count/liquidity reference pattern.
  - Pattern: `poe_trade/sql/gold/130_bulk_premium_hour.sql:1` — bulk-vs-small pricing split for stackables.
  - API/Type: `schema/migrations/0027_gold_reference_marts.sql:43` — bulk premium mart storage pattern.
  - Test: `tests/unit/test_strategy_backtest.py` — offline deterministic testing style.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml train-route --route fungible_reference --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1` completes and writes route metadata.
  - [ ] `.venv/bin/poe-ml evaluate-route --route fungible_reference --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1` writes evaluation rows with `sample_count`, `freshness_minutes`, and interval columns.
  - [ ] Route predictions always include `price_p10`, `price_p50`, `price_p90`, `support_count_recent`, and `freshness_minutes`.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Fungible route produces interval outputs
    Tool: Bash
    Steps: Train and evaluate `fungible_reference`, then inspect one prediction sample row.
    Expected: Prediction contains `price_p10`, `price_p50`, `price_p90`, `support_count_recent`, and `freshness_minutes` with non-null values.
    Evidence: .sisyphus/evidence/task-6-fungible-route.txt

  Scenario: Stale/low-sample market degrades safely
    Tool: Bash
    Steps: Score a family/time bucket with intentionally sparse or stale reference data.
    Expected: Route widens interval or falls back with an explicit stale-data reason instead of returning a confident point estimate.
    Evidence: .sisyphus/evidence/task-6-fungible-stale.txt
  ```

  **Commit**: YES | Message: `feat(ml): add fungible reference pricing route` | Files: `poe_trade/sql/ml/*`, `poe_trade/ml/*`, `pyproject.toml`, `tests/unit/*`

- [ ] 7. Train structured-family boosted models with time-aware quantile outputs

  **What to do**: Implement the `structured_boosted` route for families with enough support and meaningful structured attributes: uniques, flasks, maps, and cluster jewels, plus any additional family that clears the support threshold from Task 5. Use CatBoost first, with time-respecting training (`has_time`) and quantile or uncertainty-aware objectives. Train one family model per route family rather than one pooled monolith, and persist feature specs plus artifact metadata alongside each model. Train only on the cleaned trainable subset from Task 4, and record the number/share of rows excluded for outlier reasons per family.
  **Must NOT do**: Do not use one-hot expansion for high-cardinality categorical fields. Do not pool sparse rares into this route just to increase row counts.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: family-specific modeling, training orchestration, and artifact contracts are substantive.
  - Skills: [] — why needed: no special repo skill beyond disciplined implementation.
  - Omitted: [`ultrabrain`] — why not needed: this is conventional tabular modeling, not speculative architecture.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `11,12,14` | Blocked By: `3,4,5`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:48` — base family fields available for structured modeling.
  - Pattern: `poe_trade/sql/strategy/high_dim_jewels/discover.sql:1` — cluster jewels already recognized as a special family.
  - Pattern: `poe_trade/strategy/backtest.py:240` — forward-looking league/time filtering to mirror in rolling evaluation.
  - External: `https://catboost.ai/docs/en/references/training-parameters/common#has_time` — required for time-aware training.
  - External: `https://catboost.ai/docs/en/concepts/loss-functions-regression#rmsewithuncertainty` — uncertainty-capable objective option.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml train-route --route structured_boosted --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1` completes and writes family-specific model artifacts.
  - [ ] `.venv/bin/poe-ml evaluate-route --route structured_boosted --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1` writes per-family metrics for at least `unique`, `flask`, `map`, and `cluster_jewel` when routed rows exist.
  - [ ] Artifact metadata records family, feature columns, train window, objective, and model version.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Structured models train and evaluate by family
    Tool: Bash
    Steps: Train `structured_boosted`, run route evaluation, and query evaluation rows grouped by family.
    Expected: Separate metric rows exist for routed families and include interval/error fields.
    Evidence: .sisyphus/evidence/task-7-structured-eval.txt

  Scenario: Unsupported family is not forced into boosted route
    Tool: Bash
    Steps: Score a sparse rare/high-dimension item through the route dispatcher.
    Expected: Dispatcher refuses `structured_boosted` and sends the item to `sparse_retrieval` or fallback with a clear reason.
    Evidence: .sisyphus/evidence/task-7-structured-reject.txt
  ```

  **Commit**: YES | Message: `feat(ml): add structured boosted pricing models` | Files: `poe_trade/ml/*`, `tests/unit/*`, `pyproject.toml`

- [ ] 8. Build comparable-item retrieval for sparse rares and high-dimensional jewels

  **What to do**: Implement the `sparse_retrieval` route that indexes recent Mirage listings into a comparable-item search surface using normalized mod tokens, base/slot/rarity constraints, influence flags, ilvl bands, and per-unit normalized price fields. Start with deterministic lexical/signature retrieval inside ClickHouse or repo-native Python; rank by strict structural compatibility first, then recency and price-signal density. Use only cleaned trainable comps, not quarantined anchor listings. Output `comp_count`, `top_comp_ids`, `comp_price_p10/p50/p90`, `distance_score`, and `retrieval_window_hours`.
  **Must NOT do**: Do not introduce a separate vector database or external retrieval service in v1. Do not compare rares across incompatible base/slot families just to get enough comps.

  **Recommended Agent Profile**:
  - Category: `ultrabrain` — Reason: sparse-item similarity design is the hardest logic in the stack and needs careful normalization.
  - Skills: [] — why needed: no special repo skill beyond strong reasoning.
  - Omitted: [`protocol-compat`] — why not needed: prefer additive SQL/Python surfaces without risky schema redesign.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `9,11,12,14` | Blocked By: `3,4,5`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:56` — raw `item_json` is available and should be parsed for comparable signatures.
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:74` — `item_id` grain for traceable comparable rows.
  - Pattern: `poe_trade/sql/strategy/high_dim_jewels/discover.sql:1` — jewels are already treated as a special high-dimensional case in the repo.
  - API/Type: `schema/migrations/0025_psapi_silver_current_views.sql:53` — corruption/fracture/synthesised flags available for similarity constraints.
  - External: `https://catboost.ai/docs/en/concepts/algorithm-main-stages_categorical-features` — reason to keep retrieval for sparse combinatorial items instead of flattening them into one tabular model.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml build-comps --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --output-table poe_trade.ml_comps_v1` completes and writes rows.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_comps_v1 WHERE league='Mirage'"` returns `> 0`.
  - [ ] Comparable rows include `target_item_id`, `comp_item_id`, `distance_score`, `comp_price_chaos`, and `retrieval_window_hours`.
  - [ ] Incompatible family/base matches are prevented by deterministic filters and unit tests.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Sparse retrieval returns comparable items with traceable evidence
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml build-comps --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --output-table poe_trade.ml_comps_v1` then query one sparse rare target.
    Expected: Returned comps include IDs, distance scores, and normalized price fields from recent Mirage rows.
    Evidence: .sisyphus/evidence/task-8-comps-success.txt

  Scenario: Incompatible sparse item yields empty comps and safe fallback
    Tool: Bash
    Steps: Query the comparable builder for a deliberately unusual item with no valid same-family comps.
    Expected: Zero compatible comps or a flagged empty result; no cross-family junk matches are returned.
    Evidence: .sisyphus/evidence/task-8-comps-empty.txt
  ```

  **Commit**: YES | Message: `feat(ml): add sparse item comparable retrieval` | Files: `poe_trade/ml/*`, `poe_trade/sql/ml/*`, `pyproject.toml`, `tests/unit/*`

- [ ] 9. Add the sparse residual pricing model on top of comparable retrieval

  **What to do**: Implement a residual model for sparse routes that consumes retrieval outputs plus target-item structured features to adjust comparable medians into a final interval. Use a small, regularized booster or deterministic rules if support is too thin; the route must always surface how much of the prediction came from comps vs residual adjustment. Persist `base_comp_price_p50`, `residual_adjustment`, `final_price_p10/p50/p90`, and `residual_model_support`.
  **Must NOT do**: Do not hide a weak model behind confident outputs when `comp_count` is low. Do not skip the raw-comp baseline for evaluation.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: combines sparse retrieval with a conservative residual learner and requires disciplined evaluation.
  - Skills: [] — why needed: standard implementation discipline is sufficient.
  - Omitted: [`ultrabrain`] — why not needed: the hardest part is the retrieval step, not the residual correction.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `11,12,14` | Blocked By: `3,4,5,8`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `poe_trade/strategy/backtest.py:103` — summarize route outputs with deterministic offline metrics.
  - Pattern: `poe_trade/strategy/backtest.py:171` — persist summaries after route execution instead of ad hoc logging.
  - API/Type: `poe_trade.ml_comps_v1` — comparable output from Task 8 is a required dependency.
  - External: `https://github.com/dmlc/xgboost/blob/master/doc/python/examples/quantile_regression.md` — acceptable quantile-residual pattern if XGBoost is chosen for the sparse residual.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml train-route --route sparse_retrieval --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --comps-table poe_trade.ml_comps_v1 --model-dir artifacts/ml/mirage_v1` completes and writes route artifacts.
  - [ ] `.venv/bin/poe-ml evaluate-route --route sparse_retrieval --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --comps-table poe_trade.ml_comps_v1 --model-dir artifacts/ml/mirage_v1` writes metrics for both `comp_baseline` and `residual_adjusted` outputs.
  - [ ] Prediction rows include `comp_count`, `base_comp_price_p50`, `residual_adjustment`, and `fallback_reason`.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Residual model improves or matches raw comp baseline
    Tool: Bash
    Steps: Train/evaluate `sparse_retrieval` and compare baseline-vs-residual route metrics.
    Expected: Evaluation output includes both variants and shows residual-adjusted performance is at least reported distinctly.
    Evidence: .sisyphus/evidence/task-9-sparse-eval.txt

  Scenario: Low-comp item refuses aggressive adjustment
    Tool: Bash
    Steps: Score a target item with `comp_count` below the configured threshold.
    Expected: `residual_adjustment` is zero or conservative and `fallback_reason` explains the low-support downgrade.
    Evidence: .sisyphus/evidence/task-9-sparse-low-comp.txt
  ```

  **Commit**: YES | Message: `feat(ml): add sparse residual pricing route` | Files: `poe_trade/ml/*`, `tests/unit/*`, `pyproject.toml`

- [ ] 10. Train the separate saleability/liquidity head

  **What to do**: Implement a distinct saleability model that predicts `sale_probability_24h` and optional `time_to_exit_bucket` from the label surfaces in Task 2. Train and evaluate it independently from the price model, using `label_quality` as a sample-weighting or eligibility control so low-quality heuristic rows do not dominate. Expose the head as a reusable route-agnostic artifact that later pricing outputs can join for execution-aware confidence and fallback decisions.
  **Must NOT do**: Do not feed sale-proxy labels back into price features in a way that leaks future outcomes. Do not require trade-metadata-backed labels to exist before the model can train; degrade to heuristic-weighted mode when necessary.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: distinct model head with label-quality handling and evaluation logic.
  - Skills: [] — why needed: no special repo skill is required.
  - Omitted: [`ultrabrain`] — why not needed: conventional supervised modeling once labels exist.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: `11,12,14` | Blocked By: `2,4`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0012_liquidity_views.sql:88` — prior sell-through/time-to-sell semantics to reuse conceptually, not by object name.
  - Pattern: `schema/migrations/0010_bronze_trade_metadata_dedup_view.sql:8` — listing/delist timestamp dedup inputs.
  - Pattern: `poe_trade/strategy/backtest.py:124` — explicit no-data vs no-opportunity handling; mirror for saleability evaluation.
  - External: `https://research.google/blog/interpretable-deep-learning-for-time-series-forecasting/` — only as deferred context; v1 remains non-deep-learning.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml train-saleability --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1` completes and writes a saleability artifact.
  - [ ] `.venv/bin/poe-ml evaluate-saleability --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1` writes metrics including calibration or bucketed outcome accuracy.
  - [ ] Output rows include `sale_probability_24h`, `sale_label_quality_mix`, and `eligibility_reason` when the head cannot score a row.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Saleability head trains with label-quality awareness
    Tool: Bash
    Steps: Run saleability train/evaluate commands and inspect artifact metadata or evaluation rows.
    Expected: Output records the label-quality mix used for training and exposes `sale_probability_24h` metrics.
    Evidence: .sisyphus/evidence/task-10-saleability-eval.txt

  Scenario: No-label or low-label regime degrades safely
    Tool: Bash
    Steps: Evaluate the saleability head on a slice where label support is too thin.
    Expected: Command exits successfully with explicit `eligibility_reason`/low-support reporting instead of pretending to be calibrated.
    Evidence: .sisyphus/evidence/task-10-saleability-thin.txt
  ```

  **Commit**: YES | Message: `feat(ml): add mirage saleability head` | Files: `poe_trade/ml/*`, `tests/unit/*`, `pyproject.toml`

- [ ] 11. Build routed single-item and batch inference with PoE clipboard input

  **What to do**: Implement one inference surface that supports both single-item estimation and batch scoring. Single-item mode must accept raw PoE clipboard text copied with Ctrl+C/Ctrl+Alt+C, either from `--stdin`, `--file`, or `--clipboard`, parse it into canonical fields, assign routes, run the correct price path, join the saleability head, and return a structured estimate. The default human output should be concise and usable without extra flags and must include the central estimate plus `confidence_percent` at minimum; if saleability is available it must also include `sale_probability_percent`. JSON remains available for automation. Batch mode must take league source rows, assign routes, run the correct price path, join the saleability head, and write unified prediction rows. Each prediction must expose `route`, `price_p10/p50/p90`, `sale_probability_24h`, `confidence`, `comp_count`, `support_count_recent`, `freshness_minutes`, `fallback_reason`, and `prediction_explainer_json`. Use the dataset source by default, and add a validated `latest` source mode only after proving a safe replacement for the broken current-item view.
  **Must NOT do**: Do not expose a single opaque `predicted_price` without route/context metadata. Do not require complex JSON input for ordinary one-item usage. Do not omit confidence percent from default single-item output. Do not score from `v_ps_current_items` until a replacement or fix is verified in code and tests.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: this task integrates all route artifacts, fallback logic, and output contracts.
  - Skills: [] — why needed: no special repo skill beyond disciplined orchestration.
  - Omitted: [`frontend-ui-ux`] — why not needed: prediction serving/UI is out of scope.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: `12,14` | Blocked By: `2,4,5,6,7,8,9,10`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `04-exilelens-linux-item-capture.md:14` — PoE clipboard copy format is already documented as a primary backend input.
  - Pattern: `04-exilelens-linux-item-capture.md:60` — prior backend contract shape for parsed item text and price output.
  - Pattern: `poe_trade/strategy/scanner.py:25` — existing pattern for turning discovery outputs into persisted rows.
  - Pattern: `poe_trade/cli.py:442` — existing CLI pattern for printing persisted rows back to the console.
  - Pattern: `schema/migrations/0029_scanner_tables.sql` — additive table-first persistence pattern for downstream actions.
  - API/Type: `schema/migrations/0025_psapi_silver_current_views.sql:124` — current-item view intent; validate before using as a source.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml predict-one --league Mirage --input-format poe-clipboard --stdin < tests/fixtures/ml/sample_clipboard_item.txt` completes and prints a concise human-readable estimate by default including `confidence_percent`.
  - [ ] `.venv/bin/poe-ml predict-one --league Mirage --input-format poe-clipboard --stdin --output json < tests/fixtures/ml/sample_clipboard_item.txt` completes and prints structured JSON including `confidence_percent` and, when available, `sale_probability_percent`.
  - [ ] `.venv/bin/poe-ml predict-batch --league Mirage --model-dir artifacts/ml/mirage_v1 --source dataset --output-table poe_trade.ml_price_predictions_v1` completes and writes rows.
  - [ ] `clickhouse-client --query "DESCRIBE TABLE poe_trade.ml_price_predictions_v1"` includes `route`, `price_p50`, `sale_probability_24h`, `confidence`, `fallback_reason`, and `prediction_explainer_json`.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_predictions_v1 WHERE league='Mirage' AND route = ''"` returns `0`.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Clipboard-format single-item prediction succeeds
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml predict-one --league Mirage --input-format poe-clipboard --stdin < tests/fixtures/ml/sample_clipboard_item.txt`.
    Expected: Command exits 0 and returns parsed item fields plus route, interval estimate, and confidence shown as a percentage in the default format; if saleability is present it also shows sale probability as a percentage.
    Evidence: .sisyphus/evidence/task-11-predict-one.txt

  Scenario: Routed batch prediction writes unified outputs
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml predict-batch --league Mirage --model-dir artifacts/ml/mirage_v1 --source dataset --output-table poe_trade.ml_price_predictions_v1` and inspect schema plus one sample row per route.
    Expected: Predictions exist with route-specific metadata, interval outputs, saleability, and fallback fields.
    Evidence: .sisyphus/evidence/task-11-predict-batch.txt

  Scenario: Invalid clipboard text is rejected cleanly
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml predict-one --league Mirage --input-format poe-clipboard --stdin < tests/fixtures/ml/bad_clipboard_item.txt`.
    Expected: Command exits non-zero with a parse error that explains which clipboard-format requirement failed.
    Evidence: .sisyphus/evidence/task-11-predict-one-error.txt
  ```

  **Commit**: YES | Message: `feat(ml): add routed mirage batch prediction` | Files: `poe_trade/ml/*`, `schema/migrations/*`, `pyproject.toml`, `tests/unit/*`

- [ ] 12. Add rolling-origin evaluation, calibration, and continuous retraining loop

  **What to do**: Implement a rolling evaluation harness that trains/evaluates the routed stack over forward-only windows and writes route-level metrics to additive evaluation tables. The harness must keep listing chains on one side of each split, compare route baselines vs learned routes where relevant, and compute at minimum `mdape`, `wape`, `rmsle`, `abstain_rate`, and interval calibration metrics on the cleaned trainable subset. Also compute explicit cleaning diagnostics: `raw_coverage`, `clean_coverage`, `outlier_drop_rate`, and per-family quarantine reasons so the model’s apparent quality is never inflated by hidden filtering. On top of that, add a continuous retraining command, `poe-ml train-loop --league <league>`, that repeatedly rebuilds datasets, retrains active routes, evaluates them, and atomically refreshes the active model pointer for the requested league. The loop must persist run state by stage/route, emit real progress (`stage`, `current_route`, `routes_done`, `routes_total`, `rows_processed`, `eta_seconds` where feasible), support `poe-ml status --league <league> --run latest`, and resume safely after interruption. Hardware policy must be explicit: auto-detect the available backend, default to CPU-first execution on machines without confirmed stable GPU support, use ClickHouse-side aggregation/chunking, cap workers based on detected cores, and enforce a memory budget so training does not exhaust RAM. For the current environment profile (12 CPU cores, no confirmed NVIDIA device, limited available RAM, no swap), the default must be CPU backend, sequential route training, per-model threads capped at 6, and a default memory budget of 4 GiB unless the live availability audit lowers it further. Persist per-route, per-family, per-support-bucket evaluation rows plus a machine-readable no-leakage audit result.
  **Must NOT do**: Do not report only one pooled score. Do not use shuffled cross-validation or let the same listing chain leak across folds. Do not replace the active model with a newly trained one unless evaluation gates pass and artifacts are complete. Do not assume this machine has usable GPU training.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: evaluation discipline is the core safety mechanism for this ML stack.
  - Skills: [`evidence-bundle`] — why needed: the final review will need paste-ready verification artifacts.
  - Omitted: [`protocol-compat`] — why not needed: schema additions should already be straightforward by this point.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: `13,14` | Blocked By: `2,6,7,8,9,10,11`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `poe_trade/strategy/backtest.py:43` — offline run/evaluation command pattern.
  - Pattern: `schema/migrations/0028_research_backtests.sql:1` — run bookkeeping pattern.
  - Pattern: `schema/migrations/0031_research_backtest_summary_detail.sql:1` — summary/detail result storage pattern.
  - Pattern: `poe_trade/strategy/backtest.py:124` — explicit handling for `no_data` vs `no_opportunities`; mirror with ML evaluation statuses.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml evaluate --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --split rolling` completes and writes results.
  - [ ] `.venv/bin/poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --max-iterations 1` completes one end-to-end training cycle.
  - [ ] `.venv/bin/poe-ml status --league Mirage --run latest` returns stage/progress plus backend, workers, memory budget, and active model version.
  - [ ] `clickhouse-client --query "SELECT route, clean_coverage, raw_coverage, outlier_drop_rate, mdape, wape, rmsle, abstain_rate, interval_80_coverage FROM poe_trade.ml_eval_runs WHERE league='Mirage' ORDER BY route"` returns rows.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_eval_runs WHERE league='Mirage' AND split_kind != 'rolling'"` returns `0` for the canonical evaluation command.
  - [ ] `clickhouse-client --query "SELECT stage, current_route, routes_done, routes_total, chosen_backend, worker_count, memory_budget_gb, status FROM poe_trade.ml_train_runs WHERE league='Mirage' ORDER BY started_at DESC LIMIT 1"` returns the latest run state.
  - [ ] A no-leakage audit artifact is generated for each evaluation run.
  - [ ] If a training run fails evaluation gates, the prior active model remains the active model for that league.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Rolling evaluation writes route-level metrics
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml evaluate --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --split rolling` and query `poe_trade.ml_eval_runs`.
    Expected: Route-level metrics exist for every active route and include calibration/coverage fields plus explicit outlier-drop diagnostics.
    Evidence: .sisyphus/evidence/task-12-rolling-eval.txt

  Scenario: Endless training loop can be exercised safely
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --max-iterations 1`.
    Expected: One full cycle completes successfully; removing `--max-iterations` would leave the loop running endlessly on the configured interval, with persisted run state and no unsafe promotion behavior.
    Evidence: .sisyphus/evidence/task-12-train-loop.txt

  Scenario: Status/progress and resume work after interruption
    Tool: Bash
    Steps: Start a training loop, interrupt it after at least one stage begins, then run `poe-ml status --league Mirage --run latest` followed by a resumed `poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --resume --max-iterations 1`.
    Expected: Status shows the partial run with backend/workers/memory budget and stage progress; resumed training continues safely instead of restarting blindly or losing the previous active model.
    Evidence: .sisyphus/evidence/task-12-resume-status.txt

  Scenario: Failed candidate model is not promoted
    Tool: Bash
    Steps: Run a training/evaluation cycle configured to fail promotion gates, then inspect the active model pointer before and after the failed run.
    Expected: The candidate run is recorded as failed or non-promotable, and the previously active model remains active for the league.
    Evidence: .sisyphus/evidence/task-12-promotion-guard.txt
  ```

  **Commit**: YES | Message: `feat(ml): add rolling mirage evaluation` | Files: `poe_trade/ml/*`, `schema/migrations/*`, `pyproject.toml`, `tests/unit/*`

- [ ] 13. Publish ML reports, artifacts, and evidence bundle outputs

  **What to do**: Add reporting commands that summarize the latest Mirage model run into machine-readable tables/files and a concise operator-facing report. Report route coverage, per-route metrics, family hot spots, abstain/fallback rates, confidence calibration, the top causes of low-confidence predictions, and explicit cleaning diagnostics such as outlier drop rates and quarantine reasons. Add a short operator quickstart for the isolated tool covering the three core workflows: start/monitor training, estimate one item from clipboard text, and inspect the active model/report. Package the verification bundle so later reviews can inspect exact commands and outputs without re-running training.
  **Must NOT do**: Do not bury evaluation inside ad hoc logs. Do not present only aggregate wins while hiding weak routes, high abstain rates, or aggressive filtering.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: this is reporting and evidence shaping on top of completed evaluation data.
  - Skills: [`evidence-bundle`, `docs-specialist`] — why needed: produce concise, reusable review artifacts with minimal diff noise.
  - Omitted: [`ultrabrain`] — why not needed: the hard reasoning work is already done upstream.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: `14` | Blocked By: `12`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `README.md` — CLI-first command documentation style already used by the repo.
  - Pattern: `poe_trade/analytics/reports.py:12` — lightweight report query pattern.
  - Pattern: `schema/migrations/0031_research_backtest_summary_detail.sql:17` — detail table pattern for drill-down outputs.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml report --league Mirage --model-dir artifacts/ml/mirage_v1 --output .sisyphus/evidence/task-13-ml-report.json` completes and writes a report file.
  - [ ] The report contains `route_metrics`, `family_hotspots`, `abstain_rate`, `confidence_buckets`, `low_confidence_reasons`, and `outlier_cleaning_summary` sections.
  - [ ] Evidence-bundle output references the exact CLI commands used for build/train/evaluate/predict.
  - [ ] Quickstart docs include exactly the simple operator commands for `train-loop`, `status`, and `predict-one`.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: ML report summarizes route-level strengths and weaknesses
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml report --league Mirage --model-dir artifacts/ml/mirage_v1 --output .sisyphus/evidence/task-13-ml-report.json`.
    Expected: JSON report exists and includes per-route metrics, abstain rate, low-confidence reason summaries, and outlier-cleaning diagnostics.
    Evidence: .sisyphus/evidence/task-13-ml-report.json

  Scenario: Reporting fails loudly when evaluation data is missing
    Tool: Bash
    Steps: Run the report command against an empty/nonexistent model directory or before evaluation tables exist.
    Expected: Non-zero exit with a clear missing-evaluation error.
    Evidence: .sisyphus/evidence/task-13-ml-report-error.txt
  ```

  **Commit**: YES | Message: `feat(ml): add mirage pricing reports` | Files: `poe_trade/ml/*`, `docs/*`, `pyproject.toml`, `tests/unit/*`

- [ ] 14. Validate a safe `latest` source and complete Mirage batch-scoring smoke tests

  **What to do**: Replace or repair the current-item source path needed for `--source latest`, then add a batch-scoring smoke test over the newest Mirage snapshot. If `v_ps_current_items` remains unsafe, introduce a new additive `ml_latest_items_v1` view/table built from stable sources and wire `predict-batch --source latest` to that instead. Verify the latest-source pipeline returns routed predictions for fresh Mirage rows without leaking future context.
  **Must NOT do**: Do not silently reuse the currently broken live `v_ps_current_items` definition. Do not ship `--source latest` without an explicit validation artifact.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: latest-source validation crosses schema, dataset logic, and prediction orchestration.
  - Skills: [`protocol-compat`, `evidence-bundle`] — why needed: safe additive repair plus strong final evidence.
  - Omitted: [`playwright`] — why not needed: this is CLI/data validation, not browser work.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: none | Blocked By: `2,3,4,5,6,7,8,9,10,11,12,13`

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:108` — current-stash aggregation logic to inspect for the broken current-item path.
  - Pattern: `schema/migrations/0025_psapi_silver_current_views.sql:124` — current-item view that must be repaired or replaced safely.
  - Pattern: `schema/migrations/0018_cleanup_unused_objects.sql:6` — additive replacements are preferred over reviving removed legacy objects blindly.
  - Pattern: `poe_trade/db/clickhouse.py:43` — use the shared client for validation commands.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `.venv/bin/poe-ml predict-batch --league Mirage --model-dir artifacts/ml/mirage_v1 --source latest --output-table poe_trade.ml_price_predictions_v1` completes successfully.
  - [ ] `clickhouse-client --query "SELECT count() FROM poe_trade.ml_price_predictions_v1 WHERE league='Mirage' AND source_kind='latest'"` returns `> 0`.
  - [ ] A validation artifact demonstrates that every `latest` prediction uses context fields with timestamps `<= prediction_as_of_ts`.
  - [ ] If a replacement latest-source view/table is introduced, it is additive and documented in the report/evidence bundle.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Latest-source batch scoring succeeds after validation
    Tool: Bash
    Steps: Run `.venv/bin/poe-ml predict-batch --league Mirage --model-dir artifacts/ml/mirage_v1 --source latest --output-table poe_trade.ml_price_predictions_v1` and query latest-source row counts.
    Expected: Latest-source predictions exist with route, confidence, and timestamp-safe context fields.
    Evidence: .sisyphus/evidence/task-14-latest-success.txt

  Scenario: Future-context guard fails loudly
    Tool: Bash
    Steps: Run the latest-source validation audit against the generated predictions.
    Expected: Zero violating rows; if future context is detected, the audit exits non-zero and blocks the task.
    Evidence: .sisyphus/evidence/task-14-latest-audit.txt
  ```

  **Commit**: YES | Message: `feat(ml): validate latest mirage pricing source` | Files: `schema/migrations/*`, `poe_trade/sql/ml/*`, `poe_trade/ml/*`, `pyproject.toml`, `tests/unit/*`, `docs/*`


## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Use one atomic commit per numbered task unless two same-wave tasks touch the same contract surface and the plan explicitly says otherwise.
- Keep schema, CLI surface, and model logic commits separate so rollbacks stay cheap.
- Use conventional messages such as `feat(ml): add mirage dataset builder` and `feat(ml): add routed pricing evaluation`.

## Success Criteria
- Mirage batch predictions exist for every configured route and explicitly degrade via fallback/abstention when support is thin.
- Evaluation proves forward-only performance with route-level error metrics, route coverage, and interval calibration rather than one pooled score.
- The system can explain each prediction with route, confidence, comp count/reference source, feature freshness, and fallback reason.
- The tool can be operated with a simple three-command workflow: `train-loop`, `status`, and `predict-one`.
- Training runs show real progress, resume safely after interruption, stay within the hardware budget, and never replace the active model with a worse or failed candidate.
- Schema and CLI changes are additive, repo-native, and verified by automated evidence artifacts.
