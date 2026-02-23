"""Shared API client for Ledger UI pages."""

from __future__ import annotations

import os
from typing import Sequence

import httpx

from ..api import services
from ..api.schemas import (
    AdvisorPlanRequest,
    AdvisorPlanResponse,
    AtlasBuildDetail,
    AtlasBuildSummary,
    AtlasCoachPlanResponse,
    AtlasSurpriseResponse,
    CraftListResponse,
    FlipListResponse,
    PricingItemRequest,
    PricingSnapshotEstimateRequest,
    PricingSnapshotEstimateResponse,
    SessionLeaderboardResponse,
)

DEFAULT_LEAGUE = "Sanctum"
DEFAULT_SNAPSHOT_ITEMS = (
    PricingItemRequest(league=DEFAULT_LEAGUE, fp_loose="divine", count=1),
    PricingItemRequest(league=DEFAULT_LEAGUE, fp_loose="essence", count=1),
    PricingItemRequest(league=DEFAULT_LEAGUE, fp_loose="fossil", count=1),
)


def _env_bool_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes"}


class LedgerApiClient:
    """API-neutral client for Ledger UI renderers."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        local_mode: bool | None = None,
    ) -> None:
        self.base_url = base_url or "http://localhost:8000"
        self.local_mode = (
            local_mode
            if local_mode is not None
            else _env_bool_flag("POE_LEDGER_UI_LOCAL")
        )
        self._http_client: httpx.Client | None = None
        self._service: services.LedgerWorkflowService | None = None
        if self.local_mode:
            self._service = services.LedgerWorkflowService()

    def _ensure_http(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(base_url=self.base_url, timeout=10.0)
        return self._http_client

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        response = self._ensure_http().request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def market_overview(self) -> list[dict[str, float | str]]:
        snapshot = self.stash_pricing()
        rows: list[dict[str, float | str]] = []
        for estimate in snapshot.estimates:
            rows.append(
                {
                    "fp_loose": estimate.fp_loose,
                    "league": estimate.league,
                    "count": estimate.count,
                    "estimate": round(estimate.price.est, 3),
                    "fast": round(estimate.price.list_fast, 3),
                    "patient": round(estimate.price.list_patient, 3),
                    "confidence": round(estimate.price.confidence, 3),
                }
            )
        return rows

    def stash_pricing(
        self,
        items: Sequence[PricingItemRequest] | None = None,
    ) -> PricingSnapshotEstimateResponse:
        request = PricingSnapshotEstimateRequest(items=list(items or DEFAULT_SNAPSHOT_ITEMS))
        if self.local_mode:
            assert self._service is not None
            return self._service.pricing_snapshot(request)
        payload = self._request("POST", "/v1/pricing/snapshot-estimate", json=request.model_dump())
        return PricingSnapshotEstimateResponse(**payload)

    def flips(self) -> FlipListResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.flips()
        payload = self._request("GET", "/v1/flips")
        return FlipListResponse(**payload)

    def crafts(self) -> CraftListResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.crafts()
        payload = self._request("GET", "/v1/crafts")
        return CraftListResponse(**payload)

    def leaderboard(self) -> SessionLeaderboardResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.leaderboard()
        payload = self._request("GET", "/v1/sessions/leaderboard")
        return SessionLeaderboardResponse(**payload)

    def atlas_builds(self) -> list[AtlasBuildSummary]:
        if self.local_mode:
            assert self._service is not None
            return self._service.atlas_builds()
        payload = self._request("GET", "/v1/atlas/builds")
        return [AtlasBuildSummary(**entry) for entry in payload]

    def atlas_build_detail(self, build_id: str) -> AtlasBuildDetail | None:
        if self.local_mode:
            assert self._service is not None
            return self._service.atlas_build_detail(build_id)
        try:
            payload = self._request("GET", f"/v1/atlas/builds/{build_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return AtlasBuildDetail(**payload)

    def atlas_surprise(self) -> AtlasSurpriseResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.atlas_surprise()
        payload = self._request("POST", "/v1/atlas/surprise")
        return AtlasSurpriseResponse(**payload)

    def atlas_coach(self) -> AtlasCoachPlanResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.atlas_coach()
        payload = self._request("POST", "/v1/atlas/coach/plan")
        return AtlasCoachPlanResponse(**payload)

    def advisor_daily_plan(
        self,
        focus: str | None = None,
        mood: str | None = None,
    ) -> AdvisorPlanResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.advisor_plan(focus=focus, mood=mood)
        request = AdvisorPlanRequest(focus=focus, mood=mood)
        payload = self._request("POST", "/v1/advisor/daily-plan", json=request.model_dump())
        return AdvisorPlanResponse(**payload)

    def __del__(self) -> None:
        if self._http_client is not None:
            self._http_client.close()


__all__ = ["LedgerApiClient"]
