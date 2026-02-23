"""Helpers for cleansing captured text."""

from __future__ import annotations

import re


def normalize_item_text(text: str) -> str:
    """Drop weird whitespace and duplicate blank lines."""

    if not text:
        return ""

    cleaned = text.replace("\r", "")
    lines = [line.strip() for line in cleaned.splitlines()]
    compact = [line for line in lines if line]
    return "\n".join(compact)


def is_likely_item_text(text: str) -> bool:
    """Very simple heuristics over PoE clipboard dumps."""

    if not text:
        return False

    lowered = text.lower()
    if "rarity:" in lowered or "item level" in lowered:
        return True

    return "--------" in text or bool(re.search(r"\bimplicit\b|\bexplicit\b", lowered))
