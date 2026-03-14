from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from poe_trade.api.app import create_app, serve
from poe_trade.config import settings as config_settings

SERVICE_NAME = "api"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: Sequence[str] | None = None) -> int:
    cfg = config_settings.get_settings()
    parser = argparse.ArgumentParser(
        prog=SERVICE_NAME, description="Run the API service"
    )
    parser.add_argument("--host", default=cfg.api_bind_host, help="Bind host")
    parser.add_argument("--port", type=int, default=cfg.api_bind_port, help="Bind port")
    args = parser.parse_args(argv)

    _configure_logging()
    app = create_app(cfg)
    serve(app, host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
