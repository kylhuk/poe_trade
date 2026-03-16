from __future__ import annotations

from unittest import mock

import pytest

from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows


class EvalFeedbackRouter:
    def __call__(self, _client: ClickHouseClient, query: str):
        if "FROM poe_trade.ml_eval_runs" in query and "run_id = 'run-candidate'" in query:
            return [{"avg_mdape": 0.094, "avg_cov": 0.81}]
        if "FROM poe_trade.ml_eval_runs" in query and "run_id != 'run-candidate'" in query:
            return [
                {
                    "run_id": "run-held",
                    "avg_mdape": 0.097,
                    "avg_cov": 0.82,
                    "recorded_at": "2026-03-16 10:00:00",
                }
            ]
        if "FROM poe_trade.ml_promotion_audit_v1" in query and "verdict = 'promote'" in query:
            return [
                {
                    "candidate_run_id": "run-promoted",
                    "recorded_at": "2026-03-15 10:00:00",
                }
            ]
        if "FROM poe_trade.ml_eval_runs" in query and "run_id = 'run-promoted'" in query:
            return [{"avg_mdape": 0.100, "avg_cov": 0.80}]
        return []


def test_eval_feedback_compares_candidate_against_latest_promoted_incumbent(monkeypatch) -> None:
    monkeypatch.setattr(workflows, "_query_rows", EvalFeedbackRouter())

    payload = workflows._eval_feedback_for_run(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        run_id="run-candidate",
    )

    assert payload["candidate_vs_incumbent"]["incumbent_run_id"] == "run-promoted"
    assert payload["candidate_vs_incumbent"]["mdape_improvement"] == pytest.approx(0.006)


def test_train_loop_marks_hold_runs_as_completed(monkeypatch) -> None:
    writes: list[dict[str, object]] = []

    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflows, "_ensure_tuning_rounds_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflows, "_latest_train_run_row", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflows, "_active_model_version", lambda *_args, **_kwargs: "mirage-1")
    monkeypatch.setattr(workflows, "_dataset_row_count", lambda *_args, **_kwargs: 1234)
    monkeypatch.setattr(workflows, "train_all_routes", lambda *_args, **_kwargs: {"trained": True})
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
    monkeypatch.setattr(workflows, "_record_tuning_round", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflows, "_promote_models", lambda *_args, **_kwargs: None)

    def _capture_write(*_args, **kwargs):
        writes.append({
            "run_id": kwargs["run_id"],
            "stage": kwargs["stage"],
            "status": kwargs["status"],
            "stop_reason": kwargs["stop_reason"],
        })

    monkeypatch.setattr(workflows, "_write_train_run", _capture_write)

    result = workflows.train_loop(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v1",
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
