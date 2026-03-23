from __future__ import annotations

from poe_trade.ml.v3.hybrid_anchor import build_anchor


def test_anchor_uses_weighted_median_from_positive_weight_candidates() -> None:
    anchor = build_anchor(
        [
            {"price": 90.0, "score": 0.2},
            {"price": 120.0, "score": 0.6},
            {"price": 200.0, "score": 0.2},
        ]
    )

    assert anchor.anchor_price == 120.0


def test_anchor_ignores_zero_weight_rows_for_effective_support() -> None:
    anchor = build_anchor(
        [
            {"price": 100.0, "score": 0.0},
            {"price": 120.0, "score": 0.5},
            {"price": 150.0, "score": 0.7},
        ]
    )

    assert anchor.effective_support == 2
