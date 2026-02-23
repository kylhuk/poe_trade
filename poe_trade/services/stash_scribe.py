"""Private stash snapshot service CLI."""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from ..config import settings as config_settings
from ..db import ClickHouseClient
from ..ingestion import (
    CheckpointStore,
    PoeClient,
    RateLimitPolicy,
    StatusReporter,
    StashScribe,
    oauth_client_factory,
)

LOGGER = logging.getLogger(__name__)
SERVICE_NAME = "stash_scribe"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=SERVICE_NAME, description="Capture private stash snapshots")
    parser.add_argument("--league", help="League to capture", required=True)
    parser.add_argument("--realm", help="Realm identifier", default="")
    parser.add_argument("--account", help="Account label for snapshots")
    parser.add_argument("--once", action="store_true", help="Run a single capture")
    parser.add_argument("--dry-run", action="store_true", help="Skip ClickHouse writes")
    parser.add_argument("--poll-interval", type=float, help="Polling interval in seconds")
    parser.add_argument("--trigger-port", type=int, help="Expose manual trigger HTTP endpoint")
    args = parser.parse_args(argv)

    _configure_logging()
    cfg = config_settings.get_settings()
    try:
        policy = RateLimitPolicy(
            cfg.rate_limit_max_retries,
            cfg.rate_limit_backoff_base,
            cfg.rate_limit_backoff_max,
            cfg.rate_limit_jitter,
        )
        api_client = PoeClient(cfg.poe_api_base_url, policy, cfg.poe_user_agent, cfg.poe_request_timeout)
        auth_client = oauth_client_factory(cfg)
    except ValueError as exc:
        LOGGER.error("OAuth configuration error: %s", exc)
        return 1
    ck_client = ClickHouseClient.from_env(cfg.clickhouse_url)
    status = StatusReporter(ck_client, SERVICE_NAME)
    checkpoints = CheckpointStore(cfg.checkpoint_dir)
    scribe = StashScribe(
        api_client,
        auth_client,
        ck_client,
        checkpoints,
        status,
        args.league,
        args.realm,
        account=args.account,
    )
    trigger_server = None
    trigger_thread = None
    if args.trigger_port:
        trigger_server, trigger_thread = scribe.start_trigger_server(args.trigger_port, cfg.stash_trigger_token or None)
    try:
        interval = args.poll_interval or cfg.stash_poll_interval
        scribe.run(interval=interval, dry_run=args.dry_run, once=args.once)
    finally:
        if trigger_server:
            trigger_server.should_exit = True
            if trigger_thread:
                trigger_thread.join(timeout=1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
