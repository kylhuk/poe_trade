from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import json
import math


@dataclass(frozen=True)
class SearchResult:
    stage: int
    candidates: list[dict[str, Any]]
    dropped_affixes: list[str]
    effective_support: int
    candidate_count: int
    degradation_reason: str | None


_DEFAULT_STAGE_SUPPORT_TARGETS = {1: 8, 2: 12, 3: 18, 4: 24}
_MAX_CANDIDATES = 64
_RECENCY_WINDOW_DAYS = 14

_SEARCH_WEIGHTS = {
    "base_item_state": 0.25,
    "important_affix_overlap": 0.30,
    "tier_proximity": 0.15,
    "roll_closeness": 0.10,
    "rare_affix_bonus": 0.10,
    "recency": 0.05,
    "listing_quality": 0.05,
}

_MISSING_AFFIX_PENALTY = {
    0: -0.35,
    1: -0.20,
}


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_affix_source(
    source: Mapping[str, Any] | None,
) -> dict[str, tuple[float, int]]:
    if not source:
        return {}
    normalized: dict[str, tuple[float, int]] = {}
    for raw_affix, raw_payload in source.items():
        affix = str(raw_affix)
        if not affix:
            continue
        if isinstance(raw_payload, Mapping):
            lift = _to_float(
                raw_payload.get("lift", raw_payload.get("importance", 0.0))
            )
            support = _to_int(raw_payload.get("count", raw_payload.get("support", 0)))
        else:
            lift = _to_float(raw_payload)
            support = 1
        normalized[affix] = (lift, support)
    return normalized


def _is_usable(source: Mapping[str, tuple[float, int]], min_total_support: int) -> bool:
    return (
        bool(source)
        and sum(support for _, support in source.values()) >= min_total_support
    )


def _select_affix_source(
    *,
    cohort_30d: Mapping[str, tuple[float, int]],
    cohort_90d: Mapping[str, tuple[float, int]],
    route_prior: Mapping[str, tuple[float, int]],
    min_total_support: int,
) -> tuple[str, list[tuple[str, float, int]]]:
    if _is_usable(cohort_30d, min_total_support):
        source_name = "cohort_30d"
        source = cohort_30d
    elif _is_usable(cohort_90d, min_total_support):
        source_name = "cohort_90d"
        source = cohort_90d
    else:
        source_name = "route_prior"
        source = route_prior

    ordered = sorted(
        source.items(), key=lambda item: (-item[1][0], -item[1][1], item[0])
    )
    ranked = [(affix, lift, support) for affix, (lift, support) in ordered]
    return source_name, ranked


def rank_affixes_by_importance(
    *,
    cohort_30d: Mapping[str, Any] | None,
    cohort_90d: Mapping[str, Any] | None,
    route_prior: Mapping[str, Any] | None,
    min_total_support: int = 1,
) -> list[dict[str, Any]]:
    normalized_30d = _normalize_affix_source(cohort_30d)
    normalized_90d = _normalize_affix_source(cohort_90d)
    normalized_route_prior = _normalize_affix_source(route_prior)
    selected_source_name, ranked = _select_affix_source(
        cohort_30d=normalized_30d,
        cohort_90d=normalized_90d,
        route_prior=normalized_route_prior,
        min_total_support=min_total_support,
    )

    return [
        {
            "affix": affix,
            "importance": lift,
            "support": support,
            "source": selected_source_name,
        }
        for affix, lift, support in ranked
    ]


def _coerce_mod_payload(raw: Any) -> dict[str, float]:
    if isinstance(raw, dict):
        payload = raw
    elif isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
    else:
        return {}

    coalesced: dict[str, float] = {}
    for key, value in payload.items():
        affix = str(key)
        if not affix:
            continue
        coalesced[affix] = _to_float(value)
    return coalesced


def _row_field(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _parse_row_datetime(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        raw = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _recency_score(raw_ts: Any) -> float:
    parsed = _parse_row_datetime(raw_ts)
    if parsed is None:
        return 0.0
    age = datetime.now(UTC) - parsed
    if age <= timedelta(0):
        return 1.0
    age_days = age.total_seconds() / (24.0 * 3600.0)
    return max(0.0, 1.0 - age_days / float(_RECENCY_WINDOW_DAYS))


def _extract_support(row: Mapping[str, Any]) -> float:
    support = _to_float(
        _row_field(row, "support_count_recent", "target_support_count", "support")
    )
    return min(1.0, max(0.0, support / 20.0))


def _normalize_important_affixes(
    ranked_affixes: list[dict[str, Any]] | None,
) -> list[tuple[str, float, int]]:
    if not ranked_affixes:
        return []
    normalized: list[tuple[str, float, int]] = []
    for item in ranked_affixes:
        if not isinstance(item, Mapping):
            continue
        affix = _normalize_text(item.get("affix"))
        if not affix:
            continue
        importance = _to_float(item.get("importance"))
        support = _to_int(item.get("support"))
        normalized.append((affix, importance, max(1, support)))
    return normalized


def _sort_identity(item: Mapping[str, Any]) -> tuple:
    identity = str(
        _row_field(item, "identity_key", "candidate_identity_key", "identity") or ""
    )
    observed = _parse_row_datetime(_row_field(item, "as_of_ts", "candidate_as_of_ts"))
    observed_at = int(observed.timestamp()) if observed is not None else 0
    return (-float(item.get("score", 0.0) or 0.0), -observed_at, identity)


def _row_matches_core_state(
    row: Mapping[str, Any], parsed_item: Mapping[str, Any]
) -> bool:
    if _normalize_text(
        _row_field(row, "base_type", "candidate_base_type")
    ) != _normalize_text(parsed_item.get("base_type")):
        return False
    if _normalize_text(
        _row_field(row, "rarity", "candidate_rarity")
    ) != _normalize_text(parsed_item.get("rarity")):
        return False
    row_state = _normalize_text(
        _row_field(row, "item_state_key", "candidate_item_state_key")
    )
    target_state = _normalize_text(parsed_item.get("item_state_key"))
    if target_state and row_state:
        return row_state == target_state
    return True


def _has_affix_value(payload: Mapping[str, float], affix: str) -> bool:
    if not affix:
        return False
    return _to_float(payload.get(affix)) != 0.0


def _max_tier_penalty(abs_tier_delta: float, stage: int) -> float:
    # stage-specific tier relaxation: strict on stage1, adjacent allowed in stage2.
    if stage == 1:
        return math.inf if abs_tier_delta > 0 else 0.0
    if stage == 2:
        return 0.08 * min(abs_tier_delta, 2.0)
    return 0.0


def _score_roll_proximity(target_value: float, candidate_value: float) -> float:
    diff = abs(target_value - candidate_value)
    return max(0.0, 1.0 - min(diff, 1.0))


def _score_candidate(
    *,
    row: Mapping[str, Any],
    parsed_item: Mapping[str, Any],
    important_affixes: list[tuple[str, float, int]],
    stage: int,
) -> dict[str, Any]:
    candidate_payload = _coerce_mod_payload(
        _row_field(row, "mod_features_json", "mods", "mod_features")
    )
    target_payload = _coerce_mod_payload(parsed_item.get("mod_features_json"))

    target_values = {key: _to_float(value) for key, value in target_payload.items()}

    overlap_score = 0.0
    tier_score = 0.0
    roll_score = 0.0
    matched_affixes: list[str] = []
    missing_affixes: list[str] = []
    rare_bonus_multiplier = 0.0

    if important_affixes:
        overlap = 0
        total = 0
        tier_scores: list[float] = []
        roll_scores: list[float] = []
        for rank, (affix, importance, _) in enumerate(important_affixes):
            total += 1
            if affix not in candidate_payload:
                missing_affixes.append(affix)
                continue

            overlap += 1
            matched_affixes.append(affix)
            target_value = target_values.get(affix)
            candidate_value = candidate_payload.get(affix)
            if rank == 0 and importance >= 7.0:
                rare_bonus_multiplier = 1.0
            if target_value is not None and candidate_value is not None:
                tier_delta = abs(target_value - candidate_value)
                tier_penalty = _max_tier_penalty(tier_delta, stage)
                if tier_penalty == math.inf:
                    missing_affixes.append(affix)
                    if affix in matched_affixes:
                        matched_affixes.remove(affix)
                    continue
                tier_scores.append(max(0.0, 1.0 - tier_penalty))
                roll_scores.append(_score_roll_proximity(target_value, candidate_value))
            elif rank < 2:
                tier_scores.append(0.0)
                roll_scores.append(0.0)

        if total:
            overlap_score = (overlap / total) * _SEARCH_WEIGHTS[
                "important_affix_overlap"
            ]
            if tier_scores:
                tier_score = (sum(tier_scores) / len(tier_scores)) * _SEARCH_WEIGHTS[
                    "tier_proximity"
                ]
            if roll_scores:
                roll_score = (sum(roll_scores) / len(roll_scores)) * _SEARCH_WEIGHTS[
                    "roll_closeness"
                ]

        penalty = 0.0
        for index, affix in enumerate(important_affixes):
            if affix[0] in missing_affixes:
                if index in _MISSING_AFFIX_PENALTY:
                    penalty += _MISSING_AFFIX_PENALTY[index]
                else:
                    penalty += -0.10
    else:
        overlap_score = _SEARCH_WEIGHTS["important_affix_overlap"]
        tier_score = _SEARCH_WEIGHTS["tier_proximity"]
        roll_score = _SEARCH_WEIGHTS["roll_closeness"]
        penalty = 0.0

    recency = _recency_score(_row_field(row, "as_of_ts", "candidate_as_of_ts"))
    quality = _extract_support(row)

    score = (
        _SEARCH_WEIGHTS["base_item_state"]
        + overlap_score
        + tier_score
        + roll_score
        + (_SEARCH_WEIGHTS["rare_affix_bonus"] * rare_bonus_multiplier)
        + (_SEARCH_WEIGHTS["recency"] * recency)
        + (_SEARCH_WEIGHTS["listing_quality"] * quality)
        + penalty
    )

    score = max(0.0, min(1.0, score))

    return {
        "identity_key": str(
            _row_field(row, "identity_key", "candidate_identity_key") or ""
        ),
        "price": _to_float(
            _row_field(row, "target_price_chaos", "candidate_price_chaos")
        ),
        "score": score,
        "matched_affixes": matched_affixes,
        "missing_affixes": missing_affixes,
        "observed_at": _row_field(row, "as_of_ts", "candidate_as_of_ts"),
        "support": _to_float(
            _row_field(row, "support_count_recent", "target_support_count", "support")
        ),
    }


def _is_stage3_mandatory_affix(affix_rank: int, stage: int) -> bool:
    return stage == 3 and affix_rank < 2


def _matches_stage(
    *,
    row: Mapping[str, Any],
    parsed_item: Mapping[str, Any],
    important_affixes: list[tuple[str, float, int]],
    stage: int,
) -> bool:
    if not _row_matches_core_state(row, parsed_item):
        return False

    candidate_payload = _coerce_mod_payload(
        _row_field(row, "mod_features_json", "mods", "mod_features")
    )
    target_payload = _coerce_mod_payload(parsed_item.get("mod_features_json"))
    if not important_affixes:
        return True

    for rank, (affix, _importance, _support) in enumerate(important_affixes):
        target_value = _to_float(target_payload.get(affix))
        candidate_value = _to_float(candidate_payload.get(affix))

        if stage in {1, 2} and candidate_value == 0.0:
            return False

        if (
            stage == 3
            and _is_stage3_mandatory_affix(rank, stage)
            and candidate_value == 0.0
        ):
            return False

        if stage == 2 and candidate_value != 0.0 and target_value != 0.0:
            if abs(target_value - candidate_value) > 1.0:
                return False

    return True


def _search_stage(
    *,
    stage: int,
    parsed_item: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    important_affixes: list[tuple[str, float, int]],
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if _matches_stage(
            row=row,
            parsed_item=parsed_item,
            important_affixes=important_affixes,
            stage=stage,
        )
    ]


def score_confidence(
    *,
    stage: int,
    effective_support: int,
    p10: float,
    p50: float,
    p90: float,
) -> dict[str, Any]:
    if stage <= 0:
        return {
            "confidence": 0.10,
            "estimate_trust": "low",
            "price_recommendation_eligible": False,
        }

    support_component = min(max(int(effective_support), 0), 40) / 40.0
    width_ratio = (max(float(p90), float(p10)) - min(float(p90), float(p10))) / max(
        float(p50), 0.1
    )
    tightness_component = max(0.0, 1.0 - min(width_ratio, 1.0))
    stage_bonus = 0.02 if stage >= 3 else 0.0

    confidence = (
        0.15 + (0.45 * support_component) + (0.30 * tightness_component) + stage_bonus
    )
    confidence = max(0.10, min(0.95, confidence))

    if confidence >= 0.75:
        estimate_trust = "high"
    elif confidence >= 0.35:
        estimate_trust = "normal"
    else:
        estimate_trust = "low"

    return {
        "confidence": confidence,
        "estimate_trust": estimate_trust,
        "price_recommendation_eligible": confidence >= 0.35,
    }


def run_search(
    *,
    parsed_item: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
    ranked_affixes: list[dict[str, Any]] | None = None,
    stage_support_targets: Mapping[int, int] | None = None,
    max_candidates: int = _MAX_CANDIDATES,
) -> SearchResult:
    important_affixes = _normalize_important_affixes(ranked_affixes)
    stage_support_targets = {
        1: 8,
        2: 12,
        3: 18,
        4: 24,
        **(stage_support_targets or {}),
    }

    rows = list(candidate_rows)
    dropped_affixes: list[str] = []

    for stage in (1, 2, 3, 4):
        matching_rows = _search_stage(
            stage=stage,
            parsed_item=parsed_item,
            rows=rows,
            important_affixes=important_affixes,
        )
        scored = [
            _score_candidate(
                row=row,
                parsed_item=parsed_item,
                important_affixes=important_affixes,
                stage=stage,
            )
            for row in matching_rows
        ]
        scored.sort(key=_sort_identity)
        candidate_count = len(scored)
        effective_support = sum(
            1 for item in scored if (item.get("score") or 0.0) > 0.0
        )
        threshold = int(stage_support_targets.get(stage, 1))

        if stage == 3:
            dropped_affixes = [
                affix
                for affix, _importance, _support in reversed(important_affixes[2:])
            ]

        if stage == 4:
            if effective_support > 0:
                return SearchResult(
                    stage=4,
                    candidates=scored[: max(0, int(max_candidates))],
                    dropped_affixes=dropped_affixes,
                    effective_support=effective_support,
                    candidate_count=candidate_count,
                    degradation_reason=None
                    if effective_support >= threshold
                    else "stage_4_support_shortfall",
                )
            continue

        if effective_support >= threshold:
            return SearchResult(
                stage=stage,
                candidates=scored[: max(0, int(max_candidates))],
                dropped_affixes=dropped_affixes,
                effective_support=effective_support,
                candidate_count=candidate_count,
                degradation_reason=None,
            )

    return SearchResult(
        stage=0,
        candidates=[],
        dropped_affixes=[],
        effective_support=0,
        candidate_count=0,
        degradation_reason="no_relevant_comparables",
    )
