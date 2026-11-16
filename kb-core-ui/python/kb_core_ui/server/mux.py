"""A subset of Go 1.22's net/http.ServeMux, faithful to the parts
internal/server/server.go relies on.

The Go mux is not a generic router: pattern precedence, the implicit
subtree redirect, and the "match on the *escaped* path" rule all change
which handler (and which status code) a request reaches. Reimplementing
those rules here keeps route dispatch a parity concern of this file alone,
so the handlers in app.py can stay a line-for-line port.

Not modelled: host patterns, `{wildcard}` segments, and the 405 fallback.
The server registers a methodless "/" catch-all, so no request can ever
miss on method alone — Go returns 405 only when *nothing* matched.
"""

from __future__ import annotations

import posixpath
import urllib.parse
from dataclasses import dataclass
from typing import Callable

from kb_core_ui.server.wire import Request, Response, moved_permanently


@dataclass(frozen=True)
class Pattern:
    method: str | None
    path: str

    @property
    def subtree(self) -> bool:
        return self.path.endswith("/")

    def matches_method(self, method: str) -> bool:
        if self.method is None:
            return True
        # Go: "the GET method matches both GET and HEAD requests".
        if self.method == "GET" and method == "HEAD":
            return True
        return self.method == method

    def matches_path(self, path: str) -> bool:
        return path.startswith(self.path) if self.subtree else path == self.path

    @property
    def precedence(self) -> tuple[int, int]:
        # Longer patterns are more specific; a method-bound pattern beats the
        # methodless catch-all registered at the same path.
        return (len(self.path), 1 if self.method else 0)


Handler = Callable[[Request], Response]


def clean_path(p: str) -> str:
    """Go's net/http.cleanPath: path.Clean, but a trailing slash survives."""
    if p == "":
        return "/"
    if not p.startswith("/"):
        p = "/" + p
    cleaned = posixpath.normpath(p)
    if p.endswith("/") and cleaned != "/":
        cleaned += "/"
    return cleaned


class Mux:
    def __init__(self) -> None:
        self._routes: list[tuple[Pattern, Handler]] = []

    def handle(self, spec: str, handler: Handler) -> None:
        """spec is a Go pattern: "GET /api/tree", or "/" for any method."""
        method: str | None = None
        path = spec
        if " " in spec:
            method, path = spec.split(" ", 1)
        self._routes.append((Pattern(method=method, path=path), handler))

    def _lookup(self, method: str, path: str) -> Handler | None:
        best: tuple[tuple[int, int], Handler] | None = None
        for pattern, handler in self._routes:
            if not pattern.matches_method(method) or not pattern.matches_path(path):
                continue
            if best is None or pattern.precedence > best[0]:
                best = (pattern.precedence, handler)
        return None if best is None else best[1]

    def _has_subtree(self, path: str) -> bool:
        return any(p.path == path and p.subtree for p, _ in self._routes)

    def dispatch(self, req: Request) -> Response:
        cleaned = clean_path(req.path)
        if cleaned != req.path:
            return moved_permanently(_with_query(cleaned, req.query_string))

        # Go redirects /api/files -> /api/files/ when only the subtree
        # pattern is registered, so a client can't silently 404 on the
        # missing slash.
        if not req.raw_path.endswith("/") and self._has_subtree(req.raw_path + "/"):
            if self._lookup(req.method, req.raw_path) is None:
                return moved_permanently(_with_query(req.raw_path + "/", req.query_string))

        handler = self._lookup(req.method, req.raw_path)
        if handler is None:
            return Response.not_found()
        return handler(req)


def _with_query(path: str, query_string: str) -> str:
    escaped = urllib.parse.quote(path, safe="/%")
    return f"{escaped}?{query_string}" if query_string else escaped
