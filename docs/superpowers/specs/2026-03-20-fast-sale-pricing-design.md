# Fast-Sale Pricing Redesign Specification

## Goal

Build a pricing system that recommends a realistic **fast-sale** listing price for any given item by combining robust market comparables with ML adjustment, while filtering fake low listings and inflated stale highs.

## Problem Statement

The current ML pricing stack can produce predictions that are worse than naive baselines because:

- labels are noisy and often closer to raw listing asks than true sellable prices,
- offline evaluation does not fully reflect the live serving path,
- route/fallback/confidence behavior can dominate final output without being the primary optimization target,
- sparse rare-item features can lose discriminative signal.

## Product Objective

For each item, recommend a price that is:

- credible given current market comparables,
- likely to sell in a short horizon,
- resistant to fake lowball and inflated stale listings,
- accompanied by an honest confidence signal.

## Operational Definitions

- **Fast-sale horizon:** `24h` from listing snapshot timestamp.
- **Sold proxy:** listing disappears within horizon without explicit delist reason and had no obvious invalid price markers.
- **Unsold/censored handling:** rows without observed sell proxy inside horizon are retained with lower reliability weight instead of dropped.
- **Censored reliability weight (initial):**
  - sold-proxy positive rows: weight `1.0`,
  - censored rows with support `>= 25`: weight `0.6`,
  - censored rows with support `< 25`: weight `0.4`.
- **Normalized price:** chaos-equivalent price at snapshot time using same FX normalization path as dataset v2.
- **Robust fast-sale target:** weighted market-anchor estimate derived from comparable listings after route-aware outlier filtering.

## Non-Goals

- Predicting exact eventual sale timestamp.
- Solving all rare-item edge cases in one release.
- Replacing all existing routes in a single migration step.

## Design Overview

The new pipeline is split into explicit stages:

1. **Comparable retrieval**: gather market-neighbor listings for the candidate item.
2. **Robust market estimator**: compute a credible market band and anchor using outlier-aware filters.
3. **ML adjustment model**: predict an adjustment around the anchor based on item attributes.
4. **Recommendation policy**: produce final fast-sale recommendation, confidence, and abstain decisions.
5. **Serving-aligned evaluation**: score the exact live inference path end-to-end.

This keeps market realism as the foundation while using ML for fine-grained precision.

## Stage 1: Comparable Retrieval

### Inputs

- league, category, base_type, rarity, item modifiers and key descriptors.

### Behavior

- Route-aware retrieval rules by item family.
- Minimum support thresholds per route.
- Prioritize recency and semantic similarity.

### Deterministic Retrieval Contract

- Hard filters: same league, same route family, matching item class constraints.
- Similarity score = weighted sum of:
  - exact base type match (`0.35`),
  - mod signature overlap (`0.30`),
  - item level proximity (`0.10`),
  - influence/corruption/synthesis state compatibility (`0.10`),
  - recency decay (`0.15`).
- Tie-breakers: higher similarity, newer listing, then stable listing id.
- Candidate cap: top `K=200` comparables per query.
- Fallback behavior: if support `< route_min_support`, fallback to broader family scope before abstain.

### Outputs

- candidate comparable set with support diagnostics.

## Stage 2: Robust Market Estimator

### Core Logic

- Filter suspicious lows (fake listings, low-support anomalies).
- Filter stale/extreme highs.
- Use robust estimators (trimmed/weighted quantiles) for:
  - `credible_low`,
  - `credible_high`,
  - `anchor_price`.

### Testable Rule Set (v1)

- Recency window: last `72h` listings (configurable).
- Minimum support after filtering:
  - `structured`: 25,
  - `sparse`: 15,
  - `fallback family`: 10.
- Route-specific credibility floors:
  - structured routes: `0.60 * q25`,
  - sparse routes: `0.70 * q25`,
  - fallback family: `0.75 * q25`.
- Low trim: remove listings below `q05 - 1.5 * IQR` or below route-specific credibility floor.
- High trim: remove listings above `q95 + 1.5 * IQR` and listings older than recency window.
- Listing-quality weight formula:
  - `w_quality = sold_proxy_weight * min(1.0, ln(1 + seller_observation_count) / ln(11))`
  - where `sold_proxy_weight` is `1.0` for sold-proxy positives and `0.7` otherwise.
- Anchor calculation: weighted quantile median (`q50`) with recency and listing-quality weights.
- Credible band: weighted `q25` to weighted `q75` after trimming.

### Diagnostics

- outlier trim counts/rates,
- support count,
- recency indicators,
- band width and stability.

## Stage 3: ML Adjustment Model

### Target Formulation

- Predict relative adjustment from anchor (for example log ratio) rather than raw absolute price.

### Features

- Existing structured item fields,
- improved sparse-mod retention for rare items,
- route/family context,
- liquidity/support diagnostics from Stage 2.

### Rationale

Anchor-first targets reduce sensitivity to market-wide drift and listing-level noise.

## Stage 4: Recommendation Policy

### Output Contract

- final recommended fast-sale price,
- credible price band,
- confidence,
- abstain reason when confidence/support is insufficient.

### Rules

- Do not emit narrow precise prices when confidence is weak.
- Prefer abstain or wider band over hallucinated precision.

### Confidence Definition

- Confidence is calibrated expected relative error bucket derived from:
  - post-filter support size,
  - band stability,
  - route historical calibration,
  - model residual uncertainty on adjustment head.
- Calibration metric: Expected Calibration Error (ECE) over fixed confidence bins.
- Regression accuracy event for calibration is `RAE <= 0.30`; ECE compares predicted confidence to empirical probability of that event in each bin.

### Stage Output Contract (v1)

- `comparables`: `[{listing_id:str, price_chaos:float, observed_at:str, similarity:float, quality_weight:float}]`
- `anchor`: `{anchor_price:float, credible_low:float, credible_high:float, support_count:int, trim_low_count:int, trim_high_count:int}`
- `adjustment`: `{adjustment_ratio:float, adjusted_price:float, residual_uncertainty:float}`
- `policy`: `{recommended_price:float|null, confidence:float, abstained:bool, abstain_reasons:list[str]}`
- All prices are chaos-equivalent floats and timestamps are UTC string values.

### Abstain Rules (initial)

- Abstain if filtered support `< min_support(route)`.
- Abstain if credible band width ratio `> 0.9`.
- Abstain if confidence `< 0.35`.
- Abstain output must include reason codes (`low_support`, `unstable_band`, `low_confidence`, or combined).

## Stage 5: Evaluation and Promotion

### Evaluation Principle

Evaluate the exact serving path:

`comparables -> outlier filtering -> anchor -> ML adjustment -> policy output`

### Primary Metrics

- Fast-sale recommendation error vs robust target,
- segment-level extreme-miss rate,
- confidence calibration,
- support-aware abstain quality.

### Metric Formulas

- Relative Absolute Error (RAE): `abs(pred - target) / max(target, 0.01)`.
- Extreme miss: `RAE >= 1.0`.
- Band hit rate: `% of predictions inside [credible_low, credible_high]`.
- ECE: standard bin-based absolute gap between confidence and empirical accuracy.
- Abstain precision: `% abstains where forced-baseline RAE >= 0.75`.

### Aggregation and Cohorts

- Aggregation: micro-average and macro-average across required cohorts.
- Required cohorts:
  - route,
  - rarity,
  - liquidity/support bucket,
  - value band,
  - category family,
  - league.

### Promotion Gates

- Candidate must beat incumbent on serving-aligned metrics,
- no protected cohort regression,
- no confidence calibration degradation,
- no unacceptable increase in extreme misses.

### Numeric Gate Thresholds (initial)

- Overall RAE improves by `>= 5%` relative.
- Extreme miss rate does not worsen overall and improves by `>= 10%` in sparse cohorts.
- ECE must not worsen by more than `0.01` absolute.
- No required cohort may regress by more than `2%` relative on RAE.
- Abstain rate increase must be justified by improved extreme-miss suppression (`>= 15%` relative reduction).

Protected cohorts for gating are:

- sparse support bucket,
- top value band,
- rare + unique rarity cohorts.

### Validation Matrix

- Unit tests: retrieval scoring, outlier filtering, anchor computation, abstain policy.
- Integration tests: full serving path parity (`predict_one` end-to-end).
- Regression tests: candidate vs incumbent side-by-side on fixed evaluation slice.
- Promotion checks must use same serving path used in API inference.

## Observability

Track and expose:

- anchor usage rate,
- fallback/blend rate,
- abstain rate,
- outlier trim rate,
- confidence bucket calibration,
- worst-performing cohorts.

## Rollout Strategy

1. Shadow mode with side-by-side outputs and diagnostics.
2. Route-by-route cutover for stable cohorts.
3. Rollback path preserved through incumbent artifacts.

### Trigger-Based Rollout Controls

- Shadow duration: minimum 7 days and minimum 10k scored items.
- Cutover requires all numeric gates passing for 3 consecutive daily windows.
- Automatic rollback triggers:
  - extreme miss rate worsens by `> 15%` in any protected cohort,
  - ECE degrades by `> 0.03`,
  - abstain rate spikes by `> 25%` without error reduction.

## Risks and Mitigations

- **Risk:** Over-filtering removes true bargains.  
  **Mitigation:** Keep trim diagnostics and tune thresholds per route.
- **Risk:** Sparse categories remain under-supported.  
  **Mitigation:** Enforce abstain policy and retrieval fallback.
- **Risk:** Offline gains do not transfer live.  
  **Mitigation:** Serving-path-aligned evaluation required for promotion.

## Success Criteria

- Lower extreme miss frequency on sparse and high-value cohorts.
- Better fast-sale recommendation error than incumbent on live-path evaluation.
- Confidence monotonicity (higher confidence => better observed accuracy).
- Fewer misleading precise predictions in low-support markets.
