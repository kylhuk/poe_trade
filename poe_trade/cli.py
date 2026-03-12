"""PoE Ledger CLI exposing service router."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import logging
import os
import sys
from collections.abc import Iterator, Sequence

from .analytics import execute_refresh_group
from . import __version__
from .config import constants, settings
from .db import ClickHouseClient


def _best_effort_search_hint(evidence_snapshot: str, item_or_market_key: str) -> str:
    try:
        payload = json.loads(evidence_snapshot)
    except json.JSONDecodeError:
        return item_or_market_key
    if not isinstance(payload, dict):
        return item_or_market_key
    for key in (
        "item_name",
        "item_type_line",
        "typeLine",
        "base_type",
        "market_id",
        "category",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return item_or_market_key


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


@contextlib.contextmanager
def _temporary_env(overrides: dict[str, str]) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
    refresh_parser = subparsers.add_parser("refresh", help="Run SQL refresh groups")
    refresh_parser.add_argument(
        "layer", choices=("silver", "gold"), help="SQL layer to refresh"
    )
    refresh_parser.add_argument(
        "--group", default=None, help="Refresh group within the layer"
    )
    refresh_parser.add_argument(
        "--dry-run", action="store_true", help="List SQL files without executing them"
    )
    rebuild_parser = subparsers.add_parser("rebuild", help="Run rebuild workflows")
    rebuild_parser.add_argument(
        "layer", choices=("silver", "gold"), help="SQL layer to rebuild"
    )
    rebuild_parser.add_argument(
        "--group", default=None, help="Rebuild group within the layer"
    )
    rebuild_parser.add_argument(
        "--all",
        action="store_true",
        help="Alias for rebuilding the full selected layer",
    )
    rebuild_parser.add_argument(
        "--from",
        dest="from_ts",
        default=None,
        help="Optional lower-bound marker for operator tracking",
    )
    rebuild_parser.add_argument(
        "--dry-run", action="store_true", help="List SQL files without executing them"
    )
    strategy_parser = subparsers.add_parser("strategy", help="Inspect strategy packs")
    strategy_subparsers = strategy_parser.add_subparsers(
        dest="strategy_command", required=True
    )
    strategy_subparsers.add_parser("list", help="List discovered strategy packs")
    strategy_enable = strategy_subparsers.add_parser(
        "enable", help="Enable a strategy pack"
    )
    strategy_enable.add_argument("strategy_id", help="Strategy pack id")
    strategy_disable = strategy_subparsers.add_parser(
        "disable", help="Disable a strategy pack"
    )
    strategy_disable.add_argument("strategy_id", help="Strategy pack id")
    research_parser = subparsers.add_parser("research", help="Run research workflows")
    research_subparsers = research_parser.add_subparsers(
        dest="research_command", required=True
    )
    research_backtest = research_subparsers.add_parser(
        "backtest", help="Run a strategy backtest"
    )
    research_backtest.add_argument("--strategy", required=True, help="Strategy pack id")
    research_backtest.add_argument(
        "--league", required=True, help="League label for the run"
    )
    research_backtest.add_argument(
        "--days", type=int, required=True, help="Lookback window in days"
    )
    research_backtest.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare the run without executing ClickHouse inserts",
    )
    research_backtest_all = research_subparsers.add_parser(
        "backtest-all", help="Run backtests across many strategy packs"
    )
    research_backtest_all.add_argument(
        "--league", required=True, help="League label for the runs"
    )
    research_backtest_all.add_argument(
        "--days", type=int, required=True, help="Lookback window in days"
    )
    research_backtest_all.add_argument(
        "--enabled-only",
        action="store_true",
        help="Only backtest strategy packs marked enabled",
    )
    research_backtest_all.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare runs without executing ClickHouse inserts",
    )
    scan_parser = subparsers.add_parser("scan", help="Run scanner workflows")
    scan_subparsers = scan_parser.add_subparsers(dest="scan_command", required=True)
    scan_once = scan_subparsers.add_parser("once", help="Run one recommendation scan")
    scan_once.add_argument("--league", required=True, help="League label for the scan")
    scan_once.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare the scan without executing ClickHouse inserts",
    )
    scan_watch = scan_subparsers.add_parser(
        "watch", help="Run repeated recommendation scans"
    )
    scan_watch.add_argument("--league", required=True, help="League label for the scan")
    scan_watch.add_argument(
        "--interval-seconds",
        type=float,
        default=300.0,
        help="Delay between scan cycles",
    )
    scan_watch.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Optional cap on scan cycles",
    )
    scan_watch.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare scan cycles without executing ClickHouse inserts",
    )
    scan_plan = scan_subparsers.add_parser(
        "plan",
        help="Run one scan and print actionable buy guidance",
    )
    scan_plan.add_argument("--league", required=True, help="League label for the scan")
    scan_plan.add_argument(
        "--limit", type=int, default=20, help="Maximum recommendations to print"
    )
    scan_plan.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare the scan without executing ClickHouse inserts",
    )
    journal_parser = subparsers.add_parser(
        "journal", help="Record manual execution events"
    )
    journal_subparsers = journal_parser.add_subparsers(
        dest="journal_command", required=True
    )
    for action in ("buy", "sell"):
        journal_command = journal_subparsers.add_parser(
            action, help=f"Record a {action} event"
        )
        journal_command.add_argument(
            "--strategy", required=True, help="Strategy pack id"
        )
        journal_command.add_argument(
            "--league", required=True, help="League label for the event"
        )
        journal_command.add_argument(
            "--item-or-market-key", required=True, help="Tracked item or market key"
        )
        journal_command.add_argument(
            "--price-chaos", required=True, type=float, help="Price in chaos orbs"
        )
        journal_command.add_argument(
            "--quantity", required=True, type=float, help="Quantity traded"
        )
        journal_command.add_argument(
            "--notes", default="", help="Optional journal notes"
        )
        journal_command.add_argument(
            "--dry-run",
            action="store_true",
            help="Prepare the event without executing ClickHouse inserts",
        )
    alerts_parser = subparsers.add_parser(
        "alerts", help="Inspect or acknowledge scanner alerts"
    )
    alerts_subparsers = alerts_parser.add_subparsers(
        dest="alerts_command", required=True
    )
    alerts_subparsers.add_parser("list", help="List latest alert states")
    alerts_ack = alerts_subparsers.add_parser("ack", help="Acknowledge an alert")
    alerts_ack.add_argument("--id", required=True, help="Alert id to acknowledge")
    report_parser = subparsers.add_parser("report", help="Render reports")
    report_subparsers = report_parser.add_subparsers(
        dest="report_command", required=True
    )
    daily_report = report_subparsers.add_parser(
        "daily", help="Render the daily league report"
    )
    daily_report.add_argument(
        "--league", required=True, help="League label for the report"
    )
    sync_parser = subparsers.add_parser("sync", help="Run sync workflows")
    sync_subparsers = sync_parser.add_subparsers(dest="sync_command", required=True)
    sync_subparsers.add_parser("status", help="Show latest queue status rows")
    sync_subparsers.add_parser("psapi-once", help="Run one PSAPI daemon cycle")
    sync_cx = sync_subparsers.add_parser(
        "cxapi-backfill", help="Run one CXAPI daemon cycle with a backfill window"
    )
    sync_cx.add_argument(
        "--hours", type=int, default=168, help="Backfill window in hours"
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
    if args.command == "refresh":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        sql_files = execute_refresh_group(
            client,
            layer=args.layer,
            group=args.group,
            dry_run=args.dry_run,
        )
        for sql_file in sql_files:
            print(sql_file)
        return 0
    if args.command == "rebuild":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        sql_files = execute_refresh_group(
            client,
            layer=args.layer,
            group=args.group if not args.all else None,
            dry_run=args.dry_run,
        )
        for sql_file in sql_files:
            print(sql_file)
        return 0
    if args.command == "strategy" and args.strategy_command == "list":
        strategy_registry = importlib.import_module("poe_trade.strategy.registry")
        for pack in strategy_registry.list_strategy_packs():
            print(
                f"{pack.strategy_id}\t{pack.name}\t{int(pack.enabled)}\t{pack.execution_venue}\t{pack.latency_class}"
            )
        return 0
    if args.command == "strategy" and args.strategy_command in {"enable", "disable"}:
        strategy_registry = importlib.import_module("poe_trade.strategy.registry")
        metadata_path = strategy_registry.set_strategy_enabled(
            args.strategy_id,
            args.strategy_command == "enable",
        )
        print(metadata_path)
        return 0
    if args.command == "research" and args.research_command == "backtest":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_backtest = importlib.import_module("poe_trade.strategy.backtest")
        run_id = strategy_backtest.run_backtest(
            client,
            strategy_id=args.strategy,
            league=args.league,
            lookback_days=args.days,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(run_id)
            return 0
        print(strategy_backtest.BACKTEST_SUMMARY_HEADER)
        for row in strategy_backtest.fetch_backtest_summary_rows(client, run_id=run_id):
            print(strategy_backtest.format_summary_row(row))
        return 0
    if args.command == "research" and args.research_command == "backtest-all":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_registry = importlib.import_module("poe_trade.strategy.registry")
        strategy_backtest = importlib.import_module("poe_trade.strategy.backtest")
        packs = strategy_registry.list_strategy_packs()
        if args.enabled_only:
            packs = [pack for pack in packs if pack.enabled]
        print(strategy_backtest.BACKTEST_SUMMARY_HEADER)
        rows_to_print = []
        for pack in packs:
            run_id = strategy_backtest.run_backtest(
                client,
                strategy_id=pack.strategy_id,
                league=args.league,
                lookback_days=args.days,
                dry_run=args.dry_run,
            )
            if args.dry_run:
                rows_to_print.append(
                    {
                        "run_id": run_id,
                        "strategy_id": pack.strategy_id,
                        "league": args.league,
                        "lookback_days": args.days,
                        "status": "dry_run",
                        "opportunity_count": "",
                        "expected_profit_chaos": "",
                        "expected_roi": "",
                        "confidence": "",
                        "summary": "dry run only",
                    }
                )
                continue
            rows_to_print.extend(
                strategy_backtest.fetch_backtest_summary_rows(client, run_id=run_id)
            )
        rows_to_print.sort(
            key=lambda row: (
                strategy_backtest.backtest_status_rank(str(row.get("status", ""))),
                -float(row.get("expected_profit_chaos") or 0.0),
                str(row.get("strategy_id", "")),
            )
        )
        for row in rows_to_print:
            print(strategy_backtest.format_summary_row(row))
        return 0
    if args.command == "scan" and args.scan_command == "once":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_scanner = importlib.import_module("poe_trade.strategy.scanner")
        scan_id = strategy_scanner.run_scan_once(
            client,
            league=args.league,
            dry_run=args.dry_run,
        )
        print(scan_id)
        return 0
    if args.command == "scan" and args.scan_command == "watch":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_scanner = importlib.import_module("poe_trade.strategy.scanner")
        run_ids = strategy_scanner.run_scan_watch(
            client,
            league=args.league,
            interval_seconds=args.interval_seconds,
            max_runs=args.max_runs,
            dry_run=args.dry_run,
        )
        for run_id in run_ids:
            print(run_id)
        return 0
    if args.command == "scan" and args.scan_command == "plan":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_scanner = importlib.import_module("poe_trade.strategy.scanner")
        scan_id = strategy_scanner.run_scan_once(
            client,
            league=args.league,
            dry_run=args.dry_run,
        )
        print(f"scan_id\t{scan_id}")
        if args.dry_run:
            return 0
        payload = client.execute(
            "SELECT strategy_id, item_or_market_key, why_it_fired, buy_plan, max_buy, transform_plan, exit_plan, execution_venue, expected_profit_chaos, expected_roi, expected_hold_time, confidence, evidence_snapshot "
            "FROM poe_trade.scanner_recommendations "
            f"WHERE scanner_run_id = '{scan_id}' "
            "ORDER BY coalesce(expected_profit_chaos, 0.0) DESC, coalesce(confidence, 0.0) DESC, strategy_id "
            f"LIMIT {max(1, int(args.limit))} "
            "FORMAT JSONEachRow"
        )
        print(
            "strategy_id\tsearch_hint\titem_or_market_key\tbuy_plan\tmax_buy\ttransform_plan\texit_plan\texecution_venue\texpected_profit_chaos\texpected_roi\tconfidence\twhy_it_fired"
        )
        for line in payload.splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            hint = _best_effort_search_hint(
                str(row.get("evidence_snapshot", "")),
                str(row.get("item_or_market_key", "")),
            )
            print(
                "\t".join(
                    (
                        str(row.get("strategy_id", "")),
                        hint,
                        str(row.get("item_or_market_key", "")),
                        str(row.get("buy_plan", "")),
                        "" if row.get("max_buy") is None else str(row.get("max_buy")),
                        str(row.get("transform_plan", "")),
                        str(row.get("exit_plan", "")),
                        str(row.get("execution_venue", "")),
                        ""
                        if row.get("expected_profit_chaos") is None
                        else str(row.get("expected_profit_chaos")),
                        ""
                        if row.get("expected_roi") is None
                        else str(row.get("expected_roi")),
                        ""
                        if row.get("confidence") is None
                        else str(row.get("confidence")),
                        str(row.get("why_it_fired", "")),
                    )
                )
            )
        return 0
    if args.command == "journal" and args.journal_command in {"buy", "sell"}:
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_journal = importlib.import_module("poe_trade.strategy.journal")
        event_id = strategy_journal.record_trade_event(
            client,
            action=args.journal_command,
            strategy_id=args.strategy,
            league=args.league,
            item_or_market_key=args.item_or_market_key,
            price_chaos=args.price_chaos,
            quantity=args.quantity,
            notes=args.notes,
            dry_run=args.dry_run,
        )
        print(event_id)
        return 0
    if args.command == "alerts" and args.alerts_command == "list":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_alerts = importlib.import_module("poe_trade.strategy.alerts")
        for alert in strategy_alerts.list_alerts(client):
            print(
                f"{alert['alert_id']}\t{alert['strategy_id']}\t{alert['league']}\t{alert['status']}\t{alert['item_or_market_key']}"
            )
        return 0
    if args.command == "alerts" and args.alerts_command == "ack":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        strategy_alerts = importlib.import_module("poe_trade.strategy.alerts")
        print(strategy_alerts.ack_alert(client, alert_id=args.id))
        return 0
    if args.command == "report" and args.report_command == "daily":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        reports = importlib.import_module("poe_trade.analytics.reports")
        print(reports.daily_report(client, league=args.league))
        return 0
    if args.command == "sync" and args.sync_command == "status":
        _configure_logging()
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        payload = client.execute(
            "SELECT queue_key, feed_kind, status, last_ingest_at "
            "FROM poe_trade.poe_ingest_status ORDER BY last_ingest_at DESC LIMIT 20 FORMAT JSONEachRow"
        )
        print(payload.strip())
        return 0
    if args.command == "sync" and args.sync_command in {"psapi-once", "cxapi-backfill"}:
        _configure_logging()
        service_main = _load_service_main("market_harvester")
        overrides = {
            "POE_ENABLE_PSAPI": "true"
            if args.sync_command == "psapi-once"
            else "false",
            "POE_ENABLE_CXAPI": "true"
            if args.sync_command == "cxapi-backfill"
            else "false",
        }
        if args.sync_command == "cxapi-backfill":
            overrides["POE_CXAPI_BACKFILL_HOURS"] = str(args.hours)
        with _temporary_env(overrides):
            service_main(["--once"])
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
