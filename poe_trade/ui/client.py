"""Shared API client for Ledger UI pages."""

from __future__ import annotations

import os
from typing import Mapping, Sequence

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
    OpsDashboardResponse,
    PricingItemRequest,
    PricingSnapshotEstimateRequest,
    PricingSnapshotEstimateResponse,
    SessionLeaderboardResponse,
)
from ..bridge.local_bridge import (
    BridgeResult,
    capture_screen_text,
    clipboard_read,
    clipboard_write,
    push_overlay_payload,
    write_item_filter,
)

try:
    from poe_trade.exilelens.system_clipboard import (
        ClipboardUnavailable,
        SystemClipboard,
    )
except ImportError as exc:  # pragma: no cover - optional tooling
    ClipboardUnavailable = Exception
    SystemClipboard = None  # type: ignore[assignment]
    _clipboard_import_error = exc
else:
    _clipboard_import_error = None

try:
    from poe_trade.exilelens.system_ocr import OcrUnavailable, SystemOCR
except ImportError as exc:  # pragma: no cover - optional tooling
    OcrUnavailable = Exception
    SystemOCR = None  # type: ignore[assignment]
    _ocr_import_error = exc
else:
    _ocr_import_error = None

DEFAULT_LEAGUE = "Sanctum"
DEFAULT_SNAPSHOT_ITEMS = (
    PricingItemRequest(league=DEFAULT_LEAGUE, fp_loose="divine", count=1),
    PricingItemRequest(league=DEFAULT_LEAGUE, fp_loose="essence", count=1),
    PricingItemRequest(league=DEFAULT_LEAGUE, fp_loose="fossil", count=1),
)

DEFAULT_OVERLAY_QUEUE_PATH = os.getenv(
    "POE_LEDGER_UI_OVERLAY_QUEUE_PATH", "/tmp/overlay_payload_queue.ndjson"
)
DEFAULT_FILTER_PATH = os.getenv("POE_LEDGER_UI_FILTER_PATH", "/tmp/manual.filter")
DEFAULT_FILTER_BACKUP_PATH = os.getenv(
    "POE_LEDGER_UI_FILTER_BACKUP_PATH", "/tmp/manual.filter.bak"
)


def _env_bool_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes"}


class LedgerApiClient:
    """API-neutral client for Ledger UI renderers."""

    DEFAULT_OVERLAY_QUEUE_PATH = DEFAULT_OVERLAY_QUEUE_PATH
    DEFAULT_FILTER_PATH = DEFAULT_FILTER_PATH
    DEFAULT_FILTER_BACKUP_PATH = DEFAULT_FILTER_BACKUP_PATH

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
        self._bridge_disabled = _env_bool_flag("POE_LEDGER_UI_DISABLE_LOCAL_BRIDGE")
        self._bridge_manual_token = os.getenv(
            "POE_LEDGER_UI_BRIDGE_MANUAL_TOKEN",
            os.getenv("POE_LEDGER_BRIDGE_MANUAL_TOKEN"),
        )
        self._http_client: httpx.Client | None = None
        self._service: services.LedgerWorkflowService | None = None
        if self.local_mode:
            self._service = services.LedgerWorkflowService()

    @property
    def bridge_enabled(self) -> bool:
        return not self._bridge_disabled

    def _bridge_disabled_result(
        self, action: str, manual_trigger: bool, reason: str
    ) -> BridgeResult:
        return BridgeResult(
            action=action,
            success=False,
            message=reason,
            payload={
                "manual_trigger": manual_trigger,
                "bridge_disabled": True,
            },
        )

    def bridge_capture_screen(self, manual_trigger: bool) -> BridgeResult:
        action = "capture_screen_text"
        if self._bridge_disabled:
            return self._bridge_disabled_result(
                action, manual_trigger, "local bridge disabled"
            )
        if self.local_mode:
            if _ocr_import_error:
                return BridgeResult(
                    action=action,
                    success=False,
                    message=f"OCR helper missing: {_ocr_import_error}",
                    payload={"manual_trigger": manual_trigger},
                )
            if SystemOCR is None:
                return BridgeResult(
                    action=action,
                    success=False,
                    message="OCR helper unavailable",
                    payload={"manual_trigger": manual_trigger},
                )
            try:
                ocr = SystemOCR()
            except OcrUnavailable as exc:
                return BridgeResult(
                    action=action,
                    success=False,
                    message=f"OCR unavailable: {exc}",
                    payload={"manual_trigger": manual_trigger, "error": str(exc)},
                )
            return capture_screen_text(ocr, manual_trigger=manual_trigger)
        payload = {"manual_trigger": manual_trigger}
        return self._bridge_request("/v1/bridge/capture-screen", payload)

    def bridge_clipboard_read(self, manual_trigger: bool) -> BridgeResult:
        action = "clipboard_read"
        if self._bridge_disabled:
            return self._bridge_disabled_result(
                action, manual_trigger, "local bridge disabled"
            )
        if self.local_mode:
            if _clipboard_import_error:
                return BridgeResult(
                    action=action,
                    success=False,
                    message=f"clipboard helper missing: {_clipboard_import_error}",
                    payload={"manual_trigger": manual_trigger},
                )
            if SystemClipboard is None:
                return BridgeResult(
                    action=action,
                    success=False,
                    message="clipboard helper unavailable",
                    payload={"manual_trigger": manual_trigger},
                )
            try:
                clipboard = SystemClipboard()
            except ClipboardUnavailable as exc:
                return BridgeResult(
                    action=action,
                    success=False,
                    message=f"clipboard helper missing: {exc}",
                    payload={"manual_trigger": manual_trigger, "error": str(exc)},
                )
            return clipboard_read(clipboard, manual_trigger=manual_trigger)
        payload = {"manual_trigger": manual_trigger}
        return self._bridge_request("/v1/bridge/clipboard/read", payload)

    def bridge_clipboard_write(self, value: str, manual_trigger: bool) -> BridgeResult:
        action = "clipboard_write"
        if self._bridge_disabled:
            return self._bridge_disabled_result(
                action, manual_trigger, "local bridge disabled"
            )
        if self.local_mode:
            if _clipboard_import_error:
                return BridgeResult(
                    action=action,
                    success=False,
                    message=f"clipboard helper missing: {_clipboard_import_error}",
                    payload={"manual_trigger": manual_trigger},
                )
            if SystemClipboard is None:
                return BridgeResult(
                    action=action,
                    success=False,
                    message="clipboard helper unavailable",
                    payload={"manual_trigger": manual_trigger},
                )
            try:
                clipboard = SystemClipboard()
            except ClipboardUnavailable as exc:
                return BridgeResult(
                    action=action,
                    success=False,
                    message=f"clipboard helper missing: {exc}",
                    payload={"manual_trigger": manual_trigger, "error": str(exc)},
                )
            return clipboard_write(clipboard, value, manual_trigger=manual_trigger)
        payload = {"manual_trigger": manual_trigger, "value": value}
        return self._bridge_request("/v1/bridge/clipboard/write", payload)

    def bridge_push_overlay_payload(
        self,
        payload: dict[str, object],
        *,
        manual_trigger: bool,
        queue_path: str | None = None,
    ) -> BridgeResult:
        action = "push_overlay_payload"
        if self._bridge_disabled:
            return self._bridge_disabled_result(
                action, manual_trigger, "local bridge disabled"
            )
        path = queue_path or DEFAULT_OVERLAY_QUEUE_PATH
        if self.local_mode:
            return push_overlay_payload(path, payload, manual_trigger=manual_trigger)
        request_payload: dict[str, object] = {
            "manual_trigger": manual_trigger,
            "payload": payload,
            "queue_path": path,
        }
        return self._bridge_request("/v1/bridge/overlay/push", request_payload)

    def bridge_write_item_filter(
        self,
        contents: str,
        *,
        manual_trigger: bool,
        filter_path: str | None = None,
        backup_path: str | None = None,
    ) -> BridgeResult:
        action = "write_item_filter"
        if self._bridge_disabled:
            return self._bridge_disabled_result(
                action, manual_trigger, "local bridge disabled"
            )
        path = filter_path if filter_path else DEFAULT_FILTER_PATH
        if backup_path is None:
            backup = DEFAULT_FILTER_BACKUP_PATH
        elif backup_path == "":
            backup = None
        else:
            backup = backup_path
        if self.local_mode:
            return write_item_filter(
                path,
                contents,
                manual_trigger=manual_trigger,
                backup_path=backup,
            )
        request_payload: dict[str, object] = {
            "manual_trigger": manual_trigger,
            "contents": contents,
            "filter_path": path,
        }
        if backup is not None:
            request_payload["backup_path"] = backup
        return self._bridge_request("/v1/bridge/filter/write", request_payload)

    def _ensure_http(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(base_url=self.base_url, timeout=10.0)
        return self._http_client

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        response = self._ensure_http().request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def _bridge_request(self, path: str, payload: Mapping[str, object]) -> BridgeResult:
        request_payload = dict(payload)
        if self._bridge_manual_token:
            request_payload["manual_token"] = self._bridge_manual_token
        response_payload = self._request("POST", path, json=request_payload)
        return BridgeResult(**response_payload)

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
        request = PricingSnapshotEstimateRequest(
            items=list(items or DEFAULT_SNAPSHOT_ITEMS)
        )
        if self.local_mode:
            assert self._service is not None
            return self._service.pricing_snapshot(request)
        payload = self._request(
            "POST", "/v1/pricing/snapshot-estimate", json=request.model_dump()
        )
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

    def ops_dashboard(self) -> OpsDashboardResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.ops_dashboard()
        payload = self._request("GET", "/v1/ops/dashboard")
        return OpsDashboardResponse(**payload)

    def advisor_daily_plan(
        self,
        focus: str | None = None,
        mood: str | None = None,
    ) -> AdvisorPlanResponse:
        if self.local_mode:
            assert self._service is not None
            return self._service.advisor_plan(focus=focus, mood=mood)
        request = AdvisorPlanRequest(focus=focus, mood=mood)
        payload = self._request(
            "POST", "/v1/advisor/daily-plan", json=request.model_dump()
        )
        return AdvisorPlanResponse(**payload)

    def __del__(self) -> None:
        if self._http_client is not None:
            self._http_client.close()


__all__ = ["LedgerApiClient"]
