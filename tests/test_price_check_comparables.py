from __future__ import annotations

import logging
import sys
from collections.abc import Mapping

import pytest

sys.path.insert(0, "/mnt/data/devrepo")

from poe_trade.api import ops as api_ops
from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows


RARE_HELM = """Rarity: Rare
Grim Bane
Hubris Circlet
--------
Quality: +20%
Item Level: 86
--------
+2 to Level of Socketed Minion Gems
+93 to maximum Life
"""


class _RecordingClickHouse(ClickHouseClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.responses = list(responses)
        self.queries: list[str] = []

    def execute(self, query: str, settings: Mapping[str, str] | None = None) -> str:  # type: ignore[override]
        del settings
        self.queries.append(query)
        if self.responses:
            return self.responses.pop(0)
        return ""


class _StaticModel:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, _rows):
        return [self.value]


class _PassthroughVectorizer:
    def transform(self, rows):
        return rows


@pytest.fixture(autouse=True)
def reset_ml_runtime_caches() -> None:
    workflows.reset_serving_runtime_caches()


def test_price_check_payload_uses_base_type_lookup_and_returns_recent_comparables(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        api_ops,
        "fetch_predict_one",
        lambda _client, league, request_payload: {
            "predictedValue": 120.0,
            "fairValueP50": 121.0,
            "fastSale24hPrice": 109.0,
            "currency": "chaos",
            "confidence": 0.64,
            "interval": {"p10": 90.0, "p90": 150.0},
            "saleProbabilityPercent": 58.0,
            "priceRecommendationEligible": True,
            "fallbackReason": "",
            "mlPredicted": True,
            "predictionSource": "ml",
            "estimateTrust": "normal",
            "estimateWarning": None,
        },
    )
    client = _RecordingClickHouse(
        [
            "\n".join(
                [
                    '{"item_name":"Hubris Circlet","league":"Mirage","listed_price":118.0,"added_on":"2026-03-15 12:00:00"}',
                    '{"item_name":"Hubris Circlet","league":"Mirage","listed_price":125.0,"added_on":"2026-03-14 12:00:00"}',
                ]
            )
        ]
    )

    payload = api_ops.price_check_payload(client, league="Mirage", item_text=RARE_HELM)

    assert payload["comparables"] == [
        {
            "name": "Hubris Circlet",
            "price": 118.0,
            "currency": "chaos",
            "league": "Mirage",
            "addedOn": "2026-03-15T12:00:00Z",
        },
        {
            "name": "Hubris Circlet",
            "price": 125.0,
            "currency": "chaos",
            "league": "Mirage",
            "addedOn": "2026-03-14T12:00:00Z",
        },
    ]
    assert any("base_type = 'Hubris Circlet'" in query for query in client.queries)
    assert not any("Grim Bane" in query for query in client.queries)
    assert payload["mlPredicted"] is True
    assert payload["predictionSource"] == "ml"
    assert payload["estimateTrust"] == "normal"
    assert payload["estimateWarning"] is None
    assert payload["fairValueP50"] == 121.0
    assert payload["fastSale24hPrice"] == 109.0


def test_predict_one_uses_serving_profile_when_present(monkeypatch) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_route_for_item",
        lambda _item: {
            "route": "sparse_retrieval",
            "route_reason": "sparse_high_dimensional",
            "support_count_recent": 20,
        },
    )
    monkeypatch.setattr(
        workflows, "_load_active_route_artifact", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(workflows, "_predict_with_artifact", lambda **_kwargs: None)

    client = _RecordingClickHouse(
        [
            '{"support_count_recent":91,"reference_price_p50":13.25,"snapshot_window_id":"window-123","profile_as_of_ts":"2026-03-15 12:00:00"}',
        ]
    )

    payload = workflows.predict_one(
        client,
        league="Mirage",
        clipboard_text="dummy",
    )

    assert payload["support_count_recent"] == 91
    assert payload["price_p50"] == 13.25
    assert payload["fallback_reason"] == "ml_no_prediction_static_fallback"
    assert any(
        "FROM poe_trade.ml_serving_profile_v1" in query for query in client.queries
    )
    assert not any(
        "FROM poe_trade.ml_price_dataset_v1" in query
        and "count() AS sample_count" in query
        for query in client.queries
    )
    assert not any(
        "FROM poe_trade.ml_price_dataset_v1" in query
        and "quantileTDigest(0.5)(normalized_price_chaos) AS p50" in query
        for query in client.queries
    )


def test_predict_one_profile_miss_uses_deterministic_fallback_without_error(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_route_for_item",
        lambda _item: {
            "route": "sparse_retrieval",
            "route_reason": "sparse_high_dimensional",
            "support_count_recent": 20,
        },
    )
    monkeypatch.setattr(
        workflows, "_load_active_route_artifact", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(workflows, "_predict_with_artifact", lambda **_kwargs: None)

    client = _RecordingClickHouse(
        [
            "",
            '{"sample_count":7}',
            '{"p50":9.5}',
        ]
    )
    caplog.set_level(logging.INFO, logger="poe_trade.ml.workflows")

    payload = workflows.predict_one(
        client,
        league="Mirage",
        clipboard_text="dummy",
    )

    assert payload["support_count_recent"] == 7
    assert payload["price_p50"] == 9.5
    assert payload["fallback_reason"] == "ml_no_prediction_static_fallback"
    assert any(
        "predict_one serving profile miss; using deterministic fallback" in message
        for message in caplog.messages
    )
    assert any(
        "FROM poe_trade.ml_price_dataset_" in query
        and "count() AS sample_count" in query
        for query in client.queries
    )
    assert any(
        "FROM poe_trade.ml_price_dataset_" in query
        and "quantileTDigest(0.5)(normalized_price_chaos) AS p50" in query
        for query in client.queries
    )


def test_predict_one_feature_schema_parity_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "ilvl": 86,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 2,
            "mod_features_json": '{"MaximumLife_tier":8}',
        },
    )
    monkeypatch.setattr(
        workflows,
        "_route_for_item",
        lambda _item: {
            "route": "sparse_retrieval",
            "route_reason": "sparse_high_dimensional",
            "support_count_recent": 20,
        },
    )
    monkeypatch.setattr(
        workflows,
        "_serving_profile_lookup",
        lambda *_args, **_kwargs: {
            "hit": True,
            "support_count_recent": 91,
            "reference_price": 13.25,
            "reason": "profile_hit",
        },
    )

    schema_fields = [*workflows.BASE_FEATURE_FIELDS, "MaximumLife_tier"]
    monkeypatch.setattr(
        workflows,
        "_load_active_route_artifact",
        lambda *_args, **_kwargs: {
            "train_row_count": 900,
            "model_bundle_path": "bundle.joblib",
            "feature_schema": {
                "version": "v1",
                "fields": schema_fields,
            },
        },
    )
    monkeypatch.setattr(
        workflows,
        "_load_model_bundle",
        lambda _path: {
            "vectorizer": _PassthroughVectorizer(),
            "price_models": {
                "p10": _StaticModel(10.0),
                "p50": _StaticModel(12.0),
                "p90": _StaticModel(15.0),
            },
            "sale_model": _StaticModel(0.62),
            "price_tiers": {},
        },
    )

    payload = workflows.predict_one(
        ClickHouseClient(endpoint="http://ch"),
        league="Mirage",
        clipboard_text="dummy",
    )

    assert payload["price_p50"] == 12.0
    assert payload["fallback_reason"] == ""
    assert payload["price_recommendation_eligible"] is True


def test_predict_one_feature_schema_mismatch_fails_deterministically(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "_parse_clipboard_item",
        lambda _text: {
            "category": "helmet",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "ilvl": 86,
            "stack_size": 1,
            "corrupted": 0,
            "fractured": 0,
            "synthesised": 0,
            "mod_token_count": 2,
            "mod_features_json": '{"MaximumLife_tier":8}',
        },
    )
    monkeypatch.setattr(
        workflows,
        "_route_for_item",
        lambda _item: {
            "route": "sparse_retrieval",
            "route_reason": "sparse_high_dimensional",
            "support_count_recent": 20,
        },
    )
    monkeypatch.setattr(
        workflows,
        "_serving_profile_lookup",
        lambda *_args, **_kwargs: {
            "hit": True,
            "support_count_recent": 91,
            "reference_price": 13.25,
            "reason": "profile_hit",
        },
    )
    monkeypatch.setattr(
        workflows,
        "_load_active_route_artifact",
        lambda *_args, **_kwargs: {
            "train_row_count": 900,
            "model_bundle_path": "bundle.joblib",
            "feature_schema": {
                "version": "v1",
                "fields": [
                    field
                    for field in workflows.BASE_FEATURE_FIELDS
                    if field != "category_price_tier"
                ],
            },
        },
    )
    monkeypatch.setattr(
        workflows,
        "_load_model_bundle",
        lambda _path: {
            "vectorizer": _PassthroughVectorizer(),
            "price_models": {
                "p10": _StaticModel(10.0),
                "p50": _StaticModel(12.0),
                "p90": _StaticModel(15.0),
            },
            "sale_model": _StaticModel(0.62),
            "price_tiers": {},
        },
    )

    with pytest.raises(workflows.FeatureSchemaMismatchError, match="schema mismatch"):
        workflows.predict_one(
            ClickHouseClient(endpoint="http://ch"),
            league="Mirage",
            clipboard_text="dummy",
        )
