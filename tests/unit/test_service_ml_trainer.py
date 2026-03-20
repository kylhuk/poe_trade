from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from poe_trade.services import ml_trainer


def test_ml_trainer_persists_rollout_controls_in_status(monkeypatch) -> None:
    status_path = Path(".sisyphus/state/qa/ml-trainer-last-run.json")
    if status_path.exists():
        status_path.unlink()

    cfg = SimpleNamespace(
        clickhouse_url="http://ch",
        ml_automation_enabled=True,
        ml_automation_league="Mirage",
        ml_automation_interval_seconds=30,
        ml_automation_max_iterations=1,
        ml_automation_max_wall_clock_seconds=60,
        ml_automation_no_improvement_patience=2,
        ml_automation_min_mdape_improvement=0.005,
    )
    monkeypatch.setattr(ml_trainer.config_settings, "get_settings", lambda: cfg)
    monkeypatch.setattr(
        ml_trainer.ClickHouseClient,
        "from_env",
        lambda _url: SimpleNamespace(),
    )
    monkeypatch.setattr(
        ml_trainer.workflows,
        "warmup_active_models",
        lambda *_args, **_kwargs: {"lastAttemptAt": None, "routes": {}},
    )
    monkeypatch.setattr(
        ml_trainer.workflows,
        "train_loop",
        lambda *_args, **_kwargs: {
            "status": "completed",
            "stop_reason": "hold_no_material_improvement",
            "active_model_version": "mirage-v1",
        },
    )
    calls: list[str] = []

    def _rollout_controls(_client, *, league):
        calls.append(league)
        return {
            "league": league,
            "shadow_mode": True,
            "cutover_enabled": False,
            "candidate_model_version": "mirage-v2",
            "incumbent_model_version": "mirage-v1",
            "effective_serving_model_version": "mirage-v1",
            "updated_at": "2026-03-19 12:06:00",
            "last_action": "rollback_to_incumbent",
        }

    monkeypatch.setattr(ml_trainer.workflows, "rollout_controls", _rollout_controls)

    result = ml_trainer.main(["--once", "--league", "Mirage"])

    assert result == 0
    assert status_path.exists()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["league"] == "Mirage"
    assert payload["rollout"]["shadow_mode"] is True
    assert payload["rollout"]["cutover_enabled"] is False
    assert payload["rollout"]["candidate_model_version"] == "mirage-v2"
    assert payload["rollout"]["incumbent_model_version"] == "mirage-v1"
    assert payload["rollout"]["effective_serving_model_version"] == "mirage-v1"
    assert calls == ["Mirage", "Mirage"]


def test_ml_trainer_rejects_legacy_v1_dataset(monkeypatch) -> None:
    cfg = SimpleNamespace(
        clickhouse_url="http://ch",
        ml_automation_enabled=True,
        ml_automation_league="Mirage",
        ml_automation_interval_seconds=30,
        ml_automation_max_iterations=1,
        ml_automation_max_wall_clock_seconds=60,
        ml_automation_no_improvement_patience=2,
        ml_automation_min_mdape_improvement=0.005,
    )
    monkeypatch.setattr(ml_trainer.config_settings, "get_settings", lambda: cfg)

    try:
        ml_trainer.main(
            [
                "--once",
                "--league",
                "Mirage",
                "--dataset-table",
                "poe_trade.ml_price_dataset_v1",
                "--model-dir",
                "artifacts/ml/mirage_v2",
            ]
        )
    except ValueError as exc:
        assert "v2 dataset table" in str(exc)
    else:
        raise AssertionError("expected ValueError for legacy v1 dataset table")


def test_ml_trainer_uses_v3_training_when_enabled(monkeypatch) -> None:
    cfg = SimpleNamespace(
        clickhouse_url="http://ch",
        ml_automation_enabled=True,
        ml_automation_league="Mirage",
        ml_automation_interval_seconds=30,
        ml_automation_max_iterations=1,
        ml_automation_max_wall_clock_seconds=60,
        ml_automation_no_improvement_patience=2,
        ml_automation_min_mdape_improvement=0.005,
    )
    monkeypatch.setattr(ml_trainer.config_settings, "get_settings", lambda: cfg)
    monkeypatch.setattr(
        ml_trainer.ClickHouseClient,
        "from_env",
        lambda _url: SimpleNamespace(),
    )
    monkeypatch.setattr(
        ml_trainer.workflows,
        "warmup_active_models",
        lambda *_args, **_kwargs: {"lastAttemptAt": None, "routes": {}},
    )
    monkeypatch.setenv("POE_ML_V3_TRAINER_ENABLED", "1")
    monkeypatch.setattr(
        ml_trainer.v3_train,
        "train_all_routes_v3",
        lambda *_args, **_kwargs: {"trained_count": 2, "routes": ["a", "b"]},
    )
    monkeypatch.setattr(
        ml_trainer.workflows,
        "rollout_controls",
        lambda *_args, **_kwargs: {
            "league": "Mirage",
            "shadow_mode": False,
            "cutover_enabled": False,
            "candidate_model_version": None,
            "incumbent_model_version": None,
            "effective_serving_model_version": None,
            "updated_at": "2026-03-20 00:00:00",
            "last_action": "noop",
        },
    )

    result = ml_trainer.main(["--once", "--league", "Mirage"])

    assert result == 0
