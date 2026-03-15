from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import time
from typing import cast
from uuid import uuid4

from ..db import ClickHouseClient
from .policy import (
    CandidateRow,
    build_evidence_snapshot,
    candidate_from_source_row,
    evaluate_candidates,
    policy_from_pack,
)
from .registry import list_strategy_packs, load_candidate_sql


_LEGACY_COMPAT_HASH_EXPRESSION = "toString(cityHash64(concat(ifNull(source.semantic_key, ''), '|', ifNull(source.item_or_market_key, ''))))"


def run_scan_once(
    client: ClickHouseClient,
    *,
    league: str,
    dry_run: bool = False,
) -> str:
    scanner_run_id = uuid4().hex
    enabled_packs = [pack for pack in list_strategy_packs() if pack.enabled]

    if dry_run:
        return scanner_run_id

    for pack in enabled_packs:
        source_rows = _fetch_candidate_source_rows(client, sql=load_candidate_sql(pack))
        journal_active_keys: set[str] | None = None
        if pack.requires_journal:
            journal_active_keys = _fetch_journal_active_keys(
                client,
                strategy_id=pack.strategy_id,
                league=league,
            )
        candidates = [
            candidate_from_source_row(
                pack.strategy_id,
                source_row,
                default_league=league,
            )
            for source_row in source_rows
        ]
        source_by_candidate = {
            id(candidate): source_row
            for candidate, source_row in zip(candidates, source_rows, strict=False)
        }
        evaluation = evaluate_candidates(
            candidates,
            policy=policy_from_pack(pack),
            requested_league=league,
            journal_active_keys=journal_active_keys,
            last_alerted_at_by_key=_fetch_last_alerted_at_by_key(
                client,
                strategy_id=pack.strategy_id,
                league=league,
            ),
        )
        recommendation_rows = [
            _recommendation_payload(
                scanner_run_id=scanner_run_id,
                pack=pack,
                candidate=candidate,
                source_row=source_by_candidate[id(candidate)],
            )
            for candidate in evaluation.eligible
        ]
        if recommendation_rows:
            _ = client.execute(
                "INSERT INTO poe_trade.scanner_recommendations "
                + "(scanner_run_id, strategy_id, league, item_or_market_key, why_it_fired, buy_plan, max_buy, transform_plan, exit_plan, execution_venue, expected_profit_chaos, expected_roi, expected_hold_time, confidence, evidence_snapshot, recorded_at)\n"
                + "FORMAT JSONEachRow\n"
                + "\n".join(
                    json.dumps(row, separators=(",", ":"))
                    for row in recommendation_rows
                )
            )
            _ = client.execute(
                "INSERT INTO poe_trade.scanner_alert_log "
                + "(alert_id, scanner_run_id, strategy_id, league, item_or_market_key, status, evidence_snapshot, recorded_at)\n"
                + "FORMAT JSONEachRow\n"
                + "\n".join(
                    json.dumps(_alert_payload(row), separators=(",", ":"))
                    for row in recommendation_rows
                )
            )

    return scanner_run_id


def run_scan_watch(
    client: ClickHouseClient,
    *,
    league: str,
    interval_seconds: float,
    max_runs: int | None = None,
    dry_run: bool = False,
) -> list[str]:
    run_ids: list[str] = []
    completed_runs = 0
    while max_runs is None or completed_runs < max_runs:
        run_ids.append(run_scan_once(client, league=league, dry_run=dry_run))
        completed_runs += 1
        if max_runs is not None and completed_runs >= max_runs:
            break
        time.sleep(interval_seconds)
    return run_ids


def format_scan_timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _fetch_candidate_source_rows(
    client: ClickHouseClient,
    *,
    sql: str,
) -> list[dict[str, object]]:
    candidate_sql = sql.strip().rstrip(";")
    payload = client.execute(
        "SELECT "
        + "source.*, "
        + "formatRowNoNewline('JSONEachRow', source.*) AS source_row_json, "
        + f"{_LEGACY_COMPAT_HASH_EXPRESSION} AS legacy_hashed_item_or_market_key "
        + f"FROM ({candidate_sql}) AS source "
        + "FORMAT JSONEachRow"
    )
    return _parse_json_rows(payload)


def _fetch_last_alerted_at_by_key(
    client: ClickHouseClient,
    *,
    strategy_id: str,
    league: str,
) -> dict[str, datetime]:
    payload = client.execute(
        "SELECT item_or_market_key, max(recorded_at) AS last_recorded_at "
        + "FROM poe_trade.scanner_alert_log "
        + f"WHERE strategy_id = '{_escape_sql(strategy_id)}' "
        + f"AND league = '{_escape_sql(league)}' "
        + "GROUP BY item_or_market_key "
        + "FORMAT JSONEachRow"
    )
    rows = _parse_json_rows(payload)
    last_alerted: dict[str, datetime] = {}
    for row in rows:
        key = str(row.get("item_or_market_key") or "").strip()
        if not key:
            continue
        parsed = _parse_datetime(row.get("last_recorded_at"))
        if parsed is not None:
            last_alerted[key] = parsed
    return last_alerted


def _fetch_journal_active_keys(
    client: ClickHouseClient,
    *,
    strategy_id: str,
    league: str,
) -> set[str]:
    payload = client.execute(
        "SELECT item_or_market_key "
        + "FROM poe_trade.journal_positions "
        + f"WHERE strategy_id = '{_escape_sql(strategy_id)}' "
        + f"AND league = '{_escape_sql(league)}' "
        + "FORMAT JSONEachRow"
    )
    rows = _parse_json_rows(payload)
    active_keys: set[str] = set()
    for row in rows:
        key = str(row.get("item_or_market_key") or "").strip()
        if key:
            active_keys.add(key)
    return active_keys


def _recommendation_payload(
    *,
    scanner_run_id: str,
    pack: object,
    candidate: CandidateRow,
    source_row: Mapping[str, object],
) -> dict[str, object]:
    recorded_at = format_scan_timestamp()
    evidence_snapshot = build_evidence_snapshot(candidate)
    semantic_item_or_market_key = _canonical_item_or_market_key(
        candidate.item_or_market_key
    )
    source_row_json = str(source_row.get("source_row_json") or "")
    if source_row_json:
        _ = evidence_snapshot.setdefault("source_row_json", source_row_json)
        _ = evidence_snapshot.setdefault("evidence_snapshot", source_row_json)
    return {
        "scanner_run_id": scanner_run_id,
        "strategy_id": candidate.strategy_id,
        "league": candidate.league,
        "item_or_market_key": semantic_item_or_market_key,
        "why_it_fired": _non_empty_text(
            source_row.get("why_it_fired"),
            fallback=f"discovered by {candidate.strategy_id}",
        ),
        "buy_plan": _non_empty_text(
            source_row.get("buy_plan"), fallback="buy candidate"
        ),
        "max_buy": _as_optional_float(source_row.get("max_buy")),
        "transform_plan": _non_empty_text(
            source_row.get("transform_plan"), fallback=""
        ),
        "exit_plan": _non_empty_text(
            source_row.get("exit_plan"),
            fallback="review and sell",
        ),
        "execution_venue": str(getattr(pack, "execution_venue", "manual_trade")),
        "expected_profit_chaos": candidate.expected_profit_chaos,
        "expected_roi": candidate.expected_roi,
        "expected_hold_time": _non_empty_text(
            source_row.get("expected_hold_time"),
            fallback="unknown",
        ),
        "confidence": candidate.confidence,
        "evidence_snapshot": json.dumps(evidence_snapshot, separators=(",", ":")),
        "recorded_at": recorded_at,
    }


def _alert_payload(recommendation_row: Mapping[str, object]) -> dict[str, object]:
    strategy_id = str(recommendation_row.get("strategy_id") or "")
    league = str(recommendation_row.get("league") or "")
    semantic_item_or_market_key = _canonical_item_or_market_key(
        recommendation_row.get("item_or_market_key")
    )
    return {
        "alert_id": f"{strategy_id}|{league}|{semantic_item_or_market_key}",
        "scanner_run_id": recommendation_row.get("scanner_run_id"),
        "strategy_id": strategy_id,
        "league": league,
        "item_or_market_key": semantic_item_or_market_key,
        "status": "new",
        "evidence_snapshot": recommendation_row.get("evidence_snapshot"),
        "recorded_at": recommendation_row.get("recorded_at"),
    }


def _parse_json_rows(payload: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in payload.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        parsed = cast(object, json.loads(cleaned))
        if isinstance(parsed, dict):
            rows.append(cast(dict[str, object], parsed))
    return rows


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = f"{cleaned[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _non_empty_text(value: object, *, fallback: str) -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned else fallback


def _as_optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _canonical_item_or_market_key(value: object) -> str:
    return str(value or "").strip()


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")
