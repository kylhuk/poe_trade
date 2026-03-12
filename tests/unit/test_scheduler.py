from datetime import datetime, timezone

from poe_trade.ingestion import scheduler


class _DummyHarvester:
    def __init__(self):
        self.calls = []

    def _harvest(self, realm: str, league: str, dry_run: bool) -> None:
        self.calls.append((realm, league, dry_run))


class _DummyCxSync:
    def __init__(self):
        self.calls = []

    def sync_hour(self, realm: str, requested_hour: datetime, *, dry_run: bool = False):
        self.calls.append((realm, requested_hour, dry_run))


def test_run_market_sync_once_runs_psapi_and_cx() -> None:
    harvester = _DummyHarvester()
    cx_sync = _DummyCxSync()

    scheduler.run_market_sync(
        harvester=harvester,
        cx_sync=cx_sync,
        realms=("pc", "xbox"),
        leagues=("Mirage", "Settlers"),
        poll_interval=0.0,
        dry_run=True,
        once=True,
        cxapi_hour_offset_seconds=15,
    )

    assert harvester.calls == [("pc", "Mirage", True), ("xbox", "Mirage", True)]
    assert len(cx_sync.calls) == 2
    assert cx_sync.calls[0][0] == "pc"
    assert cx_sync.calls[1][0] == "xbox"


def test_run_market_sync_once_supports_cx_only() -> None:
    cx_sync = _DummyCxSync()

    scheduler.run_market_sync(
        harvester=None,
        cx_sync=cx_sync,
        realms=("pc",),
        leagues=("Mirage",),
        poll_interval=0.0,
        dry_run=False,
        once=True,
        cxapi_hour_offset_seconds=15,
    )

    assert len(cx_sync.calls) == 1


def test_run_market_sync_once_supports_psapi_only() -> None:
    harvester = _DummyHarvester()

    scheduler.run_market_sync(
        harvester=harvester,
        cx_sync=None,
        realms=("pc",),
        leagues=("Mirage",),
        poll_interval=0.0,
        dry_run=False,
        once=True,
        cxapi_hour_offset_seconds=15,
    )

    assert harvester.calls == [("pc", "Mirage", False)]


def test_run_market_sync_runs_refs_refresh_on_schedule(monkeypatch) -> None:
    refresh_calls = []

    def _record_refresh(
        client, *, layer: str, group: str | None = None, dry_run: bool = False
    ):
        refresh_calls.append((client, layer, group, dry_run))
        return []

    monkeypatch.setattr(scheduler, "execute_refresh_group", _record_refresh)
    refresh_client = object()

    scheduler.run_market_sync(
        harvester=None,
        cx_sync=None,
        realms=("pc",),
        leagues=("Mirage",),
        poll_interval=0.0,
        dry_run=False,
        once=True,
        cxapi_hour_offset_seconds=15,
        refresh_client=refresh_client,
        refresh_refs_minutes=5,
    )

    assert refresh_calls == [(refresh_client, "gold", "refs", False)]
