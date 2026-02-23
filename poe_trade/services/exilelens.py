"""One-shot ExileLens runner for local Linux captures."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Protocol, Sequence

from ..exilelens import (
    ClipboardUnavailable,
    ExileLensClient,
    History,
    Mode,
    OcrUnavailable,
    ROIConfig,
    SessionType,
    SystemClipboard,
    SystemOCR,
    detect_session,
)
from ..exilelens.normalizer import is_likely_item_text, normalize_item_text

logger = logging.getLogger(__name__)

COPY_FIELD_CHOICES = ("est_chaos", "list_fast", "list_normal", "list_patient")


class ClipboardWriter(Protocol):
    def write_text(self, value: str) -> None: ...


class ArgClipboardAdapter:
    def __init__(self, text: str | None) -> None:
        self._text = text or ""
        self.written: list[str] = []

    def read_text(self) -> str:
        return self._text

    def write_text(self, value: str) -> None:
        self.written.append(value)


class ArgOCRAdapter:
    def __init__(self, text: str | None, image_b64: str | None) -> None:
        self._text = text or ""
        self._image = image_b64

    def capture_text(self, roi: ROIConfig | None = None) -> tuple[str, str | None]:
        return self._text, self._image


def _parse_roi(value: str | None) -> ROIConfig | None:
    if not value:
        return None

    parts = [int(part.strip()) for part in value.split(",") if part.strip()]
    if len(parts) != 4:
        raise ValueError("ROI must be four comma-separated integers: x,y,width,height")

    return ROIConfig(*parts)


def _history_records(history: History) -> list[dict]:
    return [
        {
            "timestamp": record.timestamp.isoformat(),
            "source": record.source,
            "text": record.text,
            "image_b64": record.image_b64,
        }
        for record in history.records()
    ]


def _emit_summary(result: dict, history: History, session_type: SessionType, mode: Mode) -> None:
    payload = {
        "result": result,
        "session": session_type.value,
        "mode": mode.value,
        "history": _history_records(history),
    }
    print(json.dumps(payload, indent=2))


def _copy_price_field(result: dict, field: str | None, clipboard: ClipboardWriter | None) -> bool:
    if not field or not clipboard:
        return False

    price_block = result.get("price") or result.get("result", {}).get("price")
    if not isinstance(price_block, dict):
        return False

    value = price_block.get(field)
    if value is None:
        return False

    clipboard.write_text(str(value))
    return True


def _capture_once(
    client: ExileLensClient,
    clipboard_adapter: ArgClipboardAdapter | SystemClipboard,
    ocr_adapter: ArgOCRAdapter | SystemOCR | None,
    *,
    league: str | None,
    realm: str | None,
    roi: ROIConfig | None,
    session_type: SessionType,
    mode: Mode,
    debug_history: bool,
) -> dict:
    return client.capture(
        clipboard_adapter,
        ocr_adapter,
        league=league,
        realm=realm,
        roi=roi,
        session_type=session_type,
        mode_override=mode,
        debug_history=debug_history,
    )


def _watch_clipboard_mode(
    client: ExileLensClient,
    clipboard_adapter: SystemClipboard,
    ocr_adapter: ArgOCRAdapter | SystemOCR | None,
    history: History,
    league: str | None,
    realm: str | None,
    roi: ROIConfig | None,
    session_type: SessionType,
    mode: Mode,
    debug_history: bool,
    poll_interval: float,
    max_events: int | None,
    copy_field: str | None,
) -> int:
    last_text = ""
    events = 0
    limit = max_events if max_events and max_events > 0 else None

    try:
        while limit is None or events < limit:
            raw = clipboard_adapter.read_text()
            normalized = normalize_item_text(raw)
            if normalized and normalized != last_text and is_likely_item_text(normalized):
                last_text = normalized
                try:
                    result = _capture_once(
                        client,
                        clipboard_adapter,
                        ocr_adapter,
                        league=league,
                        realm=realm,
                        roi=roi,
                        session_type=session_type,
                        mode=mode,
                        debug_history=debug_history,
                    )
                except Exception as exc:
                    logger.debug("watch capture failed: %s", exc)
                else:
                    events += 1
                    _emit_summary(result, history, session_type, mode)
                    _copy_price_field(result, copy_field, clipboard_adapter)
                    if limit is not None and events >= limit:
                        break
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("clipboard watch interrupted")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exilelens", description="Invoke local ExileLens capture flow")
    parser.add_argument("--endpoint", default="http://localhost/v1/item/analyze")
    parser.add_argument("--league")
    parser.add_argument("--realm")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in Mode],
        default=Mode.CLIPBOARD_FIRST.value,
        help="Capture mode",
    )
    parser.add_argument(
        "--session",
        choices=[stype.value for stype in SessionType],
        help="Override detected session",
    )
    parser.add_argument("--roi", help="Bounding box for OCR (x,y,width,height)")
    parser.add_argument("--clipboard-text", help="Text to simulate clipboard capture")
    parser.add_argument("--ocr-text", help="Text to simulate OCR fallback")
    parser.add_argument("--ocr-image-b64", help="Base64 image payload for OCR capture")
    parser.add_argument("--history-size", type=int, default=5, help="Records to keep in history")
    parser.add_argument("--debug-history", action="store_true", help="Preserve OCR images in history")
    parser.add_argument("--watch-clipboard", action="store_true", help="Poll the clipboard for PoE items")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.4,
        help="Seconds between clipboard polls",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Maximum clipboard captures before exiting",
    )
    parser.add_argument(
        "--copy-field",
        choices=COPY_FIELD_CHOICES,
        help="Copy a price field into the clipboard after analyze",
    )

    args = parser.parse_args(argv)

    if args.watch_clipboard and args.clipboard_text:
        parser.error("--watch-clipboard cannot be combined with --clipboard-text")

    session_type = SessionType(args.session) if args.session else detect_session()
    mode = Mode(args.mode)
    roi = _parse_roi(args.roi)

    try:
        clipboard_adapter = ArgClipboardAdapter(args.clipboard_text) if args.clipboard_text else SystemClipboard()
    except ClipboardUnavailable as exc:
        logger.error("clipboard access failed: %s", exc)
        return 1

    try:
        ocr_adapter = ArgOCRAdapter(args.ocr_text, args.ocr_image_b64) if args.ocr_text else SystemOCR(session_type)
    except OcrUnavailable as exc:
        logger.error("ocr access failed: %s", exc)
        return 1

    history = History(maxlen=args.history_size)
    clipboard_writer: ClipboardWriter | None = clipboard_adapter if hasattr(clipboard_adapter, "write_text") else None

    with ExileLensClient(args.endpoint, history=history) as client:
        if args.watch_clipboard:
            return _watch_clipboard_mode(
                client,
                clipboard_adapter,
                ocr_adapter,
                history,
                args.league,
                args.realm,
                roi,
                session_type,
                mode,
                args.debug_history,
                args.poll_interval,
                args.max_events,
                args.copy_field,
            )

        try:
            result = _capture_once(
                client,
                clipboard_adapter,
                ocr_adapter,
                league=args.league,
                realm=args.realm,
                roi=roi,
                session_type=session_type,
                mode=mode,
                debug_history=args.debug_history,
            )
        except Exception as exc:
            logger.error("capture failed: %s", exc)
            return 1

        _emit_summary(result, history, session_type, mode)
        _copy_price_field(result, args.copy_field, clipboard_writer)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
