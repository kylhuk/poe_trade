from __future__ import annotations

from unittest import mock

from poe_trade.api import ml as api_ml
from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows


class QueryRouter:
    def __call__(self, _client: ClickHouseClient, query: str):
        if "FROM poe_trade.ml_train_runs" in query and "ORDER BY updated_at DESC" in query:
            return [
                {
                    "run_id": "train-2",
                    "stage": "dataset",
                    "status": "running",
                    "stop_reason": "running",
                    "active_model_version": "mirage-2",
                    "tuning_config_id": "cfg-2",
                    "eval_run_id": "eval-2",
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
        if "FROM poe_trade.ml_price_dataset_v1" in query and "GROUP BY route" in query:
            return [
                {"route": "fungible_reference", "rows": 400},
                {"route": "structured_boosted", "rows": 1200},
                {"route": "sparse_retrieval", "rows": 600},
                {"route": "fallback_abstain", "rows": 200},
            ]
        if "count() AS total_rows" in query:
            return [{"total_rows": 2400, "base_type_count": 310}]
        return []


def test_fetch_automation_history_exposes_observability_panels(
    monkeypatch,
) -> None:
    router = QueryRouter()
    monkeypatch.setattr(api_ml, "_query_rows", router)
    monkeypatch.setattr(workflows, "_query_rows", router)

    payload = api_ml.fetch_automation_history(
        ClickHouseClient(endpoint="http://ch"), league="Mirage", limit=10
    )

    assert payload["summary"]["runsLast7d"] == 2
    assert payload["summary"]["bestAvgMdape"] == 0.11
    assert payload["summary"]["mdapeDeltaVsPrevious"] == 0.04
    assert payload["datasetCoverage"]["totalRows"] == 2400
    assert payload["datasetCoverage"]["coverageRatio"] == 1.0
    assert payload["qualityTrend"][0]["avgMdape"] == 0.15
    assert payload["qualityTrend"][1]["verdict"] == "promote"
    assert payload["routeMetrics"][0]["route"] == "structured_boosted"
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
        dataset_table="poe_trade.ml_price_dataset_v1",
        model_dir="artifacts/ml/mirage",
        comps_table="poe_trade.ml_comps_v1",
    )

    assert observed == [
        "fungible_reference",
        "structured_boosted",
        "sparse_retrieval",
        "fallback_abstain",
    ]


def test_predict_one_uses_trained_fallback_model_without_abstaining(monkeypatch) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {"category": "gem", "base_type": "Empower Support", "rarity": "Magic"},
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
    monkeypatch.setattr(workflows, "_support_count_recent", lambda *_args, **_kwargs: 120)
    monkeypatch.setattr(workflows, "_reference_price", lambda *_args, **_kwargs: 5.0)
    monkeypatch.setattr(
        workflows,
        "_load_active_route_artifact",
        lambda *_args, **_kwargs: {"train_row_count": 900, "model_bundle_path": "bundle.joblib"},
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
