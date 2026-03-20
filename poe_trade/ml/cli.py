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
from .v3 import backfill as v3_backfill
from .v3 import eval as v3_eval
from .v3 import serve as v3_serve
from .v3 import train as v3_train
from .audit import build_audit_report
from .runtime import detect_runtime_profile, persist_runtime_profile
from .workflows import (
    build_comps,
    build_dataset,
    build_fx,
    build_listing_events_and_labels,
    evaluate_route,
    evaluate_saleability,
    evaluate_stack,
    predict_batch,
    predict_one,
    report,
    route_preview,
    snapshot_poeninja,
    status,
    train_all_routes,
    train_loop,
    train_route,
    train_saleability,
    normalize_prices,
)


class _Args(argparse.Namespace):
    command: str = ""
    subcommand: str = ""
    route: str = ""
    split: str = "rolling"
    source: str = "dataset"
    league: str = ""
    output: str | None = None
    output_table: str | None = None
    dataset_table: str = "poe_trade.ml_price_dataset_v2"
    comps_table: str = "poe_trade.ml_comps_v1"
    model_dir: str = "artifacts/ml/mirage_v2"
    as_of: str = ""
    max_iterations: int | None = None
    max_wall_clock_seconds: int | None = None
    no_improvement_patience: int | None = None
    min_mdape_improvement: float | None = None
    limit: int = 1000
    run: str = "latest"
    input_format: str = "poe-clipboard"
    stdin: bool = False
    file: str | None = None
    clipboard: bool = False
    resume: bool = False
    start_day: str = ""
    end_day: str = ""
    day: str = ""
    max_bytes: int = 13_500_000_000
    run_id: str = ""


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

    normalize_parser = subparsers.add_parser("normalize-prices")
    _ = normalize_parser.add_argument("--league", required=True)
    _ = normalize_parser.add_argument(
        "--output-table", default="poe_trade.ml_price_labels_v1"
    )

    dataset_parser = subparsers.add_parser("dataset")
    dataset_sub = dataset_parser.add_subparsers(dest="subcommand", required=True)
    dataset_build = dataset_sub.add_parser("build")
    _ = dataset_build.add_argument("--league", required=True)
    _ = dataset_build.add_argument("--as-of", required=True)
    _ = dataset_build.add_argument(
        "--output-table", default="poe_trade.ml_price_dataset_v1"
    )

    route_preview_parser = subparsers.add_parser("route-preview")
    _ = route_preview_parser.add_argument("--league", required=True)
    _ = route_preview_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = route_preview_parser.add_argument("--limit", type=int, default=1000)

    build_comps_parser = subparsers.add_parser("build-comps")
    _ = build_comps_parser.add_argument("--league", required=True)
    _ = build_comps_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = build_comps_parser.add_argument(
        "--output-table", default="poe_trade.ml_comps_v1"
    )

    train_route_parser = subparsers.add_parser("train-route")
    _ = train_route_parser.add_argument("--route", required=True)
    _ = train_route_parser.add_argument("--league", required=True)
    _ = train_route_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = train_route_parser.add_argument(
        "--comps-table", default="poe_trade.ml_comps_v1"
    )
    _ = train_route_parser.add_argument("--model-dir", required=True)

    eval_route_parser = subparsers.add_parser("evaluate-route")
    _ = eval_route_parser.add_argument("--route", required=True)
    _ = eval_route_parser.add_argument("--league", required=True)
    _ = eval_route_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = eval_route_parser.add_argument("--comps-table", default="poe_trade.ml_comps_v1")
    _ = eval_route_parser.add_argument("--model-dir", required=True)

    train_parser = subparsers.add_parser("train")
    _ = train_parser.add_argument("--league", required=True)
    _ = train_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = train_parser.add_argument("--model-dir", required=True)

    train_saleability_parser = subparsers.add_parser("train-saleability")
    _ = train_saleability_parser.add_argument("--league", required=True)
    _ = train_saleability_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = train_saleability_parser.add_argument("--model-dir", required=True)

    eval_saleability_parser = subparsers.add_parser("evaluate-saleability")
    _ = eval_saleability_parser.add_argument("--league", required=True)
    _ = eval_saleability_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = eval_saleability_parser.add_argument("--model-dir", required=True)

    evaluate_parser = subparsers.add_parser("evaluate")
    _ = evaluate_parser.add_argument("--league", required=True)
    _ = evaluate_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = evaluate_parser.add_argument("--model-dir", required=True)
    _ = evaluate_parser.add_argument("--split", default="rolling")

    train_loop_parser = subparsers.add_parser("train-loop")
    _ = train_loop_parser.add_argument("--league", required=True)
    _ = train_loop_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = train_loop_parser.add_argument("--model-dir", required=True)
    _ = train_loop_parser.add_argument("--max-iterations", type=int, default=None)
    _ = train_loop_parser.add_argument(
        "--max-wall-clock-seconds", type=int, default=None
    )
    _ = train_loop_parser.add_argument(
        "--no-improvement-patience", type=int, default=None
    )
    _ = train_loop_parser.add_argument(
        "--min-mdape-improvement", type=float, default=None
    )
    _ = train_loop_parser.add_argument("--resume", action="store_true")

    status_parser = subparsers.add_parser("status")
    _ = status_parser.add_argument("--league", required=True)
    _ = status_parser.add_argument("--run", default="latest")

    predict_one_parser = subparsers.add_parser("predict-one")
    _ = predict_one_parser.add_argument("--league", required=True)
    _ = predict_one_parser.add_argument("--input-format", default="poe-clipboard")
    _ = predict_one_parser.add_argument("--stdin", action="store_true")
    _ = predict_one_parser.add_argument("--file", default=None)
    _ = predict_one_parser.add_argument("--clipboard", action="store_true")
    _ = predict_one_parser.add_argument("--output", default="human")

    predict_batch_parser = subparsers.add_parser("predict-batch")
    _ = predict_batch_parser.add_argument("--league", required=True)
    _ = predict_batch_parser.add_argument("--model-dir", required=True)
    _ = predict_batch_parser.add_argument(
        "--source", choices=("dataset", "latest"), default="dataset"
    )
    _ = predict_batch_parser.add_argument(
        "--dataset-table", default="poe_trade.ml_price_dataset_v2"
    )
    _ = predict_batch_parser.add_argument(
        "--output-table", default="poe_trade.ml_price_predictions_v1"
    )

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

    v3_train_route_parser = subparsers.add_parser("v3-train-route")
    _ = v3_train_route_parser.add_argument("--league", required=True)
    _ = v3_train_route_parser.add_argument("--route", required=True)
    _ = v3_train_route_parser.add_argument("--model-dir", required=True)

    v3_eval_parser = subparsers.add_parser("v3-evaluate")
    _ = v3_eval_parser.add_argument("--league", required=True)
    _ = v3_eval_parser.add_argument("--run-id", required=True)

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

        guarded_dataset_commands = {
            "route-preview",
            "build-comps",
            "train-route",
            "evaluate-route",
            "train",
            "train-saleability",
            "evaluate-saleability",
            "evaluate",
            "train-loop",
            "predict-batch",
        }
        guarded_model_dir_commands = {
            "train-route",
            "evaluate-route",
            "train",
            "train-saleability",
            "evaluate-saleability",
            "evaluate",
            "train-loop",
            "predict-batch",
            "report",
        }
        if command in guarded_dataset_commands:
            workflows._ensure_non_legacy_dataset_table(str(args.dataset_table))
        if command in guarded_model_dir_commands:
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
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "v3-train-route":
            result = v3_train.train_route_v3(
                client,
                league=league,
                route=str(args.route),
                model_dir=str(args.model_dir),
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
        if command == "normalize-prices":
            result = normalize_prices(
                client,
                league=league,
                output_table=str(args.output_table),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "dataset" and args.subcommand == "build":
            _ = build_listing_events_and_labels(client, league=league)
            result = build_dataset(
                client,
                league=league,
                as_of_ts=str(args.as_of),
                output_table=str(args.output_table),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "route-preview":
            result = route_preview(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                limit=int(args.limit),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "build-comps":
            result = build_comps(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                output_table=str(args.output_table),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "train-route":
            result = train_route(
                client,
                route=str(args.route),
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
                comps_table=str(args.comps_table),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "evaluate-route":
            result = evaluate_route(
                client,
                route=str(args.route),
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
                comps_table=str(args.comps_table),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "train":
            _ = train_all_routes(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
                comps_table="poe_trade.ml_comps_v1",
            )
            _ = train_saleability(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
            )
            print(
                json.dumps(
                    {"league": league, "status": "trained"}, indent=2, sort_keys=True
                )
            )
            return 0
        if command == "train-saleability":
            result = train_saleability(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "evaluate-saleability":
            result = evaluate_saleability(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "evaluate":
            result = evaluate_stack(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
                split=str(args.split),
                output_dir=str(args.model_dir),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "train-loop":
            result = train_loop(
                client,
                league=league,
                dataset_table=str(args.dataset_table),
                model_dir=str(args.model_dir),
                max_iterations=args.max_iterations,
                max_wall_clock_seconds=args.max_wall_clock_seconds,
                no_improvement_patience=args.no_improvement_patience,
                min_mdape_improvement=args.min_mdape_improvement,
                resume=bool(args.resume),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "status":
            result = status(client, league=league, run=str(args.run))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "predict-one":
            if not args.stdin and not args.file and not args.clipboard:
                raise ValueError(
                    "predict-one requires one of --stdin, --file, or --clipboard"
                )
            if str(args.input_format) != "poe-clipboard":
                raise ValueError("only --input-format poe-clipboard is supported")
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
            result = predict_one(client, league=league, clipboard_text=text)
            if output_arg == "json":
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(
                    "\n".join(
                        [
                            f"route: {result['route']}",
                            f"price_p10: {result['price_p10']}",
                            f"price_p50: {result['price_p50']}",
                            f"price_p90: {result['price_p90']}",
                            f"sale_probability_percent: {result['sale_probability_percent']}",
                            f"confidence_percent: {result['confidence_percent']}",
                            f"fallback_reason: {result['fallback_reason']}",
                        ]
                    )
                )
            return 0
        if command == "predict-batch":
            result = predict_batch(
                client,
                league=league,
                model_dir=str(args.model_dir),
                source=str(args.source),
                output_table=str(args.output_table),
                dataset_table=str(args.dataset_table),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if command == "report":
            result = report(
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
