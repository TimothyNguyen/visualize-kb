"""JSON encoding that matches Go's encoding/json byte-for-byte.

Go escapes `<`, `>` and `&` as \\u003c/\\u003e/\\u0026 by default, so a
TypeScript return type like `Promise<TreeNode>` serializes differently there
than under json.dumps. Those bytes end up in the symbols table and in REST
response bodies, both of which are compared literally against the Go
baselines.
"""

from __future__ import annotations

import json
from typing import Any

_HTML_ESCAPES = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    " ": "\\u2028",
    " ": "\\u2029",
}


def dumps(value: Any) -> str:
    out = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    for char, escape in _HTML_ESCAPES.items():
        out = out.replace(char, escape)
    return out


def loads(text: str) -> Any:
    return json.loads(text)
