from __future__ import annotations

import sys
from collections.abc import Mapping

sys.path.insert(0, '/mnt/data/devrepo')

from poe_trade.api import ops as api_ops
from poe_trade.db import ClickHouseClient


RARE_HELM = '''Rarity: Rare
Grim Bane
Hubris Circlet
--------
Quality: +20%
Item Level: 86
--------
+2 to Level of Socketed Minion Gems
+93 to maximum Life
'''


class _RecordingClickHouse(ClickHouseClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(endpoint='http://clickhouse')
        self.responses = list(responses)
        self.queries: list[str] = []

    def execute(self, query: str, settings: Mapping[str, str] | None = None) -> str:  # type: ignore[override]
        del settings
        self.queries.append(query)
        if self.responses:
            return self.responses.pop(0)
        return ''


def test_price_check_payload_uses_base_type_lookup_and_returns_recent_comparables(monkeypatch) -> None:
    monkeypatch.setattr(
        api_ops,
        'fetch_predict_one',
        lambda _client, league, request_payload: {
            'predictedValue': 120.0,
            'currency': 'chaos',
            'confidence': 0.64,
            'interval': {'p10': 90.0, 'p90': 150.0},
            'saleProbabilityPercent': 58.0,
            'priceRecommendationEligible': True,
            'fallbackReason': '',
        },
    )
    client = _RecordingClickHouse(
        [
            '\n'.join(
                [
                    '{"item_name":"Hubris Circlet","league":"Mirage","listed_price":118.0,"added_on":"2026-03-15 12:00:00"}',
                    '{"item_name":"Hubris Circlet","league":"Mirage","listed_price":125.0,"added_on":"2026-03-14 12:00:00"}',
                ]
            )
        ]
    )

    payload = api_ops.price_check_payload(client, league='Mirage', item_text=RARE_HELM)

    assert payload['comparables'] == [
        {
            'name': 'Hubris Circlet',
            'price': 118.0,
            'currency': 'chaos',
            'league': 'Mirage',
            'addedOn': '2026-03-15T12:00:00Z',
        },
        {
            'name': 'Hubris Circlet',
            'price': 125.0,
            'currency': 'chaos',
            'league': 'Mirage',
            'addedOn': '2026-03-14T12:00:00Z',
        },
    ]
    assert any("base_type = 'Hubris Circlet'" in query for query in client.queries)
    assert not any('Grim Bane' in query for query in client.queries)
