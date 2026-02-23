"""Deterministic service layer for ledger workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from typing import Dict, List

from ..analytics.flip_finder import FlipOpportunity, find_flip_opportunities
from ..analytics.forge_oracle import CraftAction, ForgeOracle
from ..analytics.price_stats import compute_price_stats
from ..analytics.session_ledger import SessionSnapshot, summarize_session
from ..analytics.strategy_backtest import StrategyRegistry
from ..atlas import UpgradeStep
from ..bridge.local_bridge import (
    BridgeResult,
    ClipboardAdapter,
    OCRAdapter,
    capture_screen_text,
    clipboard_read,
    clipboard_write,
    push_overlay_payload,
    write_item_filter,
)
from ..etl.models import ListingCanonical
from .atlas_orchestrator import AtlasOrchestrator
from .atlas_types import AtlasBuildRecord
from ..ops.slo import (
    detect_checkpoint_drift,
    detect_repeated_rate_errors,
    evaluate_ingest_freshness,
)

try:  # pragma: no cover - platform/runtime optional dependency
    from ..exilelens.system_clipboard import ClipboardUnavailable, SystemClipboard

    _clipboard_import_error: str | None = None
except Exception as exc:  # pragma: no cover
    ClipboardUnavailable = RuntimeError  # type: ignore[assignment]
    SystemClipboard = None  # type: ignore[assignment]
    _clipboard_import_error = str(exc)

try:  # pragma: no cover - platform/runtime optional dependency
    from ..exilelens.system_ocr import OcrUnavailable, SystemOCR

    _ocr_import_error: str | None = None
except Exception as exc:  # pragma: no cover
    OcrUnavailable = RuntimeError  # type: ignore[assignment]
    SystemOCR = None  # type: ignore[assignment]
    _ocr_import_error = str(exc)

from .schemas import (
    AdvisorPlanItem,
    AdvisorPlanResponse,
    AnalyzeParsed,
    AnalyzeResponse,
    AtlasBuildDetail,
    AtlasBuildExport,
    AtlasBuildSummary,
    AtlasCoachPlanResponse,
    AtlasRunRequest,
    AtlasRunResponse,
    AtlasSurpriseResponse,
    CoachAction,
    CraftCandidate,
    CraftListResponse,
    CraftOpportunitySchema,
    BridgeCaptureScreenRequest,
    BridgeClipboardReadRequest,
    BridgeClipboardWriteRequest,
    BridgeFilterWriteRequest,
    BridgeOverlayPushRequest,
    BridgeResponse,
    FlipListResponse,
    FlipOpportunitySchema,
    ItemEstimateResponse,
    PricingSnapshotEstimateItem,
    PricingSnapshotEstimateRequest,
    PricingSnapshotEstimateResponse,
    PriceEstimate,
    SessionEndRequest,
    SessionLeaderboardItem,
    SessionLeaderboardResponse,
    SessionStartRequest,
    StrategyBacktestResultSchema,
    StrategyBacktestResponse,
    StrategyKpiSummary,
    OpsCheckpointHealth,
    OpsDashboardResponse,
    OpsIngestRate,
    OpsRequestRate,
    OpsSLOStatus,
    RateLimitAlertSchema,
)


_OVERLAY_QUEUE_PATH = "/tmp/overlay_payload_queue.ndjson"
_FILTER_PATH = "/tmp/manual.filter"
_FILTER_BACKUP_PATH = "/tmp/manual.filter.bak"
_MANUAL_REQUIRED_MESSAGE = "manual trigger required for local bridge actions"


@dataclass(frozen=True)
class ActiveSession:
    session_id: str
    realm: str
    league: str
    start_snapshot: str
    start_value: float
    start_time: datetime
    tag: str | None = None
    notes: str | None = None


class LedgerWorkflowService:
    def __init__(self) -> None:
        self._price_samples: Dict[str, List[float]] = {
            "divine": [25.0, 26.0, 27.5, 28.3, 29.9],
            "essence": [0.19, 0.24, 0.31, 0.27, 0.34],
            "fossil": [3.0, 3.1, 3.4, 3.2, 3.8],
        }
        self._price_stats: Dict[str, Dict[str, float]] = {
            key: compute_price_stats(values)
            for key, values in self._price_samples.items()
        }
        self._strategy_stats = compute_price_stats(
            [value for prices in self._price_samples.values() for value in prices]
        )
        now = datetime.now(timezone.utc)
        base_time = now - timedelta(hours=1)
        self._listings: List[ListingCanonical] = [
            ListingCanonical(
                listing_uid="flip-01",
                item_uid="item-01",
                listed_at=base_time,
                league="Sanctum",
                price_amount=0.18,
                price_currency="chaos",
                price_chaos=0.18,
                seller_id="seller-01",
                seller_meta="seed",
                last_seen_at=now,
                fp_loose="essence",
                payload_json="{}",
            ),
            ListingCanonical(
                listing_uid="flip-02",
                item_uid="item-02",
                listed_at=base_time,
                league="Sanctum",
                price_amount=2.5,
                price_currency="chaos",
                price_chaos=2.5,
                seller_id="seller-02",
                seller_meta="seed",
                last_seen_at=now,
                fp_loose="fossil",
                payload_json="{}",
            ),
        ]
        actions = (
            CraftAction(name="annul", cost=0.5, value_gain=1.1),
            CraftAction(name="vaal", cost=0.45, value_gain=0.9),
            CraftAction(name="regal", cost=0.35, value_gain=0.7),
        )
        self._forge_oracle = ForgeOracle(actions)
        session_anchor = datetime(2025, 2, 15, 10, 0, tzinfo=timezone.utc)
        snapshot_a = SessionSnapshot(
            session_id="session-01",
            realm="pc",
            league="Sanctum",
            start_snapshot="start-a",
            end_snapshot="end-a",
            start_value=18.0,
            end_value=45.0,
            start_time=session_anchor,
            end_time=session_anchor + timedelta(hours=2, minutes=15),
            tag="expedition",
            notes="seeded run",
        )
        snapshot_b = SessionSnapshot(
            session_id="session-02",
            realm="pc",
            league="Sanctum",
            start_snapshot="start-b",
            end_snapshot="end-b",
            start_value=12.0,
            end_value=29.5,
            start_time=session_anchor + timedelta(hours=3),
            end_time=session_anchor + timedelta(hours=5, minutes=5),
            tag="delve",
            notes="seeded delve",
        )
        self._completed_sessions: List[SessionSnapshot] = [snapshot_a, snapshot_b]
        self._leaderboard = [
            summarize_session(snapshot) for snapshot in self._completed_sessions
        ]
        self._active_sessions: Dict[str, ActiveSession] = {}
        self._strategy_registry = StrategyRegistry.with_builtin_strategies()
        self._deterministic_anchor = datetime(2025, 2, 15, 8, 0, tzinfo=timezone.utc)
        self._atlas_orchestrator = AtlasOrchestrator(self._deterministic_anchor)
        self._clipboard_adapter: ClipboardAdapter | None = None
        self._ocr_adapter: OCRAdapter | None = None

    def analyze_item(
        self,
        source: str,
        text: str,
        league: str | None,
        realm: str | None,
        ts_client: str | None,
        image_b64: str | None,
    ) -> AnalyzeResponse:
        fp_loose = self._infer_fp_loose(text)
        stats = self._price_stats.get(fp_loose, self._strategy_stats)
        parsed = AnalyzeParsed(
            source_item=source,
            fp_loose=fp_loose,
            detected_tags=self._detect_tags(text, league, realm),
        )
        craft_candidates = self._build_craft_candidates(fp_loose)
        flags = [] if image_b64 is None else ["has_image"]
        price = self._build_price_estimate(fp_loose, stats)
        return AnalyzeResponse(
            parsed=parsed, price=price, craft=craft_candidates, flags=flags
        )

    def pricing_snapshot(
        self, request: PricingSnapshotEstimateRequest
    ) -> PricingSnapshotEstimateResponse:
        estimates: List[PricingSnapshotEstimateItem] = []
        for item in request.items:
            stats = self._price_stats.get(item.fp_loose, self._strategy_stats)
            price = self._build_price_estimate(item.fp_loose, stats)
            totals = self._scale_price(price, item.count)
            estimates.append(
                PricingSnapshotEstimateItem(
                    league=item.league,
                    fp_loose=item.fp_loose,
                    count=item.count,
                    price=price,
                    total_est=totals["est"],
                    total_list_fast=totals["list_fast"],
                    total_list_normal=totals["list_normal"],
                    total_list_patient=totals["list_patient"],
                )
            )
        return PricingSnapshotEstimateResponse(estimates=estimates)

    def item_estimate(self, fp_loose: str, league: str) -> ItemEstimateResponse:
        stats = self._price_stats.get(fp_loose, self._strategy_stats)
        price = self._build_price_estimate(fp_loose, stats)
        return ItemEstimateResponse(league=league, fp_loose=fp_loose, price=price)

    def flips(self) -> FlipListResponse:
        seen: set[str] = set()
        opportunities: list[FlipOpportunity] = []
        for stats in self._price_stats.values():
            for opportunity in find_flip_opportunities(
                self._listings, stats, reference_ts=self._deterministic_anchor
            ):
                if opportunity.query_key in seen:
                    continue
                seen.add(opportunity.query_key)
                opportunities.append(opportunity)
        flips = [
            self._from_flip_opportunity(opportunity) for opportunity in opportunities
        ]
        return FlipListResponse(flips=flips)

    def crafts(self) -> CraftListResponse:
        plan = self._forge_oracle.best_plan(depth=2)
        if plan is None:
            return CraftListResponse(crafts=[])
        opportunity = self._forge_oracle.evaluate_plan(
            league="Sanctum",
            item_uid="item-01",
            current_price=1.0,
            plan=plan,
            detected_at=self._deterministic_anchor,
        )
        craft = CraftOpportunitySchema(
            detected_at=opportunity.detected_at,
            league=opportunity.league,
            item_uid=opportunity.item_uid,
            plan_id=opportunity.plan_id,
            craft_cost=opportunity.craft_cost,
            est_after_price=opportunity.est_after_price,
            ev=opportunity.ev,
            risk_score=opportunity.risk_score,
            details=opportunity.details,
        )
        return CraftListResponse(crafts=[craft])

    def start_session(self, request: SessionStartRequest) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        self._active_sessions[request.session_id] = ActiveSession(
            session_id=request.session_id,
            realm=request.realm,
            league=request.league,
            start_snapshot=request.start_snapshot,
            start_value=request.start_value,
            start_time=now,
            tag=request.tag,
            notes=request.notes,
        )
        return {"session_id": request.session_id, "status": "started"}

    def end_session(self, request: SessionEndRequest) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        active = self._active_sessions.pop(request.session_id, None)
        if active is None:
            return {"session_id": request.session_id, "status": "unknown"}
        snapshot = SessionSnapshot(
            session_id=active.session_id,
            realm=active.realm,
            league=active.league,
            start_snapshot=active.start_snapshot,
            end_snapshot=request.end_snapshot,
            start_value=active.start_value,
            end_value=request.end_value,
            start_time=active.start_time,
            end_time=now,
            tag=active.tag,
            notes=request.notes or active.notes,
        )
        self._completed_sessions.append(snapshot)
        self._leaderboard.append(summarize_session(snapshot))
        return {"session_id": request.session_id, "status": "ended"}

    def leaderboard(self) -> SessionLeaderboardResponse:
        ordered = sorted(
            self._leaderboard, key=lambda entry: entry.profit_per_hour, reverse=True
        )
        items = [SessionLeaderboardItem(**entry.to_row()) for entry in ordered]
        return SessionLeaderboardResponse(leaderboard=items)

    def strategy_backtest(self) -> StrategyBacktestResponse:
        results = self._strategy_registry.backtest(
            self._completed_sessions, self._strategy_stats
        )
        strategies = [self._from_strategy_result(result) for result in results]
        return StrategyBacktestResponse(strategies=strategies)

    def advisor_plan(self, focus: str | None, mood: str | None) -> AdvisorPlanResponse:
        flips = self.flips().flips
        crafts = self.crafts().crafts
        plan_items: List[AdvisorPlanItem] = []
        if flips:
            plan_items.append(
                AdvisorPlanItem(
                    tool_ref=f"tool:flip:{flips[0].query_key}",
                    action="Reprice fast-moving items",
                    summary="Use flip data to re-list below recent sells",
                    priority=1,
                )
            )
        if crafts:
            plan_items.append(
                AdvisorPlanItem(
                    tool_ref=f"tool:craft:{crafts[0].plan_id}",
                    action="Execute curated craft",
                    summary="Leverage craft plan to nudge EV",
                    priority=2,
                )
            )
        return AdvisorPlanResponse(plan_items=plan_items)

    def atlas_builds(self) -> List[AtlasBuildSummary]:
        return [
            self._build_summary(state.record)
            for state in self._atlas_orchestrator.build_states()
        ]

    def atlas_build_detail(self, build_id: str) -> AtlasBuildDetail | None:
        state = self._atlas_orchestrator.build_state(build_id)
        if state is None:
            return None
        record = state.record
        return AtlasBuildDetail(
            build_id=record.build_id,
            name=record.name,
            specialization=record.specialization,
            node_count=record.node_count,
            updated_at=record.updated_at,
            nodes=record.nodes,
            notes=record.notes,
        )

    def atlas_export(self, build_id: str) -> AtlasBuildExport | None:
        payload = self._atlas_orchestrator.export_payload(build_id)
        if payload is None:
            return None
        return AtlasBuildExport(
            build_id=build_id,
            export_url=f"https://atlas.export/{build_id}",
            payload=payload,
        )

    def atlas_run(self, request: AtlasRunRequest) -> AtlasRunResponse | None:
        run = self._atlas_orchestrator.run_build(request.build_id, request.focus)
        if run is None:
            return None
        return AtlasRunResponse(
            run_id=run.run_id,
            build_id=run.build_id,
            status=run.status,
            generated_at=run.generated_at,
            node_count=run.node_count,
            tool_ref=f"tool:atlas:run:{run.run_id}",
        )

    def atlas_surprise(self) -> AtlasSurpriseResponse:
        tool_ref = "tool:atlas:run:seed"
        last_run = self._atlas_orchestrator.last_run()
        if last_run:
            tool_ref = f"tool:atlas:run:{last_run.run_id}"
        return AtlasSurpriseResponse(
            message=self._atlas_orchestrator.surprise_message(),
            tool_ref=tool_ref,
        )

    def atlas_coach(self) -> AtlasCoachPlanResponse:
        actions: List[CoachAction] = []
        steps: List[UpgradeStep] = self._atlas_orchestrator.coach_steps()
        for index, step in enumerate(steps, start=1):
            priority = max(1, int(round(step.priority * 10)))
            tool_ref = f"tool:atlas:coach:{index}:{step.name.replace(' ', '_').lower()}"
            actions.append(
                CoachAction(
                    tool_ref=tool_ref,
                    instruction=step.description,
                    priority=priority,
                )
            )
        if not actions:
            actions.append(
                CoachAction(
                    tool_ref="tool:atlas:coach:seed",
                    instruction="BuildAtlas needs a run before coaching can start",
                    priority=1,
                )
            )
        return AtlasCoachPlanResponse(actions=actions)

    def ops_dashboard(self) -> OpsDashboardResponse:
        """Return deterministic ops telemetry for the internal dashboard."""

        reference = self._deterministic_anchor + timedelta(minutes=7)
        public_last = reference - timedelta(minutes=8)
        currency_last = reference - timedelta(minutes=54)
        slos = evaluate_ingest_freshness(public_last, currency_last, reference)
        checkpoint = detect_checkpoint_drift(
            cursor_name="stash_cursor",
            last_checkpoint=reference - timedelta(minutes=12),
            reference=reference,
            expected_interval_minutes=10,
        )
        error_counts = {429: 7, 404: 9, 408: 3}
        rate_alerts = detect_repeated_rate_errors(error_counts, window_minutes=30)
        ingest_rate = OpsIngestRate(
            window_minutes=15,
            public_stash_records_per_minute=110.5,
            currency_records_per_minute=32.2,
            public_stash_last_seen=public_last,
            currency_last_seen=currency_last,
        )
        request_rate = OpsRequestRate(
            requests_per_minute=42.7,
            error_rate_percent=1.8,
            throttled_percent=0.4,
        )
        return OpsDashboardResponse(
            timestamp=reference,
            ingest_rate=ingest_rate,
            checkpoint_health=[
                OpsCheckpointHealth(
                    cursor_name=checkpoint.cursor_name,
                    last_checkpoint=checkpoint.last_checkpoint,
                    expected_interval_minutes=checkpoint.expected_interval_minutes,
                    drift_minutes=checkpoint.drift_minutes,
                    alert=checkpoint.alert,
                )
            ],
            request_rate=request_rate,
            slo_status=[
                OpsSLOStatus(
                    stream_name=status.stream_name,
                    target_minutes=status.target_minutes,
                    observed_minutes=status.observed_minutes,
                    within_slo=status.within_slo,
                    note=status.note,
                )
                for status in slos
            ],
            rate_limit_alerts=[
                RateLimitAlertSchema(
                    status_code=entry.status_code,
                    occurrences=entry.occurrences,
                    window_minutes=entry.window_minutes,
                    severity=entry.severity,
                    alert=entry.alert,
                )
                for entry in rate_alerts
            ],
        )

    def bridge_capture_screen(
        self, request: BridgeCaptureScreenRequest
    ) -> BridgeResponse:
        blocked = self._manual_bridge_guard(
            action="capture_screen_text",
            manual_trigger=request.manual_trigger,
            manual_token=request.manual_token,
        )
        if blocked is not None:
            return blocked

        ocr, error = self._resolve_ocr_adapter()
        if error is not None or ocr is None:
            return self._bridge_failure_response(
                action="capture_screen_text",
                manual_trigger=request.manual_trigger,
                message=error or "ocr unavailable",
            )

        return self._bridge_response_from_result(
            capture_screen_text(ocr=ocr, manual_trigger=request.manual_trigger)
        )

    def bridge_clipboard_read(
        self, request: BridgeClipboardReadRequest
    ) -> BridgeResponse:
        blocked = self._manual_bridge_guard(
            action="clipboard_read",
            manual_trigger=request.manual_trigger,
            manual_token=request.manual_token,
        )
        if blocked is not None:
            return blocked

        clipboard, error = self._resolve_clipboard_adapter()
        if error is not None or clipboard is None:
            return self._bridge_failure_response(
                action="clipboard_read",
                manual_trigger=request.manual_trigger,
                message=error or "clipboard unavailable",
            )

        return self._bridge_response_from_result(
            clipboard_read(clipboard=clipboard, manual_trigger=request.manual_trigger)
        )

    def bridge_clipboard_write(
        self, request: BridgeClipboardWriteRequest
    ) -> BridgeResponse:
        blocked = self._manual_bridge_guard(
            action="clipboard_write",
            manual_trigger=request.manual_trigger,
            manual_token=request.manual_token,
        )
        if blocked is not None:
            return blocked

        clipboard, error = self._resolve_clipboard_adapter()
        if error is not None or clipboard is None:
            return self._bridge_failure_response(
                action="clipboard_write",
                manual_trigger=request.manual_trigger,
                message=error or "clipboard unavailable",
            )

        return self._bridge_response_from_result(
            clipboard_write(
                clipboard=clipboard,
                value=request.value,
                manual_trigger=request.manual_trigger,
            )
        )

    def bridge_overlay_push(self, request: BridgeOverlayPushRequest) -> BridgeResponse:
        blocked = self._manual_bridge_guard(
            action="push_overlay_payload",
            manual_trigger=request.manual_trigger,
            manual_token=request.manual_token,
        )
        if blocked is not None:
            return blocked

        queue_path = request.queue_path or _OVERLAY_QUEUE_PATH
        return self._bridge_response_from_result(
            push_overlay_payload(
                queue_path=queue_path,
                payload=request.payload,
                manual_trigger=request.manual_trigger,
            )
        )

    def bridge_filter_write(self, request: BridgeFilterWriteRequest) -> BridgeResponse:
        blocked = self._manual_bridge_guard(
            action="write_item_filter",
            manual_trigger=request.manual_trigger,
            manual_token=request.manual_token,
        )
        if blocked is not None:
            return blocked

        filter_path = request.filter_path or _FILTER_PATH
        if request.backup_path is None:
            backup_path: str | None = _FILTER_BACKUP_PATH
        elif request.backup_path == "":
            backup_path = None
        else:
            backup_path = request.backup_path

        return self._bridge_response_from_result(
            write_item_filter(
                filter_path=filter_path,
                contents=request.contents,
                manual_trigger=request.manual_trigger,
                backup_path=backup_path,
            )
        )

    def _resolve_clipboard_adapter(self) -> tuple[ClipboardAdapter | None, str | None]:
        if _clipboard_import_error is not None:
            return None, f"clipboard helper unavailable: {_clipboard_import_error}"

        if self._clipboard_adapter is not None:
            return self._clipboard_adapter, None

        if SystemClipboard is None:
            return None, "clipboard helper unavailable"

        try:
            self._clipboard_adapter = SystemClipboard()
        except ClipboardUnavailable as exc:
            self._clipboard_adapter = None
            return None, f"clipboard unavailable: {exc}"
        return self._clipboard_adapter, None

    def _resolve_ocr_adapter(self) -> tuple[OCRAdapter | None, str | None]:
        if _ocr_import_error is not None:
            return None, f"ocr helper unavailable: {_ocr_import_error}"

        if self._ocr_adapter is not None:
            return self._ocr_adapter, None

        if SystemOCR is None:
            return None, "ocr helper unavailable"

        try:
            self._ocr_adapter = SystemOCR()
        except OcrUnavailable as exc:
            self._ocr_adapter = None
            return None, f"ocr unavailable: {exc}"
        return self._ocr_adapter, None

    @staticmethod
    def _bridge_response_from_result(result: BridgeResult) -> BridgeResponse:
        return BridgeResponse(
            action=result.action,
            success=result.success,
            message=result.message,
            payload=result.payload,
        )

    @staticmethod
    def _bridge_failure_response(
        *, action: str, manual_trigger: bool, message: str
    ) -> BridgeResponse:
        return BridgeResponse(
            action=action,
            success=False,
            message=message,
            payload={"manual_trigger": manual_trigger},
        )

    def _manual_bridge_guard(
        self, *, action: str, manual_trigger: bool, manual_token: str | None
    ) -> BridgeResponse | None:
        if manual_trigger:
            expected_token = os.getenv("POE_LEDGER_BRIDGE_MANUAL_TOKEN")
            if expected_token and manual_token != expected_token:
                return self._bridge_failure_response(
                    action=action,
                    manual_trigger=manual_trigger,
                    message=(
                        "manual trigger token missing or invalid; API uses "
                        "POE_LEDGER_BRIDGE_MANUAL_TOKEN and callers must send "
                        "the same value as manual_token "
                        "(for UI, set POE_LEDGER_UI_BRIDGE_MANUAL_TOKEN)"
                    ),
                )
            return None
        return self._bridge_failure_response(
            action=action,
            manual_trigger=manual_trigger,
            message=_MANUAL_REQUIRED_MESSAGE,
        )

    def _from_flip_opportunity(
        self, opportunity: FlipOpportunity
    ) -> FlipOpportunitySchema:
        metadata = {key: str(value) for key, value in opportunity.metadata.items()}
        return FlipOpportunitySchema(
            detected_at=opportunity.detected_at,
            league=opportunity.league,
            query_key=opportunity.query_key,
            buy_max=opportunity.buy_max,
            sell_min=opportunity.sell_min,
            expected_profit=opportunity.expected_profit,
            liquidity_score=opportunity.liquidity_score,
            expiry_ts=opportunity.expiry_ts,
            metadata=metadata,
        )

    @staticmethod
    def _scale_price(price: PriceEstimate, count: int) -> dict[str, float]:
        multiplier = count if count > 0 else 0
        return {
            "est": round(price.est * multiplier, 3),
            "list_fast": round(price.list_fast * multiplier, 3),
            "list_normal": round(price.list_normal * multiplier, 3),
            "list_patient": round(price.list_patient * multiplier, 3),
        }

    def _build_price_estimate(
        self, fp_loose: str, stats: Dict[str, float]
    ) -> PriceEstimate:
        listing_count = int(stats.get("listing_count", 0))
        median = stats.get("p50", 0.0)
        fast = median * 0.85 if median else 0.0
        patient = stats.get("p90", median)
        confidence = min(1.0, listing_count / 10.0)
        return PriceEstimate(
            est=median,
            list_fast=round(fast, 3),
            list_normal=round(median, 3),
            list_patient=round(patient or 0.0, 3),
            confidence=round(confidence, 3),
            comps_count=listing_count,
        )

    def _infer_fp_loose(self, text: str) -> str:
        normalized = text.lower()
        for candidate in self._price_samples:
            if candidate in normalized:
                return candidate
        return next(iter(self._price_samples))

    def _detect_tags(
        self, text: str, league: str | None, realm: str | None
    ) -> List[str]:
        tags: List[str] = []
        if league:
            tags.append(f"league:{league}")
        if realm:
            tags.append(f"realm:{realm}")
        if len(text) > 80:
            tags.append("long_description")
        return tags

    def _build_craft_candidates(self, fp_loose: str) -> List[CraftCandidate]:
        plan = self._forge_oracle.best_plan(depth=2)
        if plan is None:
            return []
        craft_cost = sum(action.cost for action in plan.steps)
        ev = plan.expected_value
        details = ", ".join(action.name for action in plan.steps)
        plan_id = "+".join(action.name for action in plan.steps)
        candidate = CraftCandidate(
            plan_id=plan_id,
            ev=round(ev, 3),
            craft_cost=round(craft_cost, 3),
            details=details,
        )
        return [candidate]

    def _build_summary(self, record: AtlasBuildRecord) -> AtlasBuildSummary:
        return AtlasBuildSummary(
            build_id=record.build_id,
            name=record.name,
            specialization=record.specialization,
            node_count=record.node_count,
            updated_at=record.updated_at,
        )

    def _from_strategy_result(self, result) -> StrategyBacktestResultSchema:
        return StrategyBacktestResultSchema(
            strategy_id=result.definition.strategy_id,
            title=result.definition.title,
            claim_summary=result.definition.claim_summary,
            tags=list(result.definition.tags),
            success_rate=result.success_rate,
            triggers=result.triggers,
            kpi_summary=StrategyKpiSummary(**result.kpi_summary.to_row()),
            kpi_targets=result.definition.kpi_targets.to_row(),
        )
