import importlib
from types import SimpleNamespace


class _RecordingClient:
    def __init__(self):
        self.queries = []

    def execute(self, query: str) -> str:
        self.queries.append(query)
        return ""


def test_run_scan_once_records_recommendations_and_alerts() -> None:
    scanner = importlib.import_module("poe_trade.strategy.scanner")
    registry = importlib.import_module("poe_trade.strategy.registry")
    client = _RecordingClient()

    scan_id = scanner.run_scan_once(client, league="Mirage", dry_run=False)

    assert len(scan_id) == 32
    enabled_count = len(
        [pack for pack in registry.list_strategy_packs() if pack.enabled]
    )
    assert len(client.queries) == enabled_count * 2
    assert "scanner_recommendations" in client.queries[0]
    assert "scanner_alert_log" in client.queries[1]
    assert "bulk_essence" in client.queries[0]


def test_run_scan_once_dry_run_skips_clickhouse() -> None:
    scanner = importlib.import_module("poe_trade.strategy.scanner")
    client = _RecordingClient()

    scan_id = scanner.run_scan_once(client, league="Mirage", dry_run=True)

    assert len(scan_id) == 32
    assert client.queries == []


def test_run_scan_watch_runs_multiple_cycles(monkeypatch) -> None:
    scanner = importlib.import_module("poe_trade.strategy.scanner")
    calls = []

    def _fake_once(client, *, league, dry_run=False):
        calls.append((league, dry_run))
        return f"scan-{len(calls)}"

    monkeypatch.setattr(scanner, "run_scan_once", _fake_once)
    monkeypatch.setattr(scanner.time, "sleep", lambda _seconds: None)

    run_ids = scanner.run_scan_watch(
        _RecordingClient(),
        league="Mirage",
        interval_seconds=0.1,
        max_runs=3,
        dry_run=True,
    )

    assert run_ids == ["scan-1", "scan-2", "scan-3"]
    assert calls == [("Mirage", True), ("Mirage", True), ("Mirage", True)]


def test_run_scan_once_preserves_source_recommendation_fields_with_fallbacks(
    monkeypatch, tmp_path
) -> None:
    scanner = importlib.import_module("poe_trade.strategy.scanner")
    client = _RecordingClient()
    discover_sql = tmp_path / "discover.sql"
    discover_sql.write_text("SELECT 1", encoding="utf-8")
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
        discover_sql_path=discover_sql,
    )
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])

    scanner.run_scan_once(client, league="Mirage", dry_run=False)

    assert len(client.queries) == 2
    insert_query = client.queries[0]
    assert (
        "WITH formatRowNoNewline('JSONEachRow', source.*) AS source_row_json"
        in insert_query
    )
    assert "if(JSONHas(source_row_json, 'why_it_fired')" in insert_query
    assert "'discovered by demo_strategy') AS why_it_fired" in insert_query
    assert "if(JSONHas(source_row_json, 'buy_plan')" in insert_query
    assert "'buy candidate') AS buy_plan" in insert_query
    assert "if(JSONHas(source_row_json, 'max_buy')" in insert_query
    assert "if(JSONHas(source_row_json, 'transform_plan')" in insert_query
    assert "if(JSONHas(source_row_json, 'exit_plan')" in insert_query
    assert "'review and sell') AS exit_plan" in insert_query
    assert "if(JSONHas(source_row_json, 'expected_profit_chaos')" in insert_query
    assert "if(JSONHas(source_row_json, 'expected_roi')" in insert_query
    assert "if(JSONHas(source_row_json, 'expected_hold_time')" in insert_query
    assert "'unknown') AS expected_hold_time" in insert_query
    assert "if(JSONHas(source_row_json, 'confidence')" in insert_query
    assert "source_row_json AS evidence_snapshot" in insert_query
    assert (
        "coalesce(JSONExtract(source_row_json, 'Nullable(Float64)', 'expected_profit_chaos')"
        in insert_query
    )
    assert (
        "coalesce(JSONExtract(source_row_json, 'Nullable(Float64)', 'expected_roi')"
        in insert_query
    )
    assert (
        "coalesce(JSONExtract(source_row_json, 'Nullable(Float64)', 'confidence')"
        in insert_query
    )
    assert (
        "JSONExtract(source_row_json, 'Nullable(Int64)', 'sample_count')"
        in insert_query
    )

    alert_query = client.queries[1]
    assert (
        "concat(strategy_id, '|', league, '|', item_or_market_key) AS alert_id"
        in alert_query
    )
    assert "LEFT JOIN (" in alert_query
    assert (
        "dateDiff('minute', previous.last_recorded_at, candidate.recorded_at) >= 180"
        in alert_query
    )


def test_run_scan_once_skips_journal_only_strategies(monkeypatch, tmp_path) -> None:
    scanner = importlib.import_module("poe_trade.strategy.scanner")
    client = _RecordingClient()
    discover_sql = tmp_path / "discover.sql"
    discover_sql.write_text("SELECT 1", encoding="utf-8")
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
        discover_sql_path=discover_sql,
    )
    monkeypatch.setattr(scanner, "list_strategy_packs", lambda: [pack])

    scan_id = scanner.run_scan_once(client, league="Mirage", dry_run=False)

    assert len(scan_id) == 32
    assert client.queries == []
