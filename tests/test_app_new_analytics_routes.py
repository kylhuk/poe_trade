from __future__ import annotations

import json
import os
from io import BytesIO
from unittest import mock

from poe_trade.api import app as api_app
from poe_trade.api.app import ApiApp
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient


def _settings() -> Settings:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_API_CORS_ORIGINS": "https://app.example.com",
        "POE_API_MAX_BODY_BYTES": "32768",
        "POE_API_LEAGUE_ALLOWLIST": "Mirage",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        return Settings.from_env()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer phase1-token", "Origin": "https://app.example.com"}


def test_search_history_route_is_available_and_returns_json(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "analytics_search_history",
        lambda client, query_params, default_league: {
            "rows": [],
            "filters": {
                "leagueOptions": ["Mirage"],
                "price": {"min": 0.0, "max": 0.0},
                "datetime": {"min": None, "max": None},
            },
            "histograms": {"price": [], "datetime": []},
        },
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/analytics/search-history?query=Hubris%20Circlet",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )

    assert response.status == 200
    assert json.loads(response.body.decode("utf-8"))["rows"] == []


def test_opportunities_route_is_available_and_returns_json(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "analytics_opportunities",
        lambda client: {
            "distributions": {
                "opportunityType": [{"opportunity_type": "bulk_flip", "count": 3}],
                "complexityTier": [{"complexity_tier": "medium", "count": 2}],
            },
            "decisionLog": {
                "rejections": [
                    {"decision_reason": "rejected_min_confidence", "count": 1}
                ],
                "suppressions": [
                    {"decision_reason": "suppressed_duplicate", "count": 1}
                ],
            },
            "topOpportunities": [{"scannerRunId": "scan-1"}],
        },
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/analytics/opportunities",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )

    payload = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert payload["topOpportunities"][0]["scannerRunId"] == "scan-1"
