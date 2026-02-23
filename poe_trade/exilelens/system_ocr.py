"""Screenshot + OCR helpers for Linux ExileLens."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile

from .session import ROIConfig, SessionType, detect_session


class OcrUnavailable(RuntimeError):
    pass


class SystemOCR:
    """Adapter that captures the screen and runs Tesseract."""

    def __init__(self, session_type: SessionType | None = None) -> None:
        self._session_type = session_type or detect_session()
        self._screenshot_tool = self._select_tool()
        self._tesseract = shutil.which("tesseract")
        if not self._tesseract:
            raise OcrUnavailable("tesseract is required for OCR captures")

    def _select_tool(self) -> str:
        order = ["maim", "gnome-screenshot"]
        if self._session_type == SessionType.WAYLAND:
            order.insert(0, "grim")
        for name in order:
            if shutil.which(name):
                return name
        raise OcrUnavailable("no screenshot helper available; install grim, maim, or gnome-screenshot")

    def capture_text(self, roi: ROIConfig | None = None) -> tuple[str, str | None]:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        try:
            subprocess.run(self._screenshot_command(path, roi), check=True)
            ocr_result = subprocess.run(
                [self._tesseract, path, "stdout"],
                check=True,
                capture_output=True,
                text=True,
            )
            text = ocr_result.stdout.strip()
            encoded = self._image_to_base64(path)
            return text, encoded
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def _screenshot_command(self, path: str, roi: ROIConfig | None) -> list[str]:
        if self._screenshot_tool == "grim":
            cmd = ["grim"]
            if roi:
                geometry = f"{roi.x},{roi.y} {roi.width}x{roi.height}"
                cmd.extend(["-g", geometry])
            cmd.append(path)
            return cmd

        if self._screenshot_tool == "maim":
            cmd = ["maim"]
            if roi:
                geometry = f"{roi.x},{roi.y} {roi.width}x{roi.height}"
                cmd.extend(["-g", geometry])
            cmd.append(path)
            return cmd

        # gnome-screenshot does not support scripted geometry cleanly.
        return ["gnome-screenshot", "-f", path]

    def _image_to_base64(self, path: str) -> str:
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")
