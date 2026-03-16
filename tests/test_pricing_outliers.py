from __future__ import annotations

import sys
from collections.abc import Mapping

sys.path.insert(0, '/mnt/data/devrepo')

from poe_trade.api.ops import analytics_pricing_outliers
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


def test_pricing_outliers_returns_item_and_affix_summaries_with_weekly_counts() -> None:
    client = _SequentialClickHouse(
        [
            '\n'.join(
                [
                    '{"item_name":"Hubris Circlet","affix_analyzed":"","p10":80.0,"median":120.0,"p90":210.0,"items_per_week":1.5,"items_total":30,"analysis_level":"item"}',
                    '{"item_name":"Hubris Circlet","affix_analyzed":"+93 to maximum Life","p10":95.0,"median":145.0,"p90":240.0,"items_per_week":0.5,"items_total":12,"analysis_level":"affix"}',
                ]
            ),
            '{"week_start":"2026-03-02 00:00:00","too_cheap_count":3}\n{"week_start":"2026-03-09 00:00:00","too_cheap_count":2}',
        ]
    )

    payload = analytics_pricing_outliers(
        client,
        query_params={'league': ['Mirage'], 'limit': ['50']},
        default_league='Mirage',
    )

    assert payload['rows'] == [
        {
            'itemName': 'Hubris Circlet',
            'affixAnalyzed': '',
            'p10': 80.0,
            'median': 120.0,
            'p90': 210.0,
            'itemsPerWeek': 1.5,
            'itemsTotal': 30,
            'analysisLevel': 'item',
        },
        {
            'itemName': 'Hubris Circlet',
            'affixAnalyzed': '+93 to maximum Life',
            'p10': 95.0,
            'median': 145.0,
            'p90': 240.0,
            'itemsPerWeek': 0.5,
            'itemsTotal': 12,
            'analysisLevel': 'affix',
        },
    ]
    assert payload['weekly'] == [
        {'weekStart': '2026-03-02T00:00:00Z', 'tooCheapCount': 3},
        {'weekStart': '2026-03-09T00:00:00Z', 'tooCheapCount': 2},
    ]
    assert any('quantileTDigest(0.1)' in query for query in client.queries)
    assert any('ml_item_mod_tokens_v1' in query for query in client.queries)
