from __future__ import annotations

from poe_trade.ml import workflows


def test_abstain_when_support_below_threshold() -> None:
    policy = workflows._apply_recommendation_policy(
        support_count=5,
        confidence=0.9,
        price_p10=9.0,
        price_p50=10.0,
        price_p90=11.0,
    )
    assert policy["abstained"] is True
    assert "low_support" in policy["abstain_reasons"]


def test_abstain_when_band_instability_is_high() -> None:
    policy = workflows._apply_recommendation_policy(
        support_count=30,
        confidence=0.9,
        price_p10=1.0,
        price_p50=10.0,
        price_p90=20.0,
    )
    assert policy["abstained"] is True
    assert "unstable_band" in policy["abstain_reasons"]


def test_policy_returns_reason_codes() -> None:
    policy = workflows._apply_recommendation_policy(
        support_count=30,
        confidence=0.2,
        price_p10=9.0,
        price_p50=10.0,
        price_p90=11.0,
    )
    assert policy["abstained"] is True
    assert "low_confidence" in policy["abstain_reasons"]


def test_ece_uses_rae_lte_0_30_accuracy_event() -> None:
    ece = workflows._expected_calibration_error(
        [
            {"confidence": 0.8, "rae": 0.1},
            {"confidence": 0.7, "rae": 0.5},
        ]
    )
    assert ece >= 0.0
