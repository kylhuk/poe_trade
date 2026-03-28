#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

import joblib


DEFAULT_REQUIRED_ARTIFACTS = [
    "ml-pricing-benchmark-update.txt",
    "ml-pricing-benchmark-update.json",
    "ml-pricing-benchmark-update.txt.joblib",
]

REQUIRED_JSON_KEYS: dict[str, tuple[str, ...]] = {
    "ml-pricing-benchmark-update.json": (
        "contract",
        "split",
        "candidate_results",
        "ranking",
        "best_candidate",
    ),
}

EXPECTED_CANDIDATES = (
    "elasticnet_log",
    "huber_log",
    "catboost_log",
    "lightgbm_log",
    "xgboost_log",
    "quantile_regressor_log",
    "censored_quantile_log",
    "censored_forest_log",
    "knn_log",
    "stacked_ensemble_log",
)

REPORT_MARKER = "# ML Pricing Benchmark Report"
REPORT_TABLE_HEADER = "| Candidate | Val MDAPE | Test MDAPE | Val WAPE | Test WAPE |"


def _validate_report_payload(payload: dict[str, object], *, prefix: str) -> list[str]:
    errors: list[str] = []
    ranking = payload.get("ranking")
    if not isinstance(ranking, list):
        return [f"{prefix}:ranking_not_list"]
    if len(ranking) != 10:
        errors.append(f"{prefix}:expected_10_candidates_got_{len(ranking)}")
    ranking_candidates: list[str] = []
    for row in ranking:
        if not isinstance(row, dict):
            errors.append(f"{prefix}:ranking_row_not_object")
            continue
        ranking_candidates.append(str(row.get("candidate") or ""))
    if len(set(ranking_candidates)) != len(ranking_candidates):
        errors.append(f"{prefix}:ranking_has_duplicates")
    if set(ranking_candidates) != set(EXPECTED_CANDIDATES):
        errors.append(f"{prefix}:candidate_set_mismatch")

    candidate_results = payload.get("candidate_results")
    if not isinstance(candidate_results, list) or len(candidate_results) != 10:
        errors.append(f"{prefix}:candidate_results_not_10")

    best_candidate = payload.get("best_candidate")
    if not isinstance(best_candidate, dict):
        errors.append(f"{prefix}:best_candidate_not_object")
    else:
        best_name = str(best_candidate.get("candidate") or "")
        if best_name not in EXPECTED_CANDIDATES:
            errors.append(f"{prefix}:best_candidate_unknown")
        elif ranking_candidates and ranking_candidates[0] != best_name:
            errors.append(f"{prefix}:best_candidate_not_ranking_head")

    return errors


def _validate_report_semantics(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return [f"{path.name}:unreadable"]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != REPORT_MARKER:
        return [f"{path.name}:missing_title"]
    if REPORT_TABLE_HEADER not in lines:
        return [f"{path.name}:missing_table_header"]
    row_lines = [
        line for line in lines if line.startswith("| ") and line.endswith(" |")
    ]
    candidate_rows = [
        line
        for line in row_lines
        if line not in {REPORT_TABLE_HEADER, "|---|---:|---:|---:|---:|"}
    ]
    if len(candidate_rows) != 10:
        return [f"{path.name}:expected_10_candidates_got_{len(candidate_rows)}"]
    candidate_names = [row.split("|")[1].strip() for row in candidate_rows]
    if set(candidate_names) != set(EXPECTED_CANDIDATES):
        return [f"{path.name}:candidate_set_mismatch"]
    best_lines = [line for line in lines if line.startswith("Best candidate:")]
    if not best_lines:
        return [f"{path.name}:missing_best_candidate"]
    top_lines = [line for line in lines if line.startswith("Top single-model:")]
    if not top_lines:
        return [f"{path.name}:missing_top_single_model"]
    if "stacked_ensemble_log" not in best_lines[0]:
        return [f"{path.name}:best_candidate_not_stacked"]
    if "elasticnet_log" not in top_lines[0]:
        return [f"{path.name}:top_single_not_elasticnet"]
    return []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify required deterministic ML evidence artifacts and "
            "write a reproducible evidence-pack log."
        )
    )
    _ = parser.add_argument(
        "--evidence-root",
        default=".sisyphus/evidence",
        help="Directory that contains deterministic evidence artifacts.",
    )
    _ = parser.add_argument(
        "--output-log",
        default=".sisyphus/evidence/ml-pricing-benchmark-update-deterministic-pack.txt",
        help="Path to write the deterministic evidence pack log.",
    )
    _ = parser.add_argument(
        "--required",
        nargs="+",
        default=DEFAULT_REQUIRED_ARTIFACTS,
        help=(
            "Relative artifact paths under --evidence-root that are required "
            "for deterministic ML verification."
        ),
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = cast(argparse.Namespace, parser.parse_args())

    evidence_root = Path(str(args.evidence_root))
    output_log = Path(str(args.output_log))
    raw_required = [str(item) for item in cast(list[object], args.required)]
    required = sorted(set(raw_required))

    missing: list[str] = []
    invalid: list[str] = []
    present_entries: list[dict[str, object]] = []
    for rel_path in required:
        artifact_path = evidence_root / rel_path
        if not artifact_path.exists() or not artifact_path.is_file():
            missing.append(rel_path)
            continue
        json_keys = REQUIRED_JSON_KEYS.get(rel_path)
        if json_keys is not None:
            try:
                parsed = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                invalid.append(f"{rel_path}:invalid_json")
                continue
            if not isinstance(parsed, dict):
                invalid.append(f"{rel_path}:not_object")
                continue
            missing_keys = [key for key in json_keys if key not in parsed]
            if missing_keys:
                invalid.append(f"{rel_path}:missing_keys({','.join(missing_keys)})")
                continue
            invalid.extend(_validate_report_payload(parsed, prefix=rel_path))
            if invalid and any(entry.startswith(f"{rel_path}:") for entry in invalid):
                continue
        elif rel_path.endswith(".txt"):
            invalid.extend(_validate_report_semantics(artifact_path))
            if invalid and any(entry.startswith(f"{rel_path}:") for entry in invalid):
                continue
        elif rel_path.endswith(".txt.joblib"):
            try:
                loaded = joblib.load(artifact_path)
            except Exception:
                invalid.append(f"{rel_path}:unreadable")
                continue
            if not isinstance(loaded, dict):
                invalid.append(f"{rel_path}:not_object")
                continue
            invalid.extend(_validate_report_payload(loaded, prefix=rel_path))
            if invalid and any(entry.startswith(f"{rel_path}:") for entry in invalid):
                continue
        present_entries.append(
            {
                "artifact": rel_path,
                "bytes": artifact_path.stat().st_size,
                "sha256": _sha256(artifact_path),
            }
        )

    payload: dict[str, object] = {
        "evidence_root": str(evidence_root),
        "required_artifacts": required,
        "present": present_entries,
        "missing": missing,
        "invalid": invalid,
        "status": "ok"
        if not missing and not invalid
        else "missing_or_invalid_artifacts",
    }

    output_log.parent.mkdir(parents=True, exist_ok=True)
    _ = output_log.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if missing or invalid:
        missing_csv = ", ".join(missing)
        invalid_csv = ", ".join(invalid)
        details = []
        if missing_csv:
            details.append(f"missing required artifact(s): {missing_csv}")
        if invalid_csv:
            details.append(f"invalid artifact payload(s): {invalid_csv}")
        message = (
            "ERROR: deterministic ML evidence verification failed; "
            + "; ".join(details)
            + f". See {output_log} for details."
        )
        print(message)
        return 1

    print(f"deterministic ML evidence verification passed; wrote {output_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
