from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence


def _serialize(value: Mapping | Sequence) -> str:
    return json.dumps(value, sort_keys=True, separators=(",",":"))


def _hash(value: str, salt: str) -> str:
    payload = salt + value
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fp_exact(item: Mapping[str, object]) -> str:
    return _hash(_serialize(item), "exact")


def fp_loose(item: Mapping[str, object], keys: Sequence[str] | None = None) -> str:
    if keys is None:
        keys = ("name", "base_type", "rarity")
    reduced = {k: item.get(k) for k in keys if k in item}
    if not reduced:
        reduced = {"name": item.get("name"), "base_type": item.get("base_type")}
    return _hash(_serialize(reduced), "loose")
