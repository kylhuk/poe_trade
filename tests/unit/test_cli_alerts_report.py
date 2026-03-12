from types import SimpleNamespace

from poe_trade import cli


class _DummyClickHouseClient:
    def __init__(self, url: str):
        self.url = url

    @classmethod
    def from_env(cls, url: str):
        return cls(url)


def test_alerts_list_command(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _AlertsModule:
        @staticmethod
        def list_alerts(client):
            assert client.url == "http://clickhouse"
            return [
                {
                    "alert_id": "a1",
                    "strategy_id": "bulk_essence",
                    "league": "Mirage",
                    "status": "new",
                    "item_or_market_key": "essence-key",
                }
            ]

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _AlertsModule if name == "poe_trade.strategy.alerts" else None,
    )

    result = cli.main(["alerts", "list"])

    assert result == 0
    assert (
        capsys.readouterr().out.strip() == "a1\tbulk_essence\tMirage\tnew\tessence-key"
    )


def test_alerts_ack_command(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _AlertsModule:
        @staticmethod
        def ack_alert(client, *, alert_id):
            assert client.url == "http://clickhouse"
            return alert_id

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _AlertsModule if name == "poe_trade.strategy.alerts" else None,
    )

    result = cli.main(["alerts", "ack", "--id", "a1"])

    assert result == 0
    assert capsys.readouterr().out.strip() == "a1"


def test_report_daily_command(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    class _ReportsModule:
        @staticmethod
        def daily_report(client, *, league):
            assert client.url == "http://clickhouse"
            return {
                "league": league,
                "recommendations": 1,
                "alerts": 2,
                "journal_events": 3,
                "journal_positions": 1,
                "realized_pnl_chaos": 42.0,
            }

    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda name: _ReportsModule if name == "poe_trade.analytics.reports" else None,
    )

    result = cli.main(["report", "daily", "--league", "Mirage"])

    assert result == 0
    assert (
        capsys.readouterr().out.strip()
        == "{'league': 'Mirage', 'recommendations': 1, 'alerts': 2, 'journal_events': 3, 'journal_positions': 1, 'realized_pnl_chaos': 42.0}"
    )
