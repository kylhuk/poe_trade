"""Public market collector CLI."""

from __future__ import annotations

import argparse
import importlib
import logging
import os
from typing import Sequence

from ..config import settings as config_settings
from ..db import ClickHouseClient
from ..ingestion import (
    CxapiSync,
    MarketHarvester,
    PoeClient,
    StatusReporter,
    oauth_client_factory,
)
from ..ingestion.rate_limit import RateLimitPolicy
from ..ingestion.sync_state import SyncStateStore

LOGGER = logging.getLogger(__name__)
SERVICE_NAME = "market_harvester"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=SERVICE_NAME, description="Run the PoE market sync daemon"
    )
    parser.add_argument(
        "--league",
        action="append",
        dest="leagues",
        help="Primary league label for reports/bootstrap",
    )
    parser.add_argument(
        "--realm", action="append", dest="realms", help="Realm queue to target"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run one daemon cycle and exit"
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip ClickHouse writes")
    parser.add_argument(
        "--poll-interval", type=float, help="Polling interval in seconds"
    )
    parser.add_argument(
        "--bootstrap-until-league",
        help="Skip to this league during bootstrap and ingest only matching entries",
    )
    parser.add_argument(
        "--bootstrap-from-beginning",
        action="store_true",
        help="Ignore existing league checkpoint and start bootstrap from beginning",
    )
    args = parser.parse_args(argv)

    _configure_logging()
    cfg = config_settings.get_settings()
    poll_interval = args.poll_interval or cfg.psapi_poll_seconds
    leagues = args.leagues or list(cfg.leagues) or [""]
    realms = args.realms or list(cfg.realms)

    if not cfg.enable_psapi and not cfg.enable_cxapi:
        LOGGER.info(
            "%s disabled via POE_ENABLE_PSAPI=false and POE_ENABLE_CXAPI=false",
            SERVICE_NAME,
        )
        return 0

    bootstrap_until_league = args.bootstrap_until_league
    if bootstrap_until_league is None or not bootstrap_until_league.strip():
        bootstrap_until_league = cfg.stash_bootstrap_until_league or None
    else:
        bootstrap_until_league = bootstrap_until_league.strip()

    bootstrap_from_beginning = bool(args.bootstrap_from_beginning) or bool(
        cfg.stash_bootstrap_from_beginning
    )

    LOGGER.info(
        "%s starting realms=%s leagues=%s once=%s dry_run=%s interval=%ss",
        SERVICE_NAME,
        realms,
        leagues,
        args.once,
        args.dry_run,
        poll_interval,
    )
    try:
        auth_client = oauth_client_factory(cfg)
    except ValueError as exc:
        required = " and ".join(("POE_OAUTH_CLIENT_ID", "POE_OAUTH_CLIENT_SECRET"))
        LOGGER.error(
            "Missing or invalid OAuth configuration for %s: %s."
            " Ensure %s are set with valid values.",
            SERVICE_NAME,
            exc,
            required,
        )
        return 1

    policy = RateLimitPolicy(
        cfg.rate_limit_max_retries,
        cfg.rate_limit_backoff_base,
        cfg.rate_limit_backoff_max,
        cfg.rate_limit_jitter,
    )
    client = PoeClient(
        cfg.poe_api_base_url, policy, cfg.poe_user_agent, cfg.poe_request_timeout
    )
    ck_client = ClickHouseClient.from_env(cfg.clickhouse_url)
    status = StatusReporter(ck_client, SERVICE_NAME)
    sync_state = SyncStateStore(ck_client)

    harvester = None
    if cfg.enable_psapi:
        harvester = MarketHarvester(
            client,
            ck_client,
            sync_state,
            status,
            auth_client=auth_client,
            service_name=SERVICE_NAME,
            bootstrap_until_league=bootstrap_until_league,
            bootstrap_from_beginning=bootstrap_from_beginning,
            cursor_file_path=os.getenv("POE_CURSOR_FILE", ".state/cursor"),
        )

    cx_sync = None
    if cfg.enable_cxapi:
        cx_sync = CxapiSync(
            client,
            ck_client,
            sync_state,
            status,
            auth_client=auth_client,
            service_name=SERVICE_NAME,
        )

    scheduler = importlib.import_module("poe_trade.ingestion.scheduler")
    scheduler.run_market_sync(
        harvester=harvester,
        cx_sync=cx_sync,
        realms=tuple(realms),
        leagues=tuple(leagues),
        poll_interval=poll_interval,
        dry_run=args.dry_run,
        once=args.once,
        cxapi_hour_offset_seconds=cfg.cxapi_hour_offset_seconds,
        refresh_client=ck_client,
        refresh_refs_minutes=cfg.refresh_refs_minutes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
