from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import logging
import re
import time
from typing import cast
from uuid import uuid4

from .. import __version__
from ..config import constants
from ..db import ClickHouseClient, ClickHouseClientError
from .policy import (
    CandidateRow,
    CandidateDecision,
    REJECTED_INVALID_SOURCE_ROW,
    build_evidence_snapshot,
    candidate_from_source_row,
    evaluate_candidates,
    policy_from_pack,
)
from .registry import list_strategy_packs, load_candidate_sql


_LEGACY_COMPAT_HASH_EXPRESSION = "toString(cityHash64(concat(ifNull(source.semantic_key, ''), '|', ifNull(source.item_or_market_key, ''))))"
_HISTORICAL_LEGACY_COMPAT_HASH_EXPRESSION = (
    "toString(cityHash64(formatRowNoNewline('JSONEachRow', source.*)))"
)

logger = logging.getLogger(__name__)

_SCHEMA_FALLBACK_COLUMNS = frozenset(
    {
        "recommendation_source",
        "recommendation_contract_version",
        "producer_version",
        "producer_run_id",
        "opportunity_type",
        "complexity_tier",
        "required_capital_chaos",
        "estimated_operations",
        "estimated_whispers",
        "expected_profit_per_operation_chaos",
        "feasibility_score",
    }
)
_MISSING_COLUMN_ERROR_PATTERNS = (
    re.compile(r"unknown\s+(?:identifier|column)\s+[`'\"]?([a-z0-9_]+)[`'\"]?"),
    re.compile(r"missing\s+columns?\s*:\s*([^\n]+)"),
    re.compile(r"there\s+is\s+no\s+column\s+[`'\"]?([a-z0-9_]+)[`'\"]?"),
    re.compile(r"no\s+such\s+column\s+[`'\"]?([a-z0-9_]+)[`'\"]?"),
)

_RECOMMENDATION_INSERT_COLUMNS = (
    "scanner_run_id",
    "strategy_id",
    "league",
    "recommendation_source",
    "recommendation_contract_version",
    "producer_version",
    "producer_run_id",
    "item_or_market_key",
    "why_it_fired",
    "buy_plan",
    "max_buy",
    "transform_plan",
    "exit_plan",
    "execution_venue",
    "expected_profit_chaos",
    "expected_roi",
    "expected_hold_time",
    "confidence",
    "opportunity_type",
    "complexity_tier",
    "required_capital_chaos",
    "estimated_operations",
    "estimated_whispers",
    "expected_profit_per_operation_chaos",
    "feasibility_score",
    "evidence_snapshot",
    "recorded_at",
)

_RECOMMENDATION_INSERT_COLUMNS_V2 = (
    "scanner_run_id",
    "strategy_id",
    "league",
    "recommendation_source",
    "recommendation_contract_version",
    "producer_version",
    "producer_run_id",
    "item_or_market_key",
    "why_it_fired",
    "buy_plan",
    "max_buy",
    "transform_plan",
    "exit_plan",
    "execution_venue",
    "expected_profit_chaos",
    "expected_roi",
    "expected_hold_time",
    "confidence",
    "evidence_snapshot",
    "recorded_at",
)

_LEGACY_RECOMMENDATION_INSERT_COLUMNS = (
    "scanner_run_id",
    "strategy_id",
    "league",
    "item_or_market_key",
    "why_it_fired",
    "buy_plan",
    "max_buy",
    "transform_plan",
    "exit_plan",
    "execution_venue",
    "expected_profit_chaos",
    "expected_roi",
    "expected_hold_time",
    "confidence",
    "evidence_snapshot",
    "recorded_at",
)

_DECISION_INSERT_COLUMNS = (
    "scanner_run_id",
    "accepted",
    "decision_reason",
    "strategy_id",
    "league",
    "recommendation_source",
    "recommendation_contract_version",
    "producer_version",
    "producer_run_id",
    "item_or_market_key",
    "complexity_tier",
    "required_capital_chaos",
    "estimated_operations",
    "estimated_whispers",
    "expected_profit_chaos",
    "expected_profit_per_operation_chaos",
    "feasibility_score",
    "evidence_snapshot",
    "recorded_at",
)

_DECISION_COMPAT_COLUMNS = frozenset(_DECISION_INSERT_COLUMNS)

_ALERT_INSERT_COLUMNS = (
    "alert_id",
    "scanner_run_id",
    "strategy_id",
    "league",
    "recommendation_source",
    "recommendation_contract_version",
    "producer_version",
    "producer_run_id",
    "item_or_market_key",
    "status",
    "evidence_snapshot",
    "recorded_at",
)

_LEGACY_ALERT_INSERT_COLUMNS = (
    "alert_id",
    "scanner_run_id",
    "strategy_id",
    "league",
    "item_or_market_key",
    "status",
    "evidence_snapshot",
    "recorded_at",
)

_MISSING_TABLE_ERROR_PATTERNS = (
    re.compile(r"table\s+([a-z0-9_.]+)\s+does(?:n't| not)\s+exist"),
    re.compile(r"unknown\s+table\s+(?:expression|identifier)?\s*([a-z0-9_.]+)"),
    re.compile(r"table\s+([a-z0-9_.]+)\s+not\s+found"),
)


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
        try:
            source_rows = _fetch_candidate_source_rows(
                client, sql=load_candidate_sql(pack)
            )
            journal_active_keys: set[str] | None = None
            if pack.requires_journal:
                journal_active_keys = _fetch_journal_active_keys(
                    client,
                    strategy_id=pack.strategy_id,
                    league=league,
                )
            candidates: list[CandidateRow] = []
            invalid_decisions: list[CandidateDecision] = []
            source_by_candidate: dict[int, Mapping[str, object]] = {}
            for source_row in source_rows:
                try:
                    candidate = candidate_from_source_row(
                        pack.strategy_id,
                        source_row,
                        default_league=league,
                        default_estimated_operations=getattr(
                            pack, "max_estimated_operations", None
                        ),
                        default_estimated_whispers=getattr(
                            pack, "max_estimated_whispers", None
                        ),
                        default_profit_per_operation_chaos=getattr(
                            pack,
                            "advanced_override_profit_per_operation_chaos",
                            None,
                        ),
                    )
                except ValueError as exc:
                    invalid_decisions.append(
                        CandidateDecision(
                            candidate=_invalid_candidate_row(
                                strategy_id=pack.strategy_id,
                                source_row=source_row,
                                default_league=league,
                                error=str(exc),
                            ),
                            accepted=False,
                            reason=REJECTED_INVALID_SOURCE_ROW,
                        )
                    )
                    continue
                candidates.append(candidate)
                source_by_candidate[id(candidate)] = source_row
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
            decision_rows = [
                _decision_payload(
                    scanner_run_id=scanner_run_id,
                    decision=decision,
                    source_row=source_by_candidate.get(id(decision.candidate)),
                )
                for decision in (*invalid_decisions, *evaluation.decisions)
            ]
            if decision_rows:
                _insert_candidate_decision_rows(
                    client,
                    rows=decision_rows,
                )
            if recommendation_rows:
                _insert_json_rows(
                    client,
                    table="poe_trade.scanner_recommendations",
                    rows=recommendation_rows,
                    columns=_RECOMMENDATION_INSERT_COLUMNS,
                    fallback_columns=_LEGACY_RECOMMENDATION_INSERT_COLUMNS,
                )
                _insert_json_rows(
                    client,
                    table="poe_trade.scanner_alert_log",
                    rows=[_alert_payload(row) for row in recommendation_rows],
                    columns=_ALERT_INSERT_COLUMNS,
                    fallback_columns=_LEGACY_ALERT_INSERT_COLUMNS,
                )
        except Exception:
            logger.exception(
                "scanner strategy pack failed: %s",
                pack.strategy_id,
                extra={"strategy_id": pack.strategy_id, "league": league},
            )
            continue

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
        + f"{_LEGACY_COMPAT_HASH_EXPRESSION} AS legacy_hashed_item_or_market_key, "
        + f"{_HISTORICAL_LEGACY_COMPAT_HASH_EXPRESSION} AS historical_legacy_hashed_item_or_market_key "
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
    query = (
        "SELECT item_or_market_key, max(recorded_at) AS last_recorded_at "
        + "FROM poe_trade.scanner_alert_log "
        + f"WHERE strategy_id = '{_escape_sql(strategy_id)}' "
        + f"AND league = '{_escape_sql(league)}' "
        + f"AND recommendation_contract_version = {constants.RECOMMENDATION_CONTRACT_VERSION} "
        + "GROUP BY item_or_market_key "
        + "FORMAT JSONEachRow"
    )
    legacy_query = (
        "SELECT item_or_market_key, max(recorded_at) AS last_recorded_at "
        + "FROM poe_trade.scanner_alert_log "
        + f"WHERE strategy_id = '{_escape_sql(strategy_id)}' "
        + f"AND league = '{_escape_sql(league)}' "
        + "GROUP BY item_or_market_key "
        + "FORMAT JSONEachRow"
    )
    payload = _execute_with_legacy_fallback(client, query, legacy_query)
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
        "recommendation_source": _non_empty_text(
            source_row.get("recommendation_source"),
            fallback=constants.DEFAULT_RECOMMENDATION_SOURCE,
        ),
        "recommendation_contract_version": constants.RECOMMENDATION_CONTRACT_VERSION,
        "producer_version": _non_empty_text(
            source_row.get("producer_version"),
            fallback=__version__,
        ),
        "producer_run_id": _non_empty_text(
            source_row.get("producer_run_id"),
            fallback=scanner_run_id,
        ),
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
        "opportunity_type": _nullable_text(source_row.get("opportunity_type")),
        "complexity_tier": candidate.complexity_tier,
        "required_capital_chaos": candidate.required_capital_chaos,
        "estimated_operations": candidate.estimated_operations,
        "estimated_whispers": candidate.estimated_whispers,
        "expected_profit_per_operation_chaos": candidate.expected_profit_per_operation_chaos,
        "feasibility_score": candidate.feasibility_score,
        "evidence_snapshot": json.dumps(evidence_snapshot, separators=(",", ":")),
        "recorded_at": recorded_at,
    }


def _decision_payload(
    *,
    scanner_run_id: str,
    decision: CandidateDecision,
    source_row: Mapping[str, object] | None,
) -> dict[str, object]:
    candidate = decision.candidate
    source = source_row or candidate.evidence
    return {
        "scanner_run_id": scanner_run_id,
        "accepted": 1 if decision.accepted else 0,
        "decision_reason": decision.reason or "accepted",
        "strategy_id": candidate.strategy_id,
        "league": candidate.league,
        "recommendation_source": _nullable_text(source.get("recommendation_source")),
        "recommendation_contract_version": constants.RECOMMENDATION_CONTRACT_VERSION,
        "producer_version": _nullable_text(source.get("producer_version"))
        or __version__,
        "producer_run_id": _nullable_text(source.get("producer_run_id"))
        or scanner_run_id,
        "item_or_market_key": _canonical_item_or_market_key(
            candidate.item_or_market_key
        ),
        "complexity_tier": candidate.complexity_tier,
        "required_capital_chaos": candidate.required_capital_chaos,
        "estimated_operations": candidate.estimated_operations,
        "estimated_whispers": candidate.estimated_whispers,
        "expected_profit_chaos": candidate.expected_profit_chaos,
        "expected_profit_per_operation_chaos": candidate.expected_profit_per_operation_chaos,
        "feasibility_score": candidate.feasibility_score,
        "evidence_snapshot": json.dumps(
            build_evidence_snapshot(candidate), separators=(",", ":")
        ),
        "recorded_at": format_scan_timestamp(),
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
        "recommendation_source": recommendation_row.get("recommendation_source"),
        "recommendation_contract_version": recommendation_row.get(
            "recommendation_contract_version"
        ),
        "producer_version": recommendation_row.get("producer_version"),
        "producer_run_id": recommendation_row.get("producer_run_id"),
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


def _insert_json_rows(
    client: ClickHouseClient,
    *,
    table: str,
    rows: Sequence[Mapping[str, object | None]],
    columns: tuple[str, ...],
    fallback_columns: tuple[str, ...],
) -> None:
    column_sets = _insert_column_fallbacks(
        table=table,
        columns=columns,
        fallback_columns=fallback_columns,
    )
    last_error: ClickHouseClientError | None = None
    for column_set in column_sets:
        try:
            _ = client.execute(
                _insert_query(table=table, rows=rows, columns=column_set)
            )
            return
        except ClickHouseClientError as exc:
            if not _is_missing_metadata_column_error(exc):
                raise
            last_error = exc
            continue
    if last_error is not None:
        raise last_error


def _insert_candidate_decision_rows(
    client: ClickHouseClient,
    *,
    rows: Sequence[Mapping[str, object | None]],
) -> None:
    try:
        _insert_json_rows(
            client,
            table="poe_trade.scanner_candidate_decisions",
            rows=rows,
            columns=_DECISION_INSERT_COLUMNS,
            fallback_columns=(),
        )
    except ClickHouseClientError as exc:
        if not _is_decision_table_compatibility_failure(exc):
            raise
        logger.warning(
            "scanner candidate decision logging skipped due to schema compatibility: %s",
            exc,
        )


def _insert_query(
    *,
    table: str,
    rows: Sequence[Mapping[str, object | None]],
    columns: tuple[str, ...],
) -> str:
    return (
        f"INSERT INTO {table} ("
        + ", ".join(columns)
        + ")\n"
        + "FORMAT JSONEachRow\n"
        + "\n".join(
            json.dumps(
                {column: row.get(column) for column in columns}, separators=(",", ":")
            )
            for row in rows
        )
    )


def _execute_with_legacy_fallback(
    client: ClickHouseClient, query: str, legacy_query: str
) -> str:
    try:
        return client.execute(query)
    except ClickHouseClientError as exc:
        if not _is_missing_metadata_column_error(exc):
            raise
        return client.execute(legacy_query)


def _is_missing_metadata_column_error(exc: ClickHouseClientError) -> bool:
    message = str(exc).lower()
    matched_columns = _extract_missing_columns(message)
    return bool(matched_columns & _SCHEMA_FALLBACK_COLUMNS)


def _is_decision_table_compatibility_failure(exc: ClickHouseClientError) -> bool:
    message = str(exc).lower()
    matched_columns = _extract_missing_columns(message)
    if matched_columns & _DECISION_COMPAT_COLUMNS:
        return True
    if _message_mentions_any_table(
        message,
        ("poe_trade.scanner_candidate_decisions", "scanner_candidate_decisions"),
    ):
        if _message_has_missing_table_error(message):
            return True
        return False
    return False


def _message_has_missing_table_error(message: str) -> bool:
    return any(pattern.search(message) for pattern in _MISSING_TABLE_ERROR_PATTERNS)


def _message_mentions_any_table(message: str, table_names: Sequence[str]) -> bool:
    lowered = message.lower()
    return any(table_name.lower() in lowered for table_name in table_names)


def _extract_missing_columns(message: str) -> set[str]:
    matched_columns: set[str] = set()
    for pattern in _MISSING_COLUMN_ERROR_PATTERNS:
        for match in pattern.finditer(message):
            matched_columns.update(
                token
                for group in match.groups()
                for token in re.findall(r"[a-z0-9_]+", group)
            )
    return matched_columns


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


def _nullable_text(value: object) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned if cleaned else None


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


def _invalid_candidate_row(
    *,
    strategy_id: str,
    source_row: Mapping[str, object],
    default_league: str,
    error: str,
) -> CandidateRow:
    evidence = dict(source_row)
    evidence["invalid_source_row_error"] = error
    evidence.setdefault(
        "source_row_json",
        json.dumps(
            dict(source_row), sort_keys=True, separators=(",", ":"), default=str
        ),
    )
    parsed_ts = _parse_datetime(source_row.get("time_bucket")) or datetime.now(
        timezone.utc
    )
    return CandidateRow(
        strategy_id=strategy_id,
        league=str(source_row.get("league") or default_league),
        item_or_market_key="",
        candidate_ts=parsed_ts,
        evidence=evidence,
    )


def _insert_column_fallbacks(
    *,
    table: str,
    columns: tuple[str, ...],
    fallback_columns: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    if (
        table == "poe_trade.scanner_recommendations"
        and columns == _RECOMMENDATION_INSERT_COLUMNS
        and fallback_columns == _LEGACY_RECOMMENDATION_INSERT_COLUMNS
    ):
        return (
            _RECOMMENDATION_INSERT_COLUMNS,
            _RECOMMENDATION_INSERT_COLUMNS_V2,
            _LEGACY_RECOMMENDATION_INSERT_COLUMNS,
        )
    if fallback_columns:
        return (columns, fallback_columns)
    return (columns,)


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")
