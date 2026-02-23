"""ExileLens client runtime."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Protocol

import httpx

from .history import History
from .modes import Mode, select_mode
from .normalizer import is_likely_item_text, normalize_item_text
from .session import ROIConfig, SessionType, detect_session

logger = logging.getLogger(__name__)


class ClipboardAdapter(Protocol):
    def read_text(self) -> str:
        ...


class OCRAdapter(Protocol):
    def capture_text(self, roi: ROIConfig | None = None) -> tuple[str, str | None]:
        ...


class ExileLensClient:
    def __init__(self, endpoint: str, *, http_client: httpx.Client | None = None, history: History | None = None) -> None:
        self.endpoint = endpoint
        self._http_client = http_client or httpx.Client()
        self.history = history if history is not None else History()

    def __enter__(self) -> "ExileLensClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        closeable = getattr(self._http_client, "close", None)
        if callable(closeable):
            closeable()

    def capture(
        self,
        clipboard_adapter: ClipboardAdapter,
        ocr_adapter: OCRAdapter | None = None,
        *,
        league: str | None = None,
        realm: str | None = None,
        roi: ROIConfig | None = None,
        session_type: SessionType | None = None,
        mode_override: Mode | None = None,
        debug_history: bool = False,
    ) -> dict:
        actual_session = session_type or detect_session()
        mode = select_mode(actual_session, mode_override)

        if mode == Mode.CLIPBOARD_FIRST:
            clipboard_candidate = self._try_clipboard(clipboard_adapter)
            if clipboard_candidate:
                return self._dispatch(
                    clipboard_candidate,
                    source="clipboard",
                    league=league,
                    realm=realm,
                    image_b64=None,
                    debug_history=debug_history,
                )

        if ocr_adapter and mode in (Mode.CLIPBOARD_FIRST, Mode.OCR_ONLY):
            ocr_text, image_b64 = ocr_adapter.capture_text(roi)
            normalized = normalize_item_text(ocr_text)
            if normalized and is_likely_item_text(normalized):
                return self._dispatch(
                    normalized,
                    source="ocr",
                    league=league,
                    realm=realm,
                    image_b64=image_b64,
                    debug_history=debug_history,
                )

        raise RuntimeError("unable to capture valid item text")

    def _try_clipboard(self, adapter: ClipboardAdapter) -> str:
        text = adapter.read_text()
        normalized = normalize_item_text(text)
        if normalized and is_likely_item_text(normalized):
            return normalized
        return ""

    def _dispatch(
        self,
        text: str,
        *,
        source: str,
        league: str | None,
        realm: str | None,
        image_b64: str | None,
        debug_history: bool,
    ) -> dict:
        payload_image = image_b64 if debug_history else None
        payload = {
            "source": source,
            "text": text,
            "ts_client": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if league:
            payload["league"] = league
        if realm:
            payload["realm"] = realm
        if payload_image:
            payload["image_b64"] = payload_image

        logger.debug("posting ExileLens payload %s", payload)
        response = self._http_client.post(self.endpoint, json=payload)
        response.raise_for_status()

        self.history.add(source=source, text=text, debug=debug_history, image_b64=payload_image)
        return response.json()
