from __future__ import annotations

import json
import os
import sys
from io import BytesIO
from unittest import mock

sys.path.insert(0, '/mnt/data/devrepo')

from poe_trade.api import app as api_app
from poe_trade.api.app import ApiApp
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient


def _settings() -> Settings:
    env = {
        'POE_API_OPERATOR_TOKEN': 'phase1-token',
        'POE_API_CORS_ORIGINS': 'https://app.example.com',
        'POE_API_MAX_BODY_BYTES': '32768',
        'POE_API_LEAGUE_ALLOWLIST': 'Mirage',
    }
    with mock.patch.dict(os.environ, env, clear=True):
        return Settings.from_env()


def _auth_headers() -> dict[str, str]:
    return {'Authorization': 'Bearer phase1-token', 'Origin': 'https://app.example.com'}


def test_search_history_route_is_available_and_returns_json(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        'analytics_search_history',
        lambda client, query_params, default_league: {
            'rows': [],
            'filters': {'leagueOptions': ['Mirage'], 'price': {'min': 0.0, 'max': 0.0}, 'datetime': {'min': None, 'max': None}},
            'histograms': {'price': [], 'datetime': []},
        },
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint='http://ch'))

    response = app.handle(
        method='GET',
        raw_path='/api/v1/ops/analytics/search-history?query=Hubris%20Circlet',
        headers=_auth_headers(),
        body_reader=BytesIO(b''),
    )

    assert response.status == 200
    assert json.loads(response.body.decode('utf-8'))['rows'] == []
