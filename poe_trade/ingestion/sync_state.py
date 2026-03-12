from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from ..db import ClickHouseClient


@dataclass(frozen=True)
class QueueState:
    queue_key: str
    feed_kind: str
    realm: str
    next_cursor_id: str
    status: str
    retrieved_at: datetime | None


class SyncStateStore:
    def __init__(self, client: ClickHouseClient) -> None:
        self._client: ClickHouseClient = client

    def latest_cursor(
        self,
        queue_key: str,
        *,
        statuses: Iterable[str] = ("success", "idle"),
    ) -> str | None:
        state = self.latest_state(queue_key, statuses=statuses)
        if state is None:
            return None
        cursor = state.next_cursor_id.strip()
        return cursor or None

    def latest_state(
        self,
        queue_key: str,
        *,
        statuses: Iterable[str] = ("success", "idle"),
    ) -> QueueState | None:
        allowed_statuses = tuple(statuses)
        if not allowed_statuses:
            raise ValueError("At least one status must be provided")
        status_sql = ", ".join(self._quote(status) for status in allowed_statuses)
        query = (
            "SELECT queue_key, feed_kind, realm, next_cursor_id, status, retrieved_at "
            "FROM poe_trade.bronze_ingest_checkpoints "
            f"WHERE queue_key = {self._quote(queue_key)} "
            f"AND status IN ({status_sql}) "
            "ORDER BY retrieved_at DESC LIMIT 1 FORMAT JSONEachRow"
        )
        payload = self._client.execute(query)
        cleaned = payload.strip()
        if not cleaned:
            return None
        loaded = json.loads(cleaned.splitlines()[0])
        if not isinstance(loaded, dict):
            return None
        raw_record = cast(dict[str, object], loaded)
        return QueueState(
            queue_key=str(raw_record.get("queue_key") or ""),
            feed_kind=str(raw_record.get("feed_kind") or ""),
            realm=str(raw_record.get("realm") or ""),
            next_cursor_id=str(raw_record.get("next_cursor_id") or ""),
            status=str(raw_record.get("status") or ""),
            retrieved_at=self._parse_datetime(raw_record.get("retrieved_at")),
        )

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        candidate = candidate.replace(" ", "T", 1)
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None


__all__ = ["QueueState", "SyncStateStore"]
