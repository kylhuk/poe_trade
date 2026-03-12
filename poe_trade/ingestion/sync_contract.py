from __future__ import annotations

from ..config import constants


def queue_key(feed_kind: str, realm: str) -> str:
    prefix = constants.QUEUE_PREFIXES.get(feed_kind)
    if prefix is None:
        raise ValueError(f"Unsupported feed kind: {feed_kind}")
    normalized_realm = realm.strip().lower()
    if not normalized_realm:
        raise ValueError("Realm must be non-empty")
    return f"{prefix}{normalized_realm}"


def is_supported_feed_kind(feed_kind: str) -> bool:
    return feed_kind in constants.QUEUE_PREFIXES


__all__ = ["is_supported_feed_kind", "queue_key"]
