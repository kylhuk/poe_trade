import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from poe_trade.db import ClickHouseClient
import poe_trade.strategy.registry as registry
import poe_trade.strategy.scanner as scanner


class _RecordingClient:
    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.queries: list[str] = []
        self.responses: dict[str, str] = responses or {}

    def execute(self, query: str) -> str:
        self.queries.append(query)
        for marker, payload in self.responses.items():
            if marker in query:
                return payload
        return ""


def _clickhouse_client(client: _RecordingClient) -> ClickHouseClient:
    return cast(ClickHouseClient, cast(object, client))


def _extract_insert_rows(query: str) -> list[dict[str, object]]:
    marker = "FORMAT JSONEachRow\n"
    assert marker in query
    payload = query.split(marker, maxsplit=1)[1]
    rows: list[dict[str, object]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        parsed = cast(object, json.loads(line))
        assert isinstance(parsed, dict)
        rows.append(cast(dict[str, object], parsed))
    return rows


def test_fetch_candidate_source_rows_uses_stable_compat_hash() -> None:
    client = _RecordingClient()
    _ = scanner._fetch_candidate_source_rows(
        _clickhouse_client(client),
        sql="SELECT '1' AS semantic_key, 'legacy' AS item_or_market_key",
    )
    query = client.queries[0]
    assert (
        "cityHash64(concat(ifNull(source.semantic_key, ''), '|', ifNull(source.item_or_market_key, '')))"
        in query
    )
    assert "cityHash64(formatRowNoNewline('JSONEachRow', source.*))" not in query


def test_candidate_sql_contracts_provide_direct_columns() -> None:
    required_aliases = (
        "AS TIME_BUCKET",
        "AS LEAGUE",
        "AS ITEM_OR_MARKET_KEY",
        "AS EXPECTED_PROFIT_CHAOS",
        "AS EXPECTED_ROI",
        "AS CONFIDENCE",
        "AS SAMPLE_COUNT",
        "AS WHY_IT_FIRED",
        "AS BUY_PLAN",
        "AS EXIT_PLAN",
        "AS EXPECTED_HOLD_TIME",
    )
    fallback_terms = (
        "bulk_listing_count",
        "listing_count",
        "small_listing_count",
        "observed_samples",
    )

    for pack in registry.list_strategy_packs():
        if not pack.candidate_sql_path.exists():
            continue
        sql = pack.candidate_sql_path.read_text(encoding="utf-8")
        upper_sql = sql.upper()
        for alias in required_aliases:
            assert alias in upper_sql
        assert any(term in sql for term in fallback_terms)


def test_run_scan_once_records_recommendations_and_alerts() -> None:
    client = _RecordingClient()

    scan_id = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    assert len(scan_id) == 32
    assert any("cityHash64" in query for query in client.queries)
    assert any("scanner_alert_log" in query for query in client.queries)
    assert any("bulk_essence" in query for query in client.queries)


def test_run_scan_once_dry_run_skips_clickhouse() -> None:
    client = _RecordingClient()

    scan_id = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=True
    )

    assert len(scan_id) == 32
    assert client.queries == []


def test_run_scan_watch_runs_multiple_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    def _fake_once(client: object, *, league: str, dry_run: bool = False) -> str:
        _ = client
        calls.append((league, dry_run))
        return f"scan-{len(calls)}"

    def _skip_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(scanner, "run_scan_once", _fake_once)
    monkeypatch.setattr("poe_trade.strategy.scanner.time.sleep", _skip_sleep)

    run_ids = scanner.run_scan_watch(
        _clickhouse_client(_RecordingClient()),
        league="Mirage",
        interval_seconds=0.1,
        max_runs=3,
        dry_run=True,
    )

    assert run_ids == ["scan-1", "scan-2", "scan-3"]
    assert calls == [("Mirage", True), ("Mirage", True), ("Mirage", True)]


def test_run_scan_once_preserves_source_recommendation_fields_with_fallbacks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate_sql = tmp_path / "candidate.sql"
    _ = candidate_sql.write_text(
        "SELECT now() AS time_bucket, 'Mirage' AS league, 'seed-key' AS item_or_market_key, "
        + "'seed-semantic' AS semantic_key, "
        + "12.0 AS expected_profit_chaos, 0.25 AS expected_roi, 0.9 AS confidence, 33 AS sample_count, "
        + "'fired' AS why_it_fired, 'buy' AS buy_plan, 'exit' AS exit_plan, '2h' AS expected_hold_time",
        encoding="utf-8",
    )
    discover_sql = tmp_path / "discover.sql"
    _ = discover_sql.write_text("SELECT 'discover-only-marker'", encoding="utf-8")
    pack = SimpleNamespace(
        enabled=True,
        strategy_id="demo_strategy",
        execution_venue="manual_trade",
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.2,
        min_confidence=0.7,
        min_sample_count=15,
        cooldown_minutes=180,
        requires_journal=False,
        candidate_sql_path=candidate_sql,
        backtest_sql_path=candidate_sql,
        discover_sql_path=discover_sql,
    )
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    client = _RecordingClient(
        responses={
            "seed-key": (
                '{"time_bucket":"2026-03-01 00:00:00","league":"Mirage","item_or_market_key":"seed-key",'
                '"semantic_key":"seed-semantic","expected_profit_chaos":12.0,"expected_roi":0.25,"confidence":0.9,"sample_count":33,'
                '"why_it_fired":"fired","buy_plan":"buy","exit_plan":"exit","expected_hold_time":"2h",'
                '"source_row_json":"{\\"item_or_market_key\\":\\"seed-key\\",\\"semantic_key\\":\\"seed-semantic\\"}",'
                '"legacy_hashed_item_or_market_key":"123456"}'
            )
        }
    )

    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    assert len(client.queries) == 4
    fetch_query = client.queries[0]
    assert "discover-only-marker" not in fetch_query
    assert "seed-semantic" in fetch_query
    assert "semantic_key" in fetch_query
    assert (
        "formatRowNoNewline('JSONEachRow', source.*) AS source_row_json" in fetch_query
    )
    assert (
        "cityHash64(concat(ifNull(source.semantic_key, ''), '|', ifNull(source.item_or_market_key, '')))"
        in fetch_query
    )

    recommendation_query = client.queries[2]
    assert "scanner_recommendations" in recommendation_query
    assert '"item_or_market_key":"seed-semantic"' in recommendation_query
    assert '"why_it_fired":"fired"' in recommendation_query
    assert '"buy_plan":"buy"' in recommendation_query
    assert '"exit_plan":"exit"' in recommendation_query
    assert '"expected_hold_time":"2h"' in recommendation_query
    assert "123456" in recommendation_query
    assert "source_row_json" in recommendation_query

    alert_query = client.queries[3]
    assert "scanner_alert_log" in alert_query
    assert '"alert_id":"demo_strategy|Mirage|seed-semantic"' in alert_query


def test_run_scan_once_journal_blocks_without_active_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate_sql = tmp_path / "candidate.sql"
    _ = candidate_sql.write_text(
        "SELECT now() AS time_bucket, 'Mirage' AS league, 'journal-key' AS item_or_market_key, "
        + "'journal-semantic' AS semantic_key, "
        + "12.0 AS expected_profit_chaos, 0.25 AS expected_roi, 0.9 AS confidence, 33 AS sample_count, "
        + "'fired' AS why_it_fired, 'join' AS buy_plan, 'exit' AS exit_plan, '2h' AS expected_hold_time",
        encoding="utf-8",
    )
    discover_sql = tmp_path / "discover.sql"
    _ = discover_sql.write_text("SELECT 'discover-only-marker'", encoding="utf-8")
    pack = SimpleNamespace(
        enabled=True,
        strategy_id="journal_only",
        execution_venue="manual_trade",
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.2,
        min_confidence=0.7,
        min_sample_count=15,
        cooldown_minutes=120,
        requires_journal=True,
        candidate_sql_path=candidate_sql,
        backtest_sql_path=candidate_sql,
        discover_sql_path=discover_sql,
    )
    candidate_response = (
        '{"time_bucket":"2026-03-01 00:00:00","league":"Mirage","item_or_market_key":"journal-key",'
        '"semantic_key":"journal-semantic","expected_profit_chaos":12.0,"expected_roi":0.25,"confidence":0.9,"sample_count":33,'
        '"why_it_fired":"fired","buy_plan":"join","exit_plan":"exit","expected_hold_time":"2h",'
        '"source_row_json":"{\\"item_or_market_key\\":\\"journal-key\\",\\"semantic_key\\":\\"journal-semantic\\"}",'
        '"legacy_hashed_item_or_market_key":"legacy-hash"}'
    )
    client = _RecordingClient(responses={"journal-key": candidate_response})

    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])

    scan_id = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    assert len(scan_id) == 32
    assert any("journal_positions" in query for query in client.queries)
    assert not any(
        "INSERT INTO poe_trade.scanner_recommendations" in query
        for query in client.queries
    )
    assert not any(
        "INSERT INTO poe_trade.scanner_alert_log" in query for query in client.queries
    )


def test_run_scan_once_journal_recommendations_with_active_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate_sql = tmp_path / "candidate.sql"
    _ = candidate_sql.write_text(
        "SELECT now() AS time_bucket, 'Mirage' AS league, 'journal-key' AS item_or_market_key, "
        + "'journal-semantic' AS semantic_key, "
        + "12.0 AS expected_profit_chaos, 0.25 AS expected_roi, 0.9 AS confidence, 33 AS sample_count, "
        + "'fired' AS why_it_fired, 'join' AS buy_plan, 'exit' AS exit_plan, '2h' AS expected_hold_time",
        encoding="utf-8",
    )
    discover_sql = tmp_path / "discover.sql"
    _ = discover_sql.write_text("SELECT 'discover-only-marker'", encoding="utf-8")
    pack = SimpleNamespace(
        enabled=True,
        strategy_id="journal_only",
        execution_venue="manual_trade",
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.2,
        min_confidence=0.7,
        min_sample_count=15,
        cooldown_minutes=120,
        requires_journal=True,
        candidate_sql_path=candidate_sql,
        backtest_sql_path=candidate_sql,
        discover_sql_path=discover_sql,
    )
    candidate_response = (
        '{"time_bucket":"2026-03-01 00:00:00","league":"Mirage","item_or_market_key":"journal-key",'
        '"semantic_key":"journal-semantic","expected_profit_chaos":12.0,"expected_roi":0.25,"confidence":0.9,"sample_count":33,'
        '"why_it_fired":"fired","buy_plan":"join","exit_plan":"exit","expected_hold_time":"2h",'
        '"source_row_json":"{\\"item_or_market_key\\":\\"journal-key\\",\\"semantic_key\\":\\"journal-semantic\\"}",'
        '"legacy_hashed_item_or_market_key":"legacy-hash"}'
    )
    client = _RecordingClient(
        responses={
            "journal-key": candidate_response,
            "journal_positions": '{"item_or_market_key":"journal-key"}',
        }
    )

    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])

    scan_id = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    assert len(scan_id) == 32
    assert any("journal_positions" in query for query in client.queries)
    assert any(
        "INSERT INTO poe_trade.scanner_recommendations" in query
        for query in client.queries
    )
    assert any(
        "INSERT INTO poe_trade.scanner_alert_log" in query for query in client.queries
    )


def test_run_scan_once_reuses_semantic_alert_ids_for_metadata_only_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate_sql = tmp_path / "candidate.sql"
    _ = candidate_sql.write_text("SELECT 'semantic-scan-marker'", encoding="utf-8")
    discover_sql = tmp_path / "discover.sql"
    _ = discover_sql.write_text("SELECT 'discover-only-marker'", encoding="utf-8")
    pack = SimpleNamespace(
        enabled=True,
        strategy_id="demo_strategy",
        execution_venue="manual_trade",
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.2,
        min_confidence=0.7,
        min_sample_count=15,
        cooldown_minutes=0,
        requires_journal=False,
        candidate_sql_path=candidate_sql,
        backtest_sql_path=candidate_sql,
        discover_sql_path=discover_sql,
    )
    first_row = {
        "time_bucket": "2026-03-01 00:00:00",
        "updated_at": "2026-03-01 00:05:00",
        "league": "Mirage",
        "item_or_market_key": "legacy:essence:bulk",
        "semantic_key": "sem:essence:bulk",
        "expected_profit_chaos": 12.0,
        "expected_roi": 0.25,
        "confidence": 0.9,
        "sample_count": 33,
        "why_it_fired": "fired",
        "buy_plan": "buy",
        "exit_plan": "exit",
        "expected_hold_time": "2h",
        "source_row_json": '{"time_bucket":"2026-03-01 00:00:00","updated_at":"2026-03-01 00:05:00","item_or_market_key":"legacy:essence:bulk","semantic_key":"sem:essence:bulk"}',
        "legacy_hashed_item_or_market_key": "legacy-hash-1",
    }
    second_row = {
        **first_row,
        "time_bucket": "2026-03-01 01:00:00",
        "updated_at": "2026-03-01 01:05:00",
        "source_row_json": '{"time_bucket":"2026-03-01 01:00:00","updated_at":"2026-03-01 01:05:00","item_or_market_key":"legacy:essence:bulk","semantic_key":"sem:essence:bulk"}',
        "legacy_hashed_item_or_market_key": "legacy-hash-2",
    }
    rows_by_scan = [[first_row], [second_row]]
    client = _RecordingClient()

    def _fake_fetch_candidate_source_rows(
        *_args: object, **_kwargs: object
    ) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], rows_by_scan.pop(0))

    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner, "_fetch_candidate_source_rows", _fake_fetch_candidate_source_rows
    )

    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )
    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    recommendation_queries = [
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_recommendations" in query
    ]
    alert_queries = [
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_alert_log" in query
    ]

    assert len(recommendation_queries) == 2
    assert len(alert_queries) == 2

    first_recommendation = _extract_insert_rows(recommendation_queries[0])[0]
    second_recommendation = _extract_insert_rows(recommendation_queries[1])[0]
    assert first_recommendation["item_or_market_key"] == "sem:essence:bulk"
    assert second_recommendation["item_or_market_key"] == "sem:essence:bulk"

    first_evidence = cast(
        object, json.loads(str(first_recommendation["evidence_snapshot"]))
    )
    second_evidence = cast(
        object, json.loads(str(second_recommendation["evidence_snapshot"]))
    )
    assert isinstance(first_evidence, dict)
    assert isinstance(second_evidence, dict)
    assert first_evidence["item_or_market_key"] == "sem:essence:bulk"
    assert second_evidence["item_or_market_key"] == "sem:essence:bulk"
    assert first_evidence["source_row_json"] != second_evidence["source_row_json"]
    assert (
        first_evidence["legacy_hashed_item_or_market_key"]
        != second_evidence["legacy_hashed_item_or_market_key"]
    )

    first_alert = _extract_insert_rows(alert_queries[0])[0]
    second_alert = _extract_insert_rows(alert_queries[1])[0]
    assert first_alert["alert_id"] == "demo_strategy|Mirage|sem:essence:bulk"
    assert second_alert["alert_id"] == "demo_strategy|Mirage|sem:essence:bulk"
