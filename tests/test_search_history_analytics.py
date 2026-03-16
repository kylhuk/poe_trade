from __future__ import annotations

import sys
from collections.abc import Mapping

sys.path.insert(0, '/mnt/data/devrepo')

from poe_trade.api.ops import analytics_search_history, analytics_search_suggestions
from poe_trade.db import ClickHouseClient


class _SequentialClickHouse(ClickHouseClient):
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


def test_search_suggestions_returns_ranked_candidates() -> None:
    client = _SequentialClickHouse(
        [
            '\n'.join(
                [
                    '{"item_name":"Hubris Circlet","item_kind":"base_type","match_count":42}',
                    '{"item_name":"Hubris Circlet","item_kind":"base_type","match_count":21}',
                ]
            )
        ]
    )

    payload = analytics_search_suggestions(client, query='hub')

    assert payload == {
        'query': 'hub',
        'suggestions': [
            {'itemName': 'Hubris Circlet', 'itemKind': 'base_type', 'matchCount': 42},
            {'itemName': 'Hubris Circlet', 'itemKind': 'base_type', 'matchCount': 21},
        ],
    }
    assert any('LIMIT 8' in query for query in client.queries)


def test_search_history_returns_db_driven_rows_histograms_and_filter_ranges() -> None:
    client = _SequentialClickHouse(
        [
            '{"league":"Mirage"}\n{"league":"Standard"}',
            '{"min_price":10.0,"max_price":220.0,"min_added_on":"2026-03-01 00:00:00","max_added_on":"2026-03-15 00:00:00"}',
            '{"bucket_start":0.0,"bucket_end":50.0,"count":2}',
            '{"bucket_start":"2026-03-01 00:00:00","bucket_end":"2026-03-08 00:00:00","count":4}',
            '{"item_name":"Hubris Circlet","league":"Mirage","listed_price":118.0,"added_on":"2026-03-15 12:00:00"}',
        ]
    )

    payload = analytics_search_history(
        client,
        query_params={
            'query': ['Hubris Circlet'],
            'league': ['Mirage'],
            'sort': ['listed_price'],
            'order': ['asc'],
            'price_min': ['50'],
            'price_max': ['150'],
        },
        default_league='Mirage',
    )

    assert payload['filters']['leagueOptions'] == ['Mirage', 'Standard']
    assert payload['filters']['price'] == {'min': 10.0, 'max': 220.0}
    assert payload['filters']['datetime'] == {
        'min': '2026-03-01T00:00:00Z',
        'max': '2026-03-15T00:00:00Z',
    }
    assert payload['histograms']['price'] == [{'bucketStart': 0.0, 'bucketEnd': 50.0, 'count': 2}]
    assert payload['histograms']['datetime'] == [
        {'bucketStart': '2026-03-01T00:00:00Z', 'bucketEnd': '2026-03-08T00:00:00Z', 'count': 4}
    ]
    assert payload['rows'] == [
        {
            'itemName': 'Hubris Circlet',
            'league': 'Mirage',
            'listedPrice': 118.0,
            'currency': 'chaos',
            'addedOn': '2026-03-15T12:00:00Z',
        }
    ]
    assert any('ORDER BY listed_price ASC' in query for query in client.queries)
    assert any("league = 'Mirage'" in query for query in client.queries)
