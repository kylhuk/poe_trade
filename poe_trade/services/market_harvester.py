"""Public market collector CLI."""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from ..config import settings as config_settings
from ..db import ClickHouseClient
from ..ingestion import CheckpointStore, MarketHarvester, PoeClient, RateLimitPolicy, StatusReporter, oauth_client_factory

LOGGER = logging.getLogger(__name__)
SERVICE_NAME = "market_harvester"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=SERVICE_NAME, description="Harvest PoE public stash data")
    parser.add_argument("--league", action="append", dest="leagues", help="League to harvest")
    parser.add_argument("--realm", action="append", dest="realms", help="Realm to target")
    parser.add_argument("--once", action="store_true", help="Run a single fetch and exit")
    parser.add_argument("--dry-run", action="store_true", help="Skip ClickHouse writes")
    parser.add_argument("--poll-interval", type=float, help="Polling interval in seconds")
    args = parser.parse_args(argv)

    _configure_logging()
    cfg = config_settings.get_settings()
    poll_interval = args.poll_interval or cfg.market_poll_interval
    leagues = args.leagues or list(cfg.leagues)
    realms = args.realms or list(cfg.realms)
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
    client = PoeClient(cfg.poe_api_base_url, policy, cfg.poe_user_agent, cfg.poe_request_timeout)
    ck_client = ClickHouseClient.from_env(cfg.clickhouse_url)
    status = StatusReporter(ck_client, SERVICE_NAME)
    checkpoints = CheckpointStore(cfg.checkpoint_dir)

    harvester = MarketHarvester(client, ck_client, checkpoints, status, auth_client=auth_client, service_name=SERVICE_NAME)
    harvester.run(realms, leagues, poll_interval, dry_run=args.dry_run, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
