from types import SimpleNamespace

from poe_trade import cli


class _DummyClickHouseClient:
    def __init__(self, url: str):
        self.url = url
        self.queries = []

    @classmethod
    def from_env(cls, url: str):
        return cls(url)

    def execute(self, query: str) -> str:
        self.queries.append(query)
        return ""


def test_scan_once_command(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _ScannerModule:
        @staticmethod
        def run_scan_once(client, *, league, dry_run=False):
            calls.append((client.url, league, dry_run))
            return "scan-123"

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _ScannerModule if name == "poe_trade.strategy.scanner" else None,
    )

    result = cli.main(["scan", "once", "--league", "Mirage", "--dry-run"])

    assert result == 0
    assert calls == [("http://clickhouse", "Mirage", True)]
    assert capsys.readouterr().out.strip() == "scan-123"


def test_scan_watch_command(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _ScannerModule:
        @staticmethod
        def run_scan_watch(
            client, *, league, interval_seconds, max_runs=None, dry_run=False
        ):
            calls.append((client.url, league, interval_seconds, max_runs, dry_run))
            return ["scan-1", "scan-2"]

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _ScannerModule if name == "poe_trade.strategy.scanner" else None,
    )

    result = cli.main(
        [
            "scan",
            "watch",
            "--league",
            "Mirage",
            "--interval-seconds",
            "1.5",
            "--max-runs",
            "2",
            "--dry-run",
        ]
    )

    assert result == 0
    assert calls == [("http://clickhouse", "Mirage", 1.5, 2, True)]
    assert capsys.readouterr().out.strip().splitlines() == ["scan-1", "scan-2"]


def test_scan_plan_command(monkeypatch, capsys):
    calls = []
    clients = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )

    class _RecordingClient(_DummyClickHouseClient):
        @classmethod
        def from_env(cls, url: str):
            client = cls(url)
            clients.append(client)
            return client

        def execute(self, query: str) -> str:
            self.queries.append(query)
            return (
                '{"strategy_id":"bulk_essence","item_or_market_key":"abc123","why_it_fired":"spread","buy_plan":"buy bulk","max_buy":10.0,'
                '"transform_plan":"none","exit_plan":"sell","execution_venue":"manual_trade","expected_profit_chaos":20.0,'
                '"expected_roi":0.5,"expected_hold_time":"unknown","confidence":0.8,"evidence_snapshot":"{\\"item_name\\":\\"Deafening Essence of Greed\\"}"}'
            )

    monkeypatch.setattr(cli, "ClickHouseClient", _RecordingClient)

    class _ScannerModule:
        @staticmethod
        def run_scan_once(client, *, league, dry_run=False):
            calls.append((client.url, league, dry_run))
            return "scan-123"

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _ScannerModule if name == "poe_trade.strategy.scanner" else None,
    )

    result = cli.main(["scan", "plan", "--league", "Mirage", "--limit", "5"])

    assert result == 0
    assert calls == [("http://clickhouse", "Mirage", False)]
    output = capsys.readouterr().out.strip().splitlines()
    assert output[0] == "scan_id\tscan-123"
    assert output[1].startswith("strategy_id\tsearch_hint\t")
    assert output[2].startswith(
        "bulk_essence\tDeafening Essence of Greed\tabc123\tbuy bulk"
    )
    assert len(clients) == 1
    assert "scanner_recommendations" in clients[0].queries[0]
