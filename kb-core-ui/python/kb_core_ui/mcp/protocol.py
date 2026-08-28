"""JSON-RPC 2.0 over stdio — the transport mark3labs/mcp-go's ServeStdio
provides on the Go side.

Framing is newline-delimited JSON, not LSP Content-Length headers: mcp-go
reads with a bufio.Reader line at a time, so a message must be exactly one
line and must end with one.

stdio *is* the protocol here. Nothing but JSON-RPC may reach stdout — every
progress line the command prints goes to stderr, the same redirect
cmd/kb-core-ui/mcp.go makes with cmd.SetOut(os.Stderr).
"""

from __future__ import annotations

import sys
from typing import Any, Callable, TextIO

from kb_core_ui import jsonx

PROTOCOL_VERSION = "2024-11-05"

# JSON-RPC 2.0 reserved codes, as mcp-go returns them.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

Handler = Callable[[dict], Any]


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def serve_stdio(
    handlers: dict[str, Handler],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Reads requests until stdin closes. Notifications (no "id") get no
    reply, per JSON-RPC 2.0 — answering one would desynchronize the client."""
    src = stdin if stdin is not None else sys.stdin
    dst = stdout if stdout is not None else sys.stdout

    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            message = jsonx.loads(line)
        except ValueError:
            _write(dst, _error_response(None, PARSE_ERROR, "Parse error"))
            continue
        if not isinstance(message, dict):
            _write(dst, _error_response(None, INVALID_REQUEST, "Invalid Request"))
            continue

        msg_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        handler = handlers.get(method)
        if handler is None:
            if msg_id is not None:
                _write(dst, _error_response(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}"))
            continue

        try:
            result = handler(params if isinstance(params, dict) else {})
        except JsonRpcError as exc:
            if msg_id is not None:
                _write(dst, _error_response(msg_id, exc.code, exc.message))
            continue
        except Exception as exc:  # noqa: BLE001 - a handler bug must not kill the session
            if msg_id is not None:
                _write(dst, _error_response(msg_id, INTERNAL_ERROR, str(exc)))
            continue

        if msg_id is not None:
            _write(dst, {"jsonrpc": "2.0", "id": msg_id, "result": result})


def _write(dst: TextIO, payload: dict) -> None:
    dst.write(jsonx.dumps(payload) + "\n")
    dst.flush()


def _error_response(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
