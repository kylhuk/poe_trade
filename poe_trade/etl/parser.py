from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Mapping, Sequence, Tuple, Any

from .fingerprints import fp_exact, fp_loose
from .models import ItemCanonical, ListingCanonical

_CHAOS_CURRENCIES = {"chaos"}
_FRAME_TYPES = {
    0: "normal",
    1: "magic",
    2: "rare",
    3: "unique",
    4: "gem",
    5: "currency",
}


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _normalize_rarity(frame: object | None, declared: object | None) -> str:
    if isinstance(frame, int) and frame in _FRAME_TYPES:
        return _FRAME_TYPES[frame]
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return "unknown"


def _coerce_int(value: object | None) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.sub(r"[^0-9-]", "", value)
        if digits:
            try:
                return int(digits)
            except ValueError:
                pass
    return 0


def _extract_quality(item: Mapping[str, object]) -> int:
    quality_value = item.get("quality")
    quality = _coerce_int(quality_value)
    if quality:
        return quality
    for prop in item.get("properties", []) or []:
        if not isinstance(prop, Mapping):
            continue
        if prop.get("name") != "Quality":
            continue
        candidate = prop.get("value") or (prop.get("values") or [])
        if isinstance(candidate, list):
            candidate = candidate[0] if candidate else None
        quality = _coerce_int(candidate)
        if quality:
            return quality
    return 0


def _extract_influences(item: Mapping[str, object]) -> Sequence[str]:
    influences = item.get("influences")
    if isinstance(influences, Mapping):
        return [name for name, active in influences.items() if active]
    if isinstance(influences, Sequence):
        return [str(entry) for entry in influences]
    return []


def _extract_modifiers(item: Mapping[str, object]) -> tuple[Sequence[str], Sequence[int]]:
    sources: list[object] = []
    for key in ("mods", "modifiers", "explicitMods", "implicitMods"):
        candidate = item.get(key)
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
            sources.extend(candidate)
    modifier_ids: list[str] = []
    modifier_tiers: list[int] = []
    for mod in sources:
        if isinstance(mod, Mapping):
            mod_id = mod.get("id") or mod.get("name")
            modifier_ids.append(str(mod_id or ""))
            modifier_tiers.append(_coerce_int(mod.get("tier")))
        else:
            modifier_ids.append(str(mod))
            modifier_tiers.append(0)
    return modifier_ids, modifier_tiers



def _extract_flags(item: Mapping[str, object]) -> Sequence[str]:
    flags_value = item.get("flags")
    if isinstance(flags_value, Mapping):
        return [name for name, active in flags_value.items() if active]
    if isinstance(flags_value, Sequence) and not isinstance(flags_value, (str, bytes)):
        return [str(entry) for entry in flags_value]
    if isinstance(flags_value, str):
        return [flags_value]
    return []


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parse_price(amount: Mapping[str, object] | object) -> float:
    if isinstance(amount, (int, float)):
        return float(amount)
    if isinstance(amount, str) and amount.strip():
        return float(amount.strip())
    raise ValueError("Unable to parse price amount")


def _normalize_chaos(amount: float, currency: str) -> float:
    if currency.strip().lower() in _CHAOS_CURRENCIES:
        return amount
    return 0.0


def parse_bronze_row(row: Mapping[str, object]) -> Sequence[Tuple[ItemCanonical, ListingCanonical]]:
    payload_raw = row.get("payload_json")
    if payload_raw is None:
        raise ValueError("missing payload")
    if isinstance(payload_raw, str):
        payload_str = payload_raw
    else:
        payload_str = _canonical_json(payload_raw)
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise ValueError("payload not valid json") from exc

    items_payload = payload.get("items") or []
    if not isinstance(items_payload, Sequence) or isinstance(items_payload, (str, bytes)):
        return []

    captured_at = _parse_timestamp(row.get("ingested_at"))
    league = str(row.get("league") or payload.get("league") or "unknown")
    source = str(row.get("realm") or row.get("source") or "public-stash")
    stash_id = str(row.get("stash_id") or payload.get("stash_id") or "anonymous")

    result: list[Tuple[ItemCanonical, ListingCanonical]] = []
    for index, item_payload in enumerate(items_payload):
        if not isinstance(item_payload, Mapping):
            continue
        item_uid = str(item_payload.get("id") or f"{stash_id}:{index}")
        base_type = str(item_payload.get("typeLine") or item_payload.get("baseType") or item_payload.get("name") or "unknown")
        rarity = _normalize_rarity(item_payload.get("frameType"), item_payload.get("rarity"))
        ilvl = _coerce_int(item_payload.get("ilvl") or item_payload.get("level"))
        corrupted = bool(item_payload.get("corrupted"))
        quality = _extract_quality(item_payload)
        sockets = len(item_payload.get("sockets") or [])
        links = _coerce_int(item_payload.get("links"))
        influences = _extract_influences(item_payload)
        modifier_ids, modifier_tiers = _extract_modifiers(item_payload)
        flags = _extract_flags(item_payload)

        listing_data = item_payload.get("listing") or {}
        price_block = listing_data.get("price") or item_payload.get("price") or {}
        price_amount = parse_price(price_block.get("amount", 0))
        price_currency = str(price_block.get("currency") or "Chaos")
        seller_candidate = listing_data.get("seller") or item_payload.get("seller") or {}
        seller_id = str(seller_candidate.get("id") or seller_candidate.get("accountName") or f"seller-{stash_id}")
        seller_meta = str(
            seller_candidate.get("meta")
            or listing_data.get("note")
            or item_payload.get("note")
            or ""
        )
        listed_at = _parse_timestamp(listing_data.get("listed_at") or row.get("listed_at") or row.get("ingested_at"))
        last_seen_at = _parse_timestamp(item_payload.get("last_seen_at") or row.get("ingested_at"))
        listing_uid = str(item_payload.get("listing_id") or f"{stash_id}:{item_uid}")

        fp_subject = {
            "name": item_payload.get("name") or base_type,
            "base_type": base_type,
            "rarity": rarity,
            "ilvl": ilvl,
            "corrupted": corrupted,
            "quality": quality,
            "sockets": sockets,
            "links": links,
        }
        fp_e = fp_exact(fp_subject)
        fp_l = fp_loose(fp_subject)

        payload_json = payload_str
        listing_payload = {"listing": listing_data, "item": item_payload}
        listing_payload_json = _canonical_json(listing_payload)

        item_record = ItemCanonical(
            item_uid=item_uid,
            source=source,
            captured_at=captured_at,
            league=league,
            base_type=base_type,
            rarity=rarity,
            ilvl=ilvl,
            corrupted=corrupted,
            quality=quality,
            sockets=sockets,
            links=links,
            influences=influences,
            modifier_ids=modifier_ids,
            modifier_tiers=modifier_tiers,
            flags=flags,
            fp_exact=fp_e,
            fp_loose=fp_l,
            payload_json=payload_json,
        )
        listing_record = ListingCanonical(
            listing_uid=listing_uid,
            item_uid=item_uid,
            listed_at=listed_at,
            league=league,
            price_amount=price_amount,
            price_currency=price_currency,
            price_chaos=_normalize_chaos(price_amount, price_currency),
            seller_id=seller_id,
            seller_meta=seller_meta,
            last_seen_at=last_seen_at,
            fp_loose=fp_l,
            payload_json=listing_payload_json,
        )
        result.append((item_record, listing_record))
    return result
