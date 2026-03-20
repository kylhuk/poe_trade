from __future__ import annotations

import json
from unittest import mock

import pytest

from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows


class EvalFeedbackRouter:
    def __call__(self, _client: ClickHouseClient, query: str):
        if (
            "FROM poe_trade.ml_eval_runs" in query
            and "run_id = 'run-candidate'" in query
        ):
            return [{"avg_mdape": 0.094, "avg_cov": 0.81}]
        if (
            "FROM poe_trade.ml_eval_runs" in query
            and "run_id != 'run-candidate'" in query
        ):
            return [
                {
                    "run_id": "run-held",
                    "avg_mdape": 0.097,
                    "avg_cov": 0.82,
                    "recorded_at": "2026-03-16 10:00:00",
                }
            ]
        if (
            "FROM poe_trade.ml_promotion_audit_v1" in query
            and "verdict = 'promote'" in query
        ):
            return [
                {
                    "candidate_run_id": "run-promoted",
                    "recorded_at": "2026-03-15 10:00:00",
                }
            ]
        if (
            "FROM poe_trade.ml_eval_runs" in query
            and "run_id = 'run-promoted'" in query
        ):
            return [{"avg_mdape": 0.100, "avg_cov": 0.80}]
        return []


def test_eval_feedback_compares_candidate_against_latest_promoted_incumbent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(workflows, "_query_rows", EvalFeedbackRouter())

    payload = workflows._eval_feedback_for_run(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        run_id="run-candidate",
    )

    assert payload["candidate_vs_incumbent"]["incumbent_run_id"] == "run-promoted"
    assert payload["candidate_vs_incumbent"]["mdape_improvement"] == pytest.approx(
        0.006
    )


def test_train_loop_marks_hold_runs_as_completed(monkeypatch) -> None:
    writes: list[dict[str, object]] = []

    monkeypatch.setattr(
        workflows, "_ensure_supported_league", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        workflows, "_ensure_train_runs_table", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        workflows, "_ensure_tuning_rounds_table", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        workflows, "_latest_train_run_row", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        workflows, "_active_model_version", lambda *_args, **_kwargs: "mirage-1"
    )
    monkeypatch.setattr(workflows, "_dataset_row_count", lambda *_args, **_kwargs: 1234)
    monkeypatch.setattr(
        workflows,
        "_run_manifest",
        lambda *_args, **_kwargs: {
            "dataset_snapshot_id": "dataset-test",
            "eval_slice_id": "eval-test",
            "source_watermarks": {"dataset_max_as_of_ts": "2026-03-18 10:00:00"},
        },
    )
    monkeypatch.setattr(
        workflows, "train_all_routes", lambda *_args, **_kwargs: {"trained": True}
    )
    monkeypatch.setattr(
        workflows,
        "evaluate_stack",
        lambda *_args, **_kwargs: {
            "run_id": "eval-1",
            "promotion_verdict": "hold",
            "stop_reason": "hold_no_material_improvement",
            "candidate_vs_incumbent": {
                "candidate_avg_mdape": 0.095,
            },
        },
    )
    monkeypatch.setattr(
        workflows, "_record_tuning_round", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(workflows, "_promote_models", lambda *_args, **_kwargs: None)

    def _capture_write(*_args, **kwargs):
        writes.append(
            {
                "run_id": kwargs["run_id"],
                "stage": kwargs["stage"],
                "status": kwargs["status"],
                "stop_reason": kwargs["stop_reason"],
            }
        )

    monkeypatch.setattr(workflows, "_write_train_run", _capture_write)

    result = workflows.train_loop(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        model_dir="artifacts/ml/mirage",
        max_iterations=1,
        max_wall_clock_seconds=60,
        no_improvement_patience=3,
        min_mdape_improvement=0.005,
        resume=False,
    )

    assert result["runs"][0]["status"] == "completed"
    assert writes[-1]["stage"] == "done"
    assert writes[-1]["status"] == "completed"
    assert writes[-1]["stop_reason"] == "hold_no_material_improvement"


def test_now_ts_has_subsecond_precision() -> None:
    value = workflows._now_ts()
    assert value.count(":") == 2
    assert "." in value
    fractional = value.rsplit(".", 1)[1]
    assert len(fractional) == 3
    assert fractional.isdigit()


def test_train_route_uses_aggregate_rows_for_family_counts(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        workflows, "_ensure_supported_league", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(workflows, "_ensure_route", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflows, "_load_json_file", lambda _path: {})
    monkeypatch.setattr(workflows, "_query_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        workflows,
        "_training_aggregate_rows",
        lambda *_args, **_kwargs: [
            {"category": "map", "sample_count": 7},
            {"category": "map", "sample_count": 5},
            {"category": "essence", "sample_count": 3},
        ],
    )
    monkeypatch.setattr(
        workflows,
        "_fit_route_bundle_from_aggregates",
        lambda *_args, **_kwargs: (
            None,
            {
                "train_row_count": 15,
                "feature_row_count": 3,
                "support_reference_p50": 9.5,
                "sale_model_available": False,
                "model_backend": "heuristic_fallback",
            },
        ),
    )

    result = workflows.train_route(
        ClickHouseClient(endpoint="http://ch"),
        route="structured_boosted",
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        model_dir=str(tmp_path),
        comps_table="poe_trade.ml_comps_v1",
    )

    artifact = json.loads(
        tmp_path.joinpath("structured_boosted-Mirage.json").read_text()
    )
    assert result["rows_trained"] == 15
    assert artifact["family_counts"] == [
        {"family": "essence", "rows": 3},
        {"family": "map", "rows": 12},
    ]


def test_evaluate_route_reuses_aggregate_rows_for_train_max_as_of_ts(
    monkeypatch,
) -> None:
    scan_calls = {
        "route_raw_row_count": 0,
        "evaluation_rows": 0,
        "training_aggregate_rows": 0,
    }

    monkeypatch.setattr(
        workflows, "_ensure_supported_league", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(workflows, "_ensure_route", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        workflows, "_ensure_route_eval_table", lambda *_args, **_kwargs: None
    )

    def _route_raw_row_count(*_args, **_kwargs):
        scan_calls["route_raw_row_count"] += 1
        return 50

    monkeypatch.setattr(workflows, "_route_raw_row_count", _route_raw_row_count)

    def _evaluation_rows(*_args, **_kwargs):
        scan_calls["evaluation_rows"] += 1
        return [
            {
                "category": "map",
                "base_type": "Cemetery Map",
                "rarity": "Rare",
                "ilvl": 80.0,
                "stack_size": 1.0,
                "corrupted": 0.0,
                "fractured": 0.0,
                "synthesised": 0.0,
                "mod_token_count": 2.0,
                "mod_features_json": "{}",
                "normalized_price_chaos": 10.0,
                "sale_probability_label": 0.5,
                "family": "map",
                "as_of_ts": "2026-03-18 11:00:00",
            }
        ]

    monkeypatch.setattr(
        workflows,
        "_evaluation_rows",
        _evaluation_rows,
    )

    def _training_aggregate_rows(*_args, **_kwargs):
        scan_calls["training_aggregate_rows"] += 1
        return [
            {
                "category": "map",
                "sample_count": 20,
                "target_p10": 8.0,
                "target_p50": 10.0,
                "target_p90": 12.0,
                "max_as_of_ts": "2026-03-18 10:59:59",
            },
            {
                "category": "essence",
                "sample_count": 9,
                "target_p10": 3.0,
                "target_p50": 4.0,
                "target_p90": 5.0,
                "max_as_of_ts": "2026-03-18 10:00:00",
            },
        ]

    monkeypatch.setattr(
        workflows,
        "_training_aggregate_rows",
        _training_aggregate_rows,
    )
    monkeypatch.setattr(
        workflows,
        "_fit_route_bundle_from_aggregates",
        lambda *_args, **_kwargs: (
            None,
            {
                "train_row_count": 29,
                "feature_row_count": 2,
                "support_reference_p50": 9.0,
                "model_backend": "heuristic_fallback",
            },
        ),
    )
    monkeypatch.setattr(workflows, "_insert_json_rows", lambda *_args, **_kwargs: None)

    result = workflows.evaluate_route(
        ClickHouseClient(endpoint="http://ch"),
        route="structured_boosted",
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        model_dir="artifacts/ml/mirage",
    )

    assert result["sample_count"] == 1
    assert result["train_max_as_of_ts"] == "2026-03-18 10:59:59"
    optimized_scan_count = sum(scan_calls.values())
    legacy_scan_count = 4
    assert optimized_scan_count == 3
    assert optimized_scan_count < legacy_scan_count
