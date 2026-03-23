from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from functools import partial

from poe_trade.stash_scan import serialize_stash_item_to_clipboard

from poe_trade.api.auth_session import load_oauth_credential_state
from poe_trade.config import settings as config_settings
from poe_trade.db import ClickHouseClient
from poe_trade.ingestion.account_stash_harvester import AccountStashHarvester
from poe_trade.ingestion.poe_client import PoeClient
from poe_trade.ingestion.rate_limit import RateLimitPolicy
from poe_trade.ingestion.status import StatusReporter

SERVICE_NAME = "account_stash_harvester"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _price_item(
    item: dict[str, object], *, clickhouse: ClickHouseClient, league: str
) -> dict[str, object]:
    from poe_trade.api.ml import fetch_predict_one

    return fetch_predict_one(
        clickhouse,
        league=league,
        request_payload={"itemText": serialize_stash_item_to_clipboard(item)},
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=SERVICE_NAME, description="Run private account stash harvester"
    )
    parser.add_argument("--once", action="store_true", help="Run one harvest and exit")
    parser.add_argument(
        "--scan-once",
        action="store_true",
        help="Run one private stash pricing scan and exit",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip ClickHouse writes")
    parser.add_argument("--realm", help="Realm override")
    parser.add_argument("--league", help="League override")
    parser.add_argument(
        "--poll-interval", type=float, help="Polling interval in seconds"
    )
    args = parser.parse_args(argv)

    _configure_logging()
    cfg = config_settings.get_settings()
    if not cfg.enable_account_stash:
        logging.getLogger(__name__).info(
            "%s disabled via POE_ENABLE_ACCOUNT_STASH=false", SERVICE_NAME
        )
        return 0
    oauth_state = load_oauth_credential_state(cfg)
    account_name = str(oauth_state.get("account_name") or "").strip()
    access_token = str(oauth_state.get("access_token") or "").strip()
    if not account_name or not access_token:
        logging.getLogger(__name__).info(
            "%s no-op: oauth credential missing (status=%s)",
            SERVICE_NAME,
            str(oauth_state.get("status") or "unknown"),
        )
        return 0

    policy = RateLimitPolicy(
        cfg.rate_limit_max_retries,
        cfg.rate_limit_backoff_base,
        cfg.rate_limit_backoff_max,
        cfg.rate_limit_jitter,
    )
    client = PoeClient(
        cfg.poe_api_base_url, policy, cfg.poe_user_agent, cfg.poe_request_timeout
    )
    client.set_bearer_token(access_token)
    clickhouse = ClickHouseClient.from_env(cfg.clickhouse_url)
    status = StatusReporter(clickhouse, SERVICE_NAME)
    harvester = AccountStashHarvester(
        client,
        clickhouse,
        status,
        service_name=SERVICE_NAME,
        account_name=account_name,
        request_headers={},
    )
    if args.scan_once:
        harvester.run_private_scan(
            realm=args.realm or cfg.account_stash_realm,
            league=args.league or cfg.account_stash_league,
            price_item=partial(
                _price_item,
                clickhouse=clickhouse,
                league=args.league or cfg.account_stash_league,
            ),
        )
        return 0
    harvester.run(
        realm=args.realm or cfg.account_stash_realm,
        league=args.league or cfg.account_stash_league,
        interval=args.poll_interval
        if args.poll_interval is not None
        else cfg.account_stash_poll_interval,
        dry_run=args.dry_run,
        once=args.once,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
