from __future__ import annotations

import json
from collections.abc import Mapping

from poe_trade.db import ClickHouseClient
from poe_trade.ingestion.account_stash_harvester import AccountStashHarvester
from poe_trade.ingestion.poe_client import PoeClient
from poe_trade.ingestion.rate_limit import RateLimitPolicy
from poe_trade.ingestion.status import StatusReporter


class _FakePoeClient(PoeClient):
    def __init__(self) -> None:
        super().__init__(
            base_url="http://poe.invalid",
            policy=RateLimitPolicy(0, 0.0, 0.0, 0.0),
            user_agent="ua",
            timeout=1.0,
        )
        self.bearer_token: str | None = None

    def set_bearer_token(self, token: str | None) -> None:
        self.bearer_token = token

    def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        data: object | None = None,
        headers: Mapping[str, str] | None = None,
    ):
        del method, path, data, headers
        params = dict(params or {})
        if params.get("tabs") == "1":
            return {
                "tabs": [{"id": "tab-1", "i": 0, "n": "Currency", "type": "currency"}]
            }
        return {
            "stash": {
                "id": str(params.get("tabIndex") or "tab-1"),
                "items": [
                    {
                        "id": "item-1",
                        "name": "Mirror Shard",
                        "typeLine": "Mirror Shard",
                        "frameType": 0,
                        "itemClass": "Currency",
                        "icon": "https://example.invalid/icon.png",
                        "x": 1,
                        "y": 2,
                        "w": 1,
                        "h": 1,
                        "note": "~price 3 chaos",
                    }
                ],
            }
        }


class _FakeClickHouse(ClickHouseClient):
    def __init__(self) -> None:
        super().__init__(endpoint="http://clickhouse")
        self.queries: list[str] = []

    def execute(self, query: str, settings: Mapping[str, str] | None = None) -> str:
        del settings
        self.queries.append(query)
        return ""


def test_run_private_scan_publishes_items_without_valuation_callback() -> None:
    clickhouse = _FakeClickHouse()
    harvester = AccountStashHarvester(
        _FakePoeClient(),
        clickhouse,
        StatusReporter(clickhouse, "account_stash_harvester"),
        account_name="qa-exile",
        access_token="access-token",
    )

    result = harvester.run_private_scan(realm="pc", league="Mirage")

    assert result["status"] == "published"
    valuations_query = next(
        query
        for query in clickhouse.queries
        if "account_stash_item_valuations" in query
    )
    valuations_payload = valuations_query.split("FORMAT JSONEachRow\n", 1)[1]
    row = json.loads(valuations_payload)
    assert row["predicted_price"] == 0.0
    assert row["fallback_reason"] == "valuation_unavailable"
    assert row["price_recommendation_eligible"] == 0


def test_run_private_scan_uses_valuation_callback_when_available() -> None:
    clickhouse = _FakeClickHouse()
    harvester = AccountStashHarvester(
        _FakePoeClient(),
        clickhouse,
        StatusReporter(clickhouse, "account_stash_harvester"),
        account_name="qa-exile",
        access_token="access-token",
    )

    result = harvester.run_private_scan(
        realm="pc",
        league="Mirage",
        price_item=lambda _item: {
            "predictedValue": 42.0,
            "currency": "chaos",
            "confidence": 88.0,
            "interval": {"p10": 35.0, "p90": 55.0},
            "priceRecommendationEligible": True,
            "estimateTrust": "normal",
            "estimateWarning": "",
            "fallbackReason": "",
        },
    )

    assert result["status"] == "published"
    valuations_query = next(
        query
        for query in clickhouse.queries
        if "account_stash_item_valuations" in query
    )
    valuations_payload = valuations_query.split("FORMAT JSONEachRow\n", 1)[1]
    row = json.loads(valuations_payload)
    assert row["predicted_price"] == 42.0
    assert row["confidence"] == 88.0
    assert row["price_p10"] == 35.0
    assert row["price_p90"] == 55.0
    assert row["fallback_reason"] == ""
    assert row["price_recommendation_eligible"] == 1


def test_run_private_scan_publishes_before_writing_valuations() -> None:
    clickhouse = _FakeClickHouse()
    harvester = AccountStashHarvester(
        _FakePoeClient(),
        clickhouse,
        StatusReporter(clickhouse, "account_stash_harvester"),
        account_name="qa-exile",
        access_token="access-token",
    )

    _ = harvester.run_private_scan(realm="pc", league="Mirage")

    published_query_index = next(
        index
        for index, query in enumerate(clickhouse.queries)
        if "account_stash_scan_runs" in query and '"status": "published"' in query
    )
    valuations_query_index = next(
        index
        for index, query in enumerate(clickhouse.queries)
        if "account_stash_item_valuations" in query
    )

    assert published_query_index < valuations_query_index
