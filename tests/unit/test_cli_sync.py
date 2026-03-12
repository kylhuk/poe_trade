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
        return '{"queue_key":"psapi:pc","feed_kind":"psapi","status":"success","last_ingest_at":"2026-03-10 20:00:00.000"}'


def test_sync_status_command(monkeypatch, capsys):
    monkeypatch.setattr(
        cli.settings,
        "get_settings",
        lambda: SimpleNamespace(clickhouse_url="http://clickhouse"),
    )
    monkeypatch.setattr(cli, "ClickHouseClient", _DummyClickHouseClient)

    result = cli.main(["sync", "status"])

    assert result == 0
    assert '"queue_key":"psapi:pc"' in capsys.readouterr().out


def test_sync_psapi_once_command(monkeypatch):
    calls = []

    def _service_main(args):
        calls.append(
            (
                args,
                cli.os.environ.get("POE_ENABLE_PSAPI"),
                cli.os.environ.get("POE_ENABLE_CXAPI"),
            )
        )

    monkeypatch.setattr(cli, "_load_service_main", lambda _name: _service_main)

    result = cli.main(["sync", "psapi-once"])

    assert result == 0
    assert calls == [(["--once"], "true", "false")]


def test_sync_cxapi_backfill_command(monkeypatch):
    calls = []

    def _service_main(args):
        calls.append(
            (
                args,
                cli.os.environ.get("POE_ENABLE_PSAPI"),
                cli.os.environ.get("POE_ENABLE_CXAPI"),
                cli.os.environ.get("POE_CXAPI_BACKFILL_HOURS"),
            )
        )

    monkeypatch.setattr(cli, "_load_service_main", lambda _name: _service_main)

    result = cli.main(["sync", "cxapi-backfill", "--hours", "24"])

    assert result == 0
    assert calls == [(["--once"], "false", "true", "24")]
