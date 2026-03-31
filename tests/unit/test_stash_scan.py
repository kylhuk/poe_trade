from __future__ import annotations

import json
from collections.abc import Mapping

from poe_trade.db import ClickHouseClient
from poe_trade.stash_scan import (
    content_signature_for_item,
    fetch_active_scan,
    fetch_item_history,
    fetch_published_tabs,
    fetch_published_scan_id,
    lineage_key_for_item,
    lineage_key_from_previous_scan,
    normalize_stash_prediction,
    serialize_stash_item_to_clipboard,
)


class _StubClickHouse(ClickHouseClient):
    def __init__(self, payload: str) -> None:
        super().__init__(endpoint="http://clickhouse")
        self._payload = payload
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        self.queries.append(query)
        return self._payload


class _SequentialStubClickHouse(ClickHouseClient):
    def __init__(self, payloads: list[str]) -> None:
        super().__init__(endpoint="http://clickhouse")
        self._payloads = list(payloads)
        self.queries: list[str] = []

    def execute(  # pyright: ignore[reportImplicitOverride]
        self, query: str, settings: Mapping[str, str] | None = None
    ) -> str:
        self.queries.append(query)
        del settings
        if self._payloads:
            return self._payloads.pop(0)
        return ""


def test_lineage_key_prefers_upstream_item_id() -> None:
    item = {"id": "item-123", "name": "Chaos Orb", "typeLine": "Chaos Orb"}

    assert lineage_key_for_item(item) == "item:item-123"


def test_content_signature_ignores_position_changes() -> None:
    a = {
        "name": "Grim Bane",
        "typeLine": "Hubris Circlet",
        "x": 1,
        "y": 1,
        "explicitMods": ["+93 to maximum Life"],
    }
    b = {
        "name": "Grim Bane",
        "typeLine": "Hubris Circlet",
        "x": 4,
        "y": 7,
        "explicitMods": ["+93 to maximum Life"],
    }

    assert content_signature_for_item(a) == content_signature_for_item(b)


def test_lineage_key_uses_prior_signature_match_before_position_tie_break() -> None:
    assert (
        lineage_key_from_previous_scan(
            signature="sig-123",
            prior_signature_matches={"sig-123": "sig:existing-lineage"},
            prior_position_matches={"tab-1:4:7:1:1": "sig:position-lineage"},
            position_key="tab-1:4:7:1:1",
        )
        == "sig:existing-lineage"
    )


def test_normalize_stash_prediction_keeps_interval_and_trust_fields() -> None:
    result = normalize_stash_prediction(
        {
            "predictedValue": 42.0,
            "currency": "chaos",
            "confidence": 78.0,
            "interval": {"p10": 35.0, "p90": 55.0},
            "priceRecommendationEligible": True,
            "estimateTrust": "normal",
            "estimateWarning": "fallback used",
            "fallbackReason": "no_model",
        }
    )

    assert result.predicted_price == 42.0
    assert result.price_p10 == 35.0
    assert result.price_p90 == 55.0
    assert result.price_recommendation_eligible is True
    assert result.estimate_trust == "normal"
    assert result.estimate_warning == "fallback used"
    assert result.fallback_reason == "no_model"


def test_serialize_item_to_clipboard_keeps_name_base_and_mod_lines() -> None:
    item = {
        "name": "Grim Bane",
        "typeLine": "Hubris Circlet",
        "explicitMods": ["+93 to maximum Life"],
    }

    clipboard = serialize_stash_item_to_clipboard(item)

    assert "Grim Bane" in clipboard
    assert "Hubris Circlet" in clipboard
    assert "+93 to maximum Life" in clipboard


def test_fetch_published_scan_id_returns_none_for_empty_payload() -> None:
    client = _StubClickHouse(payload="")

    assert (
        fetch_published_scan_id(
            client,
            account_name="qa-exile",
            league="Mirage",
            realm="pc",
        )
        is None
    )


def test_fetch_active_scan_returns_latest_active_row() -> None:
    client = _StubClickHouse(
        payload='{"scan_id":"scan-1","is_active":1,"started_at":"2026-03-21T10:00:00Z","updated_at":"2026-03-21T10:00:01Z"}\n'
    )

    result = fetch_active_scan(
        client,
        account_name="qa-exile",
        league="Mirage",
        realm="pc",
    )

    assert result == {
        "scanId": "scan-1",
        "isActive": True,
        "startedAt": "2026-03-21T10:00:00Z",
        "updatedAt": "2026-03-21T10:00:01Z",
    }


def test_fetch_item_history_returns_header_and_entries() -> None:
    payload = "\n".join(
        [
            json.dumps(
                {
                    "lineage_key": "sig:item-1",
                    "item_name": "Grim Bane",
                    "item_class": "Helmet",
                    "rarity": "rare",
                    "icon_url": "https://web.poecdn.com/item.png",
                    "scan_id": "scan-2",
                    "priced_at": "2026-03-21T11:00:00Z",
                    "predicted_price": 45.0,
                    "confidence": 82.0,
                    "price_p10": 39.0,
                    "price_p90": 51.0,
                    "listed_price": 40.0,
                    "currency": "chaos",
                    "price_recommendation_eligible": 1,
                    "estimate_trust": "normal",
                    "estimate_warning": "",
                    "fallback_reason": "",
                }
            )
        ]
    )
    client = _StubClickHouse(payload=payload)

    result = fetch_item_history(
        client,
        account_name="qa-exile",
        league="Mirage",
        realm="pc",
        lineage_key="sig:item-1",
    )

    assert result["fingerprint"] == "sig:item-1"
    assert result["item"]["name"] == "Grim Bane"
    assert result["item"]["itemClass"] == "Helmet"
    assert result["history"][0]["scanId"] == "scan-2"
    assert result["history"][0]["interval"] == {"p10": 39.0, "p90": 51.0}


def test_fetch_published_tabs_maps_real_poe_tab_types_to_frontend_types() -> None:
    client = _SequentialStubClickHouse(
        payloads=[
            '{"scan_id":"scan-1"}\n',
            '{"scan_id":"scan-1","status":"published","started_at":"2026-03-21T10:00:00Z","updated_at":"2026-03-21T10:10:00Z","published_at":"2026-03-21T10:10:00Z","tabs_total":3,"tabs_processed":3,"items_total":3,"items_processed":3,"error_message":""}\n',
            '{"published_at":"2026-03-21T10:10:00Z"}\n',
            "\n".join(
                [
                    '{"tab_id":"tab-c","tab_index":0,"tab_name":"Currency","tab_type":"CurrencyStash"}',
                    '{"tab_id":"tab-f","tab_index":1,"tab_name":"Fragments","tab_type":"FragmentStash"}',
                    '{"tab_id":"tab-q","tab_index":2,"tab_name":"Dump","tab_type":"QuadStash"}',
                ]
            )
            + "\n",
            "\n".join(
                [
                    '{"tab_id":"tab-c","tab_index":0,"lineage_key":"sig:c1","item_id":"c1","item_name":"Chaos Orb","item_class":"Currency","rarity":"normal","x":0,"y":0,"w":1,"h":1,"listed_price":1,"currency":"chaos","predicted_price":1,"confidence":100,"price_p10":1,"price_p90":1,"price_recommendation_eligible":1,"estimate_trust":"normal","estimate_warning":"","fallback_reason":"","icon_url":"https://example.invalid/c.png","priced_at":"2026-03-21T10:10:00Z"}',
                    '{"tab_id":"tab-f","tab_index":1,"lineage_key":"sig:f1","item_id":"f1","item_name":"Mortal Grief","item_class":"Fragment","rarity":"normal","x":7,"y":0,"w":1,"h":1,"listed_price":2,"currency":"chaos","predicted_price":2,"confidence":100,"price_p10":2,"price_p90":2,"price_recommendation_eligible":1,"estimate_trust":"normal","estimate_warning":"","fallback_reason":"","icon_url":"https://example.invalid/f.png","priced_at":"2026-03-21T10:10:00Z"}',
                    '{"tab_id":"tab-q","tab_index":2,"lineage_key":"sig:q1","item_id":"q1","item_name":"Hubris Circlet","item_class":"Helmet","rarity":"rare","x":20,"y":20,"w":2,"h":2,"listed_price":3,"currency":"chaos","predicted_price":3,"confidence":100,"price_p10":3,"price_p90":3,"price_recommendation_eligible":1,"estimate_trust":"normal","estimate_warning":"","fallback_reason":"","icon_url":"https://example.invalid/q.png","priced_at":"2026-03-21T10:10:00Z"}',
                ]
            )
            + "\n",
        ]
    )

    result = fetch_published_tabs(
        client,
        account_name="qa-exile",
        league="Mirage",
        realm="pc",
    )

    assert [tab["type"] for tab in result["stashTabs"]] == [
        "currency",
        "fragment",
        "quad",
    ]
