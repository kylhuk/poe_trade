"""Helpers to record ingestion status to ClickHouse."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..db import ClickHouseClient, ClickHouseClientError

logger = logging.getLogger(__name__)


def _format_ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class StatusReporter:
    def __init__(self, client: ClickHouseClient, source: str) -> None:
        self._client = client
        self._source = source

    def report(
        self,
        league: str,
        realm: str,
        cursor: str | None,
        next_change_id: str | None,
        last_ingest_at: datetime,
        request_rate: float | None,
        status: str,
        error: str | None = None,
        error_count: int = 0,
        stalled_since: datetime | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "league": league,
            "realm": realm,
            "source": self._source,
            "last_cursor": cursor or "",
            "next_change_id": next_change_id or "",
            "last_ingest_at": _format_ts(last_ingest_at),
            "request_rate": request_rate if request_rate is not None else 0.0,
            "error_count": error_count,
            "stalled_since": _format_ts(stalled_since) if stalled_since else None,
            "last_error": error or "",
            "status": status,
        }
        query = (
            "INSERT INTO poe_trade.poe_ingest_status "
            "(league, realm, source, last_cursor, next_change_id, last_ingest_at, request_rate, error_count, stalled_since, last_error, status)\n"
            "FORMAT JSONEachRow\n"
            f"{json.dumps(row)}"
        )
        try:
            self._client.execute(query)
        except ClickHouseClientError as exc:  # pragma: no cover - depends on ClickHouse
            logger.error("Failed to write ingest status: %s", exc)
