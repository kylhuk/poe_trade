from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from ..db import ClickHouseClient
from .policy import (
    REJECTED_COOLDOWN_ACTIVE,
    REJECTED_JOURNAL_REQUIRED,
    CandidateDecision,
    CandidateRow,
    PolicyEvaluation,
    candidate_cooldown_keys,
    candidate_from_source_row,
    evaluate_candidates,
    policy_from_pack,
)
from .registry import StrategyPack, list_strategy_packs, load_candidate_sql

UNSET_COMPLETED_AT = "1970-01-01 00:00:00.000"
BACKTEST_SUMMARY_COLUMNS = (
    "run_id",
    "strategy_id",
    "league",
    "lookback_days",
    "status",
    "opportunity_count",
    "expected_profit_chaos",
    "expected_roi",
    "confidence",
    "summary",
)
BACKTEST_SUMMARY_HEADER = "\t".join(BACKTEST_SUMMARY_COLUMNS)
BACKTEST_OUTCOMES = ("completed", "no_data", "no_opportunities", "failed")

_DEFAULT_SUMMARY_TEXT = {
    "completed": "opportunities found",
    "no_data": "no source data in league/lookback window",
    "no_opportunities": "source data exists but no strategy opportunities",
    "failed": "backtest execution failed",
}


_LEGACY_COMPAT_HASH_EXPRESSION = "toString(cityHash64(concat(ifNull(source.semantic_key, ''), '|', ifNull(source.item_or_market_key, ''))))"


def get_strategy_pack(strategy_id: str) -> StrategyPack:
    for pack in list_strategy_packs():
        if pack.strategy_id == strategy_id:
            return pack
    raise ValueError(f"Unknown strategy pack: {strategy_id}")


def run_backtest(
    client: ClickHouseClient,
    *,
    strategy_id: str,
    league: str,
    lookback_days: int,
    dry_run: bool = False,
) -> str:
    pack = get_strategy_pack(strategy_id)
    run_id = uuid4().hex
    started_at = datetime.now(timezone.utc)
    started_at_sql = _format_ts(started_at)
    sql = load_candidate_sql(pack).strip().rstrip(";")
    wrapped_sql = _build_filtered_backtest_sql(
        sql, league=league, lookback_days=lookback_days
    )

    if dry_run:
        return run_id

    client.execute(
        _build_run_insert_query(
            run_id,
            strategy_id,
            league,
            lookback_days,
            started_at_sql,
            status="running",
            notes="",
        )
    )

    status = "completed"
    summary_text = _DEFAULT_SUMMARY_TEXT["completed"]
    opportunity_count = 0
    expected_profit_chaos: float | None = None
    expected_roi: float | None = None
    confidence: float | None = None

    try:
        source_rows = _fetch_source_rows(client, sql=wrapped_sql)
        evaluation, eligible_rows = _evaluate_source_rows(
            client,
            pack,
            source_rows=source_rows,
            requested_league=league,
        )
        opportunity_count = len(evaluation.eligible)
        expected_profit_chaos = _sum_optional(
            candidate.expected_profit_chaos for candidate in evaluation.eligible
        )
        expected_roi = _avg_optional(
            candidate.expected_roi for candidate in evaluation.eligible
        )
        confidence = _avg_optional(
            candidate.confidence for candidate in evaluation.eligible
        )

        if eligible_rows:
            client.execute(
                _build_detail_insert_query(
                    run_id=run_id,
                    strategy_id=strategy_id,
                    league=league,
                    lookback_days=lookback_days,
                    eligible_rows=eligible_rows,
                )
            )

        if opportunity_count == 0:
            if not source_rows:
                status = "no_data"
                summary_text = _DEFAULT_SUMMARY_TEXT["no_data"]
            else:
                status = "no_opportunities"
                summary_text = _no_opportunities_summary(evaluation.decisions)

    except Exception as exc:
        status = "failed"
        summary_text = f"{_DEFAULT_SUMMARY_TEXT['failed']}: {exc}"
        opportunity_count = 0
        expected_profit_chaos = None
        expected_roi = None
        confidence = None
        client.execute(
            _build_summary_insert_query(
                run_id=run_id,
                strategy_id=strategy_id,
                league=league,
                lookback_days=lookback_days,
                status=status,
                opportunity_count=opportunity_count,
                expected_profit_chaos=expected_profit_chaos,
                expected_roi=expected_roi,
                confidence=confidence,
                summary=summary_text,
            )
        )
        client.execute(
            _build_run_insert_query(
                run_id,
                strategy_id,
                league,
                lookback_days,
                started_at_sql,
                status="failed",
                notes=summary_text,
            )
        )
        raise

    client.execute(
        _build_summary_insert_query(
            run_id=run_id,
            strategy_id=strategy_id,
            league=league,
            lookback_days=lookback_days,
            status=status,
            opportunity_count=opportunity_count,
            expected_profit_chaos=expected_profit_chaos,
            expected_roi=expected_roi,
            confidence=confidence,
            summary=summary_text,
        )
    )
    client.execute(
        _build_run_insert_query(
            run_id,
            strategy_id,
            league,
            lookback_days,
            started_at_sql,
            status=status,
            notes="shared summary contract",
        )
    )
    return run_id


def fetch_backtest_summary_rows(
    client: ClickHouseClient,
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    payload = client.execute(
        "SELECT "
        "run_id, strategy_id, league, lookback_days, status, opportunity_count, expected_profit_chaos, expected_roi, confidence, summary "
        "FROM poe_trade.research_backtest_summary "
        f"WHERE run_id = '{_escape_sql(run_id)}' "
        "ORDER BY strategy_id "
        "FORMAT JSONEachRow"
    )
    return _parse_json_rows(payload)


def format_summary_row(row: dict[str, Any]) -> str:
    values: list[str] = []
    for column in BACKTEST_SUMMARY_COLUMNS:
        value = row.get(column)
        if value is None:
            values.append("")
        else:
            values.append(str(value))
    return "\t".join(values)


def backtest_status_rank(status: str) -> int:
    ranking = {
        "completed": 0,
        "no_opportunities": 1,
        "no_data": 2,
        "failed": 3,
    }
    return ranking.get(status, 9)


def _format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _build_filtered_backtest_sql(sql: str, *, league: str, lookback_days: int) -> str:
    return (
        "SELECT * FROM ("
        f"{sql}"
        ") AS scoped_source "
        f"WHERE ifNull(scoped_source.league, '') = '{_escape_sql(league)}' "
        f"AND scoped_source.time_bucket >= now() - INTERVAL {max(1, int(lookback_days))} DAY"
    )


def _build_run_insert_query(
    run_id: str,
    strategy_id: str,
    league: str,
    lookback_days: int,
    started_at_sql: str,
    *,
    status: str,
    notes: str,
) -> str:
    payload = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "league": league,
        "lookback_days": int(lookback_days),
        "started_at": started_at_sql,
        "completed_at": _format_ts(datetime.now(timezone.utc))
        if status != "running"
        else UNSET_COMPLETED_AT,
        "status": status,
        "notes": notes,
    }
    return (
        "INSERT INTO poe_trade.research_backtest_runs "
        "(run_id, strategy_id, league, lookback_days, started_at, completed_at, status, notes)\n"
        "FORMAT JSONEachRow\n"
        f"{json.dumps(payload, separators=(',', ':'))}"
    )


def _build_summary_insert_query(
    *,
    run_id: str,
    strategy_id: str,
    league: str,
    lookback_days: int,
    status: str,
    opportunity_count: int,
    expected_profit_chaos: float | None,
    expected_roi: float | None,
    confidence: float | None,
    summary: str,
) -> str:
    payload = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "league": league,
        "lookback_days": int(lookback_days),
        "status": status,
        "opportunity_count": int(opportunity_count),
        "expected_profit_chaos": expected_profit_chaos,
        "expected_roi": expected_roi,
        "confidence": confidence,
        "summary": summary,
        "recorded_at": _format_ts(datetime.now(timezone.utc)),
    }
    return (
        "INSERT INTO poe_trade.research_backtest_summary "
        "(run_id, strategy_id, league, lookback_days, status, opportunity_count, expected_profit_chaos, expected_roi, confidence, summary, recorded_at)\n"
        "FORMAT JSONEachRow\n"
        f"{json.dumps(payload, separators=(',', ':'))}"
    )


def _parse_json_rows(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _fetch_source_rows(
    client: ClickHouseClient,
    *,
    sql: str,
) -> list[dict[str, Any]]:
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


def _evaluate_source_rows(
    client: ClickHouseClient,
    pack: StrategyPack,
    *,
    source_rows: list[dict[str, Any]],
    requested_league: str,
) -> tuple[PolicyEvaluation, list[tuple[CandidateRow, dict[str, Any]]]]:
    candidates: list[CandidateRow] = []
    source_by_candidate_id: dict[int, dict[str, Any]] = {}
    for source_row in source_rows:
        candidate = candidate_from_source_row(
            pack.strategy_id,
            source_row,
            default_league=requested_league,
        )
        candidates.append(candidate)
        source_by_candidate_id[id(candidate)] = source_row
    sorted_candidates = sorted(candidates, key=lambda row: row.candidate_ts)
    policy = policy_from_pack(pack)
    cooldown_history = _fetch_last_alerted_at_by_key(
        client,
        strategy_id=pack.strategy_id,
        league=requested_league,
    )
    decisions: list[CandidateDecision] = []
    eligible: list[CandidateRow] = []
    batch: list[CandidateRow] = []
    last_ts: datetime | None = None

    def flush_batch() -> None:
        nonlocal batch
        if not batch:
            return
        step_eval = evaluate_candidates(
            batch,
            policy=policy,
            requested_league=requested_league,
            last_alerted_at_by_key=cooldown_history,
        )
        decisions.extend(step_eval.decisions)
        for accepted in step_eval.eligible:
            eligible.append(accepted)
            for key in candidate_cooldown_keys(accepted):
                cooldown_history[key] = accepted.candidate_ts
        batch = []

    for candidate in sorted_candidates:
        if last_ts is None or candidate.candidate_ts != last_ts:
            flush_batch()
            batch = [candidate]
            last_ts = candidate.candidate_ts
        else:
            batch.append(candidate)
    flush_batch()
    full_eval = PolicyEvaluation(eligible=tuple(eligible), decisions=tuple(decisions))
    eligible_rows = [
        (candidate, source_by_candidate_id[id(candidate)]) for candidate in eligible
    ]
    return full_eval, eligible_rows


def _build_detail_insert_query(
    *,
    run_id: str,
    strategy_id: str,
    league: str,
    lookback_days: int,
    eligible_rows: list[tuple[CandidateRow, dict[str, Any]]],
) -> str:
    recorded_at = _format_ts(datetime.now(timezone.utc))
    payload_rows = []
    for candidate, source_row in eligible_rows:
        payload_rows.append(
            {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "league": league,
                "lookback_days": int(lookback_days),
                "status": "completed",
                "recorded_at": recorded_at,
                "item_or_market_key": candidate.item_or_market_key,
                "expected_profit_chaos": candidate.expected_profit_chaos,
                "expected_roi": candidate.expected_roi,
                "confidence": candidate.confidence,
                "summary": _detail_summary(strategy_id, source_row),
                "detail_json": json.dumps(source_row, separators=(",", ":")),
            }
        )
    payload = "\n".join(json.dumps(row, separators=(",", ":")) for row in payload_rows)
    return (
        "INSERT INTO poe_trade.research_backtest_detail "
        "(run_id, strategy_id, league, lookback_days, status, recorded_at, item_or_market_key, expected_profit_chaos, expected_roi, confidence, summary, detail_json)\n"
        "FORMAT JSONEachRow\n"
        f"{payload}"
    )


def _detail_summary(strategy_id: str, source_row: dict[str, Any]) -> str:
    for field in ("summary", "why_it_fired"):
        value = source_row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"eligible candidate for {strategy_id}"


def _no_opportunities_summary(decisions: tuple[CandidateDecision, ...]) -> str:
    reasons = {decision.reason for decision in decisions if not decision.accepted}
    if reasons == {REJECTED_JOURNAL_REQUIRED}:
        return "source data exists but all candidates require journal state"
    if reasons == {REJECTED_COOLDOWN_ACTIVE}:
        return "source data exists but candidates are still cooling down"
    return _DEFAULT_SUMMARY_TEXT["no_opportunities"]


def _fetch_last_alerted_at_by_key(
    client: ClickHouseClient,
    *,
    strategy_id: str,
    league: str,
) -> dict[str, datetime]:
    payload = client.execute(
        "SELECT item_or_market_key, max(recorded_at) AS last_recorded_at "
        "FROM poe_trade.scanner_alert_log "
        f"WHERE strategy_id = '{_escape_sql(strategy_id)}' "
        f"AND league = '{_escape_sql(league)}' "
        "GROUP BY item_or_market_key "
        "FORMAT JSONEachRow"
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


def _parse_datetime(value: Any) -> datetime | None:
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


def _sum_optional(values: Any) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return float(sum(numbers))


def _avg_optional(values: Any) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return float(sum(numbers) / len(numbers))


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")
