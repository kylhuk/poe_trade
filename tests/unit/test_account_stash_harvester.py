from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

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
        self.calls: list[dict[str, Any]] = []
        self.bearer_tokens: list[str | None] = []

    def set_bearer_token(self, token: str | None) -> None:
        super().set_bearer_token(token)
        self.bearer_tokens.append(token)

    def request(self, method, path, params=None, data=None, headers=None):
        copied_headers = dict(headers) if isinstance(headers, dict) else headers
        copied_params = dict(params) if isinstance(params, dict) else params
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": copied_headers,
                "params": copied_params,
                "bearer_token": self._bearer_token,
            }
        )
        if copied_params and copied_params.get("tabs") == "1":
            return {"tabs": [{"id": "t1", "i": 0, "n": "Trade 1", "type": "normal"}]}
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
    harvester = AccountStashHarvester(
        client, clickhouse, status, access_token="access-123"
    )

    harvester.run(realm="pc", league="Mirage", interval=0.0, dry_run=False, once=True)

    assert len(clickhouse.queries) == 2
    assert "raw_account_stash_snapshot" in clickhouse.queries[0]
    assert "account_name" in clickhouse.queries[0]
    assert "silver_account_stash_items" in clickhouse.queries[1]
    assert "account_name" in clickhouse.queries[1]
    assert client.bearer_tokens == ["access-123"]
    assert client.calls[0]["bearer_token"] == "access-123"
    assert status.calls[0]["status"] == "success"


def test_harvest_writes_account_name_in_rows() -> None:
    client = _StubClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
    )

    harvester.run(realm="pc", league="Mirage", interval=0.0, dry_run=False, once=True)

    assert len(clickhouse.queries) == 2
    assert '"account_name": "qa-exile"' in clickhouse.queries[0]
    assert '"account_name": "qa-exile"' in clickhouse.queries[1]


def test_harvest_uses_bearer_token_for_account_stash_requests() -> None:
    client = _StubClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        access_token="access-123",
    )

    harvester.run(realm="pc", league="Mirage", interval=0.0, dry_run=True, once=True)

    assert len(client.calls) == 2
    assert client.calls[0]["path"] == "stash/Mirage"
    assert client.calls[0]["bearer_token"] == "access-123"
    assert client.calls[0]["headers"] is None
    assert client.calls[1]["path"] == "stash/Mirage/t1"
    assert client.calls[1]["bearer_token"] == "access-123"
    assert client.calls[1]["headers"] is None


def test_private_scan_fetches_tab_list_with_tabs_flag_and_preserves_upstream_order() -> (
    None
):
    class _PrivateScanClient(_StubClient):
        def request(self, method, path, params=None, data=None, headers=None):
            copied_headers = dict(headers) if isinstance(headers, dict) else headers
            copied_params = dict(params) if isinstance(params, dict) else params
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "headers": copied_headers,
                    "params": copied_params,
                    "bearer_token": self._bearer_token,
                }
            )
            if path.endswith("/Mirage"):
                return {
                    "tabs": [
                        {"id": "tab-2", "i": 0, "n": "Currency", "type": "currency"},
                        {"id": "tab-9", "i": 1, "n": "Dump", "type": "quad"},
                    ]
                }
            tab_id = path.rsplit("/", 1)[-1]
            return {
                "items": [
                    {
                        "id": f"item-{tab_id}",
                        "name": f"Orb {tab_id}",
                        "typeLine": f"Orb {tab_id}",
                        "itemClass": "Currency",
                        "frameType": 0,
                        "x": 0,
                        "y": 0,
                        "w": 1,
                        "h": 1,
                    }
                ]
            }

    client = _PrivateScanClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
    )

    harvester.run_private_scan(
        realm="pc",
        league="Mirage",
        price_item=lambda _item: {
            "predictedValue": 10.0,
            "currency": "chaos",
            "confidence": 85.0,
            "interval": {"p10": 8.0, "p90": 12.0},
        },
    )

    assert client.calls[0]["path"] == "stash/Mirage"
    assert client.calls[0]["bearer_token"] == "access-123"
    assert client.calls[1]["path"] == "stash/Mirage/tab-2"
    assert client.calls[1]["bearer_token"] == "access-123"
    assert client.calls[2]["path"] == "stash/Mirage/tab-9"
    tab_queries = [
        query for query in clickhouse.queries if "account_stash_scan_tabs" in query
    ]
    assert any(
        '"tab_index": 0' in query and '"tab_name": "Currency"' in query
        for query in tab_queries
    )
    assert any(
        '"tab_index": 1' in query and '"tab_name": "Dump"' in query
        for query in tab_queries
    )


def test_private_scan_preserves_pricing_metadata_and_publishes_only_after_item_rows() -> (
    None
):
    client = _StubClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
    )

    harvester.run_private_scan(
        realm="pc",
        league="Mirage",
        price_item=lambda _item: {
            "predictedValue": 55.0,
            "currency": "chaos",
            "confidence": 90.0,
            "interval": {"p10": 44.0, "p90": 66.0},
            "priceRecommendationEligible": True,
            "estimateTrust": "normal",
            "estimateWarning": "",
            "fallbackReason": "",
        },
    )

    item_queries = [
        query
        for query in clickhouse.queries
        if "account_stash_item_valuations" in query
    ]
    assert any(
        '"price_recommendation_eligible": true' in query for query in item_queries
    )
    assert any('"estimate_trust": "normal"' in query for query in item_queries)
    assert "account_stash_published_scans" in clickhouse.queries[-1]


def test_private_scan_updates_running_progress_before_publish() -> None:
    class _ProgressClient(_StubClient):
        def request(self, method, path, params=None, data=None, headers=None):
            copied_headers = dict(headers) if isinstance(headers, dict) else headers
            copied_params = dict(params) if isinstance(params, dict) else params
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "headers": copied_headers,
                    "params": copied_params,
                    "bearer_token": self._bearer_token,
                }
            )
            if path.endswith("/Mirage"):
                return {
                    "tabs": [
                        {"id": "tab-1", "i": 0, "n": "Currency", "type": "currency"},
                        {"id": "tab-2", "i": 1, "n": "Dump", "type": "quad"},
                    ]
                }
            tab_id = path.rsplit("/", 1)[-1]
            return {
                "items": [
                    {
                        "id": f"item-{tab_id}",
                        "name": f"Orb {tab_id}",
                        "typeLine": f"Orb {tab_id}",
                        "itemClass": "Currency",
                        "frameType": 0,
                        "x": 0,
                        "y": 0,
                        "w": 1,
                        "h": 1,
                    }
                ]
            }

    client = _ProgressClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
    )

    harvester.run_private_scan(
        realm="pc",
        league="Mirage",
        price_item=lambda _item: {
            "predictedValue": 10.0,
            "currency": "chaos",
            "confidence": 85.0,
            "interval": {"p10": 8.0, "p90": 12.0},
        },
    )

    assert any(
        '"status": "running"' in query and '"tabs_processed": 1' in query
        for query in clickhouse.queries
    )
    assert any(
        '"status": "running"' in query and '"tabs_processed": 2' in query
        for query in clickhouse.queries
    )


def test_private_scan_marks_failed_and_skips_publish_when_item_lacks_concrete_value() -> (
    None
):
    class _FailureProgressClient(_StubClient):
        def request(self, method, path, params=None, data=None, headers=None):
            copied_headers = dict(headers) if isinstance(headers, dict) else headers
            copied_params = dict(params) if isinstance(params, dict) else params
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "headers": copied_headers,
                    "params": copied_params,
                    "bearer_token": self._bearer_token,
                }
            )
            if path.endswith("/Mirage"):
                return {
                    "tabs": [
                        {"id": "tab-1", "i": 0, "n": "Currency", "type": "currency"},
                        {"id": "tab-2", "i": 1, "n": "Dump", "type": "quad"},
                    ]
                }
            tab_id = path.rsplit("/", 1)[-1]
            if tab_id == "tab-1":
                return {
                    "items": [
                        {
                            "id": "item-1",
                            "name": "Orb 1",
                            "typeLine": "Orb 1",
                            "itemClass": "Currency",
                            "frameType": 0,
                            "x": 0,
                            "y": 0,
                            "w": 1,
                            "h": 1,
                        }
                    ]
                }
            return {
                "items": [
                    {
                        "id": "item-2",
                        "name": "Orb 2",
                        "typeLine": "Orb 2",
                        "itemClass": "Currency",
                        "frameType": 0,
                        "x": 0,
                        "y": 0,
                        "w": 1,
                        "h": 1,
                    }
                ]
            }

    client = _FailureProgressClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
    )

    seen = {"count": 0}

    def _price_item(_item):
        seen["count"] += 1
        if seen["count"] == 1:
            return {
                "predictedValue": 12.0,
                "currency": "chaos",
                "confidence": 80.0,
                "interval": {"p10": 10.0, "p90": 14.0},
            }
        return {"confidence": 0.0}

    result = harvester.run_private_scan(
        realm="pc", league="Mirage", price_item=_price_item
    )

    assert result["status"] == "failed"
    assert any('"status": "failed"' in query for query in clickhouse.queries)
    assert any(
        '"status": "failed"' in query and '"tabs_processed": 1' in query
        for query in clickhouse.queries
    )
    assert any(
        '"status": "failed"' in query and '"items_processed": 1' in query
        for query in clickhouse.queries
    )
    assert not any(
        "account_stash_published_scans" in query for query in clickhouse.queries
    )


def test_private_scan_maps_upstream_auth_error_to_invalid_poe_session_message() -> None:
    class _InvalidSessionClient(_StubClient):
        def request(self, method, path, params=None, data=None, headers=None):
            raise RuntimeError("PoE client error 401: unauthorized")

    client = _InvalidSessionClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
    )

    result = harvester.run_private_scan(
        realm="pc",
        league="Mirage",
        price_item=lambda _item: {"predictedValue": 1.0},
    )

    assert result["status"] == "failed"
    assert result["error"] == "account stash access denied"


def test_private_scan_refreshes_bearer_token_once_on_401_and_retries_failed_request() -> (
    None
):
    class _RefreshingClient(_StubClient):
        def __init__(self) -> None:
            super().__init__()
            self.seen_retry = False

        def request(self, method, path, params=None, data=None, headers=None):
            copied_headers = dict(headers) if isinstance(headers, dict) else headers
            copied_params = dict(params) if isinstance(params, dict) else params
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "headers": copied_headers,
                    "params": copied_params,
                    "bearer_token": self._bearer_token,
                }
            )
            if path.endswith("/Mirage"):
                return {
                    "tabs": [
                        {"id": "tab-1", "i": 0, "n": "Currency", "type": "currency"},
                        {"id": "tab-2", "i": 1, "n": "Dump", "type": "quad"},
                    ]
                }
            if path.endswith("/tab-1") and not self.seen_retry:
                self.seen_retry = True
                raise RuntimeError("PoE client error 401: unauthorized")
            return {
                "items": [
                    {
                        "id": path.rsplit("/", 1)[-1],
                        "name": "Orb",
                        "typeLine": "Orb",
                        "itemClass": "Currency",
                        "frameType": 0,
                        "x": 0,
                        "y": 0,
                        "w": 1,
                        "h": 1,
                    }
                ]
            }

    client = _RefreshingClient()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)
    refresh_calls = {"count": 0}

    def _refresh() -> str:
        refresh_calls["count"] += 1
        return "access-456"

    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
        refresh_access_token=_refresh,
    )

    result = harvester.run_private_scan(
        realm="pc",
        league="Mirage",
        price_item=lambda _item: {
            "predictedValue": 10.0,
            "currency": "chaos",
            "confidence": 85.0,
            "interval": {"p10": 8.0, "p90": 12.0},
        },
    )

    assert result["status"] == "published"
    assert refresh_calls["count"] == 1
    assert client.bearer_tokens == ["access-123", "access-456"]
    assert any(call["bearer_token"] == "access-456" for call in client.calls)


def test_private_scan_fails_terminally_when_retry_still_returns_401() -> None:
    class _Terminal401Client(_StubClient):
        def request(self, method, path, params=None, data=None, headers=None):
            copied_headers = dict(headers) if isinstance(headers, dict) else headers
            copied_params = dict(params) if isinstance(params, dict) else params
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "headers": copied_headers,
                    "params": copied_params,
                    "bearer_token": self._bearer_token,
                }
            )
            if path.endswith("/Mirage"):
                return {
                    "tabs": [
                        {"id": "tab-1", "i": 0, "n": "Currency", "type": "currency"}
                    ]
                }
            raise RuntimeError("PoE client error 401: unauthorized")

    client = _Terminal401Client()
    clickhouse = _StubClickHouse()
    status = _StubStatus(clickhouse)

    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        account_name="qa-exile",
        access_token="access-123",
        refresh_access_token=lambda: "access-456",
    )

    result = harvester.run_private_scan(
        realm="pc",
        league="Mirage",
        price_item=lambda _item: {
            "predictedValue": 10.0,
            "currency": "chaos",
            "confidence": 85.0,
            "interval": {"p10": 8.0, "p90": 12.0},
        },
    )

    assert result["status"] == "failed"
    assert result["error"] == "account stash access denied"
    assert any('"status": "failed"' in query for query in clickhouse.queries)
