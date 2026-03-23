from __future__ import annotations

from datetime import date

from poe_trade.ml.v3 import sql
from poe_trade.ml.v3 import routes


def test_disk_usage_query_targets_system_parts() -> None:
    query = sql.disk_usage_query()

    assert "FROM system.parts" in query
    assert "database = 'poe_trade'" in query


def test_build_events_insert_query_scopes_league_and_day() -> None:
    query = sql.build_events_insert_query(league="Mirage", day=date(2026, 3, 20))

    assert f"INSERT INTO {sql.EVENTS_TABLE}" in query
    assert "WHERE league = 'Mirage'" in query
    assert "toDate('2026-03-20')" in query
    assert "lagInFrame" in query


def test_build_disappearance_events_insert_query_uses_snapshot_delta() -> None:
    query = sql.build_disappearance_events_insert_query(
        league="Mirage", day=date(2026, 3, 20)
    )

    assert f"INSERT INTO {sql.EVENTS_TABLE}" in query
    assert "arrayExcept" in query
    assert "disappeared" in query


def test_build_sale_proxy_labels_insert_query_uses_event_table() -> None:
    query = sql.build_sale_proxy_labels_insert_query(
        league="Mirage", day=date(2026, 3, 20)
    )

    assert f"INSERT INTO {sql.SALE_LABELS_TABLE}" in query
    assert f"FROM {sql.EVENTS_TABLE}" in query
    assert "sold_probability" in query


def test_build_training_examples_insert_query_uses_observations_and_labels() -> None:
    query = sql.build_training_examples_insert_query(
        league="Mirage", day=date(2026, 3, 20)
    )

    assert f"INSERT INTO {sql.TRAINING_TABLE}" in query
    assert f"FROM {sql.OBSERVATIONS_TABLE} AS obs" in query
    assert f"LEFT JOIN {sql.SALE_LABELS_TABLE} AS labels" in query
    assert "target_fast_sale_24h_price" in query


def test_training_sql_emits_route_and_item_state_search_keys() -> None:
    query = sql.build_training_examples_insert_query(
        league="Mirage", day=date(2026, 3, 20)
    )

    assert "AS route" in query
    assert "AS item_state_key" in query
    assert "lowerUTF8(ifNull(obs.rarity, ''))" in query
    assert "'|corrupted=', toString(toUInt8(ifNull(obs.corrupted, 0) != 0))" in query
    assert "'|fractured=', toString(toUInt8(ifNull(obs.fractured, 0) != 0))" in query
    assert (
        "'|synthesised=', toString(toUInt8(ifNull(obs.synthesised, 0) != 0))" in query
    )


def test_retrieval_candidate_sql_can_partition_by_route_and_state() -> None:
    query = sql.build_retrieval_candidate_query(
        league="Mirage",
        route="sparse_retrieval",
        item_state_key="rare|corrupted=1|fractured=0|synthesised=0",
    )

    assert "PARTITION BY league, route, item_state_key" in query
    assert "route = 'sparse_retrieval'" in query
    assert "item_state_key = 'rare|corrupted=1|fractured=0|synthesised=0'" in query


def test_retrieval_candidate_sql_includes_identity_and_mod_payload() -> None:
    query = sql.build_retrieval_candidate_query(
        league="Mirage",
        route="sparse_retrieval",
        item_state_key="rare|corrupted=1|fractured=0|synthesised=0",
    )

    assert "identity_key," in query
    assert "mod_features_json" in query


def test_route_sql_fragment_delegates_to_routes_module() -> None:
    query = sql.build_training_examples_insert_query(
        league="Mirage", day=date(2026, 3, 20)
    )

    assert routes.route_sql_expression() in query


def test_sql_select_route_matches_routes_module() -> None:
    parsed = {"category": "cluster_jewel", "rarity": "Rare"}

    assert sql.select_route(parsed) == routes.select_route(parsed)
