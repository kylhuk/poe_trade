from __future__ import annotations

import json

from poe_trade.ml.v3 import serve


class _Client:
    def execute(self, query: str, settings=None) -> str:  # noqa: ANN001
        if "quantileTDigest(0.5)(target_price_chaos)" in query:
            return json.dumps({"p50": 120.0, "rows": 32}) + "\n"
        return ""


def test_predict_one_v3_fallback_returns_dual_prices(monkeypatch) -> None:
    monkeypatch.setattr(
        serve.workflows,
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
            "mod_features_json": "{}",
        },
    )

    payload = serve.predict_one_v3(
        _Client(),
        league="Mirage",
        clipboard_text="dummy",
        model_dir="/does/not/exist",
    )

    assert payload["route"] == "sparse_retrieval"
    assert payload["fair_value_p50"] == 120.0
    assert payload["fast_sale_24h_price"] == 108.0
    assert payload["prediction_source"] == "v3_median_fallback"
    assert payload["price_recommendation_eligible"] is True
