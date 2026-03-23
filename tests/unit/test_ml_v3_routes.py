from __future__ import annotations

from poe_trade.ml.v3 import routes, sql


def test_select_route_matches_current_sparse_rare_behavior() -> None:
    parsed = {"category": "helmet", "rarity": "Rare"}

    assert routes.select_route(parsed) == "sparse_retrieval"


def test_select_route_matches_cluster_jewel_behavior() -> None:
    parsed = {"category": "cluster_jewel", "rarity": "Rare"}

    assert routes.select_route(parsed) == "cluster_jewel_retrieval"


def test_select_route_keeps_unique_cluster_jewel_on_cluster_route() -> None:
    parsed = {"category": "cluster_jewel", "rarity": "Unique"}

    assert routes.select_route(parsed) == "cluster_jewel_retrieval"


def test_select_route_keeps_essence_behavior_from_previous_serving_logic() -> None:
    assert routes.select_route({"category": "essence", "rarity": "Magic"}) == (
        "fallback_abstain"
    )
    assert routes.select_route({"category": "essence", "rarity": "Rare"}) == (
        "sparse_retrieval"
    )


def test_serving_and_training_share_route_contract() -> None:
    parsed = {"category": "ring", "rarity": "Unique"}

    assert sql.select_route(parsed) == routes.select_route(parsed)


def test_route_sql_expression_preserves_edge_case_rule_order() -> None:
    expr = routes.route_sql_expression()

    assert expr.index("= 'cluster_jewel'") < expr.index("= 'Unique'")
    assert "IN ('essence')" not in expr
    assert "= 'Rare'" in expr
