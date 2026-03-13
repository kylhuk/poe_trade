from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from poe_trade.ml import workflows


def test_candidate_vs_incumbent_promote_verdict():
    comparison = workflows._candidate_vs_incumbent_summary(
        candidate={"run_id": "cand-1", "avg_mdape": 0.8, "avg_cov": 0.85},
        incumbent={"run_id": "inc-1", "avg_mdape": 0.9, "avg_cov": 0.82},
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
        candidate={"run_id": "cand-1", "avg_mdape": 0.8, "avg_cov": 0.7},
        incumbent={"run_id": "inc-1", "avg_mdape": 0.9, "avg_cov": 0.82},
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
        candidate={"run_id": "cand-1", "avg_mdape": 0.8, "avg_cov": 0.9},
        incumbent={"run_id": "inc-1", "avg_mdape": 0.9, "avg_cov": 0.9},
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
        dataset_table="poe_trade.ml_price_dataset_v1",
        model_dir=str(tmp_path),
        max_iterations=5,
        max_wall_clock_seconds=3600,
        no_improvement_patience=1,
        min_mdape_improvement=0.1,
        resume=False,
    )

    assert result["status"] == "stopped_no_improvement"
    assert result["stop_reason"] == "no_improvement_patience_exhausted"


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

    with pytest.raises(ValueError, match="resume requested"):
        workflows.train_loop(
            client,
            league="Mirage",
            dataset_table="poe_trade.ml_price_dataset_v1",
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
        dataset_table="poe_trade.ml_price_dataset_v1",
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
            dataset_table="poe_trade.ml_price_dataset_v1",
            model_dir="artifacts/ml/mirage_v1",
            split="random",
            output_dir="artifacts/ml/mirage_v1",
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
