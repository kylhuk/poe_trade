from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import pytest

from poe_trade.ml import workflows


def test_candidate_vs_incumbent_promote_verdict():
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-1",
            "avg_mdape": 0.7,
            "avg_cov": 0.85,
            "eval_slice_id": "eval-slice-1",
        },
        incumbent={
            "run_id": "inc-1",
            "avg_mdape": 0.9,
            "avg_cov": 0.82,
            "eval_slice_id": "eval-slice-1",
        },
    )
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "max_mdape_regression": 0.0,
        "cohort": "none",
    }

    assert workflows._should_promote(comparison) is True
    assert workflows._promotion_stop_reason(comparison) == "promote"


def test_candidate_vs_incumbent_hold_for_coverage():
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-1",
            "avg_mdape": 0.7,
            "avg_cov": 0.7,
            "eval_slice_id": "eval-slice-2",
        },
        incumbent={
            "run_id": "inc-1",
            "avg_mdape": 0.9,
            "avg_cov": 0.82,
            "eval_slice_id": "eval-slice-2",
        },
    )
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "max_mdape_regression": 0.0,
        "cohort": "none",
    }

    assert workflows._should_promote(comparison) is False
    assert workflows._promotion_stop_reason(comparison) == "hold_coverage_floor"


def test_candidate_vs_incumbent_hold_for_protected_regression():
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-1",
            "avg_mdape": 0.7,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-3",
        },
        incumbent={
            "run_id": "inc-1",
            "avg_mdape": 0.9,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-3",
        },
    )
    comparison["protected_cohort_regression"] = {
        "regression": True,
        "max_mdape_regression": 0.03,
        "cohort": "structured_boosted|unique|high",
    }

    assert workflows._should_promote(comparison) is False
    assert (
        workflows._promotion_stop_reason(comparison)
        == "hold_protected_cohort_regression"
    )


def test_train_loop_stops_for_no_improvement(monkeypatch, tmp_path):
    client = cast(workflows.ClickHouseClient, cast(object, SimpleNamespace()))
    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda _client: None)
    monkeypatch.setattr(workflows, "_ensure_tuning_rounds_table", lambda _client: None)
    monkeypatch.setattr(
        workflows, "_active_model_version", lambda _client, _league: "v0"
    )
    monkeypatch.setattr(workflows, "train_all_routes", lambda *args, **kwargs: None)
    monkeypatch.setattr(workflows, "_dataset_row_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(workflows, "_write_train_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(workflows, "_record_tuning_round", lambda *args, **kwargs: None)
    monkeypatch.setattr(workflows, "_promote_models", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        workflows, "_latest_train_run_row", lambda _c, _l: {"run_id": "r"}
    )
    monkeypatch.setattr(
        workflows,
        "_resolve_tuning_controls",
        lambda **kwargs: workflows.TuningControls(
            max_iterations=5,
            max_wall_clock_seconds=3600,
            no_improvement_patience=1,
            min_mdape_improvement=0.1,
            warm_start_enabled=True,
            resume_supported=False,
        ),
    )
    monkeypatch.setattr(
        workflows,
        "_run_manifest",
        lambda *_args, **_kwargs: {
            "dataset_snapshot_id": "dataset-test",
            "eval_slice_id": "eval-slice-test",
            "source_watermarks": {"dataset_max_as_of_ts": "2026-03-18 10:00:00"},
        },
    )

    def _fake_eval(*args, **kwargs):
        return {
            "run_id": "eval-1",
            "promotion_verdict": "hold",
            "stop_reason": "hold_no_material_improvement",
            "candidate_vs_incumbent": {
                "candidate_avg_mdape": 0.9,
                "incumbent_avg_mdape": 0.9,
                "mdape_improvement": 0.0,
                "coverage_floor_ok": True,
                "protected_cohort_regression": {"regression": False},
            },
        }

    monkeypatch.setattr(workflows, "evaluate_stack", _fake_eval)

    result = workflows.train_loop(
        client,
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        model_dir=str(tmp_path),
        max_iterations=5,
        max_wall_clock_seconds=3600,
        no_improvement_patience=1,
        min_mdape_improvement=0.1,
        resume=False,
    )

    assert result["status"] == "stopped_no_improvement"
    assert result["stop_reason"] == "no_improvement_patience_exhausted"


def test_training_uses_adjustment_vs_anchor_target_for_price_heads() -> None:
    ratio = workflows._anchor_adjustment_target(price=12.0, anchor_price=10.0)
    restored = workflows._invert_anchor_adjustment_target(
        adjustment_target=ratio,
        anchor_price=10.0,
    )
    assert restored == pytest.approx(12.0)


def test_censored_reliability_weights_1_0_0_6_0_4_are_applied() -> None:
    sold = workflows._censored_reliability_weight(is_sold_proxy=True, support_count=10)
    supported = workflows._censored_reliability_weight(
        is_sold_proxy=False,
        support_count=25,
    )
    thin = workflows._censored_reliability_weight(is_sold_proxy=False, support_count=24)
    assert sold == 1.0
    assert supported == 0.6
    assert thin == 0.4


def test_train_loop_resume_requires_existing_run(monkeypatch, tmp_path):
    client = cast(workflows.ClickHouseClient, cast(object, SimpleNamespace()))
    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda _client: None)
    monkeypatch.setattr(workflows, "_ensure_tuning_rounds_table", lambda _client: None)
    monkeypatch.setattr(workflows, "_latest_train_run_row", lambda _c, _l: None)
    monkeypatch.setattr(
        workflows,
        "_resolve_tuning_controls",
        lambda **kwargs: workflows.TuningControls(
            max_iterations=1,
            max_wall_clock_seconds=60,
            no_improvement_patience=1,
            min_mdape_improvement=0.01,
            warm_start_enabled=True,
            resume_supported=False,
        ),
    )
    monkeypatch.setattr(
        workflows,
        "_run_manifest",
        lambda *_args, **_kwargs: {
            "dataset_snapshot_id": "dataset-test",
            "eval_slice_id": "eval-slice-test",
            "source_watermarks": {"dataset_max_as_of_ts": "2026-03-18 10:00:00"},
        },
    )

    with pytest.raises(ValueError, match="resume requested"):
        workflows.train_loop(
            client,
            league="Mirage",
            dataset_table="poe_trade.ml_price_dataset_v2",
            model_dir=str(tmp_path),
            max_iterations=1,
            max_wall_clock_seconds=60,
            no_improvement_patience=1,
            min_mdape_improvement=0.01,
            resume=True,
        )


def test_train_loop_stops_for_iteration_budget(monkeypatch, tmp_path):
    client = cast(workflows.ClickHouseClient, cast(object, SimpleNamespace()))
    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda _client: None)
    monkeypatch.setattr(workflows, "_ensure_tuning_rounds_table", lambda _client: None)
    monkeypatch.setattr(
        workflows, "_active_model_version", lambda _client, _league: "v0"
    )
    monkeypatch.setattr(workflows, "train_all_routes", lambda *args, **kwargs: None)
    monkeypatch.setattr(workflows, "_dataset_row_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(workflows, "_write_train_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(workflows, "_record_tuning_round", lambda *args, **kwargs: None)
    monkeypatch.setattr(workflows, "_promote_models", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        workflows,
        "_resolve_tuning_controls",
        lambda **kwargs: workflows.TuningControls(
            max_iterations=2,
            max_wall_clock_seconds=3600,
            no_improvement_patience=99,
            min_mdape_improvement=0.001,
            warm_start_enabled=True,
            resume_supported=False,
        ),
    )
    monkeypatch.setattr(
        workflows, "_latest_train_run_row", lambda _c, _l: {"run_id": "r"}
    )
    monkeypatch.setattr(
        workflows,
        "_run_manifest",
        lambda *_args, **_kwargs: {
            "dataset_snapshot_id": "dataset-test",
            "eval_slice_id": "eval-slice-test",
            "source_watermarks": {"dataset_max_as_of_ts": "2026-03-18 10:00:00"},
        },
    )
    monkeypatch.setattr(
        workflows,
        "evaluate_stack",
        lambda *args, **kwargs: {
            "run_id": "eval-iter",
            "promotion_verdict": "hold",
            "stop_reason": "hold_no_material_improvement",
            "candidate_vs_incumbent": {
                "candidate_avg_mdape": 0.9,
                "incumbent_avg_mdape": 0.91,
                "mdape_improvement": 0.01,
                "coverage_floor_ok": True,
                "protected_cohort_regression": {"regression": False},
            },
        },
    )

    result = workflows.train_loop(
        client,
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        model_dir=str(tmp_path),
        max_iterations=2,
        max_wall_clock_seconds=3600,
        no_improvement_patience=99,
        min_mdape_improvement=0.001,
        resume=False,
    )

    assert result["status"] == "stopped_budget"
    assert result["stop_reason"] == "iteration_budget_exhausted"


def test_evaluate_stack_rejects_unsupported_split():
    with pytest.raises(ValueError, match="unsupported split"):
        workflows.evaluate_stack(
            cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
            league="Mirage",
            dataset_table="poe_trade.ml_price_dataset_v2",
            model_dir="artifacts/ml/mirage_v2",
            split="random",
            output_dir="artifacts/ml/mirage_v2",
        )


def test_status_includes_contract_fields(monkeypatch):
    def _fake_query(_client, query: str):
        if "FROM poe_trade.ml_train_runs" in query:
            return [
                {
                    "run_id": "train-1",
                    "stage": "done",
                    "current_route": "",
                    "routes_done": 4,
                    "routes_total": 4,
                    "rows_processed": 10,
                    "eta_seconds": 0,
                    "chosen_backend": "cpu",
                    "worker_count": 4,
                    "memory_budget_gb": 2.0,
                    "active_model_version": "v1",
                    "status": "completed",
                    "stop_reason": "promoted_against_incumbent",
                    "tuning_config_id": "cfg",
                    "eval_run_id": "eval-2",
                }
            ]
        if "FROM poe_trade.ml_eval_runs" in query and "run_id = 'eval-2'" in query:
            return [
                {
                    "avg_mdape": 0.7,
                    "avg_cov": 0.82,
                }
            ]
        if "FROM poe_trade.ml_eval_runs" in query and "run_id != 'eval-2'" in query:
            return [
                {
                    "run_id": "eval-1",
                    "avg_mdape": 0.75,
                    "avg_cov": 0.8,
                    "recorded_at": "2026-03-12 00:00:00",
                }
            ]
        if "FROM poe_trade.ml_route_hotspots_v1" in query:
            return [
                {
                    "route": "fungible_reference",
                    "family": "fungible_reference",
                    "support_bucket": "high",
                    "sample_count": 200,
                    "candidate_mdape": 0.7,
                    "incumbent_mdape": 0.75,
                    "mdape_delta": 0.05,
                    "candidate_abstain_rate": 0.05,
                    "incumbent_abstain_rate": 0.06,
                    "abstain_rate_delta": -0.01,
                    "recorded_at": "2026-03-12 00:00:00",
                }
            ]
        if "FROM poe_trade.ml_model_registry_v1" in query:
            return [{"model_version": "v1"}]
        if "FROM poe_trade.ml_promotion_audit_v1" in query:
            return [{"verdict": "promote"}]
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda _client: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)

    payload = workflows.status(
        cast(workflows.ClickHouseClient, cast(object, SimpleNamespace())),
        league="Mirage",
        run="latest",
    )

    assert "candidate_vs_incumbent" in payload
    assert "route_hotspots" in payload
    assert "latest_avg_mdape" in payload
    assert "latest_avg_interval_coverage" in payload
    assert payload["promotion_verdict"] == "promote"


def test_fit_route_bundle_uses_tuned_gradient_boosting_params_with_mod_features():
    aggregate_rows = [
        {
            "category": "other",
            "base_type": "Amulet",
            "rarity": "Rare",
            "ilvl": 80,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 4,
            "mod_features_json": json.dumps(
                {
                    "MaximumLife_tier": 6,
                    "MaximumLife_roll": 0.55,
                    "FireResistance_tier": 5,
                    "FireResistance_roll": 0.44,
                }
            ),
            "target_p10": 35.0,
            "target_p50": 50.0,
            "target_p90": 70.0,
            "sale_probability_label": 0.32,
            "sample_count": 12,
        },
        {
            "category": "other",
            "base_type": "Ring",
            "rarity": "Rare",
            "ilvl": 82,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 1,
            "synthesised": 0,
            "mod_token_count": 5,
            "mod_features_json": json.dumps(
                {
                    "MaximumLife_tier": 7,
                    "MaximumLife_roll": 0.68,
                    "ChaosResistance_tier": 4,
                    "ChaosResistance_roll": 0.40,
                }
            ),
            "target_p10": 42.0,
            "target_p50": 58.0,
            "target_p90": 83.0,
            "sale_probability_label": 0.41,
            "sample_count": 10,
        },
        {
            "category": "other",
            "base_type": "Boots",
            "rarity": "Rare",
            "ilvl": 84,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 1,
            "mod_token_count": 6,
            "mod_features_json": json.dumps(
                {
                    "MovementSpeed_tier": 8,
                    "MovementSpeed_roll": 0.78,
                    "MaximumLife_tier": 5,
                    "MaximumLife_roll": 0.46,
                }
            ),
            "target_p10": 30.0,
            "target_p50": 47.0,
            "target_p90": 65.0,
            "sale_probability_label": 0.36,
            "sample_count": 14,
        },
        {
            "category": "other",
            "base_type": "Helmet",
            "rarity": "Rare",
            "ilvl": 79,
            "stack_size": 1,
            "corrupted": 1,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 4,
            "mod_features_json": json.dumps(
                {
                    "MaximumLife_tier": 4,
                    "MaximumLife_roll": 0.40,
                    "LightningResistance_tier": 5,
                    "LightningResistance_roll": 0.45,
                }
            ),
            "target_p10": 24.0,
            "target_p50": 39.0,
            "target_p90": 58.0,
            "sale_probability_label": 0.28,
            "sample_count": 11,
        },
        {
            "category": "other",
            "base_type": "Gloves",
            "rarity": "Rare",
            "ilvl": 83,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 5,
            "mod_features_json": json.dumps(
                {
                    "AttackSpeed_tier": 7,
                    "AttackSpeed_roll": 0.66,
                    "MaximumLife_tier": 6,
                    "MaximumLife_roll": 0.52,
                }
            ),
            "target_p10": 33.0,
            "target_p50": 49.0,
            "target_p90": 68.0,
            "sale_probability_label": 0.39,
            "sample_count": 13,
        },
        {
            "category": "other",
            "base_type": "Belt",
            "rarity": "Rare",
            "ilvl": 81,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 4,
            "mod_features_json": json.dumps(
                {
                    "Strength_tier": 5,
                    "Strength_roll": 0.50,
                    "MaximumLife_tier": 7,
                    "MaximumLife_roll": 0.64,
                }
            ),
            "target_p10": 38.0,
            "target_p50": 54.0,
            "target_p90": 76.0,
            "sale_probability_label": 0.43,
            "sample_count": 12,
        },
    ]

    bundle, stats = workflows._fit_route_bundle_from_aggregates(
        aggregate_rows,
        route="fallback_abstain",
        trained_at="2026-03-18T00:00:00Z",
    )

    assert bundle is not None
    assert stats["model_backend"] == "sklearn_gradient_boosting"

    price_models = bundle["price_models"]
    for quantile in ("p10", "p50", "p90"):
        model = price_models[quantile]
        params = model.get_params()
        assert params["n_estimators"] == 180
        assert params["learning_rate"] == 0.035
        assert params["max_depth"] == 4
        assert params["min_samples_leaf"] == 3
        assert params["min_samples_split"] == 6
        assert params["subsample"] == 0.8
        assert params["max_features"] == "sqrt"

    assert bundle["sale_model"] is not None
    sale_params = bundle["sale_model"].get_params()
    assert sale_params["n_estimators"] == 120
    assert sale_params["learning_rate"] == 0.04
    assert sale_params["max_depth"] == 3
    assert sale_params["min_samples_leaf"] == 4
    assert sale_params["min_samples_split"] == 8
    assert sale_params["subsample"] == 0.85
    assert sale_params["max_features"] == "sqrt"


def test_fit_route_bundle_uses_more_regularized_params_for_sparse_retrieval():
    aggregate_rows = [
        {
            "category": "fossil",
            "base_type": f"Base-{index}",
            "rarity": "Rare",
            "ilvl": 75 + index,
            "stack_size": 1,
            "corrupted": index % 2,
            "fractured": (index + 1) % 2,
            "synthesised": 0,
            "mod_token_count": 3 + (index % 4),
            "mod_features_json": json.dumps(
                {
                    "MaximumLife_tier": 3 + index,
                    "MaximumLife_roll": round(0.25 + (index * 0.07), 2),
                }
            ),
            "target_p10": 15.0 + index,
            "target_p50": 24.0 + (index * 2),
            "target_p90": 36.0 + (index * 3),
            "sale_probability_label": 0.2 + (index * 0.05),
            "sample_count": 6 + index,
        }
        for index in range(6)
    ]

    bundle, stats = workflows._fit_route_bundle_from_aggregates(
        aggregate_rows,
        route="sparse_retrieval",
        trained_at="2026-03-18T00:00:00Z",
    )

    assert bundle is not None
    assert stats["model_backend"] == "sklearn_gradient_boosting"

    price_model = bundle["price_models"]["p50"]
    price_params = price_model.get_params()
    assert price_params["n_estimators"] == 90
    assert price_params["learning_rate"] == 0.03
    assert price_params["max_depth"] == 2
    assert price_params["min_samples_leaf"] == 8
    assert price_params["min_samples_split"] == 16
    assert price_params["subsample"] == 0.85
    assert price_params["max_features"] == "sqrt"

    assert bundle["sale_model"] is not None
    sale_params = bundle["sale_model"].get_params()
    assert sale_params["n_estimators"] == 70
    assert sale_params["learning_rate"] == 0.04
    assert sale_params["max_depth"] == 2
    assert sale_params["min_samples_leaf"] == 8
    assert sale_params["min_samples_split"] == 16
    assert sale_params["subsample"] == 0.9
    assert sale_params["max_features"] == "sqrt"


def test_fit_route_bundle_uses_log_winsorized_target_for_structured_boosted_other():
    aggregate_rows = [
        {
            "category": "ring",
            "base_type": f"Unique Ring {index}",
            "rarity": "Unique",
            "ilvl": 80 + index,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 4,
            "mod_features_json": "{}",
            "target_p10": 40.0 + index,
            "target_p50": 55.0 + (index * 2.0),
            "target_p90": 75.0 + (index * 3.0),
            "sale_probability_label": 0.45,
            "sample_count": 80,
        }
        for index in range(5)
    ]
    aggregate_rows.append(
        {
            "category": "ring",
            "base_type": "Ultra Rare Ring",
            "rarity": "Unique",
            "ilvl": 86,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 5,
            "mod_features_json": "{}",
            "target_p10": 2500.0,
            "target_p50": 5000.0,
            "target_p90": 9000.0,
            "sale_probability_label": 0.5,
            "sample_count": 1,
        }
    )

    bundle, _stats = workflows._fit_route_bundle_from_aggregates(
        aggregate_rows,
        route="structured_boosted_other",
        trained_at="2026-03-18T00:00:00Z",
    )

    assert bundle is not None
    ring_bundle = bundle["family_scoped_bundles"]["ring"]
    assert ring_bundle["target_transform"] == "log1p_winsorized_p50_anchor"
    assert ring_bundle["target_transform_meta"]["winsor_upper"] < 5000.0
    ring_price_params = ring_bundle["price_models"]["p50"].get_params()
    assert ring_price_params["n_estimators"] == 180
    assert ring_price_params["learning_rate"] == 0.025
    assert ring_price_params["max_depth"] == 2
    assert ring_price_params["min_samples_leaf"] == 8
    assert ring_price_params["min_samples_split"] == 16
    assert ring_price_params["subsample"] == 0.85
    ring_sale_params = ring_bundle["sale_model"].get_params()
    assert ring_sale_params["n_estimators"] == 110
    assert ring_sale_params["learning_rate"] == 0.035
    assert ring_sale_params["max_depth"] == 2
    assert ring_sale_params["min_samples_leaf"] == 8
    assert ring_sale_params["min_samples_split"] == 16
    assert ring_sale_params["subsample"] == 0.9


def test_predict_with_bundle_inverts_log_winsorized_targets() -> None:
    class _VectorizerStub:
        def transform(self, rows):
            return rows

    class _ModelStub:
        def __init__(self, value: float) -> None:
            self.value = value

        def predict(self, _x):
            return [self.value]

    bundle = {
        "vectorizer": _VectorizerStub(),
        "price_models": {
            "p10": _ModelStub(2.0),
            "p50": _ModelStub(3.0),
            "p90": _ModelStub(4.0),
        },
        "sale_model": None,
        "route": "structured_boosted_other",
        "target_transform": "log1p_winsorized_p50_anchor",
        "price_tiers": {},
    }

    predicted = workflows._predict_with_bundle(
        bundle=bundle,
        parsed_item={
            "category": "ring",
            "base_type": "Two-Stone Ring",
            "rarity": "Unique",
        },
    )

    assert predicted is not None
    assert predicted["price_p10"] == pytest.approx(6.38905609893, rel=1e-6)
    assert predicted["price_p50"] == pytest.approx(19.0855369232, rel=1e-6)
    assert predicted["price_p90"] == pytest.approx(53.5981500331, rel=1e-6)
