from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class _RouteRule:
    route: str
    categories: frozenset[str] | None = None
    rarity: str | None = None


_ORDERED_ROUTE_RULES: tuple[_RouteRule, ...] = (
    _RouteRule(
        route="cluster_jewel_retrieval", categories=frozenset({"cluster_jewel"})
    ),
    _RouteRule(
        route="fungible_reference",
        categories=frozenset({"fossil", "scarab", "logbook"}),
    ),
    _RouteRule(
        route="structured_boosted_other",
        rarity="Unique",
        categories=frozenset({"ring", "amulet", "belt", "jewel"}),
    ),
    _RouteRule(route="structured_boosted", rarity="Unique"),
    _RouteRule(route="sparse_retrieval", rarity="Rare"),
)

_DEFAULT_ROUTE = "fallback_abstain"


def _matches_rule(*, category: str, rarity: str, rule: _RouteRule) -> bool:
    if rule.rarity is not None and rarity != rule.rarity:
        return False
    if rule.categories is not None and category not in rule.categories:
        return False
    return True


def _sql_condition_for_rule(
    rule: _RouteRule, *, category_expr: str, rarity_expr: str
) -> str:
    parts: list[str] = []
    if rule.categories is not None:
        if len(rule.categories) == 1:
            category = next(iter(rule.categories))
            parts.append(f"{category_expr} = '{category}'")
        else:
            categories = ",".join(
                f"'{category}'" for category in sorted(rule.categories)
            )
            parts.append(f"{category_expr} IN ({categories})")
    if rule.rarity is not None:
        parts.append(f"{rarity_expr} = '{rule.rarity}'")
    return " AND ".join(parts)


def select_route(parsed: Mapping[str, Any]) -> str:
    category = str(parsed.get("category") or "other")
    rarity = str(parsed.get("rarity") or "")
    for rule in _ORDERED_ROUTE_RULES:
        if _matches_rule(category=category, rarity=rarity, rule=rule):
            return rule.route
    return _DEFAULT_ROUTE


def route_sql_expression(
    *, category_expr: str = "category", rarity_expr: str = "rarity"
) -> str:
    clauses = [
        f"{_sql_condition_for_rule(rule, category_expr=category_expr, rarity_expr=rarity_expr)}, '{rule.route}'"
        for rule in _ORDERED_ROUTE_RULES
    ]
    return "multiIf(" + ", ".join(clauses) + f", '{_DEFAULT_ROUTE}'" + ")"
