"""Pydantic API schemas for Ledger workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PriceEstimate(BaseModel):
    est: float
    list_fast: float
    list_normal: float
    list_patient: float
    confidence: float
    comps_count: int


class AnalyzeRequest(BaseModel):
    source: str
    text: str
    league: Optional[str] = None
    realm: Optional[str] = None
    ts_client: Optional[str] = None
    image_b64: Optional[str] = None


class AnalyzeParsed(BaseModel):
    source_item: str
    fp_loose: str
    detected_tags: List[str]


class CraftCandidate(BaseModel):
    plan_id: str
    ev: float
    craft_cost: float
    details: str


class AnalyzeResponse(BaseModel):
    parsed: AnalyzeParsed
    price: PriceEstimate
    craft: List[CraftCandidate]
    flags: List[str]


class PricingItemRequest(BaseModel):
    league: str
    fp_loose: str
    count: int = Field(..., gt=0)


class PricingSnapshotEstimateRequest(BaseModel):
    items: List[PricingItemRequest]


class PricingSnapshotEstimateItem(BaseModel):
    league: str
    fp_loose: str
    count: int
    price: PriceEstimate
    total_est: float
    total_list_fast: float
    total_list_normal: float
    total_list_patient: float


class PricingSnapshotEstimateResponse(BaseModel):
    estimates: List[PricingSnapshotEstimateItem]


class ItemEstimateResponse(BaseModel):
    league: str
    fp_loose: str
    price: PriceEstimate


class FlipOpportunitySchema(BaseModel):
    detected_at: datetime
    league: str
    query_key: str
    buy_max: float
    sell_min: float
    expected_profit: float
    liquidity_score: float
    expiry_ts: datetime
    metadata: Dict[str, str]


class FlipListResponse(BaseModel):
    flips: List[FlipOpportunitySchema]


class CraftOpportunitySchema(BaseModel):
    detected_at: datetime
    league: str
    item_uid: str
    plan_id: str
    craft_cost: float
    est_after_price: float
    ev: float
    risk_score: float
    details: str


class CraftListResponse(BaseModel):
    crafts: List[CraftOpportunitySchema]


class SessionStartRequest(BaseModel):
    session_id: str
    realm: str
    league: str
    start_snapshot: str
    start_value: float
    tag: Optional[str] = None
    notes: Optional[str] = None


class SessionEndRequest(BaseModel):
    session_id: str
    end_snapshot: str
    end_value: float
    notes: Optional[str] = None


class SessionLeaderboardItem(BaseModel):
    session_id: str
    realm: str
    league: str
    duration_s: float
    profit_chaos: float
    profit_per_hour: float
    tag: Optional[str]
    notes: Optional[str]


class SessionLeaderboardResponse(BaseModel):
    leaderboard: List[SessionLeaderboardItem]


class StrategyKpiSummary(BaseModel):
    profit_per_hour: float
    expected_value: float
    liquidity: float
    variance: float


class StrategyBacktestResultSchema(BaseModel):
    strategy_id: str
    title: str
    claim_summary: str
    tags: List[str]
    success_rate: float
    triggers: int
    kpi_summary: StrategyKpiSummary
    kpi_targets: Dict[str, str]


class StrategyBacktestResponse(BaseModel):
    strategies: List[StrategyBacktestResultSchema]


class AdvisorPlanRequest(BaseModel):
    focus: Optional[str] = None
    mood: Optional[str] = None


class AdvisorPlanItem(BaseModel):
    tool_ref: str
    action: str
    summary: str
    priority: int


class AdvisorPlanResponse(BaseModel):
    plan_items: List[AdvisorPlanItem]


class AtlasBuildSummary(BaseModel):
    build_id: str
    name: str
    specialization: str
    node_count: int
    updated_at: datetime


class AtlasBuildDetail(AtlasBuildSummary):
    nodes: List[str]
    notes: str


class AtlasBuildExport(BaseModel):
    build_id: str
    export_url: str
    payload: Dict[str, str]


class AtlasRunRequest(BaseModel):
    build_id: str
    focus: Optional[str] = None


class AtlasRunResponse(BaseModel):
    run_id: str
    build_id: str
    status: str
    generated_at: datetime
    node_count: int
    tool_ref: str


class AtlasSurpriseResponse(BaseModel):
    message: str
    tool_ref: str


class CoachAction(BaseModel):
    tool_ref: str
    instruction: str
    priority: int


class AtlasCoachPlanResponse(BaseModel):
    actions: List[CoachAction]


class OpsIngestRate(BaseModel):
    window_minutes: int
    public_stash_records_per_minute: float
    currency_records_per_minute: float
    public_stash_last_seen: datetime
    currency_last_seen: datetime


class OpsRequestRate(BaseModel):
    requests_per_minute: float
    error_rate_percent: float
    throttled_percent: float


class OpsCheckpointHealth(BaseModel):
    cursor_name: str
    last_checkpoint: datetime
    expected_interval_minutes: int
    drift_minutes: float
    alert: bool


class OpsSLOStatus(BaseModel):
    stream_name: str
    target_minutes: int
    observed_minutes: float
    within_slo: bool
    note: Optional[str] = None


class RateLimitAlertSchema(BaseModel):
    status_code: int
    occurrences: int
    window_minutes: int
    severity: str
    alert: bool


class OpsDashboardResponse(BaseModel):
    timestamp: datetime
    ingest_rate: OpsIngestRate
    checkpoint_health: List[OpsCheckpointHealth]
    request_rate: OpsRequestRate
    slo_status: List[OpsSLOStatus]
    rate_limit_alerts: List[RateLimitAlertSchema]


class BridgeResponse(BaseModel):
    action: str
    success: bool
    message: str
    payload: Dict[str, object]


class BridgeRequest(BaseModel):
    manual_trigger: bool = False
    manual_token: Optional[str] = None


class BridgeCaptureScreenRequest(BridgeRequest):
    pass


class BridgeClipboardReadRequest(BridgeRequest):
    pass


class BridgeClipboardWriteRequest(BridgeRequest):
    value: str


class BridgeOverlayPushRequest(BridgeRequest):
    payload: Dict[str, object]
    queue_path: Optional[str] = None


class BridgeFilterWriteRequest(BridgeRequest):
    contents: str
    filter_path: Optional[str] = None
    backup_path: Optional[str] = None
