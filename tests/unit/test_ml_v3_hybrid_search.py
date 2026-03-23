from __future__ import annotations

import pytest
import importlib
import sys

from poe_trade.ml.v3.hybrid_search import (
    SearchResult,
    rank_affixes_by_importance,
    run_search,
    score_confidence,
)


def test_rank_affixes_prefers_high_lift_even_with_low_frequency() -> None:
    ranked = rank_affixes_by_importance(
        cohort_30d={
            "high_lift_low_freq": {"lift": 4.2, "count": 2},
            "mid_lift_high_freq": {"lift": 2.1, "count": 60},
            "low_lift_very_high_freq": {"lift": 1.2, "count": 220},
        },
        cohort_90d={},
        route_prior={},
    )

    assert [entry["affix"] for entry in ranked] == [
        "high_lift_low_freq",
        "mid_lift_high_freq",
        "low_lift_very_high_freq",
    ]


def test_rank_affixes_uses_fallback_chain_for_empty_or_thin_cohorts() -> None:
    from_90d = rank_affixes_by_importance(
        cohort_30d={},
        cohort_90d={
            "cohort90d_winner": {"lift": 2.7, "count": 8},
            "cohort90d_other": {"lift": 2.1, "count": 5},
        },
        route_prior={"route_prior_top": {"lift": 9.9, "count": 99}},
        min_total_support=10,
    )
    assert [entry["source"] for entry in from_90d] == ["cohort_90d", "cohort_90d"]
    assert from_90d[0]["affix"] == "cohort90d_winner"

    from_route_prior = rank_affixes_by_importance(
        cohort_30d={"thin_30d": {"lift": 8.0, "count": 2}},
        cohort_90d={"thin_90d": {"lift": 7.5, "count": 2}},
        route_prior={
            "route_prior_a": {"lift": 1.8, "count": 50},
            "route_prior_b": {"lift": 1.1, "count": 40},
        },
        min_total_support=5,
    )
    assert [entry["source"] for entry in from_route_prior] == [
        "route_prior",
        "route_prior",
    ]
    assert [entry["affix"] for entry in from_route_prior] == [
        "route_prior_a",
        "route_prior_b",
    ]


def test_rank_affixes_tie_break_is_deterministic() -> None:
    first_call = rank_affixes_by_importance(
        cohort_30d={
            "zeta": {"lift": 2.0, "count": 5},
            "alpha": {"lift": 2.0, "count": 5},
            "beta": {"lift": 2.0, "count": 5},
        },
        cohort_90d={},
        route_prior={},
    )
    second_call = rank_affixes_by_importance(
        cohort_30d={
            "beta": {"lift": 2.0, "count": 5},
            "zeta": {"lift": 2.0, "count": 5},
            "alpha": {"lift": 2.0, "count": 5},
        },
        cohort_90d={},
        route_prior={},
    )

    assert [entry["affix"] for entry in first_call] == ["alpha", "beta", "zeta"]
    assert [entry["affix"] for entry in second_call] == ["alpha", "beta", "zeta"]


def test_rank_affixes_uses_route_prior_as_terminal_fallback_when_all_sources_thin() -> (
    None
):
    ranked = rank_affixes_by_importance(
        cohort_30d={"thin_30d": {"lift": 6.0, "count": 1}},
        cohort_90d={"thin_90d": {"lift": 5.0, "count": 1}},
        route_prior={
            "route_prior_z": {"lift": 1.1, "count": 1},
            "route_prior_a": {"lift": 1.1, "count": 1},
        },
        min_total_support=10,
    )

    assert [entry["source"] for entry in ranked] == ["route_prior", "route_prior"]
    assert [entry["affix"] for entry in ranked] == ["route_prior_a", "route_prior_z"]


def test_importing_v3_package_does_not_eager_import_heavy_modules() -> None:
    for module_name in [
        "poe_trade.ml.v3",
        "poe_trade.ml.v3.backfill",
        "poe_trade.ml.v3.eval",
        "poe_trade.ml.v3.serve",
        "poe_trade.ml.v3.train",
    ]:
        sys.modules.pop(module_name, None)

    module = importlib.import_module("poe_trade.ml.v3")

    assert hasattr(module, "__all__")
    assert "poe_trade.ml.v3.backfill" not in sys.modules
    assert "poe_trade.ml.v3.eval" not in sys.modules
    assert "poe_trade.ml.v3.serve" not in sys.modules
    assert "poe_trade.ml.v3.train" not in sys.modules


def test_run_search_preserves_high_value_affixes_before_common_ones() -> None:
    ranked_affixes = rank_affixes_by_importance(
        cohort_30d={
            "high_value": {"lift": 9.0, "count": 4},
            "high_support": {"lift": 8.0, "count": 3},
            "light_radius": {"lift": 0.5, "count": 120},
        },
        cohort_90d={},
        route_prior={},
    )
    target_item = {
        "base_type": "Vaal Axe",
        "rarity": "Rare",
        "item_state_key": "rare|corrupted=1|fractured=0|synthesised=0",
        "mod_features_json": '{"high_value": 10, "high_support": 7}',
    }
    candidate_rows = [
        {
            "identity_key": "a1",
            "base_type": "Vaal Axe",
            "rarity": "Rare",
            "item_state_key": "rare|corrupted=1|fractured=0|synthesised=0",
            "mod_features_json": '{"high_value": 10, "high_support": 7}',
            "target_price_chaos": 40.0,
            "support_count_recent": 5,
            "as_of_ts": "2026-03-20T10:00:00",
        },
        {
            "identity_key": "a2",
            "base_type": "Vaal Axe",
            "rarity": "Rare",
            "item_state_key": "rare|corrupted=1|fractured=0|synthesised=0",
            "mod_features_json": '{"high_value": 12, "high_support": 8}',
            "target_price_chaos": 42.0,
            "support_count_recent": 6,
            "as_of_ts": "2026-03-20T09:00:00",
        },
    ]

    result = run_search(
        parsed_item=target_item,
        candidate_rows=candidate_rows,
        ranked_affixes=ranked_affixes,
        stage_support_targets={1: 3, 2: 3, 3: 1, 4: 24},
        max_candidates=64,
    )

    assert result.stage == 3
    assert result.dropped_affixes == ["light_radius"]
    assert result.effective_support == 2


def test_run_search_applies_similarity_weights_and_penalties() -> None:
    ranked_affixes = rank_affixes_by_importance(
        cohort_30d={"explicit.crit_chance": {"lift": 6.0, "count": 12}},
        cohort_90d={},
        route_prior={},
    )
    target_item = {
        "base_type": "Hubris Circlet",
        "rarity": "Rare",
        "item_state_key": "rare|corrupted=0|fractured=0|synthesised=0",
        "mod_features_json": '{"explicit.crit_chance": 30}',
    }
    rows = [
        {
            "identity_key": "v1",
            "base_type": "Hubris Circlet",
            "rarity": "Rare",
            "item_state_key": "rare|corrupted=0|fractured=0|synthesised=0",
            "mod_features_json": '{"explicit.crit_chance": 30}',
            "target_price_chaos": 120.0,
            "support_count_recent": 8,
        }
    ]

    result = run_search(
        parsed_item=target_item,
        candidate_rows=rows,
        ranked_affixes=ranked_affixes,
        stage_support_targets={1: 1, 2: 1, 3: 1, 4: 1},
        max_candidates=64,
    )

    assert result.stage == 1
    assert result.candidate_count == 1
    assert result.candidates[0]["score"] == pytest.approx(0.82, rel=1e-3)


def test_run_search_uses_prior_only_stage_zero_when_no_candidates_exist() -> None:
    target_item = {
        "base_type": "Any",
        "rarity": "Rare",
        "item_state_key": "rare|corrupted=0|fractured=0|synthesised=0",
    }
    result = run_search(
        parsed_item=target_item,
        candidate_rows=[],
        ranked_affixes=[],
        stage_support_targets={1: 1, 2: 1, 3: 1, 4: 1},
        max_candidates=64,
    )

    assert isinstance(result, SearchResult)
    assert result.stage == 0
    assert result.candidate_count == 0
    assert result.effective_support == 0
    assert result.degradation_reason is not None


def test_confidence_formula_matches_spec_components() -> None:
    result = score_confidence(
        stage=3,
        effective_support=22,
        p10=88.0,
        p50=100.0,
        p90=124.0,
    )

    assert result["confidence"] == pytest.approx(0.61, rel=1e-3)
    assert result["estimate_trust"] == "normal"


def test_stage_zero_sets_low_confidence_and_not_eligible() -> None:
    result = score_confidence(
        stage=0,
        effective_support=0,
        p10=90.0,
        p50=100.0,
        p90=130.0,
    )

    assert result["confidence"] == 0.10
    assert result["price_recommendation_eligible"] is False
