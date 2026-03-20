from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


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
)

FEATURE_SCHEMA_VERSION = "v3"


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
    row: dict[str, Any] = {
        "category": str(parsed_item.get("category") or "other"),
        "base_type": str(parsed_item.get("base_type") or ""),
        "rarity": str(parsed_item.get("rarity") or ""),
        "ilvl": int(parsed_item.get("ilvl") or 0),
        "stack_size": int(parsed_item.get("stack_size") or 1),
        "corrupted": int(parsed_item.get("corrupted") or 0),
        "fractured": int(parsed_item.get("fractured") or 0),
        "synthesised": int(parsed_item.get("synthesised") or 0),
        "mod_token_count": int(parsed_item.get("mod_token_count") or 0),
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
