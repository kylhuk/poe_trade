"""PoE Ledger CLI exposing service router."""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from typing import Sequence

from . import __version__
from .config import constants, settings


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_service_main(name: str):
    module = importlib.import_module(f"poe_trade.services.{name}")
    return getattr(module, "main")


def _ensure_settings() -> None:
    _ = settings.get_settings()


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="poe-ledger-cli")
    parser.add_argument(
        "--version",
        action="version",
        version=f"poe_trade {__version__}",
        help="Show version",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)
    service_parser = subparsers.add_parser("service", help="Run a service by name")
    service_parser.add_argument(
        "--name",
        choices=constants.SERVICE_NAMES,
        required=True,
        help="Service to start",
    )
    service_parser.add_argument(
        "service_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the service",
    )

    args = parser.parse_args(argv)
    if args.command == "service":
        _configure_logging()
        _ensure_settings()
        service_main = _load_service_main(args.name)
        forwarded = args.service_args
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]
        service_main(forwarded)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
