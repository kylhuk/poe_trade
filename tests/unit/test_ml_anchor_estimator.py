from __future__ import annotations

from poe_trade.ml import workflows


def test_comparable_similarity_score_is_deterministic() -> None:
    item = {
        "base_type": "Cemetery Map",
        "mod_signature": "pack_size,quantity",
        "ilvl": 83,
        "state": "normal",
    }
    comp = {
        "base_type": "Cemetery Map",
        "mod_signature": "pack_size,quantity",
        "ilvl": 82,
        "state": "normal",
        "hours_ago": 1,
    }

    score_a = workflows._comparable_similarity_score(item=item, comparable=comp)
    score_b = workflows._comparable_similarity_score(item=item, comparable=comp)
    assert score_a == score_b


def test_retrieval_caps_to_top_200_and_tiebreaks_deterministically() -> None:
    item = {"league": "Mirage", "route_family": "structured", "item_class": "map"}
    rows = [
        {
            "listing_id": f"id-{idx:03d}",
            "league": "Mirage",
            "route_family": "structured",
            "item_class": "map",
            "base_type": "Cemetery Map",
            "mod_signature": "a",
            "ilvl": 80,
            "state": "normal",
            "hours_ago": idx % 5,
        }
        for idx in range(300)
    ]

    selected = workflows._select_top_comparables(
        item=item, comparable_rows=rows, cap=200
    )
    assert len(selected) == 200
    # deterministic by stable listing_id tie-break
    assert selected[0]["listing_id"] <= selected[1]["listing_id"]


def test_retrieval_fallbacks_to_broader_family_before_abstain() -> None:
    item = {"league": "Mirage", "route_family": "structured", "item_class": "map"}
    rows = [
        {
            "listing_id": "broader-1",
            "league": "Mirage",
            "route_family": "fallback",
            "item_class": "map",
            "base_type": "Cemetery Map",
            "mod_signature": "a",
            "ilvl": 80,
            "state": "normal",
            "hours_ago": 1,
        }
    ]

    selected = workflows._select_top_comparables(
        item=item,
        comparable_rows=rows,
        cap=200,
        allow_broader_fallback=True,
    )
    assert selected


def test_anchor_applies_support_minimums_25_15_10_by_route() -> None:
    comps = [{"price_chaos": 10.0, "hours_ago": 1, "seller_observation_count": 1}] * 9
    payload = workflows._robust_anchor_from_comparables(comps, route_kind="fallback")
    assert payload["support_count"] == 0
    assert payload["abstain_reason"] == "low_support"


def test_anchor_applies_credibility_floors_60_70_75_percent_q25() -> None:
    comps = [
        {"price_chaos": 1.0, "hours_ago": 1, "seller_observation_count": 1},
        {"price_chaos": 10.0, "hours_ago": 1, "seller_observation_count": 1},
        {"price_chaos": 11.0, "hours_ago": 1, "seller_observation_count": 1},
        {"price_chaos": 12.0, "hours_ago": 1, "seller_observation_count": 1},
        {"price_chaos": 13.0, "hours_ago": 1, "seller_observation_count": 1},
    ] * 6
    payload = workflows._robust_anchor_from_comparables(comps, route_kind="structured")
    assert payload["trim_low_count"] >= 1


def test_anchor_applies_72h_recency_window() -> None:
    comps = [
        {"price_chaos": 10.0, "hours_ago": 1, "seller_observation_count": 1},
        {"price_chaos": 100.0, "hours_ago": 200, "seller_observation_count": 1},
    ] * 20
    payload = workflows._robust_anchor_from_comparables(comps, route_kind="structured")
    assert payload["trim_high_count"] >= 1


def test_anchor_outputs_contract_fields() -> None:
    comps = [{"price_chaos": 10.0, "hours_ago": 1, "seller_observation_count": 1}] * 30
    payload = workflows._robust_anchor_from_comparables(comps, route_kind="structured")
    assert set(payload) >= {
        "anchor_price",
        "credible_low",
        "credible_high",
        "support_count",
        "trim_low_count",
        "trim_high_count",
    }
