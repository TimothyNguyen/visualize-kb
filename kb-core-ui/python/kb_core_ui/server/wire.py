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
from typing import Any, Callable, Iterable

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
    stream: Callable[[], Iterable[bytes]] | None = None
    """When set, the transport (httpd.py) writes headers with no
    Content-Length and then writes each chunk this factory yields as it
    becomes available, instead of the fixed ``body`` bytes -- the SSE chat
    stream (T11). ``body``/``headers`` from the normal JSON path are unused
    for a streaming response except for the caller-supplied headers, which
    still apply (Content-Type, Cache-Control, etc). A *factory* rather than a
    bare iterator so nothing starts running the underlying generator until
    the transport is actually ready to write bytes -- constructing the
    Response never begins doing the work."""

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


def format_sse_event(event: str, data: Any) -> bytes:
    """One well-formed SSE frame: an explicit ``event:`` line (never left to
    the implicit/unnamed "message" default) plus one ``data:`` line carrying
    compact JSON, terminated by the required blank line. A payload
    containing a literal newline would otherwise silently truncate the frame
    at the browser's EventSource parser, so newlines are rejected up front
    rather than smuggled through as multiple ``data:`` lines only some
    servers reassemble correctly."""

    payload = jsonx.dumps(data)
    if "\n" in payload or "\r" in payload:
        raise ValueError("SSE data payload must not contain a raw newline")
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


SSE_HEARTBEAT_FRAME = b": heartbeat\n\n"
"""Keep-alive written as an SSE *comment* rather than a named event. A
comment is discarded by the EventSource parser before any listener runs, so
a heartbeat cannot be mistaken for answer content -- unlike a named
``heartbeat`` event, which every client would have to remember to filter."""


def write_sse(events: Callable[[], Iterable[bytes]]) -> Response:
    """A streaming Server-Sent-Events response (T11). ``events`` is a
    zero-arg factory returning an iterable of already-framed SSE byte
    chunks (see :func:`format_sse_event`) -- the transport calls it once it
    is ready to start writing, so no retrieval/provider work happens before
    the client is actually listening.

    ``X-Accel-Buffering: no`` and an explicit ``no-cache`` stop an
    intermediary proxy from buffering the whole stream before relaying it,
    which would defeat incremental delivery entirely.
    """

    return Response(
        status=200,
        headers={
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
        stream=events,
    )


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
