"""FastAPI gateway"""

from __future__ import annotations

import logging
from typing import Sequence

import uvicorn

from ..api.app import get_app
from ..config import settings as config_settings

logger = logging.getLogger(__name__)

SERVICE_NAME = "ledger_api"


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
    app = get_app()
    uvicorn.run(app, host="0.0.0.0", port=port or 8000, log_level="info")
