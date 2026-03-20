from __future__ import annotations

from datetime import date

from poe_trade.ml.v3 import sql


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
