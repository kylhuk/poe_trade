"""One-shot ExileLens runner for local Linux captures."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Sequence

from ..exilelens import ExileLensClient, History, Mode, ROIConfig, SessionType, detect_session

logger = logging.getLogger(__name__)


class ArgClipboardAdapter:
    def __init__(self, text: str | None) -> None:
        self._text = text or ""

    def read_text(self) -> str:
        return self._text


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

    args = parser.parse_args(argv)

    session_type = (
        SessionType(args.session) if args.session else detect_session()
    )
    mode = Mode(args.mode)

    roi = _parse_roi(args.roi)

    clipboard_adapter = ArgClipboardAdapter(args.clipboard_text)
    ocr_adapter = ArgOCRAdapter(args.ocr_text, args.ocr_image_b64) if args.ocr_text else None

    history = History(maxlen=args.history_size)

    try:
        with ExileLensClient(args.endpoint, history=history) as client:
            result = client.capture(
                clipboard_adapter,
                ocr_adapter,
                league=args.league,
                realm=args.realm,
                roi=roi,
                session_type=session_type,
                mode_override=mode,
                debug_history=args.debug_history,
            )
    except Exception as exc:  # pragma: no cover - CLI failure path
        logger.error("capture failed: %s", exc)
        return 1

    summary = {
        "result": result,
        "session": session_type.value,
        "mode": mode.value,
        "history": [
            {"timestamp": record.timestamp.isoformat(), "source": record.source, "text": record.text, "image_b64": record.image_b64}
            for record in history.records()
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
