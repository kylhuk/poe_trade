from types import SimpleNamespace

from poe_trade import cli


class _DummyClickHouseClient:
    def __init__(self, url: str):
        self.url = url

    @classmethod
    def from_env(cls, url: str):
        return cls(url)


def test_journal_buy_command(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _JournalModule:
        @staticmethod
        def record_trade_event(client, **kwargs):
            calls.append((client.url, kwargs))
            return "event-123"

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _JournalModule if name == "poe_trade.strategy.journal" else None,
    )

    result = cli.main(
        [
            "journal",
            "buy",
            "--strategy",
            "bulk_essence",
            "--league",
            "Mirage",
            "--item-or-market-key",
            "essence-key",
            "--price-chaos",
            "100",
            "--quantity",
            "20",
            "--notes",
            "entry",
            "--dry-run",
        ]
    )

    assert result == 0
    assert calls == [
        (
            "http://clickhouse",
            {
                "action": "buy",
                "strategy_id": "bulk_essence",
                "league": "Mirage",
                "item_or_market_key": "essence-key",
                "price_chaos": 100.0,
                "quantity": 20.0,
                "notes": "entry",
                "dry_run": True,
            },
        )
    ]
    assert capsys.readouterr().out.strip() == "event-123"
