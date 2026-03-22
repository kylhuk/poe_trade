import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from poe_trade import __version__
from poe_trade.config import constants
from poe_trade.db import ClickHouseClient, ClickHouseClientError
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


class _FallbackInsertClient(_RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self.v3_attempts = 0
        self.v2_attempts = 0

    def execute(self, query: str) -> str:
        if "INSERT INTO poe_trade.scanner_recommendations" in query:
            if "complexity_tier" in query:
                self.queries.append(query)
                self.v3_attempts += 1
                raise ClickHouseClientError("Unknown column complexity_tier")
            if "recommendation_source" in query:
                self.queries.append(query)
                self.v2_attempts += 1
                raise ClickHouseClientError("Unknown column recommendation_source")
        return super().execute(query)


class _FailingQueryClient(_RecordingClient):
    def __init__(self, marker: str, message: str) -> None:
        super().__init__()
        self.marker = marker
        self.message = message

    def execute(self, query: str) -> str:
        self.queries.append(query)
        if self.marker in query:
            raise ClickHouseClientError(self.message)
        return ""


class _DecisionCompatFailureClient(_RecordingClient):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def execute(self, query: str) -> str:
        self.queries.append(query)
        if "INSERT INTO poe_trade.scanner_candidate_decisions" in query:
            raise ClickHouseClientError(self.message)
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


def _pack(
    tmp_path: Path,
    *,
    strategy_id: str = "demo_strategy",
    requires_journal: bool = False,
    cooldown_minutes: int = 0,
) -> SimpleNamespace:
    candidate_sql = tmp_path / f"{strategy_id}.sql"
    _ = candidate_sql.write_text("SELECT 'candidate-marker'", encoding="utf-8")
    return SimpleNamespace(
        enabled=True,
        strategy_id=strategy_id,
        execution_venue="manual_trade",
        min_expected_profit_chaos=10.0,
        min_expected_roi=0.2,
        min_confidence=0.7,
        min_sample_count=15,
        cooldown_minutes=cooldown_minutes,
        requires_journal=requires_journal,
        candidate_sql_path=candidate_sql,
        backtest_sql_path=candidate_sql,
        discover_sql_path=candidate_sql,
    )


def _candidate_row(
    *,
    semantic_key: str = "sem:key:1",
    item_or_market_key: str = "legacy:key:1",
    expected_profit_chaos: float = 12.0,
    expected_roi: float = 0.25,
    confidence: float = 0.9,
    sample_count: int = 33,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "time_bucket": "2026-03-01 00:00:00",
        "league": "Mirage",
        "item_or_market_key": item_or_market_key,
        "semantic_key": semantic_key,
        "expected_profit_chaos": expected_profit_chaos,
        "expected_roi": expected_roi,
        "confidence": confidence,
        "sample_count": sample_count,
        "why_it_fired": "fired",
        "buy_plan": "buy",
        "exit_plan": "sell",
        "expected_hold_time": "30m",
        "source_row_json": json.dumps(
            {
                "item_or_market_key": item_or_market_key,
                "semantic_key": semantic_key,
            },
            separators=(",", ":"),
        ),
        "legacy_hashed_item_or_market_key": "legacy-hash",
    }
    if extra:
        row.update(extra)
    return row


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
    assert "cityHash64(formatRowNoNewline('JSONEachRow', source.*))" in query
    assert "historical_legacy_hashed_item_or_market_key" in query


def test_run_scan_once_records_recommendations_and_alerts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [_candidate_row()],
    )
    client = _RecordingClient()

    scan_id = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    assert len(scan_id) == 32
    assert any("scanner_candidate_decisions" in query for query in client.queries)
    assert any("scanner_recommendations" in query for query in client.queries)
    assert any("scanner_alert_log" in query for query in client.queries)
    assert any("demo_strategy" in query for query in client.queries)


def test_run_scan_once_isolates_pack_failures_and_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken_pack = _pack(tmp_path, strategy_id="broken_strategy")
    healthy_pack = _pack(tmp_path, strategy_id="healthy_strategy")

    def _rows_for_pack(*_args: object, **kwargs: object) -> list[dict[str, object]]:
        sql = str(kwargs.get("sql") or "")
        if "broken_strategy" in sql:
            raise ClickHouseClientError("broken pack source fetch failed")
        return [
            _candidate_row(
                semantic_key="sem:healthy:1", item_or_market_key="legacy:healthy:1"
            )
        ]

    monkeypatch.setattr(
        scanner, "list_strategy_packs", lambda: [broken_pack, healthy_pack]
    )
    monkeypatch.setattr(scanner, "load_candidate_sql", lambda pack: pack.strategy_id)
    monkeypatch.setattr(scanner, "_fetch_candidate_source_rows", _rows_for_pack)
    client = _RecordingClient()

    with caplog.at_level("ERROR"):
        scan_id = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert len(scan_id) == 32
    assert any("healthy_strategy" in query for query in client.queries)
    recommendation_query = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_recommendations" in query
    )
    recommendation_row = _extract_insert_rows(recommendation_query)[0]
    assert recommendation_row["strategy_id"] == "healthy_strategy"
    assert "broken_strategy" in caplog.text
    assert "scanner strategy pack failed: broken_strategy" in caplog.text


def test_run_scan_once_isolates_unexpected_pack_runtime_errors_and_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken_pack = _pack(tmp_path, strategy_id="broken_strategy")
    healthy_pack = _pack(tmp_path, strategy_id="healthy_strategy")

    def _rows_for_pack(*_args: object, **kwargs: object) -> list[dict[str, object]]:
        sql = str(kwargs.get("sql") or "")
        if "broken_strategy" in sql:
            raise RuntimeError("unexpected pack bug")
        return [
            _candidate_row(
                semantic_key="sem:healthy:1", item_or_market_key="legacy:healthy:1"
            )
        ]

    monkeypatch.setattr(
        scanner, "list_strategy_packs", lambda: [broken_pack, healthy_pack]
    )
    monkeypatch.setattr(scanner, "load_candidate_sql", lambda pack: pack.strategy_id)
    monkeypatch.setattr(scanner, "_fetch_candidate_source_rows", _rows_for_pack)
    client = _RecordingClient()

    with caplog.at_level("ERROR"):
        scan_id = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert len(scan_id) == 32
    recommendation_query = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_recommendations" in query
    )
    recommendation_row = _extract_insert_rows(recommendation_query)[0]
    assert recommendation_row["strategy_id"] == "healthy_strategy"
    assert "scanner strategy pack failed: broken_strategy" in caplog.text
    assert "unexpected pack bug" in caplog.text


def test_run_scan_once_dry_run_skips_clickhouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RecordingClient()
    monkeypatch.setattr(
        scanner, "list_strategy_packs", lambda: [SimpleNamespace(enabled=True)]
    )

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
                '"opportunity_type":"bulk_flip",'
                '"source_row_json":"{\\"item_or_market_key\\":\\"seed-key\\",\\"semantic_key\\":\\"seed-semantic\\"}",'
                '"legacy_hashed_item_or_market_key":"123456"}'
            )
        }
    )

    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    assert len(client.queries) == 5
    fetch_query = client.queries[0]
    cooldown_query = client.queries[1]
    decision_query = client.queries[2]
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
    assert (
        f"recommendation_contract_version = {constants.RECOMMENDATION_CONTRACT_VERSION}"
        in cooldown_query
    )
    assert "scanner_candidate_decisions" in decision_query

    recommendation_query = client.queries[3]
    assert "scanner_recommendations" in recommendation_query
    recommendation_row = _extract_insert_rows(recommendation_query)[0]
    assert recommendation_row["item_or_market_key"] == "seed-semantic"
    assert recommendation_row["why_it_fired"] == "fired"
    assert recommendation_row["buy_plan"] == "buy"
    assert recommendation_row["exit_plan"] == "exit"
    assert recommendation_row["expected_hold_time"] == "2h"
    assert recommendation_row["recommendation_source"] == "strategy_pack"
    assert (
        recommendation_row["recommendation_contract_version"]
        == constants.RECOMMENDATION_CONTRACT_VERSION
    )
    assert recommendation_row["producer_version"] == __version__
    assert recommendation_row["producer_run_id"] == recommendation_row["scanner_run_id"]
    assert recommendation_row["opportunity_type"] == "bulk_flip"
    assert "123456" in recommendation_query
    assert "source_row_json" in recommendation_query

    alert_query = client.queries[4]
    assert "scanner_alert_log" in alert_query
    alert_row = _extract_insert_rows(alert_query)[0]
    assert alert_row["alert_id"] == "demo_strategy|Mirage|seed-semantic"
    assert alert_row["recommendation_source"] == "strategy_pack"
    assert (
        alert_row["recommendation_contract_version"]
        == constants.RECOMMENDATION_CONTRACT_VERSION
    )
    assert alert_row["producer_version"] == __version__
    assert alert_row["producer_run_id"] == recommendation_row["scanner_run_id"]


def test_run_scan_once_preserves_explicit_recommendation_provenance_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate_sql = tmp_path / "candidate.sql"
    _ = candidate_sql.write_text(
        "SELECT 'provenance-marker'",
        encoding="utf-8",
    )
    discover_sql = tmp_path / "discover.sql"
    _ = discover_sql.write_text("SELECT 'discover-only-marker'", encoding="utf-8")
    pack = SimpleNamespace(
        enabled=True,
        strategy_id="ml_anomaly",
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
    row = {
        "time_bucket": "2026-03-01 00:00:00",
        "league": "Mirage",
        "item_or_market_key": "legacy:ml:1",
        "semantic_key": "sem:ml:1",
        "expected_profit_chaos": 12.0,
        "expected_roi": 0.25,
        "confidence": 0.9,
        "sample_count": 33,
        "why_it_fired": "model anomaly",
        "buy_plan": "buy",
        "exit_plan": "sell",
        "expected_hold_time": "30m",
        "recommendation_source": "ml_anomaly",
        "producer_version": "mirage-model-v2",
        "producer_run_id": "train-42",
        "source_row_json": '{"item_or_market_key":"legacy:ml:1","semantic_key":"sem:ml:1"}',
        "legacy_hashed_item_or_market_key": "legacy-hash",
    }
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [row],
    )
    client = _RecordingClient()

    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    recommendation_query = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_recommendations" in query
    )
    alert_query = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_alert_log" in query
    )
    recommendation_row = _extract_insert_rows(recommendation_query)[0]
    alert_row = _extract_insert_rows(alert_query)[0]

    assert recommendation_row["recommendation_source"] == "ml_anomaly"
    assert recommendation_row["producer_version"] == "mirage-model-v2"
    assert recommendation_row["producer_run_id"] == "train-42"
    assert (
        recommendation_row["recommendation_contract_version"]
        == constants.RECOMMENDATION_CONTRACT_VERSION
    )
    assert alert_row["recommendation_source"] == "ml_anomaly"
    assert alert_row["producer_version"] == "mirage-model-v2"
    assert alert_row["producer_run_id"] == "train-42"


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


def test_run_scan_once_journal_recommendations_with_historical_legacy_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pack = _pack(
        tmp_path,
        strategy_id="journal_only",
        requires_journal=True,
        cooldown_minutes=120,
    )
    row = _candidate_row(
        semantic_key="journal-semantic",
        item_or_market_key="journal-key",
        extra={
            "historical_legacy_hashed_item_or_market_key": "old-legacy-hash",
        },
    )
    client = _RecordingClient(
        responses={
            "journal_positions": '{"item_or_market_key":"old-legacy-hash"}',
        }
    )

    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [row],
    )

    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    assert any(
        "INSERT INTO poe_trade.scanner_recommendations" in query
        for query in client.queries
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


def test_run_scan_once_logs_invalid_source_rows_and_continues_pack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate_sql = tmp_path / "candidate.sql"
    _ = candidate_sql.write_text("SELECT 'invalid-row-marker'", encoding="utf-8")
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
        discover_sql_path=candidate_sql,
    )
    invalid_row = {
        "time_bucket": "2026-03-01 00:00:00",
        "league": "Mirage",
        "item_or_market_key": "missing-semantic",
    }
    valid_row = {
        "time_bucket": "2026-03-01 01:00:00",
        "league": "Mirage",
        "item_or_market_key": "legacy:valid:1",
        "semantic_key": "sem:valid:1",
        "expected_profit_chaos": 12.0,
        "expected_roi": 0.25,
        "confidence": 0.9,
        "sample_count": 33,
        "why_it_fired": "valid row",
        "buy_plan": "buy",
        "exit_plan": "sell",
        "expected_hold_time": "30m",
        "source_row_json": '{"item_or_market_key":"legacy:valid:1","semantic_key":"sem:valid:1"}',
        "legacy_hashed_item_or_market_key": "legacy-hash",
    }
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [invalid_row, valid_row],
    )
    client = _RecordingClient()

    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    decision_query = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_candidate_decisions" in query
    )
    decision_rows = _extract_insert_rows(decision_query)
    reasons = {str(row["decision_reason"]): row for row in decision_rows}
    assert "invalid_source_row" in reasons
    assert reasons["invalid_source_row"]["accepted"] == 0
    assert reasons["invalid_source_row"]["item_or_market_key"] == ""
    assert "missing semantic_key" in str(
        reasons["invalid_source_row"]["evidence_snapshot"]
    )

    recommendation_query = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_recommendations" in query
    )
    recommendation_row = _extract_insert_rows(recommendation_query)[0]
    assert recommendation_row["item_or_market_key"] == "sem:valid:1"


def test_recommendation_insert_falls_back_v3_to_v2_to_v1() -> None:
    client = _FallbackInsertClient()
    rows = [
        {
            "scanner_run_id": "scan-1",
            "strategy_id": "demo_strategy",
            "league": "Mirage",
            "recommendation_source": "strategy_pack",
            "recommendation_contract_version": constants.RECOMMENDATION_CONTRACT_VERSION,
            "producer_version": __version__,
            "producer_run_id": "scan-1",
            "item_or_market_key": "sem:key:1",
            "why_it_fired": "spread",
            "buy_plan": "buy",
            "max_buy": 10.0,
            "transform_plan": "",
            "exit_plan": "sell",
            "execution_venue": "manual_trade",
            "expected_profit_chaos": 12.0,
            "expected_roi": 0.25,
            "expected_hold_time": "30m",
            "confidence": 0.9,
            "complexity_tier": "simple",
            "required_capital_chaos": 50.0,
            "estimated_operations": 2,
            "estimated_whispers": 3,
            "expected_profit_per_operation_chaos": 6.0,
            "feasibility_score": 0.8,
            "evidence_snapshot": "{}",
            "recorded_at": "2026-03-01 00:00:00.000",
        }
    ]

    scanner._insert_json_rows(
        _clickhouse_client(client),
        table="poe_trade.scanner_recommendations",
        rows=rows,
        columns=scanner._RECOMMENDATION_INSERT_COLUMNS,
        fallback_columns=scanner._LEGACY_RECOMMENDATION_INSERT_COLUMNS,
    )

    recommendation_queries = [
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_recommendations" in query
    ]
    assert len(recommendation_queries) == 3
    assert "complexity_tier" in recommendation_queries[0]
    assert "recommendation_source" in recommendation_queries[1]
    assert "recommendation_source" not in recommendation_queries[2]
    assert "complexity_tier" not in recommendation_queries[2]


def test_run_scan_once_emits_decision_rows_for_acceptance_and_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate_sql = tmp_path / "candidate.sql"
    _ = candidate_sql.write_text("SELECT 'decision-row-marker'", encoding="utf-8")
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
        discover_sql_path=candidate_sql,
    )
    accepted_row = {
        "time_bucket": "2026-03-01 00:00:00",
        "league": "Mirage",
        "item_or_market_key": "legacy:accepted:1",
        "semantic_key": "sem:accepted:1",
        "expected_profit_chaos": 12.0,
        "expected_roi": 0.25,
        "confidence": 0.9,
        "sample_count": 33,
        "estimated_operations": 2,
        "estimated_whispers": 3,
        "expected_profit_per_operation_chaos": 6.0,
        "feasibility_score": 0.8,
        "why_it_fired": "keep",
        "buy_plan": "buy",
        "exit_plan": "sell",
        "expected_hold_time": "30m",
        "source_row_json": '{"item_or_market_key":"legacy:accepted:1","semantic_key":"sem:accepted:1"}',
        "legacy_hashed_item_or_market_key": "legacy-hash-1",
    }
    rejected_row = {
        **accepted_row,
        "item_or_market_key": "legacy:rejected:1",
        "semantic_key": "sem:rejected:1",
        "expected_profit_chaos": 5.0,
        "source_row_json": '{"item_or_market_key":"legacy:rejected:1","semantic_key":"sem:rejected:1"}',
        "legacy_hashed_item_or_market_key": "legacy-hash-2",
    }
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [accepted_row, rejected_row],
    )
    client = _RecordingClient()

    _ = scanner.run_scan_once(
        _clickhouse_client(client), league="Mirage", dry_run=False
    )

    decision_query = next(
        query
        for query in client.queries
        if "INSERT INTO poe_trade.scanner_candidate_decisions" in query
    )
    decision_rows = _extract_insert_rows(decision_query)
    rows_by_key = {str(row["item_or_market_key"]): row for row in decision_rows}

    assert rows_by_key["sem:accepted:1"]["accepted"] == 1
    assert rows_by_key["sem:accepted:1"]["decision_reason"] == "accepted"
    assert rows_by_key["sem:accepted:1"]["estimated_operations"] == 2
    assert rows_by_key["sem:accepted:1"]["feasibility_score"] == 0.8
    assert rows_by_key["sem:rejected:1"]["accepted"] == 0
    assert (
        rows_by_key["sem:rejected:1"]["decision_reason"]
        == "below_min_expected_profit_chaos"
    )


def test_run_scan_once_skips_decision_insert_on_missing_table_compat_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [_candidate_row()],
    )
    client = _DecisionCompatFailureClient(
        "Table poe_trade.scanner_candidate_decisions doesn't exist"
    )

    with caplog.at_level("WARNING"):
        _ = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert any(
        "INSERT INTO poe_trade.scanner_recommendations" in query
        for query in client.queries
    )
    assert any(
        "INSERT INTO poe_trade.scanner_alert_log" in query for query in client.queries
    )
    assert "decision logging skipped due to schema compatibility" in caplog.text


def test_run_scan_once_skips_decision_insert_on_unqualified_missing_table_compat_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [_candidate_row()],
    )
    client = _DecisionCompatFailureClient(
        "Table scanner_candidate_decisions doesn't exist"
    )

    with caplog.at_level("WARNING"):
        _ = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert any(
        "INSERT INTO poe_trade.scanner_recommendations" in query
        for query in client.queries
    )
    assert any(
        "INSERT INTO poe_trade.scanner_alert_log" in query for query in client.queries
    )
    assert "decision logging skipped due to schema compatibility" in caplog.text


def test_run_scan_once_skips_decision_insert_on_known_missing_column_compat_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [_candidate_row()],
    )
    client = _DecisionCompatFailureClient(
        "Unknown column decision_reason in table poe_trade.scanner_candidate_decisions"
    )

    with caplog.at_level("WARNING"):
        _ = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert any(
        "INSERT INTO poe_trade.scanner_recommendations" in query
        for query in client.queries
    )
    assert any(
        "INSERT INTO poe_trade.scanner_alert_log" in query for query in client.queries
    )
    assert "scanner_candidate_decisions" in caplog.text


def test_run_scan_once_logs_on_candidate_payload_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    client = _RecordingClient(responses={"candidate-marker": "{not-json"})

    with caplog.at_level("ERROR"):
        scan_id = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert len(scan_id) == 32
    assert "scanner strategy pack failed: demo_strategy" in caplog.text
    assert "demo_strategy" in caplog.text


def test_run_scan_once_logs_on_failed_clickhouse_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [_candidate_row()],
    )
    client = _FailingQueryClient(
        "INSERT INTO poe_trade.scanner_candidate_decisions",
        "insert failed",
    )

    with caplog.at_level("ERROR"):
        scan_id = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert len(scan_id) == 32
    assert "scanner strategy pack failed: demo_strategy" in caplog.text
    assert "insert failed" in caplog.text


def test_execute_with_legacy_fallback_only_handles_known_missing_column_errors() -> (
    None
):
    client = _FailingQueryClient(
        "SELECT v3",
        "Missing data while processing column stats",
    )

    with pytest.raises(ClickHouseClientError, match="Missing data while processing"):
        _ = scanner._execute_with_legacy_fallback(
            _clickhouse_client(client),
            "SELECT v3",
            "SELECT legacy",
        )

    assert client.queries == ["SELECT v3"]


def test_execute_with_legacy_fallback_ignores_unknown_unrelated_columns() -> None:
    client = _FailingQueryClient(
        "SELECT v3",
        "Unknown column some_other_column in table foo",
    )

    with pytest.raises(ClickHouseClientError, match="some_other_column"):
        _ = scanner._execute_with_legacy_fallback(
            _clickhouse_client(client),
            "SELECT v3",
            "SELECT legacy",
        )

    assert client.queries == ["SELECT v3"]


def test_execute_with_legacy_fallback_only_for_known_metadata_columns() -> None:
    client = _FailingQueryClient(
        "SELECT v3",
        "Unknown column recommendation_contract_version in table scanner_alert_log",
    )

    _ = scanner._execute_with_legacy_fallback(
        _clickhouse_client(client),
        "SELECT v3",
        "SELECT legacy",
    )

    assert client.queries == ["SELECT v3", "SELECT legacy"]


def test_execute_with_legacy_fallback_handles_quoted_missing_columns_error() -> None:
    client = _FailingQueryClient(
        "SELECT v3",
        "Missing columns: 'recommendation_source', 'producer_version' while processing query",
    )

    _ = scanner._execute_with_legacy_fallback(
        _clickhouse_client(client),
        "SELECT v3",
        "SELECT legacy",
    )

    assert client.queries == ["SELECT v3", "SELECT legacy"]


def test_run_scan_once_skips_decision_insert_on_quoted_missing_columns_compat_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pack = _pack(tmp_path)
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])
    monkeypatch.setattr(
        scanner,
        "_fetch_candidate_source_rows",
        lambda *_args, **_kwargs: [_candidate_row()],
    )
    client = _DecisionCompatFailureClient(
        "Missing columns: 'decision_reason', 'estimated_operations' while processing query"
    )

    with caplog.at_level("WARNING"):
        _ = scanner.run_scan_once(
            _clickhouse_client(client), league="Mirage", dry_run=False
        )

    assert any(
        "INSERT INTO poe_trade.scanner_recommendations" in query
        for query in client.queries
    )
    assert any(
        "INSERT INTO poe_trade.scanner_alert_log" in query for query in client.queries
    )
    assert "decision logging skipped due to schema compatibility" in caplog.text


def test_direct_and_light_transform_candidate_sql_emit_richer_evidence_columns() -> (
    None
):
    sql_root = Path(scanner.__file__).resolve().parents[1] / "sql" / "strategy"
    required_aliases = (
        "AS ESTIMATED_OPERATIONS",
        "AS ESTIMATED_WHISPERS",
        "AS LIQUIDITY_SCORE",
        "AS STALENESS_MINUTES",
    )

    for strategy_id in (
        "bulk_essence",
        "bulk_fossils",
        "fossil_scarcity",
        "fragment_sets",
        "cx_market_making",
        "dump_tab_reprice",
        "map_logbook_packages",
        "scarab_reroll",
    ):
        sql = (sql_root / strategy_id / "candidate.sql").read_text(encoding="utf-8")
        upper_sql = sql.upper()
        for alias in required_aliases:
            assert alias in upper_sql
