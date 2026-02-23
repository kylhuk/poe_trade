"""Session ledger processor"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from ..analytics.session_ledger import SessionSnapshot, compute_session_profit
from ._runner import run_idle_service

logger = logging.getLogger(__name__)

SERVICE_NAME = "session_ledger"


def _default_session() -> SessionSnapshot:
    now = datetime.now(timezone.utc)
    return SessionSnapshot(
        session_id="session-1",
        start_value=1200.0,
        end_value=1350.0,
        start_time=now - timedelta(hours=2),
        end_time=now,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the session ledger service")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    snapshot = _default_session()
    metrics = compute_session_profit(snapshot)
    logger.info("Session %s profit %s", snapshot.session_id, metrics)

    if args.dry_run:
        return

    run_idle_service(SERVICE_NAME)
