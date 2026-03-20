from __future__ import annotations

import json
from typing import Any
from unittest import mock

from poe_trade.api import ml as api_ml
from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows


class QueryRouter:
    def __call__(self, _client: ClickHouseClient, query: str):
        if (
            "FROM poe_trade.ml_train_runs" in query
            and "ORDER BY updated_at DESC" in query
        ):
            return [
                {
                    "run_id": "train-2",
                    "stage": "dataset",
                    "status": "running",
                    "stop_reason": "running",
                    "active_model_version": "mirage-2",
                    "tuning_config_id": "cfg-2",
                    "eval_run_id": "eval-2",
                    "dataset_snapshot_id": "dataset-aaa",
                    "eval_slice_id": "eval-slice-aaa",
                    "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-15 11:59:59"}',
                    "updated_at": "2026-03-15 12:00:00.000",
                    "rows_processed": 2400,
                },
                {
                    "run_id": "train-2",
                    "stage": "done",
                    "status": "completed",
                    "stop_reason": "promoted_against_incumbent",
                    "active_model_version": "mirage-2",
                    "tuning_config_id": "cfg-2",
                    "eval_run_id": "eval-2",
                    "dataset_snapshot_id": "dataset-aaa",
                    "eval_slice_id": "eval-slice-aaa",
                    "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-15 11:59:59"}',
                    "updated_at": "2026-03-15 12:00:00.000",
                    "rows_processed": 2400,
                },
                {
                    "run_id": "train-1",
                    "stage": "done",
                    "status": "completed",
                    "stop_reason": "hold_no_material_improvement",
                    "active_model_version": "mirage-1",
                    "tuning_config_id": "cfg-1",
                    "eval_run_id": "eval-1",
                    "dataset_snapshot_id": "dataset-bbb",
                    "eval_slice_id": "eval-slice-bbb",
                    "source_watermarks_json": '{"dataset_max_as_of_ts":"2026-03-14 05:59:59"}',
                    "updated_at": "2026-03-14 06:00:00.000",
                    "rows_processed": 1800,
                },
            ]
        if "FROM poe_trade.ml_eval_runs" in query and "GROUP BY run_id" in query:
            return [
                {
                    "run_id": "eval-2",
                    "avg_mdape": 0.11,
                    "avg_cov": 0.82,
                    "recorded_at": "2026-03-15 12:00:00",
                },
                {
                    "run_id": "eval-1",
                    "avg_mdape": 0.15,
                    "avg_cov": 0.78,
                    "recorded_at": "2026-03-14 06:00:00",
                },
            ]
        if "FROM poe_trade.ml_promotion_audit_v1" in query:
            return [
                {
                    "candidate_run_id": "eval-2",
                    "verdict": "promote",
                    "recorded_at": "2026-03-15 12:00:00",
                    "candidate_model_version": "mirage-2",
                },
                {
                    "candidate_run_id": "eval-1",
                    "verdict": "hold",
                    "recorded_at": "2026-03-14 06:00:00",
                    "candidate_model_version": "mirage-1",
                },
            ]
        if "FROM poe_trade.ml_model_registry_v1" in query:
            return [
                {
                    "model_version": "mirage-2",
                    "promoted_at": "2026-03-15 12:05:00",
                },
                {
                    "model_version": "mirage-1",
                    "promoted_at": "2026-03-13 10:00:00",
                },
            ]
        if (
            "FROM poe_trade.ml_route_eval_v1" in query
            and "GROUP BY route, family, support_bucket" in query
        ):
            return [
                {
                    "route": "structured_boosted",
                    "family": "other",
                    "support_bucket": "high",
                    "sample_count": 420,
                    "avg_mdape": 0.1,
                    "avg_cov": 0.83,
                    "recorded_at": "2026-03-15 12:00:00",
                },
                {
                    "route": "structured_boosted_other",
                    "family": "ring",
                    "support_bucket": "medium",
                    "sample_count": 160,
                    "avg_mdape": 0.12,
                    "avg_cov": 0.81,
                    "recorded_at": "2026-03-15 12:00:00",
                },
            ]
        if "FROM poe_trade.ml_route_eval_v1" in query and "GROUP BY route" in query:
            return [
                {
                    "route": "structured_boosted",
                    "sample_count": 600,
                    "avg_mdape": 0.09,
                    "avg_cov": 0.84,
                    "avg_abstain_rate": 0.0,
                    "recorded_at": "2026-03-15 12:00:00",
                },
                {
                    "route": "fallback_abstain",
                    "sample_count": 180,
                    "avg_mdape": 0.22,
                    "avg_cov": 0.77,
                    "avg_abstain_rate": 0.0,
                    "recorded_at": "2026-03-15 12:00:00",
                },
            ]
        if (
            "FROM poe_trade.ml_route_eval_v1" in query
            and "GROUP BY run_id, route" in query
        ):
            return [
                {
                    "run_id": "eval-2",
                    "route": "structured_boosted",
                    "sample_count": 600,
                    "avg_mdape": 0.09,
                    "avg_cov": 0.84,
                    "recorded_at": "2026-03-15 12:00:00",
                },
                {
                    "run_id": "eval-2",
                    "route": "cluster_jewel_retrieval",
                    "sample_count": 150,
                    "avg_mdape": 0.13,
                    "avg_cov": 0.8,
                    "recorded_at": "2026-03-15 12:00:00",
                },
                {
                    "run_id": "eval-2",
                    "route": "structured_boosted_other",
                    "sample_count": 140,
                    "avg_mdape": 0.12,
                    "avg_cov": 0.81,
                    "recorded_at": "2026-03-15 12:00:00",
                },
                {
                    "run_id": "eval-1",
                    "route": "structured_boosted",
                    "sample_count": 520,
                    "avg_mdape": 0.12,
                    "avg_cov": 0.79,
                    "recorded_at": "2026-03-14 06:00:00",
                },
            ]
        if "FROM poe_trade.ml_price_dataset_v2" in query and "GROUP BY route" in query:
            return [
                {"route": "fungible_reference", "rows": 400},
                {"route": "structured_boosted", "rows": 1200},
                {"route": "structured_boosted_other", "rows": 300},
                {"route": "sparse_retrieval", "rows": 450},
                {"route": "cluster_jewel_retrieval", "rows": 150},
                {"route": "fallback_abstain", "rows": 200},
            ]
        if "count() AS total_rows" in query:
            return [{"total_rows": 2700, "base_type_count": 310}]
        return []


def test_fetch_automation_history_exposes_observability_panels(
    monkeypatch,
) -> None:
    router = QueryRouter()
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda _client: None)
    monkeypatch.setattr(api_ml, "_query_rows", router)
    monkeypatch.setattr(workflows, "_query_rows", router)

    payload = api_ml.fetch_automation_history(
        ClickHouseClient(endpoint="http://ch"), league="Mirage", limit=10
    )

    assert payload["summary"]["runsLast7d"] == 2
    assert payload["summary"]["bestAvgMdape"] == 0.11
    assert payload["summary"]["mdapeDeltaVsPrevious"] == 0.04
    assert payload["datasetCoverage"]["totalRows"] == 2700
    assert payload["datasetCoverage"]["coverageRatio"] == 1.0
    assert payload["qualityTrend"][0]["avgMdape"] == 0.15
    assert payload["qualityTrend"][1]["verdict"] == "promote"
    assert payload["routeMetrics"][0]["route"] == "fungible_reference"
    assert any(
        row.get("route") == "structured_boosted" and row.get("avgMdape") == 0.09
        for row in payload["modelMetrics"]
    )
    assert any(
        row.get("route") == "structured_boosted" and row.get("rowsProcessed") == 2400
        for row in payload["modelMetrics"]
    )
    assert any(
        row.get("route") == "structured_boosted_other"
        for row in payload["modelMetrics"]
    )
    assert any(
        row.get("route") == "structured_boosted_other"
        for row in payload["routeFamilies"]
    )
    assert any(
        row.get("route") == "cluster_jewel_retrieval" for row in payload["modelHistory"]
    )
    assert any(
        route.get("route") == "cluster_jewel_retrieval"
        for route in payload["datasetCoverage"]["routes"]
    )
    assert payload["promotions"][0]["modelVersion"] == "mirage-2"
    assert payload["history"][0]["rowsProcessed"] == 2400


def test_train_all_routes_includes_fallback_route(monkeypatch) -> None:
    observed: list[str] = []

    def _fake_train_route(*_args, route: str, **_kwargs):
        observed.append(route)
        return {"route": route}

    monkeypatch.setattr(workflows, "train_route", _fake_train_route)

    workflows.train_all_routes(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        model_dir="artifacts/ml/mirage",
        comps_table="poe_trade.ml_comps_v1",
    )

    assert observed == [
        "fungible_reference",
        "structured_boosted",
        "structured_boosted_other",
        "sparse_retrieval",
        "cluster_jewel_retrieval",
        "fallback_abstain",
    ]


def test_predict_one_uses_trained_fallback_model_without_abstaining(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "gem",
            "base_type": "Empower Support",
            "rarity": "Magic",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_route_for_item",
        lambda _item: {
            "route": "fallback_abstain",
            "route_reason": "generalized_fallback",
            "support_count_recent": 120,
        },
    )
    monkeypatch.setattr(
        workflows,
        "_serving_profile_lookup",
        lambda *_args, **_kwargs: {
            "hit": True,
            "support_count_recent": 120,
            "reference_price": 5.0,
            "reason": "profile_hit",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_load_active_route_artifact",
        lambda *_args, **_kwargs: {
            "train_row_count": 900,
            "model_bundle_path": "bundle.joblib",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_predict_with_artifact",
        lambda **_kwargs: {
            "price_p10": 7.0,
            "price_p50": 8.0,
            "price_p90": 10.0,
            "sale_probability": 0.61,
        },
    )

    payload = workflows.predict_one(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        clipboard_text="dummy",
    )

    assert payload["route"] == "fallback_abstain"
    assert payload["fallback_reason"] == ""
    assert payload["confidence_percent"] > 35.0
    assert payload["price_recommendation_eligible"] is True


def test_predict_one_low_confidence_blends_with_reference_price(monkeypatch) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "other",
            "base_type": "Brittle Rare",
            "rarity": "Rare",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_route_for_item",
        lambda _item: {
            "route": "sparse_retrieval",
            "route_reason": "sparse_high_dimensional",
            "support_count_recent": 1,
        },
    )
    monkeypatch.setattr(
        workflows,
        "_serving_profile_lookup",
        lambda *_args, **_kwargs: {
            "hit": True,
            "support_count_recent": 1,
            "reference_price": 20.0,
            "reason": "profile_hit",
        },
    )
    monkeypatch.setattr(
        workflows, "_safe_incumbent_model_version", lambda *_a, **_k: ""
    )
    monkeypatch.setattr(
        workflows,
        "_load_active_route_artifact",
        lambda *_args, **_kwargs: {
            "train_row_count": 1,
            "model_bundle_path": "bundle.joblib",
            "active_model_version": "cand-v1",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_predict_with_artifact",
        lambda **_kwargs: {
            "price_p10": 120.0,
            "price_p50": 200.0,
            "price_p90": 260.0,
            "sale_probability": 0.9,
        },
    )

    payload = workflows.predict_one(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        clipboard_text="dummy",
    )

    assert payload["fallback_reason"] == "low_confidence_reference_blend"
    assert payload["price_p50"] < 200.0
    assert payload["price_p50"] > 20.0


def test_predict_one_low_confidence_prefers_incumbent_when_available(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "other",
            "base_type": "Brittle Rare",
            "rarity": "Rare",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_route_for_item",
        lambda _item: {
            "route": "sparse_retrieval",
            "route_reason": "sparse_high_dimensional",
            "support_count_recent": 1,
        },
    )
    monkeypatch.setattr(
        workflows,
        "_serving_profile_lookup",
        lambda *_args, **_kwargs: {
            "hit": True,
            "support_count_recent": 1,
            "reference_price": 20.0,
            "reason": "profile_hit",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_safe_incumbent_model_version",
        lambda *_a, **_k: "inc-v1",
    )

    def _fake_load_active_route_artifact(*_args, **kwargs):
        model_version = kwargs.get("model_version")
        if model_version == "inc-v1":
            return {
                "train_row_count": 800,
                "model_bundle_path": "bundle-inc.joblib",
                "active_model_version": "inc-v1",
            }
        return {
            "train_row_count": 1,
            "model_bundle_path": "bundle-cand.joblib",
            "active_model_version": "cand-v2",
        }

    monkeypatch.setattr(
        workflows,
        "_load_active_route_artifact",
        _fake_load_active_route_artifact,
    )

    def _fake_predict_with_artifact(
        *, artifact: dict[str, Any], parsed_item: dict[str, Any]
    ):
        del parsed_item
        if artifact.get("active_model_version") == "inc-v1":
            return {
                "price_p10": 45.0,
                "price_p50": 60.0,
                "price_p90": 85.0,
                "sale_probability": 0.55,
            }
        return {
            "price_p10": 120.0,
            "price_p50": 200.0,
            "price_p90": 260.0,
            "sale_probability": 0.9,
        }

    monkeypatch.setattr(
        workflows, "_predict_with_artifact", _fake_predict_with_artifact
    )

    payload = workflows.predict_one(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        clipboard_text="dummy",
    )

    assert payload["fallback_reason"] == "low_confidence_incumbent_blend"
    assert payload["price_p50"] < 200.0
    assert payload["price_p50"] > 40.0


def test_status_exposes_run_manifest_fields(monkeypatch) -> None:
    def _fake_query(_client: ClickHouseClient, query: str):
        if "FROM poe_trade.ml_train_runs" in query:
            return [
                {
                    "run_id": "train-9",
                    "stage": "done",
                    "current_route": "",
                    "routes_done": 5,
                    "routes_total": 5,
                    "rows_processed": 2400,
                    "eta_seconds": 0,
                    "chosen_backend": "cpu",
                    "worker_count": 6,
                    "memory_budget_gb": 4.0,
                    "active_model_version": "mirage-9",
                    "status": "completed",
                    "stop_reason": "promoted_against_incumbent",
                    "tuning_config_id": "cfg-9",
                    "eval_run_id": "eval-9",
                    "dataset_snapshot_id": "dataset-9abc",
                    "eval_slice_id": "eval-slice-9abc",
                    "source_watermarks_json": json.dumps(
                        {"dataset_max_as_of_ts": "2026-03-15 12:00:00"}
                    ),
                    "updated_at": "2026-03-15 12:01:00.000",
                }
            ]
        if "FROM poe_trade.ml_eval_runs" in query and "run_id = 'eval-9'" in query:
            return [{"avg_mdape": 0.1, "avg_cov": 0.82}]
        if "FROM poe_trade.ml_eval_runs" in query and "run_id != 'eval-9'" in query:
            return [{"run_id": "eval-8", "avg_mdape": 0.12, "avg_cov": 0.8}]
        if "FROM poe_trade.ml_route_hotspots_v1" in query:
            return []
        if "FROM poe_trade.ml_promotion_audit_v1" in query:
            return [{"verdict": "promote"}]
        if "FROM poe_trade.ml_model_registry_v1" in query:
            return [{"model_version": "mirage-9"}]
        return []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda _league: None)
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda _client: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)

    payload = workflows.status(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        run="latest",
    )

    assert payload["dataset_snapshot_id"] == "dataset-9abc"
    assert payload["eval_slice_id"] == "eval-slice-9abc"
    assert payload["source_watermarks"]["dataset_max_as_of_ts"] == "2026-03-15 12:00:00"


def test_train_run_history_falls_back_when_manifest_columns_missing(
    monkeypatch,
) -> None:
    def _fake_query(_client: ClickHouseClient, query: str):
        if "FROM poe_trade.ml_train_runs" not in query:
            return []
        if "dataset_snapshot_id" in query:
            raise workflows.ClickHouseClientError("unknown column")
        return [
            {
                "run_id": "train-legacy-1",
                "stage": "done",
                "current_route": "",
                "routes_done": 5,
                "routes_total": 5,
                "rows_processed": 1200,
                "eta_seconds": 0,
                "chosen_backend": "cpu",
                "worker_count": 6,
                "memory_budget_gb": 4.0,
                "active_model_version": "legacy-v1",
                "status": "completed",
                "stop_reason": "hold_no_material_improvement",
                "tuning_config_id": "cfg-legacy",
                "eval_run_id": "eval-legacy-1",
                "updated_at": "2026-03-15 12:00:00.000",
            }
        ]

    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda _client: None)
    monkeypatch.setattr(workflows, "_query_rows", _fake_query)

    rows = workflows.train_run_history(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        limit=1,
    )

    assert len(rows) == 1
    assert rows[0]["run_id"] == "train-legacy-1"
    assert rows[0]["eval_run_id"] == "eval-legacy-1"


def test_protected_cohort_regression_holds_when_support_meets_threshold(
    monkeypatch,
) -> None:
    def _fake_query(_client: ClickHouseClient, query: str):
        if "run_id = 'cand-1'" in query:
            return [
                {
                    "route": "structured_boosted",
                    "family": "unique",
                    "support_bucket": "medium",
                    "mdape": 0.12,
                    "support_count": 80,
                }
            ]
        if "run_id = 'inc-1'" in query:
            return [
                {
                    "route": "structured_boosted",
                    "family": "unique",
                    "support_bucket": "medium",
                    "mdape": 0.08,
                    "support_count": 75,
                }
            ]
        return []

    monkeypatch.setattr(workflows, "_query_rows", _fake_query)

    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-1",
            "avg_mdape": 0.07,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-protected",
        },
        incumbent={
            "run_id": "inc-1",
            "avg_mdape": 0.10,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-protected",
        },
    )
    protected = workflows._protected_cohort_check(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        candidate_run_id="cand-1",
        incumbent_run_id="inc-1",
    )
    comparison["protected_cohort_regression"] = protected

    assert protected["regression"] is True
    assert protected["reason_code"] == "hold_protected_cohort_regression"
    assert protected["minimum_support_count"] == 50
    assert protected["cohort"] == "structured_boosted|unique|medium"
    assert protected["cohort_detail"]["candidate_support_count"] == 80
    assert workflows._should_promote(comparison) is False
    assert (
        workflows._promotion_stop_reason(comparison)
        == "hold_protected_cohort_regression"
    )


def test_protected_cohort_zero_regression_threshold_is_strict(monkeypatch) -> None:
    def _fake_query(_client: ClickHouseClient, query: str):
        if "run_id = 'cand-strict'" in query:
            return [
                {
                    "route": "structured_boosted",
                    "family": "unique",
                    "support_bucket": "high",
                    "mdape": 0.1001,
                    "support_count": 120,
                }
            ]
        if "run_id = 'inc-strict'" in query:
            return [
                {
                    "route": "structured_boosted",
                    "family": "unique",
                    "support_bucket": "high",
                    "mdape": 0.10,
                    "support_count": 115,
                }
            ]
        return []

    monkeypatch.setattr(workflows, "_query_rows", _fake_query)

    protected = workflows._protected_cohort_check(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        candidate_run_id="cand-strict",
        incumbent_run_id="inc-strict",
    )

    assert protected["regression"] is True
    assert protected["max_mdape_regression"] > 0.0
    assert protected["reason_code"] == "hold_protected_cohort_regression"


def test_protected_cohort_keeps_split_family_keys_for_structured_routes(
    monkeypatch,
) -> None:
    def _fake_query(_client: ClickHouseClient, query: str):
        if "run_id = 'cand-ring'" in query:
            return [
                {
                    "route": "structured_boosted_other",
                    "family": "ring",
                    "support_bucket": "high",
                    "mdape": 0.20,
                    "support_count": 120,
                }
            ]
        if "run_id = 'inc-other'" in query:
            return [
                {
                    "route": "structured_boosted_other",
                    "family": "other",
                    "support_bucket": "high",
                    "mdape": 0.10,
                    "support_count": 120,
                }
            ]
        return []

    monkeypatch.setattr(workflows, "_query_rows", _fake_query)

    protected = workflows._protected_cohort_check(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        candidate_run_id="cand-ring",
        incumbent_run_id="inc-other",
    )

    assert protected["regression"] is False
    assert protected["max_mdape_regression"] == 0.0
    assert protected["cohort"] == "none"
    assert protected["cohort_detail"] is None


def test_fetch_status_exposes_protected_cohort_policy_values(monkeypatch) -> None:
    monkeypatch.setattr(
        api_ml.workflows,
        "status",
        lambda _client, league, run: {
            "league": league,
            "run_id": "train-3",
            "status": "completed",
            "promotion_verdict": "hold",
            "stop_reason": "hold_protected_cohort_regression",
            "active_model_version": "mirage-2",
            "latest_avg_mdape": 0.13,
            "latest_avg_interval_coverage": 0.82,
            "promotion_policy": {
                "protected_cohort": {
                    "cohort_dimensions": ["route", "family", "support_bucket"],
                    "minimum_support_count": 50,
                    "eligible_support_buckets": ["medium", "high"],
                    "max_mdape_regression": 0.02,
                }
            },
            "candidate_vs_incumbent": {
                "candidate_run_id": "eval-3",
                "incumbent_run_id": "eval-2",
                "protected_cohort_policy": {
                    "minimum_support_count": 50,
                    "cohort_dimensions": ["route", "family", "support_bucket"],
                },
                "protected_cohort_regression": {
                    "regression": True,
                    "reason_code": "hold_protected_cohort_regression",
                    "minimum_support_count": 50,
                },
            },
            "warmup": {
                "lastAttemptAt": "2026-03-15 11:00:00",
                "routes": {"fungible_reference": "warm"},
            },
            "route_hotspots": {"top_improving": [], "top_regressing": []},
        },
    )

    payload = api_ml.fetch_status(
        ClickHouseClient(endpoint="http://ch"), league="Mirage"
    )

    assert (
        payload["promotion_policy"]["protected_cohort"]["minimum_support_count"] == 50
    )
    assert (
        payload["candidate_vs_incumbent"]["protected_cohort_regression"]["reason_code"]
        == "hold_protected_cohort_regression"
    )


def test_integrity_gate_pass_fixture_keeps_promotion_eligible() -> None:
    gate = workflows._integrity_gate_assessment(
        {
            "source_watermarks": {
                "dataset_max_as_of_ts": "2026-03-15 12:00:00",
                "poeninja_max_sample_time_utc": "2026-03-15 12:25:00",
                "price_labels_max_updated_at": "2026-03-15 12:10:00",
            }
        },
        [
            {
                "route": "structured_boosted",
                "train_max_as_of_ts": "2026-03-15 11:59:59",
                "eval_min_as_of_ts": "2026-03-15 12:00:00",
            }
        ],
    )
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-1",
            "avg_mdape": 0.70,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-integrity-pass",
        },
        incumbent={
            "run_id": "inc-1",
            "avg_mdape": 0.90,
            "avg_cov": 0.85,
            "eval_slice_id": "eval-slice-integrity-pass",
        },
    )
    comparison["integrity_gate"] = gate
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "reason_code": None,
    }

    assert gate["pass"] is True
    assert gate["reason_codes"] == []
    assert workflows._should_promote(comparison) is True
    assert workflows._promotion_stop_reason(comparison) == "promote"


def test_integrity_gate_overlap_fixture_returns_leakage_hold_reason() -> None:
    gate = workflows._integrity_gate_assessment(
        {
            "source_watermarks": {
                "dataset_max_as_of_ts": "2026-03-15 12:00:00",
                "poeninja_max_sample_time_utc": "2026-03-15 12:05:00",
                "price_labels_max_updated_at": "2026-03-15 12:03:00",
            }
        },
        [
            {
                "route": "sparse_retrieval",
                "train_max_as_of_ts": "2026-03-15 12:00:00",
                "eval_min_as_of_ts": "2026-03-15 12:00:00",
            }
        ],
    )
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-2",
            "avg_mdape": 0.60,
            "avg_cov": 0.91,
            "eval_slice_id": "eval-slice-integrity-overlap",
        },
        incumbent={
            "run_id": "inc-2",
            "avg_mdape": 0.80,
            "avg_cov": 0.85,
            "eval_slice_id": "eval-slice-integrity-overlap",
        },
    )
    comparison["integrity_gate"] = gate
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "reason_code": None,
    }

    assert gate["pass"] is True
    assert gate["leakage"]["detected"] is False
    assert gate["reason_codes"] == []


def test_integrity_gate_stale_fixture_returns_freshness_hold_reason() -> None:
    gate = workflows._integrity_gate_assessment(
        {
            "source_watermarks": {
                "dataset_max_as_of_ts": "2026-03-15 12:00:00",
                "poeninja_max_sample_time_utc": "2026-03-15 07:00:00",
                "price_labels_max_updated_at": "2026-03-15 12:05:00",
            }
        },
        [
            {
                "route": "fungible_reference",
                "train_max_as_of_ts": "2026-03-15 11:59:59",
                "eval_min_as_of_ts": "2026-03-15 12:00:00",
            }
        ],
    )
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-3",
            "avg_mdape": 0.60,
            "avg_cov": 0.91,
            "eval_slice_id": "eval-slice-integrity-stale",
        },
        incumbent={
            "run_id": "inc-3",
            "avg_mdape": 0.80,
            "avg_cov": 0.88,
            "eval_slice_id": "eval-slice-integrity-stale",
        },
    )
    comparison["integrity_gate"] = gate
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "reason_code": None,
    }

    assert gate["pass"] is False
    assert gate["freshness"]["stale"] is True
    assert gate["reason_codes"] == [workflows.PROMOTION_FRESHNESS_REASON_CODE]
    assert workflows._should_promote(comparison) is False
    assert (
        workflows._promotion_stop_reason(comparison)
        == workflows.PROMOTION_FRESHNESS_REASON_CODE
    )


def test_integrity_gate_missing_watermark_keys_fails_closed() -> None:
    gate = workflows._integrity_gate_assessment(
        {
            "source_watermarks": {
                "dataset_max_as_of_ts": "2026-03-15 12:00:00",
            }
        },
        [
            {
                "route": "structured_boosted",
                "train_max_as_of_ts": "2026-03-15 11:59:59",
                "eval_min_as_of_ts": "2026-03-15 12:00:00",
            }
        ],
    )

    assert gate["pass"] is False
    assert gate["freshness"]["stale"] is True
    assert workflows.PROMOTION_FRESHNESS_REASON_CODE in gate["reason_codes"]
    assert (
        "poeninja_max_sample_time_utc" in gate["freshness"]["missing_or_unparsed_keys"]
    )


def test_fetch_status_exposes_integrity_reason_codes(monkeypatch) -> None:
    monkeypatch.setattr(
        api_ml.workflows,
        "status",
        lambda _client, league, run: {
            "league": league,
            "run_id": "train-4",
            "status": "completed",
            "promotion_verdict": "hold",
            "stop_reason": workflows.PROMOTION_LEAKAGE_REASON_CODE,
            "active_model_version": "mirage-3",
            "latest_avg_mdape": 0.12,
            "latest_avg_interval_coverage": 0.82,
            "promotion_policy": {
                "protected_cohort": {
                    "minimum_support_count": 50,
                },
                "integrity": {
                    "leakage_reason_code": workflows.PROMOTION_LEAKAGE_REASON_CODE,
                    "freshness_reason_code": workflows.PROMOTION_FRESHNESS_REASON_CODE,
                    "freshness_max_lag_minutes": workflows.PROMOTION_FRESHNESS_MAX_LAG_MINUTES,
                },
            },
            "candidate_vs_incumbent": {
                "hold_reason_codes": [
                    workflows.PROMOTION_LEAKAGE_REASON_CODE,
                    workflows.PROMOTION_FRESHNESS_REASON_CODE,
                ],
                "integrity_gate": {
                    "pass": False,
                    "reason_codes": [
                        workflows.PROMOTION_LEAKAGE_REASON_CODE,
                        workflows.PROMOTION_FRESHNESS_REASON_CODE,
                    ],
                },
                "protected_cohort_regression": {"regression": False},
            },
            "route_hotspots": {"top_improving": [], "top_regressing": []},
        },
    )

    payload = api_ml.fetch_status(
        ClickHouseClient(endpoint="http://ch"), league="Mirage"
    )

    assert payload["candidate_vs_incumbent"]["hold_reason_codes"] == [
        workflows.PROMOTION_LEAKAGE_REASON_CODE,
        workflows.PROMOTION_FRESHNESS_REASON_CODE,
    ]
    assert (
        payload["promotion_policy"]["integrity"]["freshness_reason_code"]
        == workflows.PROMOTION_FRESHNESS_REASON_CODE
    )


def test_shadow_gate_pass_requires_same_slice_and_strict_mdape_improvement() -> None:
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-pass",
            "avg_mdape": 0.08,
            "avg_cov": 0.91,
            "eval_slice_id": "eval-slice-shadow-1",
        },
        incumbent={
            "run_id": "inc-pass",
            "avg_mdape": 0.12,
            "avg_cov": 0.88,
            "eval_slice_id": "eval-slice-shadow-1",
        },
    )
    comparison["integrity_gate"] = {
        "pass": True,
        "reason_codes": [],
    }
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "reason_code": None,
    }

    assert comparison["shadow_gate"]["pass"] is True
    assert comparison["shadow_gate"]["same_eval_slice"] is True
    assert comparison["mdape_relative_improvement"] >= 0.20
    assert workflows._should_promote(comparison) is True
    assert workflows._promotion_hold_reason_codes(comparison) == []
    assert workflows._promotion_stop_reason(comparison) == "promote"


def test_shadow_gate_mdape_miss_fixture_returns_hold_reason() -> None:
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-mdape-miss",
            "avg_mdape": 0.17,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-shadow-2",
        },
        incumbent={
            "run_id": "inc-mdape-miss",
            "avg_mdape": 0.20,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-shadow-2",
        },
    )
    comparison["integrity_gate"] = {"pass": True, "reason_codes": []}
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "reason_code": None,
    }

    assert comparison["shadow_gate"]["pass"] is False
    assert (
        workflows.PROMOTION_SHADOW_MDAPE_REASON_CODE
        in comparison["shadow_gate"]["reason_codes"]
    )
    assert workflows._should_promote(comparison) is False
    assert (
        workflows._promotion_stop_reason(comparison) == "hold_no_material_improvement"
    )


def test_shadow_gate_slice_mismatch_fixture_returns_hold_reason() -> None:
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={
            "run_id": "cand-slice-mismatch",
            "avg_mdape": 0.08,
            "avg_cov": 0.9,
            "eval_slice_id": "eval-slice-shadow-candidate",
        },
        incumbent={
            "run_id": "inc-slice-mismatch",
            "avg_mdape": 0.12,
            "avg_cov": 0.88,
            "eval_slice_id": "eval-slice-shadow-incumbent",
        },
    )
    comparison["integrity_gate"] = {"pass": True, "reason_codes": []}
    comparison["protected_cohort_regression"] = {
        "regression": False,
        "reason_code": None,
    }

    assert comparison["shadow_gate"]["pass"] is False
    assert (
        workflows.PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE
        in comparison["shadow_gate"]["reason_codes"]
    )
    assert workflows._should_promote(comparison) is False
    assert (
        workflows._promotion_stop_reason(comparison)
        == workflows.PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE
    )


def test_fetch_status_exposes_shadow_gate_reason_codes(monkeypatch) -> None:
    monkeypatch.setattr(
        api_ml.workflows,
        "status",
        lambda _client, league, run: {
            "league": league,
            "run_id": "train-shadow",
            "status": "completed",
            "promotion_verdict": "hold",
            "stop_reason": workflows.PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE,
            "active_model_version": "mirage-shadow",
            "latest_avg_mdape": 0.12,
            "latest_avg_interval_coverage": 0.83,
            "promotion_policy": {
                "shadow": {
                    "min_relative_mdape_improvement": 0.2,
                    "require_same_eval_slice": True,
                },
                "protected_cohort": {
                    "minimum_support_count": 50,
                    "max_mdape_regression": 0.0,
                },
                "integrity": {
                    "freshness_max_lag_minutes": workflows.PROMOTION_FRESHNESS_MAX_LAG_MINUTES
                },
            },
            "candidate_vs_incumbent": {
                "hold_reason_codes": [
                    workflows.PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE
                ],
                "shadow_gate": {
                    "pass": False,
                    "same_eval_slice": False,
                    "reason_codes": [
                        workflows.PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE
                    ],
                },
            },
            "route_hotspots": {"top_improving": [], "top_regressing": []},
        },
    )

    payload = api_ml.fetch_status(
        ClickHouseClient(endpoint="http://ch"), league="Mirage"
    )

    assert payload["candidate_vs_incumbent"]["hold_reason_codes"] == [
        workflows.PROMOTION_SHADOW_SLICE_MISMATCH_REASON_CODE
    ]
    assert payload["candidate_vs_incumbent"]["shadow_gate"]["pass"] is False
    assert payload["promotion_policy"]["shadow"]["require_same_eval_slice"] is True


def test_warmup_active_models_records_routes(monkeypatch) -> None:
    workflows._ACTIVE_ROUTE_MODEL_DIRS.clear()
    workflows._MODEL_BUNDLE_CACHE.clear()
    workflows._WARMUP_STATE.clear()

    routes = [
        {"route": route, "model_dir": "artifacts/ml/mirage_v1"}
        for route in workflows.ROUTES
    ]

    def _fake_query(_client: ClickHouseClient, query: str):
        if "FROM poe_trade.ml_model_registry_v1" in query:
            return routes
        return []

    monkeypatch.setattr(workflows, "_query_rows", _fake_query)
    monkeypatch.setattr(
        workflows,
        "_load_json_file",
        lambda _path: {"model_bundle_path": "bundle.joblib"},
    )
    monkeypatch.setattr(
        workflows,
        "_validate_route_artifact",
        lambda **_kwargs: {"valid": True, "reason": "warm"},
    )
    monkeypatch.setattr(
        workflows, "_load_model_bundle", lambda _path: {"price_models": {}}
    )
    monkeypatch.setattr(workflows, "_now_ts", lambda: "2026-03-18T00:00:00")

    status = workflows.warmup_active_models(
        ClickHouseClient(endpoint="http://ch"), league="Mirage"
    )

    assert status["routes"].get("fungible_reference") == "warm"
    assert (
        workflows._ACTIVE_ROUTE_MODEL_DIRS[("Mirage", "structured_boosted")]
        == "artifacts/ml/mirage_v1"
    )


def test_promote_models_triggers_warmup(monkeypatch) -> None:
    monkeypatch.setattr(workflows, "_insert_json_rows", lambda *_args, **_kwargs: None)
    called: list[str] = []

    def _fake_warmup(_client: ClickHouseClient, *, league: str) -> dict[str, Any]:
        called.append(league)
        return {"lastAttemptAt": "2026-03-18T01:00:00", "routes": {}}

    monkeypatch.setattr(workflows, "warmup_active_models", _fake_warmup)

    workflows._promote_models(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        model_dir="artifacts/ml/mirage_v1",
        model_version="mirage-promo",
        routes=["fallback_abstain"],
    )

    assert called == ["Mirage"]
