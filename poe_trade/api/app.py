"""Focused FastAPI surface for ledger workflows."""

from __future__ import annotations

from typing import List

from fastapi import FastAPI, HTTPException

from ..config import constants, settings
from .schemas import (
    AdvisorPlanRequest,
    AdvisorPlanResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AtlasBuildDetail,
    AtlasBuildExport,
    AtlasBuildSummary,
    AtlasCoachPlanResponse,
    AtlasRunRequest,
    AtlasRunResponse,
    AtlasSurpriseResponse,
    CraftListResponse,
    FlipListResponse,
    ItemEstimateResponse,
    PricingSnapshotEstimateRequest,
    PricingSnapshotEstimateResponse,
    SessionEndRequest,
    SessionLeaderboardResponse,
    SessionStartRequest,
    StrategyBacktestResponse,
    OpsDashboardResponse,
    BridgeCaptureScreenRequest,
    BridgeClipboardReadRequest,
    BridgeClipboardWriteRequest,
    BridgeFilterWriteRequest,
    BridgeOverlayPushRequest,
    BridgeResponse,
)
from .services import LedgerWorkflowService

app = FastAPI(title="Wraeclast Ledger API", version="0.2.0")
service = LedgerWorkflowService()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    cfg = settings.get_settings()
    return {
        "status": "ok",
        "clickhouse": cfg.clickhouse_url,
        "realm": cfg.realms[0] if cfg.realms else "unknown",
    }


@app.get("/v1/meta/services")
def list_services() -> dict[str, List[str]]:
    return {
        "services": constants.SERVICE_NAMES,
        "optional": constants.OPTIONAL_SERVICES,
    }


@app.post("/v1/item/analyze", response_model=AnalyzeResponse)
def analyze_item(request: AnalyzeRequest) -> AnalyzeResponse:
    return service.analyze_item(
        source=request.source,
        text=request.text,
        league=request.league,
        realm=request.realm,
        ts_client=request.ts_client,
        image_b64=request.image_b64,
    )


@app.post("/v1/pricing/snapshot-estimate", response_model=PricingSnapshotEstimateResponse)
def pricing_snapshot(request: PricingSnapshotEstimateRequest) -> PricingSnapshotEstimateResponse:
    return service.pricing_snapshot(request)


@app.post("/v1/stash/price", response_model=PricingSnapshotEstimateResponse)
def stash_price(request: PricingSnapshotEstimateRequest) -> PricingSnapshotEstimateResponse:
    return service.pricing_snapshot(request)


@app.get("/v1/pricing/item-estimate", response_model=ItemEstimateResponse)
def pricing_item_estimate(fp_loose: str, league: str) -> ItemEstimateResponse:
    return service.item_estimate(fp_loose=fp_loose, league=league)


@app.get("/v1/flips", response_model=FlipListResponse)
def flips() -> FlipListResponse:
    return service.flips()


@app.get("/v1/flips/top", response_model=FlipListResponse)
def flips_top() -> FlipListResponse:
    return service.flips()


@app.get("/v1/crafts", response_model=CraftListResponse)
def crafts() -> CraftListResponse:
    return service.crafts()


@app.get("/v1/crafts/top", response_model=CraftListResponse)
def crafts_top() -> CraftListResponse:
    return service.crafts()


@app.post("/v1/sessions/start")
def start_session(request: SessionStartRequest) -> dict[str, str]:
    return service.start_session(request)


@app.post("/v1/sessions/end")
def end_session(request: SessionEndRequest) -> dict[str, str]:
    return service.end_session(request)


@app.get("/v1/sessions/leaderboard", response_model=SessionLeaderboardResponse)
def session_leaderboard() -> SessionLeaderboardResponse:
    return service.leaderboard()


@app.get("/v1/strategies/backtest", response_model=StrategyBacktestResponse)
def strategy_backtest() -> StrategyBacktestResponse:
    return service.strategy_backtest()


@app.post("/v1/advisor/daily-plan", response_model=AdvisorPlanResponse)
def advisor_plan(request: AdvisorPlanRequest) -> AdvisorPlanResponse:
    return service.advisor_plan(focus=request.focus, mood=request.mood)


@app.get("/v1/atlas/builds", response_model=List[AtlasBuildSummary])
def atlas_builds() -> List[AtlasBuildSummary]:
    return service.atlas_builds()


@app.get("/v1/builds/search", response_model=List[AtlasBuildSummary])
def atlas_builds_search(query: str | None = None) -> List[AtlasBuildSummary]:
    return service.atlas_builds()


@app.get("/v1/atlas/builds/{build_id}", response_model=AtlasBuildDetail)
def atlas_build_detail(build_id: str) -> AtlasBuildDetail:
    detail = service.atlas_build_detail(build_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="build not found")
    return detail


@app.get("/v1/builds/{build_id}", response_model=AtlasBuildDetail)
def atlas_build_detail_alias(build_id: str) -> AtlasBuildDetail:
    return atlas_build_detail(build_id)


@app.get("/v1/atlas/builds/{build_id}/export", response_model=AtlasBuildExport)
def atlas_build_export(build_id: str) -> AtlasBuildExport:
    export = service.atlas_export(build_id)
    if export is None:
        raise HTTPException(status_code=404, detail="build not found")
    return export


@app.get("/v1/builds/{build_id}/export", response_model=AtlasBuildExport)
def atlas_build_export_alias(build_id: str) -> AtlasBuildExport:
    return atlas_build_export(build_id)


@app.post("/v1/atlas/runs", response_model=AtlasRunResponse)
def atlas_run(request: AtlasRunRequest) -> AtlasRunResponse:
    run = service.atlas_run(request)
    if run is None:
        raise HTTPException(status_code=404, detail="build not found")
    return run


@app.post("/v1/atlas/surprise", response_model=AtlasSurpriseResponse)
def atlas_surprise() -> AtlasSurpriseResponse:
    return service.atlas_surprise()


@app.post("/v1/atlas/coach/plan", response_model=AtlasCoachPlanResponse)
def atlas_coach_plan() -> AtlasCoachPlanResponse:
    return service.atlas_coach()


@app.get("/v1/ops/dashboard", response_model=OpsDashboardResponse)
def ops_dashboard() -> OpsDashboardResponse:
    return service.ops_dashboard()



@app.post("/v1/bridge/capture-screen", response_model=BridgeResponse)
def bridge_capture_screen(request: BridgeCaptureScreenRequest) -> BridgeResponse:
    return service.bridge_capture_screen(request)


@app.post("/v1/bridge/clipboard/read", response_model=BridgeResponse)
def bridge_clipboard_read(request: BridgeClipboardReadRequest) -> BridgeResponse:
    return service.bridge_clipboard_read(request)


@app.post("/v1/bridge/clipboard/write", response_model=BridgeResponse)
def bridge_clipboard_write(request: BridgeClipboardWriteRequest) -> BridgeResponse:
    return service.bridge_clipboard_write(request)


@app.post("/v1/bridge/overlay/push", response_model=BridgeResponse)
def bridge_overlay_push(request: BridgeOverlayPushRequest) -> BridgeResponse:
    return service.bridge_overlay_push(request)


@app.post("/v1/bridge/filter/write", response_model=BridgeResponse)
def bridge_filter_write(request: BridgeFilterWriteRequest) -> BridgeResponse:
    return service.bridge_filter_write(request)


@app.get("/v1/meta/health")
def meta_health() -> dict[str, str]:
    return healthz()



def get_app() -> FastAPI:
    return app
