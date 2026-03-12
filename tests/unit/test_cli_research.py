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


def test_research_backtest_command(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _BacktestModule:
        BACKTEST_SUMMARY_HEADER = "run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary"

        @staticmethod
        def run_backtest(client, *, strategy_id, league, lookback_days, dry_run=False):
            calls.append((client.url, strategy_id, league, lookback_days, dry_run))
            return "run-123"

        @staticmethod
        def fetch_backtest_summary_rows(client, *, run_id):
            return [
                {
                    "run_id": run_id,
                    "strategy_id": "bulk_essence",
                    "league": "Mirage",
                    "lookback_days": 14,
                    "status": "completed",
                    "opportunity_count": 2,
                    "expected_profit_chaos": 12.5,
                    "expected_roi": 0.4,
                    "confidence": 0.8,
                    "summary": "opportunities found",
                }
            ]

        @staticmethod
        def format_summary_row(row):
            return "\t".join(
                str(row.get(k, ""))
                for k in (
                    "run_id",
                    "strategy_id",
                    "league",
                    "lookback_days",
                    "status",
                    "opportunity_count",
                    "expected_profit_chaos",
                    "expected_roi",
                    "confidence",
                    "summary",
                )
            )

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _BacktestModule if name == "poe_trade.strategy.backtest" else None,
    )

    result = cli.main(
        [
            "research",
            "backtest",
            "--strategy",
            "bulk_essence",
            "--league",
            "Mirage",
            "--days",
            "14",
            "--dry-run",
        ]
    )

    assert result == 0
    assert calls == [("http://clickhouse", "bulk_essence", "Mirage", 14, True)]
    assert capsys.readouterr().out.strip() == "run-123"


def test_research_backtest_all_command(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _Pack:
        def __init__(self, strategy_id, enabled):
            self.strategy_id = strategy_id
            self.enabled = enabled

    class _RegistryModule:
        @staticmethod
        def list_strategy_packs():
            return [_Pack("bulk_essence", True), _Pack("scarab_reroll", False)]

    class _BacktestModule:
        BACKTEST_SUMMARY_HEADER = "run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary"

        @staticmethod
        def run_backtest(client, *, strategy_id, league, lookback_days, dry_run=False):
            calls.append((client.url, strategy_id, league, lookback_days, dry_run))
            return f"run-{strategy_id}"

        @staticmethod
        def fetch_backtest_summary_rows(client, *, run_id):
            raise AssertionError("dry-run path must not fetch summaries")

        @staticmethod
        def backtest_status_rank(status):
            return 9

        @staticmethod
        def format_summary_row(row):
            return "\t".join(
                str(row.get(k, ""))
                for k in (
                    "run_id",
                    "strategy_id",
                    "league",
                    "lookback_days",
                    "status",
                    "opportunity_count",
                    "expected_profit_chaos",
                    "expected_roi",
                    "confidence",
                    "summary",
                )
            )

    def _import_module(name):
        if name == "poe_trade.strategy.registry":
            return _RegistryModule
        if name == "poe_trade.strategy.backtest":
            return _BacktestModule
        return None

    monkeypatch.setattr(cli.importlib, "import_module", _import_module)

    result = cli.main(
        [
            "research",
            "backtest-all",
            "--league",
            "Mirage",
            "--days",
            "14",
            "--enabled-only",
            "--dry-run",
        ]
    )

    assert result == 0
    assert calls == [("http://clickhouse", "bulk_essence", "Mirage", 14, True)]
    assert capsys.readouterr().out.strip().splitlines() == [
        "run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary",
        "run-bulk_essence\tbulk_essence\tMirage\t14\tdry_run\t\t\t\t\tdry run only",
    ]


def test_research_backtest_all_command_includes_summary_rows(monkeypatch, capsys):
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

    monkeypatch.setattr(cli, "ClickHouseClient", _RecordingClient)

    class _Pack:
        def __init__(self, strategy_id, enabled):
            self.strategy_id = strategy_id
            self.enabled = enabled

    class _RegistryModule:
        @staticmethod
        def list_strategy_packs():
            return [_Pack("bulk_essence", True)]

    class _BacktestModule:
        BACKTEST_SUMMARY_HEADER = "run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary"

        @staticmethod
        def run_backtest(client, *, strategy_id, league, lookback_days, dry_run=False):
            calls.append((client.url, strategy_id, league, lookback_days, dry_run))
            return "run-bulk_essence"

        @staticmethod
        def fetch_backtest_summary_rows(client, *, run_id):
            return [
                {
                    "run_id": run_id,
                    "strategy_id": "bulk_essence",
                    "league": "Mirage",
                    "lookback_days": 14,
                    "status": "completed",
                    "opportunity_count": 3,
                    "expected_profit_chaos": 9.5,
                    "expected_roi": 0.2,
                    "confidence": 0.75,
                    "summary": "opportunities found",
                }
            ]

        @staticmethod
        def backtest_status_rank(status):
            return 0 if status == "completed" else 9

        @staticmethod
        def format_summary_row(row):
            return "\t".join(
                str(row.get(k, ""))
                for k in (
                    "run_id",
                    "strategy_id",
                    "league",
                    "lookback_days",
                    "status",
                    "opportunity_count",
                    "expected_profit_chaos",
                    "expected_roi",
                    "confidence",
                    "summary",
                )
            )

    def _import_module(name):
        if name == "poe_trade.strategy.registry":
            return _RegistryModule
        if name == "poe_trade.strategy.backtest":
            return _BacktestModule
        return None

    monkeypatch.setattr(cli.importlib, "import_module", _import_module)

    result = cli.main(
        [
            "research",
            "backtest-all",
            "--league",
            "Mirage",
            "--days",
            "14",
            "--enabled-only",
        ]
    )

    assert result == 0
    assert calls == [("http://clickhouse", "bulk_essence", "Mirage", 14, False)]
    assert len(clients) == 1
    assert clients[0].queries == []
    assert capsys.readouterr().out.strip().splitlines() == [
        "run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary",
        "run-bulk_essence\tbulk_essence\tMirage\t14\tcompleted\t3\t9.5\t0.2\t0.75\topportunities found",
    ]
