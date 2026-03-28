from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from poe_trade.config import settings
from poe_trade.db import ClickHouseClient

from . import workflows
from .v3 import benchmark as v3_benchmark
from .v3 import backfill as v3_backfill
from .v3 import eval as v3_eval
from .v3 import serve as v3_serve
from .v3 import train as v3_train
from .audit import build_audit_report
from .runtime import detect_runtime_profile, persist_runtime_profile
from .workflows import build_fx, snapshot_poeninja


class _Args(argparse.Namespace):
    command: str = ""
    subcommand: str = ""
    league: str = ""
    output: str | None = None
    output_table: str | None = None
    model_dir: str = "artifacts/ml/mirage"
    as_of: str = ""
    limit: int = 1000
    run: str = "latest"
    stdin: bool = False
    file: str | None = None
    clipboard: bool = False
    day: str = ""
    max_bytes: int = 13_500_000_000
    start_day: str = ""
    end_day: str = ""
    run_id: str = ""
    max_rows: int = 60000
    max_rows_per_route: int = 60000
    route: str = ""
    input: str = ""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="poe-ml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit-data")
    _ = audit_parser.add_argument("--league", required=True)
    _ = audit_parser.add_argument("--output", default=None)

    snapshot_parser = subparsers.add_parser("snapshot-poeninja")
    _ = snapshot_parser.add_argument("--league", required=True)
    _ = snapshot_parser.add_argument(
        "--output-table", default="poe_trade.raw_poeninja_currency_overview"
    )
    _ = snapshot_parser.add_argument("--max-iterations", type=int, default=1)

    fx_parser = subparsers.add_parser("build-fx")
    _ = fx_parser.add_argument("--league", required=True)
    _ = fx_parser.add_argument("--output-table", default="poe_trade.ml_fx_hour_v1")

    status_parser = subparsers.add_parser("status")
    _ = status_parser.add_argument("--league", required=True)
    _ = status_parser.add_argument("--run", default="latest")

    report_parser = subparsers.add_parser("report")
    _ = report_parser.add_argument("--league", required=True)
    _ = report_parser.add_argument("--model-dir", required=True)
    _ = report_parser.add_argument("--output", required=True)

    v3_backfill_parser = subparsers.add_parser("v3-backfill")
    _ = v3_backfill_parser.add_argument("--league", required=True)
    _ = v3_backfill_parser.add_argument("--start-day", required=True)
    _ = v3_backfill_parser.add_argument("--end-day", required=True)
    _ = v3_backfill_parser.add_argument("--max-bytes", type=int, default=13_500_000_000)

    v3_replay_day_parser = subparsers.add_parser("v3-replay-day")
    _ = v3_replay_day_parser.add_argument("--league", required=True)
    _ = v3_replay_day_parser.add_argument("--day", required=True)
    _ = v3_replay_day_parser.add_argument(
        "--max-bytes", type=int, default=13_500_000_000
    )

    v3_disk_usage_parser = subparsers.add_parser("v3-disk-usage")
    _ = v3_disk_usage_parser.add_argument("--league", default="Mirage")

    v3_train_parser = subparsers.add_parser("v3-train")
    _ = v3_train_parser.add_argument("--league", required=True)
    _ = v3_train_parser.add_argument("--model-dir", required=True)
    _ = v3_train_parser.add_argument("--max-rows-per-route", type=int, default=60000)

    v3_train_route_parser = subparsers.add_parser("v3-train-route")
    _ = v3_train_route_parser.add_argument("--league", required=True)
    _ = v3_train_route_parser.add_argument("--route", required=True)
    _ = v3_train_route_parser.add_argument("--model-dir", required=True)
    _ = v3_train_route_parser.add_argument("--max-rows", type=int, default=60000)

    v3_eval_parser = subparsers.add_parser("v3-evaluate")
    _ = v3_eval_parser.add_argument("--league", required=True)
    _ = v3_eval_parser.add_argument("--run-id", required=True)

    v3_benchmark_parser = subparsers.add_parser("v3-benchmark")
    _ = v3_benchmark_parser.add_argument("--input", required=True)
    _ = v3_benchmark_parser.add_argument("--output", required=True)

    v3_predict_one_parser = subparsers.add_parser("v3-predict-one")
    _ = v3_predict_one_parser.add_argument("--league", required=True)
    _ = v3_predict_one_parser.add_argument("--stdin", action="store_true")
    _ = v3_predict_one_parser.add_argument("--file", default=None)
    _ = v3_predict_one_parser.add_argument("--clipboard", action="store_true")
    _ = v3_predict_one_parser.add_argument("--model-dir", default="artifacts/ml")
    _ = v3_predict_one_parser.add_argument("--output", default="human")

    args = parser.parse_args(argv, namespace=_Args())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        cfg = settings.get_settings()
        client = ClickHouseClient.from_env(cfg.clickhouse_url)
        runtime_profile = detect_runtime_profile()
        _ = persist_runtime_profile(runtime_profile)

        command = args.command
        league = args.league
        output_arg = args.output or ""

        if command == "report":
            workflows._ensure_non_legacy_model_dir(str(args.model_dir))

        if command == "audit-data":
            audit_payload = build_audit_report(
                client,
                league=league,
                runtime_profile=runtime_profile,
            )
            text = json.dumps(audit_payload, indent=2, sort_keys=True)
            if output_arg:
                output_path = Path(output_arg)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _ = output_path.write_text(text + "\n", encoding="utf-8")
            print(text)
            return 0
        if command == "snapshot-poeninja":
            result = snapshot_poeninja(
                client,
                league=league,
                output_table=str(args.output_table),
                max_iterations=int(args.max_iterations or 1),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-backfill":
            result = v3_backfill.backfill_range(
                client,
                league=league,
                start_day=str(args.start_day),
                end_day=str(args.end_day),
                max_bytes=int(args.max_bytes),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-replay-day":
            from datetime import datetime

            parsed_day = datetime.strptime(str(args.day), "%Y-%m-%d").date()
            result = v3_backfill.replay_day(
                client,
                league=league,
                day=parsed_day,
                max_bytes=int(args.max_bytes),
            )
            print(json.dumps(result.__dict__, indent=2, sort_keys=True))
            return 0
        if command == "v3-disk-usage":
            result = {
                "bytes_on_disk": v3_backfill.disk_usage_bytes(client),
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-train":
            result = v3_train.train_all_routes_v3(
                client,
                league=league,
                model_dir=str(args.model_dir),
                max_rows_per_route=int(args.max_rows_per_route),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-train-route":
            result = v3_train.train_route_v3(
                client,
                league=league,
                route=str(args.route),
                model_dir=str(args.model_dir),
                max_rows=int(args.max_rows),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-evaluate":
            result = v3_eval.evaluate_run(
                client,
                league=league,
                run_id=str(args.run_id),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-benchmark":
            input_path = Path(str(args.input))
            payload_text = input_path.read_text(encoding="utf-8")
            if payload_text.lstrip().startswith("["):
                rows = json.loads(payload_text)
            else:
                rows = [
                    json.loads(line)
                    for line in payload_text.splitlines()
                    if line.strip()
                ]
            result = v3_benchmark.save_benchmark_artifacts(rows, str(args.output))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-predict-one":
            if not args.stdin and not args.file and not args.clipboard:
                raise ValueError(
                    "v3-predict-one requires one of --stdin, --file, or --clipboard"
                )
            if args.stdin:
                text = sys.stdin.read()
            elif args.file:
                text = Path(str(args.file)).read_text(encoding="utf-8")
            else:
                clip = os.getenv("POE_ML_CLIPBOARD_TEXT", "")
                if not clip:
                    raise ValueError(
                        "--clipboard requires POE_ML_CLIPBOARD_TEXT in this environment"
                    )
                text = clip
            result = v3_serve.predict_one_v3(
                client,
                league=league,
                clipboard_text=text,
                model_dir=str(args.model_dir),
            )
            if output_arg == "json":
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(
                    "\n".join(
                        [
                            f"route: {result['route']}",
                            f"fair_value_p50: {result['fair_value_p50']}",
                            f"fast_sale_24h_price: {result['fast_sale_24h_price']}",
                            f"sale_probability_24h: {result['sale_probability_24h']}",
                            f"confidence_percent: {result['confidence_percent']}",
                            f"prediction_source: {result['prediction_source']}",
                        ]
                    )
                )
            return 0
        if command == "build-fx":
            result = build_fx(
                client, league=league, output_table=str(args.output_table)
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "status":
            result = workflows.status(client, league=league, run=str(args.run))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "report":
            result = workflows.report(
                client,
                league=league,
                model_dir=str(args.model_dir),
                output=str(args.output),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        logging.getLogger(__name__).exception("poe-ml command failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
