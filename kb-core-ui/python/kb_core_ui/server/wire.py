"""Request/response value types plus the four ways server.go writes a body.

Go's net/http fixes the exact bytes of a response — writeJSON appends a
newline because json.Encoder does, http.NotFound sends
"404 page not found\n" with a nosniff header, and http.Redirect emits a
short HTML body. The REST baselines capture status and body verbatim, so
those details are contract, not incidental.
"""

from __future__ import annotations

import html
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from kb_core_ui import jsonx


@dataclass(frozen=True)
class Request:
    method: str
    raw_path: str
    """The still-percent-encoded path — Go's r.URL.EscapedPath(). Symbol ids
    embed '/' as %2F, so decoding before the route split corrupts them."""
    path: str
    """The decoded path — Go's r.URL.Path."""
    query: dict[str, list[str]]
    query_string: str
    body: bytes

    def get_query(self, name: str) -> str:
        """Go's url.Values.Get: first value, or "" when absent."""
        values = self.query.get(name)
        return values[0] if values else ""


@dataclass(frozen=True)
class Response:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def not_found() -> "Response":
        # http.NotFound -> http.Error(w, "404 page not found", 404).
        return Response(
            status=404,
            body=b"404 page not found\n",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "X-Content-Type-Options": "nosniff",
            },
        )


def write_json(value: Any, status: int = 200) -> Response:
    """server.go's writeJSON: json.Encoder output, which is compact, HTML-safe
    and newline-terminated."""
    return Response(
        status=status,
        body=(jsonx.dumps(value) + "\n").encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def write_error(status: int, msg: str) -> Response:
    return write_json({"error": msg}, status=status)


def write_text(text: str) -> Response:
    # No explicit Content-Type: Go sniffs plain text the same way.
    return Response(status=200, body=text.encode("utf-8"), headers={})


def moved_permanently(location: str) -> Response:
    # http.Redirect's GET body.
    body = f'<a href="{html.escape(location)}">Moved Permanently</a>.\n\n'
    return Response(
        status=301,
        body=body.encode("utf-8"),
        headers={"Location": location, "Content-Type": "text/html; charset=utf-8"},
    )


def path_unescape(escaped: str) -> str:
    """Go's url.PathUnescape, which rejects malformed % sequences instead of
    passing them through the way urllib.parse.unquote does."""
    i = 0
    while i < len(escaped):
        if escaped[i] == "%":
            hexits = escaped[i + 1 : i + 3]
            if len(hexits) != 2 or any(c not in "0123456789abcdefABCDEF" for c in hexits):
                raise ValueError(f"invalid URL escape {escaped[i:i + 3]!r}")
            i += 3
            continue
        i += 1
    return urllib.parse.unquote(escaped, errors="surrogateescape")
