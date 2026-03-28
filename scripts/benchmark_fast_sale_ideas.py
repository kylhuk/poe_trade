#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_trade.ml.v3 import benchmark


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fast-sale 24h benchmark on a JSON or JSONL dataset"
    )
    _ = parser.add_argument("--input", required=True)
    _ = parser.add_argument("--output", required=True)
    return parser


def _load_rows(input_path: Path) -> list[dict[str, object]]:
    payload_text = input_path.read_text(encoding="utf-8")
    if payload_text.lstrip().startswith("["):
        try:
            parsed = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"failed to parse JSON input: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("JSON input must be an array of objects")
        rows: list[dict[str, object]] = []
        for row in parsed:
            if not isinstance(row, dict):
                raise ValueError("JSON array input must contain objects")
            rows.append(dict(row))
        return rows
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(payload_text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"failed to parse JSONL input at line {line_number}: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"JSONL input line {line_number} must be an object")
        rows.append(dict(parsed))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_path = Path(str(args.input))
    output_path = Path(str(args.output))

    try:
        rows = _load_rows(input_path)
        report = benchmark.run_fast_sale_benchmark(rows)
        artifacts = benchmark.save_fast_sale_benchmark_artifacts(report, output_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "fast-sale benchmark command failed: %s", exc
        )
        return 1

    print(
        json.dumps(
            {
                "benchmark": report["benchmark"],
                "contract": report["contract"],
                "split": report["split"],
                "row_count": report["row_count"],
                "candidate_count": report["contract"]["candidate_count"],
                "best_candidate": report["best_candidate"],
                "artifacts": artifacts["artifacts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
