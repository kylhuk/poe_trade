"""Shared helpers for stub service mains."""

from __future__ import annotations

import logging
import signal
from threading import Event

logger = logging.getLogger(__name__)


def run_idle_service(name: str, interval: float = 30.0) -> None:
    """Block until a termination signal arrives."""

    stop_event = Event()

    def _handle(signum: int, _frame: object | None) -> None:  # pragma: no cover - signal
        logger.info("%s received signal %s", name, signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    logger.info("%s entering idle loop (sleep=%ss).", name, interval)
    try:
        while not stop_event.wait(interval):
            logger.debug("%s heartbeat", name)
    except KeyboardInterrupt:  # pragma: no cover - ctrl+c
        stop_event.set()
    logger.info("%s gracefully shutting down.", name)
