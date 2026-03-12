import importlib


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
