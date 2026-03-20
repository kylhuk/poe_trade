from __future__ import annotations

import json

from poe_trade.ml.v3 import train


class _Client:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def execute(self, _query: str, settings=None) -> str:  # noqa: ANN001
        return self.payload


def test_train_route_v3_returns_no_data_when_empty() -> None:
    client = _Client(payload="")

    result = train.train_route_v3(
        client,
        league="Mirage",
        route="sparse_retrieval",
        model_dir="artifacts/ml",
    )

    assert result["status"] == "no_data"
    assert result["row_count"] == 0


def test_train_route_v3_writes_bundle_for_small_dataset(tmp_path) -> None:
    rows = [
        {
            "feature_vector_json": '{"ilvl":86,"stack_size":1,"corrupted":0}',
            "mod_features_json": '{"MaximumLife_tier":8,"MaximumLife_roll":0.9}',
            "target_price_chaos": 100.0,
            "target_fast_sale_24h_price": 92.0,
            "target_sale_probability_24h": 0.8,
        },
        {
            "feature_vector_json": '{"ilvl":84,"stack_size":1,"corrupted":0}',
            "mod_features_json": '{"MaximumLife_tier":7,"MaximumLife_roll":0.7}',
            "target_price_chaos": 80.0,
            "target_fast_sale_24h_price": 72.0,
            "target_sale_probability_24h": 0.6,
        },
        {
            "feature_vector_json": '{"ilvl":70,"stack_size":1,"corrupted":1}',
            "mod_features_json": '{"MaximumLife_tier":5,"MaximumLife_roll":0.4}',
            "target_price_chaos": 40.0,
            "target_fast_sale_24h_price": 35.0,
            "target_sale_probability_24h": 0.2,
        },
    ]
    payload = "\n".join(json.dumps(row) for row in rows) + "\n"
    client = _Client(payload=payload)

    result = train.train_route_v3(
        client,
        league="Mirage",
        route="sparse_retrieval",
        model_dir=str(tmp_path),
    )

    assert result["status"] == "trained"
    assert result["row_count"] == 3
    assert result["model_bundle_path"].endswith("bundle.joblib")
