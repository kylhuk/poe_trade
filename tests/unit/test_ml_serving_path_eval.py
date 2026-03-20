from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from poe_trade.ml import workflows


def test_serving_path_eval_uses_predict_one_pipeline(monkeypatch) -> None:
    client = cast(workflows.ClickHouseClient, cast(object, SimpleNamespace()))
    rows = [
        {
            "clipboard_text": "item-a",
            "target_price": 10.0,
            "credible_low": 9.5,
            "credible_high": 11.0,
            "route": "structured_boosted",
            "rarity": "Rare",
            "support_bucket": "high",
            "value_band": "mid",
            "category_family": "map",
            "league": "Mirage",
        },
        {
            "clipboard_text": "item-b",
            "target_price": 12.0,
            "credible_low": 10.0,
            "credible_high": 13.0,
            "route": "structured_boosted",
            "rarity": "Rare",
            "support_bucket": "high",
            "value_band": "mid",
            "category_family": "map",
            "league": "Mirage",
        },
    ]

    monkeypatch.setattr(
        workflows,
        "_serving_eval_rows",
        lambda *_args, **_kwargs: rows,
        raising=False,
    )

    calls: list[str] = []

    def _predict(_client, *, league: str, clipboard_text: str, model_version=None):
        calls.append(clipboard_text)
        return {
            "route": "structured_boosted",
            "price_p50": 10.5,
            "confidence": 0.7,
            "fallback_reason": "",
            "price_recommendation_eligible": True,
        }

    monkeypatch.setattr(workflows, "predict_one", _predict)

    payload = workflows.evaluate_serving_path(
        client,
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        limit=50,
    )

    assert calls == ["item-a", "item-b"]
    assert payload["overall"]["count"] == 2
    assert "relative_abs_error_mean" in payload["overall"]
    assert "extreme_miss_rate" in payload["overall"]
    assert "band_hit_rate" in payload["overall"]
    assert "abstain_precision" in payload["overall"]


def test_serving_path_eval_reports_route_segment_metrics(monkeypatch) -> None:
    client = cast(workflows.ClickHouseClient, cast(object, SimpleNamespace()))
    rows = [
        {
            "clipboard_text": "item-a",
            "target_price": 10.0,
            "credible_low": 9.5,
            "credible_high": 11.0,
            "route": "structured_boosted",
            "rarity": "Rare",
            "support_bucket": "high",
            "value_band": "mid",
            "category_family": "map",
            "league": "Mirage",
        }
    ]
    monkeypatch.setattr(
        workflows,
        "_serving_eval_rows",
        lambda *_args, **_kwargs: rows,
        raising=False,
    )
    monkeypatch.setattr(
        workflows,
        "predict_one",
        lambda *_args, **_kwargs: {
            "route": "structured_boosted",
            "price_p50": 10.1,
            "confidence": 0.8,
            "fallback_reason": "",
            "price_recommendation_eligible": True,
        },
    )

    payload = workflows.evaluate_serving_path(
        client,
        league="Mirage",
        dataset_table="poe_trade.ml_price_dataset_v2",
        limit=10,
    )

    assert set(payload["cohorts"]) == {
        "route",
        "rarity",
        "support_bucket",
        "value_band",
        "category_family",
        "league",
    }
    assert payload["cohorts"]["route"]["structured_boosted"]["count"] == 1
