# ML v3 Hard-Cut Accuracy Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild pricing to a single v3 pipeline that preserves only `raw_*`, uses ClickHouse-first transforms, predicts every item type, and outputs both fair value (`p50`) and 24h fast-sale price.

**Architecture:** Build event-sourced item lifecycle tables from `poe_trade.raw_public_stash_pages`, derive probabilistic sale labels from disappearance/relist behavior, train a route-aware retrieval+rerank stack, and serve dual outputs (`fair_value_p50`, `fast_sale_24h_price`). After v3 cutover, remove all legacy non-raw derived pipeline objects and fallback code paths.

**Tech Stack:** ClickHouse (`MergeTree` / `ReplacingMergeTree`, codecs, partitioned backfill), Python 3.11, scikit-learn + CatBoost + Optuna, existing API/CLI/service layer.

---

## File Structure

- Create: `schema/migrations/0051_ml_v3_silver_observations.sql`
- Create: `schema/migrations/0052_ml_v3_events_and_sale_proxy_labels.sql`
- Create: `schema/migrations/0053_ml_v3_training_and_serving_store.sql`
- Create: `schema/migrations/0054_ml_v3_eval_and_promotion.sql`
- Create: `schema/migrations/0055_ml_v3_cleanup_legacy_derived.sql`
- Create: `poe_trade/ml/v3/__init__.py`
- Create: `poe_trade/ml/v3/sql.py`
- Create: `poe_trade/ml/v3/backfill.py`
- Create: `poe_trade/ml/v3/features.py`
- Create: `poe_trade/ml/v3/train.py`
- Create: `poe_trade/ml/v3/serve.py`
- Create: `poe_trade/ml/v3/eval.py`
- Modify: `poe_trade/ml/cli.py`
- Modify: `poe_trade/services/ml_trainer.py`
- Modify: `poe_trade/api/ml.py`
- Modify: `poe_trade/api/ops.py`
- Modify: `pyproject.toml`
- Modify: `tests/unit/test_migrations.py`
- Create: `tests/unit/test_ml_v3_sql_contract.py`
- Create: `tests/unit/test_ml_v3_backfill.py`
- Create: `tests/unit/test_ml_v3_features.py`
- Create: `tests/unit/test_ml_v3_train.py`
- Create: `tests/unit/test_ml_v3_serve.py`
- Create: `tests/unit/test_ml_v3_eval.py`
- Modify: `tests/unit/test_ml_cli.py`
- Modify: `tests/unit/test_api_ml_routes.py`
- Modify: `tests/test_price_check_comparables.py`
- Modify: `tests/unit/test_service_ml_trainer.py`
- Modify: `README.md`
- Modify: `docs/ops-runbook.md`

## Task 1: ClickHouse v3 Foundation (raw preserved, derived rebuilt)

**Files:**
- Create: `schema/migrations/0051_ml_v3_silver_observations.sql`
- Modify: `tests/unit/test_migrations.py`
- Test: `tests/unit/test_migrations.py`, `tests/unit/test_ml_v3_sql_contract.py`

- [ ] Write failing migration tests for v3 observation schema.
- [ ] Run: `.venv/bin/pytest tests/unit/test_migrations.py -k v3 -v` (expect FAIL).
- [ ] Implement migration 0051.
- [ ] Re-run same tests (expect PASS).

## Task 2: Lifecycle Events + Sale Proxy Labels in SQL

**Files:**
- Create: `schema/migrations/0052_ml_v3_events_and_sale_proxy_labels.sql`
- Create: `poe_trade/ml/v3/sql.py`
- Test: `tests/unit/test_ml_v3_sql_contract.py`

- [ ] Add failing SQL contract tests for events and sale labels.
- [ ] Run: `.venv/bin/pytest tests/unit/test_ml_v3_sql_contract.py -v` (expect FAIL).
- [ ] Implement SQL objects and helper query builders.
- [ ] Re-run tests (expect PASS).

## Task 3: Feature Contract (tier + roll parity)

**Files:**
- Create: `poe_trade/ml/v3/features.py`
- Modify: `poe_trade/api/ops.py`
- Test: `tests/unit/test_ml_v3_features.py`, `tests/test_ml_clipboard_parsing.py`

- [ ] Write failing feature parity tests.
- [ ] Run: `.venv/bin/pytest tests/unit/test_ml_v3_features.py tests/test_ml_clipboard_parsing.py -v` (expect FAIL).
- [ ] Implement canonical v3 feature builder.
- [ ] Re-run tests (expect PASS).

## Task 4: Disk-Budgeted Backfill (15GB-safe)

**Files:**
- Create: `poe_trade/ml/v3/backfill.py`
- Modify: `poe_trade/ml/cli.py`
- Test: `tests/unit/test_ml_v3_backfill.py`, `tests/unit/test_ml_cli.py`

- [ ] Write failing tests for partitioned backfill and disk guardrails.
- [ ] Run: `.venv/bin/pytest tests/unit/test_ml_v3_backfill.py tests/unit/test_ml_cli.py -k v3 -v` (expect FAIL).
- [ ] Implement backfill runner and CLI commands.
- [ ] Re-run tests (expect PASS).

## Task 5: Training Store + Retrieval Candidates

**Files:**
- Create: `schema/migrations/0053_ml_v3_training_and_serving_store.sql`
- Modify: `poe_trade/ml/v3/sql.py`
- Test: `tests/unit/test_ml_v3_sql_contract.py`

- [ ] Add failing tests for v3 training and serving stores.
- [ ] Run: `.venv/bin/pytest tests/unit/test_ml_v3_sql_contract.py -k training -v` (expect FAIL).
- [ ] Implement migration 0053.
- [ ] Re-run tests (expect PASS).

## Task 6: Training (fair value + fast-sale)

**Files:**
- Create: `poe_trade/ml/v3/train.py`
- Modify: `pyproject.toml`
- Modify: `poe_trade/services/ml_trainer.py`
- Test: `tests/unit/test_ml_v3_train.py`, `tests/unit/test_service_ml_trainer.py`

- [ ] Write failing tests for route experts and dual outputs.
- [ ] Run: `.venv/bin/pytest tests/unit/test_ml_v3_train.py tests/unit/test_service_ml_trainer.py -k v3 -v` (expect FAIL).
- [ ] Add dependencies and implement trainer.
- [ ] Re-run tests (expect PASS).

## Task 7: Serving (always predict, dual price outputs)

**Files:**
- Create: `poe_trade/ml/v3/serve.py`
- Modify: `poe_trade/api/ml.py`
- Modify: `poe_trade/api/ops.py`
- Test: `tests/unit/test_ml_v3_serve.py`, `tests/unit/test_api_ml_routes.py`, `tests/test_price_check_comparables.py`

- [ ] Write failing tests for v3 response contract.
- [ ] Run: `.venv/bin/pytest tests/unit/test_ml_v3_serve.py tests/unit/test_api_ml_routes.py tests/test_price_check_comparables.py -k v3 -v` (expect FAIL).
- [ ] Implement serving adapter and API payload mapping.
- [ ] Re-run tests (expect PASS).

## Task 8: Evaluation + Promotion Gates

**Files:**
- Create: `schema/migrations/0054_ml_v3_eval_and_promotion.sql`
- Create: `poe_trade/ml/v3/eval.py`
- Modify: `poe_trade/services/ml_trainer.py`
- Test: `tests/unit/test_ml_v3_eval.py`, `tests/unit/test_ml_promotion_serving_gate.py`, `tests/unit/test_ml_serving_path_eval.py`

- [ ] Add failing tests for slice-aware quality and calibration gates.
- [ ] Run: `.venv/bin/pytest tests/unit/test_ml_v3_eval.py tests/unit/test_ml_promotion_serving_gate.py tests/unit/test_ml_serving_path_eval.py -k v3 -v` (expect FAIL).
- [ ] Implement migration 0054 and evaluator logic.
- [ ] Re-run tests (expect PASS).

## Task 9: Legacy Derived Cleanup

**Files:**
- Create: `schema/migrations/0055_ml_v3_cleanup_legacy_derived.sql`
- Modify: `poe_trade/ml/cli.py`
- Modify: `poe_trade/ml/workflows.py`
- Test: `tests/unit/test_migrations.py`, `tests/unit/test_ml_cli.py`

- [ ] Add failing tests ensuring cleanup excludes all `raw_*` tables.
- [ ] Run: `.venv/bin/pytest tests/unit/test_migrations.py tests/unit/test_ml_cli.py -k cleanup -v` (expect FAIL).
- [ ] Implement cleanup migration and remove legacy command paths.
- [ ] Re-run tests (expect PASS).

## Task 10: Documentation + Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ops-runbook.md`

- [ ] Update docs for v3-only pipeline and disk-budgeted backfill.
- [ ] Run: `.venv/bin/pytest tests/unit -v` (expect PASS).
- [ ] Run: `.venv/bin/pytest tests/test_price_check_comparables.py tests/test_ml_clipboard_parsing.py -v` (expect PASS).
- [ ] Run: `poe-migrate --status --dry-run` and confirm coherent migration status.

## Hard Constraints

- Preserve only `poe_trade.raw_*` as canonical historical data.
- Use ClickHouse SQL for heavy transforms; Python only orchestrates batch windows.
- Backfill by partition/day with checkpointed resume.
- Enforce storage budget guardrails using `system.parts` before each batch.
- Use explicit type/codec choices (`LowCardinality`, `UInt8`, `Float32/64`, `ZSTD` on large strings).
- Drop legacy derived objects after successful v3 cutover.
