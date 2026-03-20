from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from poe_trade.ml import workflows


def test_status_surfaces_serving_path_gate_metrics_for_shadow_mode(monkeypatch) -> None:
    client = cast(workflows.ClickHouseClient, cast(object, SimpleNamespace()))
    monkeypatch.setattr(workflows, "_ensure_supported_league", lambda *_a, **_k: None)
    monkeypatch.setattr(workflows, "_ensure_train_runs_table", lambda *_a, **_k: None)
    monkeypatch.setattr(
        workflows,
        "train_run_history",
        lambda *_a, **_k: [
            {
                "league": "Mirage",
                "run_id": "r1",
                "status": "completed",
                "source_watermarks_json": "{}",
            }
        ],
    )
    monkeypatch.setattr(workflows, "_latest_eval_run_id", lambda *_a, **_k: "eval-1")
    monkeypatch.setattr(workflows, "_eval_feedback_for_run", lambda *_a, **_k: {})
    monkeypatch.setattr(workflows, "_latest_route_hotspots", lambda *_a, **_k: {})
    monkeypatch.setattr(
        workflows, "_promotion_verdict_for_run", lambda *_a, **_k: "hold"
    )
    monkeypatch.setattr(workflows, "_active_model_version", lambda *_a, **_k: "v1")

    payload = workflows.status(client, league="Mirage", run="latest")

    assert payload["serving_path_gate"]["shadow_min_days"] == 7
    assert "rollback_thresholds" in payload["serving_path_gate"]
    assert payload["observability"]["anchor_usage_rate"] == 0.0
