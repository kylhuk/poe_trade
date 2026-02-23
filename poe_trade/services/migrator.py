"""Migration entrypoint for ClickHouse schema."""

from __future__ import annotations

import logging
from typing import Sequence

from ..db import main as migrate_main

LOGGER = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        return migrate_main(argv)
    except Exception as exc:  # pragma: no cover - fatal
        LOGGER.exception("migration runner failed: %s", exc)
        return 1
