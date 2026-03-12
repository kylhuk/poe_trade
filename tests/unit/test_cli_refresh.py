from pathlib import Path
from types import SimpleNamespace

from poe_trade import cli


class _DummyClickHouseClient:
    def __init__(self, url: str):
        self.url = url

    @classmethod
    def from_env(cls, url: str):
        return cls(url)


def test_refresh_gold_refs_dry_run(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    def _fake_execute(client, *, layer, group=None, dry_run=False):
        calls.append((client.url, layer, group, dry_run))
        return [
            Path("/tmp/100_currency_ref_hour.sql"),
            Path("/tmp/110_listing_ref_hour.sql"),
        ]

    monkeypatch.setattr(cli, "execute_refresh_group", _fake_execute)

    result = cli.main(["refresh", "gold", "--group", "refs", "--dry-run"])

    assert result == 0
    assert calls == [("http://clickhouse", "gold", "refs", True)]
    output = capsys.readouterr().out
    assert "/tmp/100_currency_ref_hour.sql" in output
    assert "/tmp/110_listing_ref_hour.sql" in output


def test_refresh_silver_without_group(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    def _fake_execute(client, *, layer, group=None, dry_run=False):
        calls.append((client.url, layer, group, dry_run))
        return []

    monkeypatch.setattr(cli, "execute_refresh_group", _fake_execute)

    result = cli.main(["refresh", "silver"])

    assert result == 0
    assert calls == [("http://clickhouse", "silver", None, False)]
    assert capsys.readouterr().out == ""
