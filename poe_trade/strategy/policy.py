from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from typing import cast

from .opportunity import OpportunityScoreInput, normalize_opportunity_metrics


@dataclass(frozen=True)
class StrategyPolicy:
    min_expected_profit_chaos: float | None = None
    min_expected_roi: float | None = None
    min_confidence: float | None = None
    min_sample_count: int | None = None
    cooldown_minutes: int = 0
    requires_journal: bool = False
    max_staleness_minutes: int | None = None
    min_liquidity_score: float | None = None
    max_estimated_whispers: int | None = None
    max_estimated_operations: int | None = None


@dataclass(frozen=True)
class CandidateRow:
    strategy_id: str
    league: str
    item_or_market_key: str
    candidate_ts: datetime
    expected_profit_chaos: float | None = None
    expected_roi: float | None = None
    confidence: float | None = None
    sample_count: int | None = None
    legacy_item_or_market_keys: tuple[str, ...] = ()
    complexity_tier: str | None = None
    required_capital_chaos: float | None = None
    estimated_operations: int | None = None
    estimated_whispers: int | None = None
    staleness_minutes: int | None = None
    liquidity_score: float | None = None
    expected_profit_per_operation_chaos: float | None = None
    feasibility_score: float | None = None
    evidence: Mapping[str, object] = field(
        default_factory=lambda: cast(dict[str, object], {})
    )


@dataclass(frozen=True)
class CandidateDecision:
    candidate: CandidateRow
    accepted: bool
    reason: str | None = None
    blocked_by_key: str | None = None
    blocked_until: datetime | None = None


@dataclass(frozen=True)
class PolicyEvaluation:
    eligible: tuple[CandidateRow, ...]
    decisions: tuple[CandidateDecision, ...]


REJECTED_LEAGUE = "league_mismatch"
REJECTED_MIN_EXPECTED_PROFIT = "below_min_expected_profit_chaos"
REJECTED_MIN_EXPECTED_ROI = "below_min_expected_roi"
REJECTED_MIN_CONFIDENCE = "below_min_confidence"
REJECTED_MIN_SAMPLE_COUNT = "below_min_sample_count"
REJECTED_JOURNAL_REQUIRED = "journal_state_required"
REJECTED_COOLDOWN_ACTIVE = "cooldown_active"
REJECTED_DUPLICATE = "dedupe_loser"
REJECTED_INVALID_SOURCE_ROW = "invalid_source_row"
REJECTED_MAX_STALENESS = "above_max_staleness_minutes"
REJECTED_MIN_LIQUIDITY = "below_min_liquidity_score"
REJECTED_MAX_ESTIMATED_WHISPERS = "above_max_estimated_whispers"
REJECTED_MAX_ESTIMATED_OPERATIONS = "above_max_estimated_operations"


def policy_from_pack(pack: object) -> StrategyPolicy:
    return StrategyPolicy(
        min_expected_profit_chaos=as_optional_float(
            getattr(pack, "min_expected_profit_chaos", None)
        ),
        min_expected_roi=as_optional_float(getattr(pack, "min_expected_roi", None)),
        min_confidence=as_optional_float(getattr(pack, "min_confidence", None)),
        min_sample_count=as_optional_int(getattr(pack, "min_sample_count", None)),
        cooldown_minutes=max(
            0, as_optional_int(getattr(pack, "cooldown_minutes", 0)) or 0
        ),
        requires_journal=bool(getattr(pack, "requires_journal", False)),
        max_staleness_minutes=as_optional_int(
            getattr(pack, "max_staleness_minutes", None)
        ),
        min_liquidity_score=as_optional_float(
            getattr(pack, "min_liquidity_score", None)
        ),
        max_estimated_whispers=as_optional_int(
            getattr(pack, "max_estimated_whispers", None)
        ),
        max_estimated_operations=as_optional_int(
            getattr(pack, "max_estimated_operations", None)
        ),
    )


def candidate_from_source_row(
    strategy_id: str,
    source_row: Mapping[str, object],
    *,
    default_league: str | None = None,
    default_estimated_operations: int | None = None,
    default_estimated_whispers: int | None = None,
    default_profit_per_operation_chaos: float | None = None,
) -> CandidateRow:
    source_row_dict = dict(source_row)
    source_row_json = _source_row_json(source_row_dict)
    semantic_key = str(source_row_dict.get("semantic_key") or "").strip()
    if not semantic_key:
        raise ValueError("candidate row missing semantic_key")
    source_item_or_market_key = str(
        source_row_dict.get("item_or_market_key") or ""
    ).strip()
    legacy_hashed_key = str(
        source_row_dict.get("legacy_hashed_item_or_market_key") or ""
    ).strip()
    legacy_keys = _legacy_item_or_market_keys(source_row_dict)
    historical_legacy_keys = _historical_legacy_item_or_market_keys(source_row_dict)
    if legacy_hashed_key:
        legacy_keys = normalize_compatibility_keys(legacy_hashed_key, legacy_keys)
    if historical_legacy_keys:
        legacy_keys = _append_compatibility_keys(legacy_keys, historical_legacy_keys)
    if source_item_or_market_key and source_item_or_market_key != semantic_key:
        legacy_keys = normalize_compatibility_keys(
            source_item_or_market_key, legacy_keys
        )

    evidence = dict(source_row_dict)
    _ = evidence.setdefault("source_row_json", source_row_json)
    if source_item_or_market_key and source_item_or_market_key != semantic_key:
        _ = evidence.setdefault("source_item_or_market_key", source_item_or_market_key)
    if legacy_hashed_key:
        _ = evidence.setdefault("legacy_hashed_item_or_market_key", legacy_hashed_key)
    if historical_legacy_keys:
        _ = evidence.setdefault(
            "historical_legacy_hashed_item_or_market_keys", list(historical_legacy_keys)
        )

    expected_profit_chaos = as_optional_float(
        source_row_dict.get("expected_profit_chaos")
    )
    normalized_opportunity = normalize_opportunity_metrics(
        OpportunityScoreInput(
            expected_profit_chaos=expected_profit_chaos,
            estimated_operations=as_optional_int(
                source_row_dict.get("estimated_operations")
            ),
            estimated_whispers=as_optional_int(
                source_row_dict.get("estimated_whispers")
            ),
            expected_profit_per_operation_chaos=as_optional_float(
                source_row_dict.get("expected_profit_per_operation_chaos")
            ),
        ),
        default_estimated_operations=default_estimated_operations,
        default_estimated_whispers=default_estimated_whispers,
        default_profit_per_operation_chaos=default_profit_per_operation_chaos,
    )

    return CandidateRow(
        strategy_id=strategy_id,
        league=str(source_row_dict.get("league") or default_league or ""),
        item_or_market_key=semantic_key,
        candidate_ts=parse_candidate_ts(source_row_dict.get("time_bucket")),
        expected_profit_chaos=expected_profit_chaos,
        expected_roi=as_optional_float(source_row_dict.get("expected_roi")),
        confidence=as_optional_float(source_row_dict.get("confidence")),
        sample_count=candidate_sample_count(source_row_dict),
        legacy_item_or_market_keys=tuple(
            key for key in legacy_keys if key and key != semantic_key
        ),
        complexity_tier=_as_optional_text(source_row_dict.get("complexity_tier")),
        required_capital_chaos=as_optional_float(
            source_row_dict.get("required_capital_chaos")
        ),
        estimated_operations=normalized_opportunity.estimated_operations,
        estimated_whispers=normalized_opportunity.estimated_whispers,
        staleness_minutes=as_optional_int(source_row_dict.get("staleness_minutes")),
        liquidity_score=as_optional_float(source_row_dict.get("liquidity_score")),
        expected_profit_per_operation_chaos=normalized_opportunity.expected_profit_per_operation_chaos,
        feasibility_score=as_optional_float(source_row_dict.get("feasibility_score")),
        evidence=evidence,
    )


def candidate_sample_count(source_row: Mapping[str, object]) -> int | None:
    for field in (
        "sample_count",
        "bulk_listing_count",
        "listing_count",
        "observed_samples",
    ):
        value = as_optional_int(source_row.get(field))
        if value is not None:
            return value
    return None


def parse_candidate_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = f"{cleaned[:-1]}+00:00"
        parsed = datetime.fromisoformat(cleaned)
    else:
        raise ValueError("candidate row missing time_bucket")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def as_optional_float(value: object) -> float | None:
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


def as_optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def normalize_compatibility_keys(
    item_or_market_key: str,
    legacy_item_or_market_keys: Sequence[str] | None = None,
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for key in (item_or_market_key, *(legacy_item_or_market_keys or ())):
        if not key or key in seen:
            continue
        ordered.append(key)
        seen.add(key)
    return tuple(ordered)


def candidate_cooldown_keys(candidate: CandidateRow) -> tuple[str, ...]:
    return normalize_compatibility_keys(
        candidate.item_or_market_key,
        legacy_item_or_market_keys=candidate.legacy_item_or_market_keys,
    )


def _append_compatibility_keys(
    existing_keys: Sequence[str],
    additional_keys: Sequence[str],
) -> tuple[str, ...]:
    appended = tuple(key for key in additional_keys if key and key not in existing_keys)
    return tuple(existing_keys) + appended


def candidate_meets_minima(
    candidate: CandidateRow, policy: StrategyPolicy
) -> tuple[bool, str | None]:
    if policy.min_expected_profit_chaos is not None and (
        candidate.expected_profit_chaos is None
        or candidate.expected_profit_chaos < policy.min_expected_profit_chaos
    ):
        return False, REJECTED_MIN_EXPECTED_PROFIT
    if policy.min_expected_roi is not None and (
        candidate.expected_roi is None
        or candidate.expected_roi < policy.min_expected_roi
    ):
        return False, REJECTED_MIN_EXPECTED_ROI
    if policy.min_confidence is not None and (
        candidate.confidence is None or candidate.confidence < policy.min_confidence
    ):
        return False, REJECTED_MIN_CONFIDENCE
    if policy.min_sample_count is not None and policy.min_sample_count > 0:
        if (
            candidate.sample_count is None
            or candidate.sample_count < policy.min_sample_count
        ):
            return False, REJECTED_MIN_SAMPLE_COUNT
    if policy.max_staleness_minutes is not None and policy.max_staleness_minutes >= 0:
        if (
            candidate.staleness_minutes is None
            or candidate.staleness_minutes > policy.max_staleness_minutes
        ):
            return False, REJECTED_MAX_STALENESS
    if policy.min_liquidity_score is not None:
        if (
            candidate.liquidity_score is None
            or candidate.liquidity_score < policy.min_liquidity_score
        ):
            return False, REJECTED_MIN_LIQUIDITY
    if policy.max_estimated_whispers is not None and policy.max_estimated_whispers >= 0:
        if (
            candidate.estimated_whispers is None
            or candidate.estimated_whispers > policy.max_estimated_whispers
        ):
            return False, REJECTED_MAX_ESTIMATED_WHISPERS
    if (
        policy.max_estimated_operations is not None
        and policy.max_estimated_operations > 0
    ):
        if (
            candidate.estimated_operations is None
            or candidate.estimated_operations > policy.max_estimated_operations
        ):
            return False, REJECTED_MAX_ESTIMATED_OPERATIONS
    return True, None


def passes_journal_gate(
    candidate: CandidateRow,
    policy: StrategyPolicy,
    *,
    journal_active_keys: set[str] | None,
) -> bool:
    if not policy.requires_journal:
        return True
    if not journal_active_keys:
        return False
    for key in candidate_cooldown_keys(candidate):
        if key in journal_active_keys:
            return True
    return False


def cooldown_block(
    candidate: CandidateRow,
    policy: StrategyPolicy,
    *,
    last_alerted_at_by_key: Mapping[str, datetime] | None,
) -> tuple[bool, str | None, datetime | None]:
    if policy.cooldown_minutes <= 0 or not last_alerted_at_by_key:
        return False, None, None
    cooldown = timedelta(minutes=policy.cooldown_minutes)
    for key in candidate_cooldown_keys(candidate):
        last_seen = last_alerted_at_by_key.get(key)
        if last_seen is None:
            continue
        blocked_until = last_seen + cooldown
        if candidate.candidate_ts < blocked_until:
            return True, key, blocked_until
    return False, None, None


def dedupe_candidates(candidates: Sequence[CandidateRow]) -> tuple[CandidateRow, ...]:
    winners = _dedupe_winner_entries(candidates)
    ordered = [entry[2] for entry in winners.values()]
    ordered.sort(key=lambda row: _candidate_rank(row, 0))
    return tuple(ordered)


def evaluate_candidates(
    candidates: Sequence[CandidateRow],
    *,
    policy: StrategyPolicy,
    requested_league: str,
    journal_active_keys: set[str] | None = None,
    last_alerted_at_by_key: Mapping[str, datetime] | None = None,
) -> PolicyEvaluation:
    decisions: list[CandidateDecision] = []
    eligible: list[CandidateRow] = []

    league_filtered_candidates: list[tuple[int, CandidateRow]] = []
    for index, candidate in enumerate(candidates):
        if candidate.league != requested_league:
            decisions.append(
                CandidateDecision(
                    candidate=candidate, accepted=False, reason=REJECTED_LEAGUE
                )
            )
            continue
        league_filtered_candidates.append((index, candidate))

    winner_entries = _dedupe_winner_entries(
        [candidate for _, candidate in league_filtered_candidates]
    )
    dedupe_winners = [entry[2] for entry in winner_entries.values()]
    dedupe_winners.sort(key=lambda row: _candidate_rank(row, 0))
    winner_indexes = {
        league_filtered_candidates[entry[0]][0] for entry in winner_entries.values()
    }

    for index, candidate in enumerate(candidates):
        if candidate.league == requested_league and index not in winner_indexes:
            decisions.append(
                CandidateDecision(
                    candidate=candidate, accepted=False, reason=REJECTED_DUPLICATE
                )
            )

    for candidate in dedupe_winners:
        meets_minima, minima_reason = candidate_meets_minima(candidate, policy)
        if not meets_minima:
            decisions.append(
                CandidateDecision(
                    candidate=candidate, accepted=False, reason=minima_reason
                )
            )
            continue
        if not passes_journal_gate(
            candidate, policy, journal_active_keys=journal_active_keys
        ):
            decisions.append(
                CandidateDecision(
                    candidate=candidate,
                    accepted=False,
                    reason=REJECTED_JOURNAL_REQUIRED,
                )
            )
            continue
        blocked, blocked_by_key, blocked_until = cooldown_block(
            candidate,
            policy,
            last_alerted_at_by_key=last_alerted_at_by_key,
        )
        if blocked:
            decisions.append(
                CandidateDecision(
                    candidate=candidate,
                    accepted=False,
                    reason=REJECTED_COOLDOWN_ACTIVE,
                    blocked_by_key=blocked_by_key,
                    blocked_until=blocked_until,
                )
            )
            continue
        decisions.append(CandidateDecision(candidate=candidate, accepted=True))
        eligible.append(candidate)

    return PolicyEvaluation(eligible=tuple(eligible), decisions=tuple(decisions))


def build_evidence_snapshot(candidate: CandidateRow) -> dict[str, object]:
    snapshot = dict(candidate.evidence)
    for identity_field in (
        "legacy_item_or_market_keys",
        "source_item_or_market_key",
        "legacy_hashed_item_or_market_key",
        "historical_legacy_hashed_item_or_market_key",
        "historical_legacy_hashed_item_or_market_keys",
    ):
        snapshot.pop(identity_field, None)
    _ = snapshot.setdefault("strategy_id", candidate.strategy_id)
    _ = snapshot.setdefault("league", candidate.league)
    snapshot["item_or_market_key"] = candidate.item_or_market_key
    _ = snapshot.setdefault("time_bucket", candidate.candidate_ts.isoformat())
    _ = snapshot.setdefault("expected_profit_chaos", candidate.expected_profit_chaos)
    _ = snapshot.setdefault("expected_roi", candidate.expected_roi)
    _ = snapshot.setdefault("confidence", candidate.confidence)
    _ = snapshot.setdefault("sample_count", candidate.sample_count)
    _ = snapshot.setdefault("complexity_tier", candidate.complexity_tier)
    _ = snapshot.setdefault("required_capital_chaos", candidate.required_capital_chaos)
    _ = snapshot.setdefault("estimated_operations", candidate.estimated_operations)
    _ = snapshot.setdefault("estimated_whispers", candidate.estimated_whispers)
    _ = snapshot.setdefault("staleness_minutes", candidate.staleness_minutes)
    _ = snapshot.setdefault("liquidity_score", candidate.liquidity_score)
    _ = snapshot.setdefault(
        "expected_profit_per_operation_chaos",
        candidate.expected_profit_per_operation_chaos,
    )
    _ = snapshot.setdefault("feasibility_score", candidate.feasibility_score)
    source_item_or_market_key = str(
        candidate.evidence.get("source_item_or_market_key") or ""
    ).strip()
    if (
        source_item_or_market_key
        and source_item_or_market_key != candidate.item_or_market_key
        and source_item_or_market_key in candidate.legacy_item_or_market_keys
    ):
        snapshot["source_item_or_market_key"] = source_item_or_market_key

    legacy_hashed_item_or_market_key = str(
        candidate.evidence.get("legacy_hashed_item_or_market_key") or ""
    ).strip()
    if (
        legacy_hashed_item_or_market_key
        and legacy_hashed_item_or_market_key in candidate.legacy_item_or_market_keys
    ):
        snapshot["legacy_hashed_item_or_market_key"] = legacy_hashed_item_or_market_key

    historical_legacy_keys = _historical_legacy_item_or_market_keys(candidate.evidence)
    if historical_legacy_keys:
        snapshot["historical_legacy_hashed_item_or_market_keys"] = list(
            key
            for key in historical_legacy_keys
            if key in candidate.legacy_item_or_market_keys
        )
        if not snapshot["historical_legacy_hashed_item_or_market_keys"]:
            snapshot.pop("historical_legacy_hashed_item_or_market_keys", None)
    if candidate.legacy_item_or_market_keys:
        snapshot["legacy_item_or_market_keys"] = list(
            candidate.legacy_item_or_market_keys
        )
    return snapshot


def _candidate_rank(candidate: CandidateRow, index: int) -> tuple[object, ...]:
    return (
        _sort_numeric_desc(candidate.feasibility_score),
        _sort_numeric_desc(candidate.expected_profit_per_operation_chaos),
        _sort_numeric_desc(candidate.expected_profit_chaos),
        _sort_numeric_desc(candidate.expected_roi),
        _sort_numeric_desc(candidate.confidence),
        _sort_numeric_desc(
            float(candidate.sample_count)
            if candidate.sample_count is not None
            else None
        ),
        _sort_numeric_asc(
            float(candidate.estimated_operations)
            if candidate.estimated_operations is not None
            else None
        ),
        _sort_numeric_asc(
            float(candidate.estimated_whispers)
            if candidate.estimated_whispers is not None
            else None
        ),
        -candidate.candidate_ts.timestamp(),
        candidate.item_or_market_key,
        index,
    )


def _sort_numeric_desc(value: float | None) -> tuple[int, float]:
    if value is None:
        return (1, 0.0)
    return (0, -float(value))


def _sort_numeric_asc(value: float | None) -> tuple[int, float]:
    if value is None:
        return (1, 0.0)
    return (0, float(value))


def _as_optional_text(value: object) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned if cleaned else None


def _dedupe_winner_entries(
    candidates: Sequence[CandidateRow],
) -> dict[tuple[str, str], tuple[int, tuple[object, ...], CandidateRow]]:
    winners: dict[tuple[str, str], tuple[int, tuple[object, ...], CandidateRow]] = {}
    for index, candidate in enumerate(candidates):
        rank = _candidate_rank(candidate, index)
        dedupe_key = (candidate.league, candidate.item_or_market_key)
        current = winners.get(dedupe_key)
        if current is None or rank < current[1]:
            winners[dedupe_key] = (index, rank, candidate)
    return winners


def _legacy_item_or_market_keys(source_row: Mapping[str, object]) -> tuple[str, ...]:
    value = source_row.get("legacy_item_or_market_keys")
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return ()
        if cleaned.startswith("["):
            try:
                parsed = cast(object, json.loads(cleaned))
            except json.JSONDecodeError:
                return (cleaned,)
            if isinstance(parsed, list):
                items = cast(list[object], parsed)
                return tuple(str(item).strip() for item in items if str(item).strip())
        return (cleaned,)
    if isinstance(value, list | tuple):
        items = cast(list[object] | tuple[object, ...], value)
        return tuple(str(item).strip() for item in items if str(item).strip())
    return ()


def _historical_legacy_item_or_market_keys(
    source_row: Mapping[str, object],
) -> tuple[str, ...]:
    single = str(
        source_row.get("historical_legacy_hashed_item_or_market_key") or ""
    ).strip()
    multiple = _legacy_item_or_market_keys(
        {
            "legacy_item_or_market_keys": source_row.get(
                "historical_legacy_hashed_item_or_market_keys"
            )
        }
    )
    if single:
        return normalize_compatibility_keys(single, multiple)
    return multiple


def _source_row_json(source_row: Mapping[str, object]) -> str:
    existing = source_row.get("source_row_json")
    if isinstance(existing, str) and existing.strip():
        return existing
    return json.dumps(
        dict(source_row), sort_keys=True, separators=(",", ":"), default=str
    )
