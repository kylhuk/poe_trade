from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

from ..analytics import execute_refresh_group
from ..db import ClickHouseClient
from .cxapi_sync import last_completed_hour


class PsapiHarvester(Protocol):
    def _harvest(self, realm: str, league: str, dry_run: bool) -> None: ...


class CxapiHourSync(Protocol):
    def sync_hour(
        self,
        realm: str,
        requested_hour: datetime,
        *,
        dry_run: bool = False,
    ) -> None: ...


def run_market_sync(
    *,
    harvester: PsapiHarvester | None,
    cx_sync: CxapiHourSync | None,
    realms: tuple[str, ...],
    leagues: tuple[str, ...],
    poll_interval: float,
    dry_run: bool,
    once: bool,
    cxapi_hour_offset_seconds: int,
    refresh_client: object | None = None,
    refresh_refs_minutes: int = 0,
) -> None:
    active_league = leagues[0] if leagues else ""
    last_cx_hours: dict[str, datetime] = {}
    last_refs_refresh_at: datetime | None = None

    while True:
        now = datetime.now(timezone.utc)
        cx_hour = last_completed_hour(now, offset_seconds=cxapi_hour_offset_seconds)

        for realm in realms:
            if harvester is not None:
                harvester._harvest(realm, active_league, dry_run)
            if cx_sync is not None and last_cx_hours.get(realm) != cx_hour:
                cx_sync.sync_hour(realm, cx_hour, dry_run=dry_run)
                last_cx_hours[realm] = cx_hour

        if (
            refresh_client is not None
            and refresh_refs_minutes > 0
            and _should_refresh_refs(last_refs_refresh_at, now, refresh_refs_minutes)
        ):
            execute_refresh_group(
                cast(ClickHouseClient, refresh_client),
                layer="gold",
                group="refs",
                dry_run=dry_run,
            )
            last_refs_refresh_at = now

        if once:
            return
        time.sleep(poll_interval)


def _should_refresh_refs(
    last_refs_refresh_at: datetime | None,
    now: datetime,
    refresh_refs_minutes: int,
) -> bool:
    if last_refs_refresh_at is None:
        return True
    interval = timedelta(minutes=max(1, int(refresh_refs_minutes)))
    return now - last_refs_refresh_at >= interval


__all__ = ["run_market_sync"]
