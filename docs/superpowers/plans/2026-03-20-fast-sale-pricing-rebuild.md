# Fast-Sale Pricing Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace noisy ask-price-first prediction with a robust comparable-anchor + ML adjustment pipeline that improves fast-sale recommendation quality and confidence honesty.

**Architecture:** Add deterministic comparable retrieval and outlier filtering to build a credible market anchor, train ML on adjustment-vs-anchor targets, and evaluate/promo-gate the exact serving path end-to-end. Keep incumbent path available during shadow rollout and enforce numeric promotion gates.

**Tech Stack:** Python 3.11, ClickHouse SQL/materialized views, scikit-learn, pytest.

---

### Task 1: Add Serving-Path Evaluation Baseline

**Files:**
- Modify: `poe_trade/ml/workflows.py`
- Create: `tests/unit/test_ml_serving_path_eval.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_serving_path_eval_uses_predict_one_pipeline():
    assert False

def test_serving_path_eval_reports_route_segment_metrics():
    assert False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_ml_serving_path_eval.py -v`
Expected: FAIL with missing serving-path evaluation function/report fields.

- [ ] **Step 3: Implement minimal serving-path evaluator**

Add function(s) in `poe_trade/ml/workflows.py` that score end-to-end `predict_one` outputs on an evaluation slice and emit:
- relative absolute error,
- extreme-miss rate,
- band hit rate,
- abstain precision,
- confidence calibration bucket stats,
- segment breakdowns.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_ml_serving_path_eval.py -v`
Expected: PASS.


### Task 2: Build Comparable Retrieval + Robust Anchor Module

**Files:**
- Modify: `poe_trade/ml/workflows.py`
- Create: `tests/unit/test_ml_anchor_estimator.py`

- [ ] **Step 1: Write failing tests for deterministic retrieval and anchor math**

```python
def test_comparable_similarity_score_is_deterministic():
    assert False

def test_anchor_filters_fake_lows_and_stale_highs():
    assert False

def test_anchor_outputs_contract_fields():
    assert False

def test_retrieval_caps_to_top_200_and_tiebreaks_deterministically():
    assert False

def test_retrieval_fallbacks_to_broader_family_before_abstain():
    assert False

def test_anchor_applies_support_minimums_25_15_10_by_route():
    assert False

def test_anchor_applies_credibility_floors_60_70_75_percent_q25():
    assert False

def test_anchor_applies_72h_recency_window():
    assert False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_ml_anchor_estimator.py -v`
Expected: FAIL due to missing retrieval/anchor functions.

- [ ] **Step 3: Implement retrieval scoring and outlier-aware anchor**

Implement deterministic comparable scoring with spec weights, trimming rules, and output contract fields:
- `anchor_price`, `credible_low`, `credible_high`,
- `support_count`, `trim_low_count`, `trim_high_count`,
- comparable list with similarity and quality weight.

Explicit similarity formula constants to implement and test:
- base type match `0.35`,
- mod signature overlap `0.30`,
- ilvl proximity `0.10`,
- state compatibility `0.10`,
- recency decay `0.15`.

- [ ] **Step 3a: Enforce retrieval contract invariants**

Implement and verify:
- `K=200` cap,
- ordering by similarity then recency then listing id,
- hard filters for league/route family/item class,
- broader-family fallback before abstain.

- [ ] **Step 3b: Enforce exact anchor constants**

Implement and verify:
- support minima (`25/15/10`),
- credibility floors (`0.60/0.70/0.75 * q25`),
- `72h` recency window,
- trim formulas from spec.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_ml_anchor_estimator.py -v`
Expected: PASS.


### Task 3: Add Adjustment-vs-Anchor Targets in Training

**Files:**
- Modify: `poe_trade/ml/workflows.py`
- Modify: `tests/unit/test_ml_tuning.py`

- [ ] **Step 1: Add failing tests for anchor-relative target transform**

```python
def test_training_uses_adjustment_vs_anchor_target_for_price_heads():
    assert False

def test_censored_reliability_weights_1_0_0_6_0_4_are_applied():
    assert False
```

- [ ] **Step 2: Run focused tests**

Run: `.venv/bin/pytest tests/unit/test_ml_tuning.py -k anchor -v`
Expected: FAIL.

- [ ] **Step 3: Implement minimal target transform and inverse**

Add training/inference transform for `log(price / anchor)` (or equivalent), ensure inverse is applied in serving.

- [ ] **Step 3a: Implement censored-row reliability weighting**

Apply and propagate row weights:
- sold-proxy positive: `1.0`,
- censored support `>=25`: `0.6`,
- censored support `<25`: `0.4`.

- [ ] **Step 4: Re-run focused tests**

Run: `.venv/bin/pytest tests/unit/test_ml_tuning.py -k anchor -v`
Expected: PASS.


### Task 4: Implement Confidence + Abstain Policy

**Files:**
- Modify: `poe_trade/ml/workflows.py`
- Modify: `tests/test_price_check_comparables.py`
- Create: `tests/unit/test_ml_confidence_policy.py`

- [ ] **Step 1: Write failing policy tests**

```python
def test_abstain_when_support_below_threshold():
    assert False

def test_abstain_when_band_instability_is_high():
    assert False

def test_policy_returns_reason_codes():
    assert False

def test_ece_uses_rae_lte_0_30_accuracy_event():
    assert False
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv/bin/pytest tests/unit/test_ml_confidence_policy.py tests/test_price_check_comparables.py -k "abstain or confidence" -v`
Expected: FAIL.

- [ ] **Step 3: Implement confidence scoring and abstain boundaries**

Implement spec thresholds and ensure policy output includes:
- `recommended_price` nullable,
- `confidence`,
- `abstained`,
- `abstain_reasons`.

- [ ] **Step 3a: Add output-contract validation tests**

Validate exact schema/types for `comparables`, `anchor`, `adjustment`, and `policy`, including UTC timestamp strings.

- [ ] **Step 4: Run tests and confirm pass**

Run: `.venv/bin/pytest tests/unit/test_ml_confidence_policy.py tests/test_price_check_comparables.py -k "abstain or confidence" -v`
Expected: PASS.


### Task 5: Align Promotion Gates to Serving Metrics

**Files:**
- Modify: `poe_trade/ml/workflows.py`
- Modify: `poe_trade/ml/contract.py`
- Modify: `tests/unit/test_ml_observability.py`

- [ ] **Step 1: Write failing gate tests**

```python
def test_promotion_requires_serving_path_rae_improvement():
    assert False

def test_promotion_blocks_on_calibration_regression():
    assert False

def test_promotion_requires_all_required_cohort_dimensions_present():
    assert False

def test_promotion_enforces_numeric_thresholds_exactly():
    assert False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/unit/test_ml_observability.py -k promotion -v`
Expected: FAIL.

- [ ] **Step 3: Implement numeric gate checks**

Update promotion decision path to consume serving-path metrics and enforce numeric thresholds from spec.

- [ ] **Step 3a: Enforce all threshold values as constants**

Enforce:
- RAE relative improvement `>=5%`,
- overall extreme-miss rate does not worsen,
- sparse extreme miss improvement `>=10%`,
- ECE degradation `<=0.01`,
- per-cohort regression cap `<=2%`,
- abstain-rate increase requires `>=15%` extreme-miss suppression.

- [ ] **Step 3b: Enforce protected cohorts and required cohort dimensions**

Protected cohorts: sparse support, top value band, rare+unique. Required dimensions: route, rarity, support bucket, value band, category family, league.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/unit/test_ml_observability.py -k promotion -v`
Expected: PASS.


### Task 6: Add Dataset Diagnostics for Outlier/Anchor Signals

**Files:**
- Create: `schema/migrations/0050_ml_fast_sale_anchor_signals_v1.sql`
- Modify: `tests/unit/test_ml_workflows_incremental_repair.py`
- Modify: `poe_trade/ml/workflows.py`

- [ ] **Step 1: Write failing tests for expected diagnostic fields usage**

```python
def test_incremental_pipeline_exposes_anchor_support_and_trim_diagnostics():
    assert False
```

- [ ] **Step 2: Run test and verify failure**

Run: `.venv/bin/pytest tests/unit/test_ml_workflows_incremental_repair.py -k anchor -v`
Expected: FAIL.

- [ ] **Step 3: Add migration and wiring**

Add additive schema for anchor/outlier diagnostics and wire readers in workflow paths.

- [ ] **Step 4: Run tests and migration status checks**

Run: `.venv/bin/pytest tests/unit/test_ml_workflows_incremental_repair.py -k anchor -v`
Expected: PASS.


### Task 7: Verify End-to-End Deterministic Behavior

**Files:**
- Modify: `docs/evidence/ml-pricing-deterministic-pack.md`
- Optional create/update evidence artifacts under `.sisyphus/evidence/` (only if generated)

- [ ] **Step 1: Run targeted ML unit test suites**

Run: `.venv/bin/pytest tests/unit/test_ml_*.py tests/test_price_check_comparables.py -v`
Expected: PASS.

- [ ] **Step 2: Run deterministic gate**

Run: `make ci-deterministic`
Expected: PASS with updated ML evidence checks.

- [ ] **Step 3: Run bounded ML loop smoke test (if environment available)**

Run: `.venv/bin/poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v2 --model-dir artifacts/ml/mirage_v2 --max-iterations 1 --max-wall-clock-seconds 900 --no-improvement-patience 1 --min-mdape-improvement 0.005`
Expected: command completes with explicit stop reason and serving-path metrics emitted.


### Task 8: Shadow Rollout and Cutover Readiness

**Files:**
- Modify: `poe_trade/ml/workflows.py`
- Modify: `docs/ops-runbook.md`
- Modify: `tests/unit/test_ml_observability.py`
- Modify: `tests/unit/test_api_ml_routes.py`

- [ ] **Step 1: Add failing tests for shadow metric serialization**

```python
def test_status_surfaces_serving_path_gate_metrics_for_shadow_mode():
    assert False
```

- [ ] **Step 1a: Run tests to confirm failure before implementation**

Run: `.venv/bin/pytest tests/unit/test_ml_observability.py tests/unit/test_api_ml_routes.py -k "shadow or status" -v`
Expected: FAIL with missing/new status fields or gate payloads.

- [ ] **Step 2: Implement shadow counters and gate payload exposure**

Expose running window metrics needed for cutover and rollback triggers.

- [ ] **Step 2a: Enforce rollout trigger constants in status/gate payload**

Expose and validate:
- minimum `7d` shadow duration,
- minimum `10k` scored items,
- `3` consecutive passing windows,
- rollback trigger thresholds (`>15%` protected-cohort extreme-miss worsening, `>0.03` ECE degradation, `>25%` abstain spike without improvement).

- [ ] **Step 2b: Add observability fields and tests for all spec counters**

Ensure status/report surfaces and tests assert:
- `anchor_usage_rate`,
- `fallback_or_blend_rate`,
- `abstain_rate`,
- `outlier_trim_rate`,
- confidence calibration outputs.

- [ ] **Step 3: Update runbook with exact rollout commands and rollback triggers**

Document command-first operator procedure with threshold values from the spec.

- [ ] **Step 4: Verify docs and status tests**

Run: `.venv/bin/pytest tests/unit/test_ml_observability.py tests/unit/test_api_ml_routes.py -k "shadow or status" -v`
Expected: PASS.


## Final Verification Checklist

- [ ] `.venv/bin/pytest tests/unit/test_ml_*.py tests/test_price_check_comparables.py -v`
- [ ] `.venv/bin/pytest tests/unit -v`
- [ ] `make ci-deterministic`
- [ ] `poe-migrate --status --dry-run`

## Notes for Implementers

- Keep changes additive where possible; do not remove incumbent path until shadow evidence is stable.
- Do not claim quality improvements without serving-path metrics.
- Prefer explicit route-level diagnostics over hidden fallback behavior.

## Commit Checkpoints

- [ ] Commit after Task 2: retrieval + anchor contracts.
- [ ] Commit after Task 4: confidence/abstain + output schema.
- [ ] Commit after Task 5: promotion gates.
- [ ] Final commit after Task 8 + verification.
