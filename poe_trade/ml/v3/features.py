from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .routes import select_route
from .sql import RING_CANONICAL_FAMILIES


BASE_FEATURE_FIELDS: tuple[str, ...] = (
    "category",
    "base_type",
    "rarity",
    "ilvl",
    "stack_size",
    "corrupted",
    "fractured",
    "synthesised",
    "mod_token_count",
    "support_count_recent",
    "strategy_family",
    "cohort_key",
    "parent_cohort_key",
    "material_state_signature",
    "item_name",
    "item_type_line",
    "item_state_key",
    "route_family",
    "base_identity_key",
)

FAST_SALE_SIGNAL_FIELDS: tuple[str, ...] = (
    "ilvl",
    "stack_size",
    "corrupted",
    "fractured",
    "synthesised",
    "support_count_recent",
    "recognized_affix_count",
    "all_attributes_value",
    "all_resistances_value",
    "physical_damage_tier",
    "item_found_rarity_increase_value",
    "chaos_resistance_value",
    "lightning_resistance_value",
    "increased_cast_speed_value",
    "increased_mana_value",
    "cold_resistance_value",
    "increased_energy_shield_value",
    "life_leech_value",
    "intelligence_value",
    "fire_resistance_value",
    "strength_value",
    "dexterity_value",
)

FEATURE_SCHEMA_VERSION = "v3"

RING_INFLUENCE_FAMILIES: frozenset[str] = frozenset(
    {
        "shaper",
        "elder",
        "crusader",
        "redeemer",
        "hunter",
        "warlord",
    }
)

_PASSTHROUGH_EXCLUDED_KEYS: frozenset[str] = frozenset(
    {
        "as_of_ts",
        "observed_at",
        "inserted_at",
        "split_bucket",
        "realm",
        "league",
        "account_name",
        "stash_name",
        "checkpoint",
        "next_change_id",
        "item_id",
        "identity_key",
        "stash_id",
        "parsed_currency",
        "parsed_amount",
        "normalized_affix_hash",
        "note",
        "forum_note",
        "effective_price_note",
        "label_source",
        "sale_confidence_flag",
        "feature_vector_json",
        "mod_features_json",
        "affixes",
        "fx_hour",
        "fx_source",
        "fx_chaos_per_divine",
        "target_price_divine",
        "target_fast_sale_24h_price_divine",
        "target_price_chaos",
        "target_fast_sale_24h_price",
    }
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _to_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except OverflowError:
            return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return int(float(text))
    except (OverflowError, ValueError):
        return default


def _to_flag_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "on"}:
            return 1
        if normalized in {"false", "f", "no", "n", "off"}:
            return 0
    return 1 if _to_int(value, default=default) != 0 else 0


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_item_state_key(parsed_item: Mapping[str, Any]) -> str:
    rarity = _normalized_text(parsed_item.get("rarity"))
    corrupted = _to_flag_int(parsed_item.get("corrupted"))
    fractured = _to_flag_int(parsed_item.get("fractured"))
    synthesised = _to_flag_int(parsed_item.get("synthesised"))
    return f"{rarity}|corrupted={corrupted}|fractured={fractured}|synthesised={synthesised}"


def build_base_identity_key(parsed_item: Mapping[str, Any]) -> str:
    base_type = _normalized_text(parsed_item.get("base_type"))
    return f"{base_type}|{build_item_state_key(parsed_item)}"


def _fast_sale_signal_value(feature_row: Mapping[str, Any], field: str) -> int:
    value = feature_row.get(field)
    if isinstance(value, (int, float, bool, str)):
        return _to_int(value, default=0)
    return 0


def canonicalize_mod_features_json(raw: str | None) -> dict[str, float]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    cleaned: dict[str, float] = {}
    for key, value in payload.items():
        feature_name = str(key).strip()
        if not feature_name:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        cleaned[feature_name] = numeric
    return cleaned


def _normalize_mod_feature_family(feature_name: str) -> str:
    for suffix in ("_present", "_quality_roll"):
        if feature_name.endswith(suffix):
            return feature_name[: -len(suffix)]
    return feature_name


def ring_parser_invariant_counts(row: Mapping[str, Any]) -> dict[str, int]:
    counts = {
        "synthesised_and_fractured": 0,
        "synthesised_and_influenced": 0,
        "too_many_prefixes": 0,
        "too_many_suffixes": 0,
        "non_ring_mod_family": 0,
        "non_influenced_ring_with_influence_family": 0,
    }

    synthesised = _to_flag_int(row.get("synthesised"))
    fractured = _to_flag_int(row.get("fractured"))
    influence_mask = _to_int(row.get("influence_mask"), default=0)
    prefix_count = _to_int(row.get("prefix_count"), default=0)
    suffix_count = _to_int(row.get("suffix_count"), default=0)

    counts["synthesised_and_fractured"] = int(synthesised == 1 and fractured == 1)
    counts["synthesised_and_influenced"] = int(synthesised == 1 and influence_mask != 0)
    counts["too_many_prefixes"] = int(prefix_count > 3)
    counts["too_many_suffixes"] = int(suffix_count > 3)

    mod_features_raw = row.get("mod_features_json")
    mod_feature_names: set[str] = set()
    if isinstance(mod_features_raw, dict):
        mod_feature_names = {str(key) for key in mod_features_raw}
    elif isinstance(mod_features_raw, str):
        try:
            parsed = json.loads(mod_features_raw)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            mod_feature_names = {str(key) for key in parsed}

    mod_families = {
        _normalize_mod_feature_family(feature_name)
        for feature_name in mod_feature_names
    }
    non_ring_families = {
        family
        for family in mod_families
        if family
        and family not in RING_CANONICAL_FAMILIES
        and family not in RING_INFLUENCE_FAMILIES
    }
    counts["non_ring_mod_family"] = int(bool(non_ring_families))
    counts["non_influenced_ring_with_influence_family"] = int(
        influence_mask == 0
        and any(family in RING_INFLUENCE_FAMILIES for family in mod_families)
    )
    return counts


def validate_ring_parser_row(row: Mapping[str, Any]) -> dict[str, int]:
    counts = ring_parser_invariant_counts(row)
    violations = {name: count for name, count in counts.items() if count}
    if violations:
        formatted = ", ".join(
            f"{name}={count}" for name, count in sorted(violations.items())
        )
        raise ValueError(f"ring parser invariant violation(s): {formatted}")
    return counts


def _passthrough_feature_row(parsed_item: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in parsed_item.items():
        text = str(key)
        if text in _PASSTHROUGH_EXCLUDED_KEYS:
            continue
        if text.startswith("target_") or text.startswith("label_"):
            continue
        row[text] = value
    return row


def build_feature_row(parsed_item: Mapping[str, Any]) -> dict[str, Any]:
    item_state_key = build_item_state_key(parsed_item)
    row: dict[str, Any] = _passthrough_feature_row(parsed_item)
    row.update(
        {
            "category": str(parsed_item.get("category") or "other"),
            "base_type": str(parsed_item.get("base_type") or ""),
            "rarity": str(parsed_item.get("rarity") or ""),
            "ilvl": _to_int(parsed_item.get("ilvl"), default=0),
            "stack_size": _to_int(parsed_item.get("stack_size"), default=1),
            "corrupted": _to_flag_int(parsed_item.get("corrupted"), default=0),
            "fractured": _to_flag_int(parsed_item.get("fractured"), default=0),
            "synthesised": _to_flag_int(parsed_item.get("synthesised"), default=0),
            "mod_token_count": _to_int(parsed_item.get("mod_token_count"), default=0),
            "support_count_recent": _to_int(
                parsed_item.get("support_count_recent"), default=0
            ),
            "strategy_family": str(parsed_item.get("strategy_family") or ""),
            "cohort_key": str(parsed_item.get("cohort_key") or ""),
            "parent_cohort_key": str(parsed_item.get("parent_cohort_key") or ""),
            "material_state_signature": str(
                parsed_item.get("material_state_signature") or ""
            ),
            "item_name": str(parsed_item.get("item_name") or ""),
            "item_type_line": str(parsed_item.get("item_type_line") or ""),
            "item_state_key": item_state_key,
            "route_family": select_route(parsed_item),
            "base_identity_key": build_base_identity_key(parsed_item),
        }
    )
    mod_features = canonicalize_mod_features_json(
        str(parsed_item.get("mod_features_json") or "{}")
    )
    row.update(mod_features)
    return row


def build_fast_sale_feature_row(parsed_item: Mapping[str, Any]) -> dict[str, Any]:
    row = build_feature_row(parsed_item)
    row.pop("item_name", None)
    row.pop("item_type_line", None)

    for field in FAST_SALE_SIGNAL_FIELDS:
        row[field] = _to_float(parsed_item.get(field), 0.0)

    active_signals = [
        field
        for field in FAST_SALE_SIGNAL_FIELDS
        if _fast_sale_signal_value(row, field) != 0
    ]
    row["fast_sale_stat_signature"] = "|".join(active_signals)
    row["fast_sale_signal_count"] = len(active_signals)
    return row


def feature_schema(feature_row: Mapping[str, Any]) -> dict[str, Any]:
    fields = sorted(str(key) for key in feature_row.keys())
    fingerprint = hashlib.sha256(
        json.dumps(fields, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "version": FEATURE_SCHEMA_VERSION,
        "fields": fields,
        "field_count": len(fields),
        "fingerprint": fingerprint,
    }
