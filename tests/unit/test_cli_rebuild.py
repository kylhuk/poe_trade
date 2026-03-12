from pathlib import Path
from types import SimpleNamespace

from poe_trade import cli


class _DummyClickHouseClient:
    def __init__(self, url: str):
        self.url = url

    @classmethod
    def from_env(cls, url: str):
        return cls(url)


def test_rebuild_gold_all_dry_run(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    def _fake_execute(client, *, layer, group=None, dry_run=False):
        calls.append((client.url, layer, group, dry_run))
        return [Path("/tmp/gold.sql")]

    monkeypatch.setattr(cli, "execute_refresh_group", _fake_execute)

    result = cli.main(["rebuild", "gold", "--all", "--dry-run"])

    assert result == 0
    assert calls == [("http://clickhouse", "gold", None, True)]
    assert capsys.readouterr().out.strip() == "/tmp/gold.sql"


def test_rebuild_silver_from_marker(monkeypatch, capsys):
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

    result = cli.main(["rebuild", "silver", "--from", "2026-03-01"])

    assert result == 0
    assert calls == [("http://clickhouse", "silver", None, False)]
    assert capsys.readouterr().out == ""
