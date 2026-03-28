#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the fast-sale benchmark JSON/JSONL dataset"
    )
    _ = parser.add_argument("--input", required=True)
    return parser


def _load_rows(input_path: Path) -> list[dict[str, object]]:
    payload_text = input_path.read_text(encoding="utf-8")
    if payload_text.lstrip().startswith("["):
        parsed = json.loads(payload_text)
        if not isinstance(parsed, list):
            raise ValueError("JSON input must be an array of objects")
        return [dict(row) for row in parsed if isinstance(row, dict)]
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(payload_text.splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"JSONL input line {line_number} must be an object")
        rows.append(dict(parsed))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        rows = _load_rows(Path(str(args.input)))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

    timestamps: Counter[str] = Counter()
    identities: Counter[str] = Counter()
    targets: list[float] = []
    for row in rows:
        timestamps[str(row.get("as_of_ts") or "")] += 1
        identities[str(row.get("identity_key") or row.get("item_id") or "")] += 1
        try:
            targets.append(float(row.get("target_fast_sale_24h_price") or 0.0))
        except (TypeError, ValueError):
            targets.append(0.0)

    summary = {
        "row_count": len(rows),
        "target_count": sum(1 for value in targets if value > 0),
        "unique_timestamps": len(timestamps),
        "unique_identity_keys": len(identities),
        "duplicate_identity_groups": sum(
            1 for count in identities.values() if count > 1
        ),
        "target_min": min(targets) if targets else 0.0,
        "target_median": statistics.median(targets) if targets else 0.0,
        "target_mean": statistics.mean(targets) if targets else 0.0,
        "target_max": max(targets) if targets else 0.0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
