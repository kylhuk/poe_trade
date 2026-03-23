from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .routes import select_route


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
    "item_state_key",
    "route_family",
    "base_identity_key",
)

FEATURE_SCHEMA_VERSION = "v3"


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


def build_item_state_key(parsed_item: Mapping[str, Any]) -> str:
    rarity = _normalized_text(parsed_item.get("rarity"))
    corrupted = _to_flag_int(parsed_item.get("corrupted"))
    fractured = _to_flag_int(parsed_item.get("fractured"))
    synthesised = _to_flag_int(parsed_item.get("synthesised"))
    return f"{rarity}|corrupted={corrupted}|fractured={fractured}|synthesised={synthesised}"


def build_base_identity_key(parsed_item: Mapping[str, Any]) -> str:
    base_type = _normalized_text(parsed_item.get("base_type"))
    return f"{base_type}|{build_item_state_key(parsed_item)}"


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


def build_feature_row(parsed_item: Mapping[str, Any]) -> dict[str, Any]:
    item_state_key = build_item_state_key(parsed_item)
    row: dict[str, Any] = {
        "category": str(parsed_item.get("category") or "other"),
        "base_type": str(parsed_item.get("base_type") or ""),
        "rarity": str(parsed_item.get("rarity") or ""),
        "ilvl": _to_int(parsed_item.get("ilvl"), default=0),
        "stack_size": _to_int(parsed_item.get("stack_size"), default=1),
        "corrupted": _to_flag_int(parsed_item.get("corrupted"), default=0),
        "fractured": _to_flag_int(parsed_item.get("fractured"), default=0),
        "synthesised": _to_flag_int(parsed_item.get("synthesised"), default=0),
        "mod_token_count": _to_int(parsed_item.get("mod_token_count"), default=0),
        "item_state_key": item_state_key,
        "route_family": select_route(parsed_item),
        "base_identity_key": build_base_identity_key(parsed_item),
    }
    mod_features = canonicalize_mod_features_json(
        str(parsed_item.get("mod_features_json") or "{}")
    )
    row.update(mod_features)
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
