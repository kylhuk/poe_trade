from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from poe_trade.api.stash import fetch_stash_tabs, stash_status_payload
from poe_trade.db import ClickHouseClient


class _StubClickHouse(ClickHouseClient):
    def __init__(self, payload: str) -> None:
        super().__init__(endpoint="http://clickhouse")
        self._payload: str = payload

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        return self._payload


class _RecordingClickHouse(_StubClickHouse):
    def __init__(self, payload: str) -> None:
        super().__init__(payload)
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        self.queries.append(query)
        return self._payload


def test_fetch_stash_tabs_empty() -> None:
    client = _StubClickHouse(payload="")
    assert fetch_stash_tabs(client, league="Mirage", realm="pc") == {"stashTabs": []}


def test_fetch_stash_tabs_maps_item_shape() -> None:
    raw_payload = {
        "tab": {"id": "1", "n": "Trade 1", "type": "normal"},
        "payload": {
            "items": [
                {
                    "id": "item-1",
                    "name": "Chaos Orb",
                    "itemClass": "Currency",
                    "frameType": 0,
                    "x": 0,
                    "y": 0,
                    "w": 1,
                    "h": 1,
                    "note": "~price 10 chaos",
                    "icon": "https://web.poecdn.com/test.png",
                }
            ]
        },
    }
    line = json.dumps({"tab_id": "1", "payload_json": json.dumps(raw_payload)})
    client = _StubClickHouse(payload=f"{line}\n")

    result = fetch_stash_tabs(client, league="Mirage", realm="pc")
    stash_tabs = cast(list[dict[str, object]], result["stashTabs"])

    assert len(stash_tabs) == 1
    tab = stash_tabs[0]
    assert tab["id"] == "1"
    assert tab["name"] == "Trade 1"
    assert tab["type"] == "normal"
    items = cast(list[dict[str, object]], tab["items"])
    assert len(items) == 1
    item = items[0]
    assert item["id"] == "item-1"
    assert item["listedPrice"] == 10.0
    assert item["currency"] == "chaos"


def test_fetch_stash_tabs_query_is_account_scoped() -> None:
    client = _RecordingClickHouse(payload="")

    _ = fetch_stash_tabs(
        client,
        league="Mirage",
        realm="pc",
        account_name="qa-exile",
    )

    assert len(client.queries) == 1
    assert "account_name" in client.queries[0]
    assert "qa-exile" in client.queries[0]
    assert "OR account_name" not in client.queries[0]


def test_fetch_stash_tabs_query_uses_legacy_scope_when_account_empty() -> None:
    client = _RecordingClickHouse(payload="")

    _ = fetch_stash_tabs(client, league="Mirage", realm="pc")

    assert len(client.queries) == 1
    assert "account_name = ''" in client.queries[0]
    assert "OR account_name" not in client.queries[0]


def test_stash_status_query_is_account_scoped() -> None:
    client = _RecordingClickHouse(payload='{"tabs":1,"snapshots":2}\n')

    _ = stash_status_payload(
        client,
        league="Mirage",
        realm="pc",
        enable_account_stash=True,
        session={
            "status": "connected",
            "account_name": "qa-exile",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    assert len(client.queries) == 1
    assert "account_name" in client.queries[0]
    assert "qa-exile" in client.queries[0]
    assert "OR account_name" not in client.queries[0]


def test_stash_status_connected_empty_when_scoped_rows_missing() -> None:
    client = _StubClickHouse(payload='{"tabs":0,"snapshots":0}\n')

    payload = stash_status_payload(
        client,
        league="Mirage",
        realm="pc",
        enable_account_stash=True,
        session={
            "status": "connected",
            "account_name": "qa-exile",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    assert payload["status"] == "connected_empty"
    assert payload["connected"] is True
    assert payload["tabCount"] == 0
    assert payload["itemCount"] == 0


def test_stash_status_connected_populated_when_scoped_rows_exist() -> None:
    client = _StubClickHouse(payload='{"tabs":2,"snapshots":5}\n')

    payload = stash_status_payload(
        client,
        league="Mirage",
        realm="pc",
        enable_account_stash=True,
        session={
            "status": "connected",
            "account_name": "qa-exile",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    assert payload["status"] == "connected_populated"
    assert payload["connected"] is True
    assert payload["tabCount"] == 2
    assert payload["itemCount"] == 5


def test_stash_status_disconnected_for_disconnected_session() -> None:
    client = _StubClickHouse(payload='{"tabs":2,"snapshots":5}\n')

    payload = stash_status_payload(
        client,
        league="Mirage",
        realm="pc",
        enable_account_stash=True,
        session={
            "status": "disconnected",
            "account_name": "qa-exile",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    assert payload["status"] == "disconnected"
    assert payload["connected"] is False


def test_stash_status_session_expired_for_expired_session() -> None:
    client = _StubClickHouse(payload='{"tabs":2,"snapshots":5}\n')

    payload = stash_status_payload(
        client,
        league="Mirage",
        realm="pc",
        enable_account_stash=True,
        session={
            "status": "session_expired",
            "account_name": "qa-exile",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    assert payload["status"] == "session_expired"
    assert payload["connected"] is False


def test_stash_status_feature_unavailable_explains_flag() -> None:
    client = _StubClickHouse(payload='{"tabs":2,"snapshots":5}\n')

    payload = stash_status_payload(
        client,
        league="Mirage",
        realm="pc",
        enable_account_stash=False,
        session=None,
    )

    assert payload["status"] == "feature_unavailable"
    assert payload["connected"] is False
    assert payload["reason"] == "set POE_ENABLE_ACCOUNT_STASH=true to enable stash APIs"
    assert payload["featureFlag"] == "POE_ENABLE_ACCOUNT_STASH"
