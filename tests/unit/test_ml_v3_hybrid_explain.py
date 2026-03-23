from __future__ import annotations

from poe_trade.ml.v3.hybrid_explain import build_hybrid_response


def test_build_response_includes_value_drivers_and_search_diagnostics() -> None:
    payload = build_hybrid_response(
        fair_value={"p10": 90.0, "p50": 100.0, "p90": 120.0},
        fast_sale_24h_price=92.0,
        sale_probability_24h=0.64,
        confidence=0.61,
        estimate_trust="normal",
        search={
            "stage": 2,
            "candidate_count": 11,
            "effective_support": 8,
            "dropped_affixes": ["explicit.light_radius"],
            "degradation_reason": None,
        },
        comparables={
            "anchor_price": 99.0,
            "anchor_low": 90.0,
            "anchor_high": 120.0,
        },
    )

    assert payload["searchDiagnostics"]["stage"] == 2
    assert payload["valueDrivers"]["positive"]


def test_stage_zero_response_omits_alternate_scenarios() -> None:
    payload = build_hybrid_response(
        fair_value={"p10": 90.0, "p50": 100.0, "p90": 120.0},
        fast_sale_24h_price=92.0,
        sale_probability_24h=0.64,
        confidence=0.10,
        estimate_trust="low",
        search={
            "stage": 0,
            "candidate_count": 0,
            "effective_support": 0,
            "dropped_affixes": [],
            "degradation_reason": "no_relevant_comparables",
        },
        comparables={
            "anchor_price": 100.0,
            "anchor_low": 90.0,
            "anchor_high": 120.0,
        },
    )

    assert payload["scenarioPrices"]["weakerRolls"] == []
