from __future__ import annotations

import json

from poe_trade.api.stash import fetch_stash_tabs
from poe_trade.db import ClickHouseClient


class _StubClickHouse(ClickHouseClient):
    def __init__(self, payload: str) -> None:
        super().__init__(endpoint="http://clickhouse")
        self._payload = payload

    def execute(self, query: str, settings=None) -> str:
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

    assert len(result["stashTabs"]) == 1
    tab = result["stashTabs"][0]
    assert tab["id"] == "1"
    assert tab["name"] == "Trade 1"
    assert tab["type"] == "normal"
    assert len(tab["items"]) == 1
    item = tab["items"][0]
    assert item["id"] == "item-1"
    assert item["listedPrice"] == 10.0
    assert item["currency"] == "chaos"
