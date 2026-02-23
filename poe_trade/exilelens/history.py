"""In-memory scan history."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class ScanRecord:
    timestamp: datetime
    source: str
    text: str
    image_b64: str | None


class History:
    def __init__(self, maxlen: int = 10) -> None:
        self._records: deque[ScanRecord] = deque(maxlen=maxlen)

    def add(self, source: str, text: str, debug: bool, image_b64: str | None = None) -> None:
        stored_image = image_b64 if debug else None
        record = ScanRecord(timestamp=datetime.now(timezone.utc), source=source, text=text, image_b64=stored_image)
        self._records.append(record)

    def records(self) -> list[ScanRecord]:
        return list(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterable[ScanRecord]:
        return iter(self._records)
