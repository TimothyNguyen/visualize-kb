from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from harness.errors import ManifestError


@dataclass(frozen=True)
class NormalizeContext:
    fixture_root: str
    engine: str


NormalizerFn = Callable[[Any, NormalizeContext], Any]

NORMALIZERS: dict[str, NormalizerFn] = {}


def register(name: str) -> Callable[[NormalizerFn], NormalizerFn]:
    def _decorator(fn: NormalizerFn) -> NormalizerFn:
        NORMALIZERS[name] = fn
        return fn

    return _decorator


def _walk_strings(value: Any, fn: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, dict):
        return {k: _walk_strings(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_strings(v, fn) for v in value]
    return value


@register("line_endings")
def normalize_line_endings(value: Any, ctx: NormalizeContext) -> Any:
    return _walk_strings(value, lambda s: s.replace("\r\n", "\n").replace("\r", "\n"))


@register("fixture_root_path")
def normalize_fixture_root_path(value: Any, ctx: NormalizeContext) -> Any:
    root = ctx.fixture_root
    variants = [v for v in {root, root.replace("\\", "/"), root.replace("/", "\\")} if v]

    def _replace(s: str) -> str:
        for variant in variants:
            s = s.replace(variant, "<FIXTURE_ROOT>")
        return s

    return _walk_strings(value, _replace)


_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})"
)


@register("timestamp")
def normalize_timestamp(value: Any, ctx: NormalizeContext) -> Any:
    return _walk_strings(value, lambda s: _TIMESTAMP_RE.sub("<TIMESTAMP>", s))


_GENERATED_ID_RE = re.compile(
    r"\b(rule|lesson|business|overview|reference)-[a-z0-9-]{0,40}-\d{10,}\b"
)


@register("generated_id")
def normalize_generated_id(value: Any, ctx: NormalizeContext) -> Any:
    return _walk_strings(value, lambda s: _GENERATED_ID_RE.sub(r"\1-<SLUG>-<NANOTS>", s))


_EDGE_KEYS = {"source", "target", "kind"}


@register("edge_order")
def normalize_edge_order(value: Any, ctx: NormalizeContext) -> Any:
    """Sorts graph.Edge arrays.

    Store.Subgraph collects its result in a map[graph.Edge]bool and returns
    it by ranging that map. Go randomizes map iteration order, so
    /api/graph/subgraph serves the same edge *set* in a different order on
    every call — Go disagrees with itself, not just with the port. Sorting is
    declared per case (SPEC.md C4/V2), never globally: /api/graph reads its
    edges straight out of SQLite and stays order-stable, so it must keep
    failing on a real reordering.
    """

    def _walk(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: _walk(x) for k, x in v.items()}
        if isinstance(v, list):
            items = [_walk(x) for x in v]
            if items and all(isinstance(i, dict) and set(i) == _EDGE_KEYS for i in items):
                items.sort(key=lambda e: (e["source"], e["target"], e["kind"]))
            return items
        return v

    return _walk(value)


@register("key_order")
def normalize_key_order(value: Any, ctx: NormalizeContext) -> Any:
    if isinstance(value, dict):
        return {k: normalize_key_order(value[k], ctx) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [normalize_key_order(v, ctx) for v in value]
    return value


def canonicalize(value: Any, normalizer_names: Sequence[str], ctx: NormalizeContext) -> Any:
    for name in normalizer_names:
        if name not in NORMALIZERS:
            raise ManifestError(f"unknown normalizer {name!r} (known: {sorted(NORMALIZERS)})")
        value = NORMALIZERS[name](value, ctx)
    return value


def canonical_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# Which response headers are contract rather than transport. Content-Type
# decides whether a browser executes a .js asset or renders it as text, so it
# is exactly the kind of difference that breaks the React app while every
# body still matches. Date, Server, Connection, Last-Modified and friends are
# per-process or per-implementation and carry no contract, so a capture that
# included them could never pass.
#
# Content-Length is deliberately absent too. It is framing, not contract: Go
# buffers a handler response up to 2048 bytes and sets Content-Length, then
# switches to chunked encoding past that, so /api/bots sends no
# Content-Length purely because its roster is 2.7KB. A client receives the
# same bytes either way, and comparing it would pin the port to an internal
# Go buffer size.
#
# This is a capture, not an ignore list: it declares what is observed, the
# same way stdout_exit observes stdout and stdout_stderr_exit observes both.
_CONTRACT_HEADERS = frozenset(
    {
        "content-type",
        "location",
        "x-content-type-options",
        "access-control-allow-origin",
        "access-control-allow-methods",
        "access-control-allow-headers",
    }
)


def to_comparable(capture: str, raw: Any) -> dict[str, Any]:
    if capture == "stdout_exit":
        return {"exit_code": raw.exit_code, "stdout": raw.stdout}
    if capture == "stdout_stderr_exit":
        return {"exit_code": raw.exit_code, "stdout": raw.stdout, "stderr": raw.stderr}
    if capture == "json_body_status":
        return {"status": raw.status, "body": raw.json_body}
    if capture == "status_text_body":
        return {"status": raw.status, "text_body": raw.text_body}
    if capture == "status_headers":
        return {
            "status": raw.status,
            "headers": {k: v for k, v in raw.headers.items() if k in _CONTRACT_HEADERS},
        }
    if capture == "json_result":
        return {"result": raw}
    raise ManifestError(f"unknown capture kind {capture!r}")
