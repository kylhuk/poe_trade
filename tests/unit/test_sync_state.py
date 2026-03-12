from __future__ import annotations

import json
from typing import Any, cast

import pytest

from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.ingestion.sync_state import SyncStateStore


class RecordingClient:
    def __init__(self, payload: str = "", error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.queries: list[str] = []

    def execute(self, query: str) -> str:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.payload


def test_latest_cursor_returns_none_when_no_rows() -> None:
    store = SyncStateStore(cast(Any, RecordingClient()))
    assert store.latest_cursor("psapi:pc") is None


def test_latest_cursor_reads_queue_state() -> None:
    payload = json.dumps(
        {
            "queue_key": "psapi:pc",
            "feed_kind": "psapi",
            "realm": "pc",
            "next_cursor_id": "next-123",
            "status": "success",
        }
    )
    client = RecordingClient(payload=payload)
    store = SyncStateStore(cast(Any, client))

    assert store.latest_cursor("psapi:pc") == "next-123"
    assert "WHERE queue_key = 'psapi:pc'" in client.queries[0]
    assert "status IN ('success', 'idle')" in client.queries[0]


def test_latest_state_allows_custom_statuses() -> None:
    payload = json.dumps(
        {
            "queue_key": "cxapi:pc",
            "feed_kind": "cxapi",
            "realm": "pc",
            "next_cursor_id": "1741561200",
            "status": "paused",
        }
    )
    client = RecordingClient(payload=payload)
    store = SyncStateStore(cast(Any, client))

    state = store.latest_state("cxapi:pc", statuses=("paused",))

    assert state is not None
    assert state.feed_kind == "cxapi"
    assert "status IN ('paused')" in client.queries[0]


def test_latest_state_raises_on_clickhouse_error() -> None:
    client = RecordingClient(error=ClickHouseClientError("boom"))
    store = SyncStateStore(cast(Any, client))
    with pytest.raises(ClickHouseClientError, match="boom"):
        store.latest_state("psapi:pc")


def test_latest_state_rejects_empty_status_list() -> None:
    store = SyncStateStore(cast(Any, RecordingClient()))
    with pytest.raises(ValueError, match="At least one status"):
        store.latest_state("psapi:pc", statuses=())
