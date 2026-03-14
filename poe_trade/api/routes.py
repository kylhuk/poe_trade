from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Callable

from .responses import Response

Handler = Callable[[Mapping[str, object]], Response]


@dataclass(frozen=True)
class Route:
    template: str
    methods: tuple[str, ...]
    pattern: re.Pattern[str]
    handler: Handler


@dataclass(frozen=True)
class RouteMatch:
    route: Route | None
    params: dict[str, str]
    allowed_methods: tuple[str, ...]


class Router:
    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, template: str, methods: tuple[str, ...], handler: Handler) -> None:
        self._routes.append(
            Route(
                template=template,
                methods=tuple(methods),
                pattern=_compile_template(template),
                handler=handler,
            )
        )

    def match(self, method: str, path: str) -> RouteMatch:
        allowed: list[str] = []
        for route in self._routes:
            matched = route.pattern.fullmatch(path)
            if not matched:
                continue
            if method in route.methods:
                params = {
                    key: value
                    for key, value in matched.groupdict().items()
                    if isinstance(value, str)
                }
                return RouteMatch(route=route, params=params, allowed_methods=())
            allowed.extend(route.methods)
        if not allowed:
            return RouteMatch(route=None, params={}, allowed_methods=())
        normalized = tuple(sorted(set(allowed)))
        return RouteMatch(route=None, params={}, allowed_methods=normalized)


def _compile_template(template: str) -> re.Pattern[str]:
    pattern = re.escape(template)
    pattern = re.sub(r"\\\{([a-zA-Z_][a-zA-Z0-9_]*)\\\}", r"(?P<\1>[^/]+)", pattern)
    return re.compile(pattern)
