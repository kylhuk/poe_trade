"""Tool-calling advisor (optional)."""

from __future__ import annotations

import logging
from typing import Sequence

from ..config import settings as config_settings
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "llm_advisor"


def main(argv: Sequence[str] | None = None) -> None:
    cfg = config_settings.get_settings()
    port = cfg.service_ports.get(SERVICE_NAME, None)
    logger.info(
        "%s starting on port %s (clickhouse=%s) realms=%s leagues=%s",
        SERVICE_NAME,
        port,
        cfg.clickhouse_url,
        cfg.realms,
        cfg.leagues,
    )
    run_idle_service(SERVICE_NAME)
