from __future__ import annotations

import pytest

from poe_trade.ml.v3 import sql


@pytest.mark.parametrize(
    ("family", "predicate_fragment"),
    [
        (
            "flask",
            r"match(lowerUTF8(concat(ifNull(item_type_line, ''), ' ', ifNull(base_type, ''))), '(^|\\W)flask(\\W|$)')",
        ),
        (
            "map",
            r"match(lowerUTF8(concat(ifNull(item_type_line, ''), ' ', ifNull(base_type, ''))), '(^|\\W)map(\\W|$)')",
        ),
        (
            "cluster_jewel",
            r"match(lowerUTF8(concat(ifNull(item_type_line, ''), ' ', ifNull(base_type, ''))), '(^|\\W)cluster\\s+jewel(\\W|$)')",
        ),
        (
            "boots",
            r"match(lowerUTF8(concat(ifNull(item_type_line, ''), ' ', ifNull(base_type, ''))), '(^|\\W)boots(\\W|$)')",
        ),
    ],
)
def test_item_family_sample_query_filters_family_and_orders_rows(
    family: str, predicate_fragment: str
) -> None:
    query = sql.build_item_family_sample_query(
        league="Mirage",
        as_of_ts="2026-03-24 10:00:00",
        family=family,
    )

    assert f"FROM {sql.TRAINING_TABLE}" in query
    assert "WHERE league = 'Mirage'" in query
    assert (
        "route IN ('cluster_jewel_retrieval', 'structured_boosted', 'structured_boosted_other', 'sparse_retrieval', 'fallback_abstain')"
        in query
    )
    assert "target_price_chaos > 0" in query
    assert predicate_fragment in query
    assert "ORDER BY as_of_ts ASC, identity_key ASC, item_id ASC" in query
    assert "LIMIT 10000" in query


def test_item_family_sample_queries_reject_unknown_family() -> None:
    with pytest.raises(ValueError, match="unknown item family"):
        sql.build_item_family_sample_query(
            league="Mirage",
            as_of_ts="2026-03-24 10:00:00",
            family="sword",
        )
