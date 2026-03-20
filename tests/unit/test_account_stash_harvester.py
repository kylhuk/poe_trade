from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from poe_trade.db import ClickHouseClient
from poe_trade.ingestion.account_stash_harvester import (
    AccountStashHarvester,
    parse_listed_price,
    stash_endpoint,
)
from poe_trade.ingestion.poe_client import PoeClient
from poe_trade.ingestion.rate_limit import RateLimitPolicy
from poe_trade.ingestion.status import StatusReporter


class _StubClient(PoeClient):
    def __init__(self) -> None:
        super().__init__(
            "https://api.pathofexile.com", RateLimitPolicy(0, 0.1, 1.0, 0.0), "ua", 1.0
        )
        self.calls: list[tuple[str, str, Mapping[str, str] | None]] = []

    def request(self, method, path, params=None, data=None, headers=None):
        copied_headers = dict(headers) if isinstance(headers, dict) else headers
        self.calls.append((method, path, copied_headers))
        if path.endswith("/Mirage"):
            return [{"id": "t1", "n": "Trade 1", "type": "normal"}]
        return {
            "items": [
                {
                    "id": "i1",
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
        }


class _StubClickHouse(ClickHouseClient):
    def __init__(self) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.queries: list[str] = []

    def execute(self, query: str, settings=None) -> str:
        self.queries.append(query)
        return ""


class _StubStatus(StatusReporter):
    def __init__(self, client: ClickHouseClient) -> None:
        super().__init__(client, "account_stash_harvester")
        self.calls: list[dict[str, object]] = []

    def report(
        self,
        queue_key: str,
        feed_kind: str,
        contract_version: int,
        league: str | None,
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
        self.calls.append(
            {
                "queue_key": queue_key,
                "feed_kind": feed_kind,
                "league": league,
                "realm": realm,
                "status": status,
                "error": error,
                "at": last_ingest_at.astimezone(timezone.utc).isoformat(),
            }
        )


def test_stash_endpoint_shape() -> None:
    assert stash_endpoint("pc", "Mirage") == "stash/Mirage"
    assert stash_endpoint("xbox", "Mirage") == "stash/xbox/Mirage"
    assert stash_endpoint("pc", "Mirage", tab_id="123") == "stash/Mirage/123"


def test_parse_listed_price() -> None:
    assert parse_listed_price("~price 10 chaos") == (10.0, "chaos")
    assert parse_listed_price("~b/o 1.5 div") == (1.5, "div")
    assert parse_listed_price("no price") is None


def test_harvest_writes_raw_and_flat_rows() -> None:
    client = _StubClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(client, clickhouse, status)

    harvester.run(realm="pc", league="Mirage", interval=0.0, dry_run=False, once=True)

    assert len(clickhouse.queries) == 2
    assert "raw_account_stash_snapshot" in clickhouse.queries[0]
    assert "account_name" in clickhouse.queries[0]
    assert "silver_account_stash_items" in clickhouse.queries[1]
    assert "account_name" in clickhouse.queries[1]
    assert status.calls[0]["status"] == "success"


def test_harvest_writes_account_name_in_rows() -> None:
    client = _StubClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client, clickhouse, status, account_name="qa-exile"
    )

    harvester.run(realm="pc", league="Mirage", interval=0.0, dry_run=False, once=True)

    assert len(clickhouse.queries) == 2
    assert '"account_name": "qa-exile"' in clickhouse.queries[0]
    assert '"account_name": "qa-exile"' in clickhouse.queries[1]


def test_harvest_uses_server_side_cookie_header() -> None:
    client = _StubClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        request_headers={"Cookie": "POESESSID=POESESSID-123"},
    )

    harvester.run(realm="pc", league="Mirage", interval=0.0, dry_run=True, once=True)

    assert len(client.calls) == 2
    assert client.calls[0][2] == {"Cookie": "POESESSID=POESESSID-123"}
    assert client.calls[1][2] == {"Cookie": "POESESSID=POESESSID-123"}
