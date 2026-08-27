from __future__ import annotations

import json
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any

from harness.errors import McpProtocolError

_PROTOCOL_VERSION = "2024-11-05"


class McpSession:
    """Minimal newline-delimited JSON-RPC 2.0 client over a child process's
    stdio, matching mark3labs/mcp-go's stdio transport (bufio.Reader line
    reads — not LSP Content-Length framing)."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self._next_id = 1
        self._queue: queue.Queue[str | None] = queue.Queue()
        # Windows pipes don't support select() on file objects, so a
        # background reader thread + queue is the portable way to get a
        # read-with-timeout.
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self._queue.put(line)
        finally:
            self._queue.put(None)

    def _read_message(self, timeout_s: float) -> dict:
        try:
            line = self._queue.get(timeout=timeout_s)
        except queue.Empty as exc:
            raise TimeoutError(f"no MCP message within {timeout_s}s") from exc
        if line is None:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise McpProtocolError(f"MCP server closed stdout unexpectedly: {stderr}")
        line = line.strip()
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise McpProtocolError(f"malformed MCP message: {line!r}") from exc

    def _write_message(self, obj: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _call(self, method: str, params: dict, timeout_s: float = 10.0) -> Any:
        msg_id = self._next_id
        self._next_id += 1
        self._write_message({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        while True:
            resp = self._read_message(timeout_s)
            if resp.get("id") == msg_id:
                if "error" in resp:
                    raise McpProtocolError(f"{method} failed: {resp['error']}")
                return resp.get("result", {})
            # unrelated notification/response — keep waiting for our id

    def initialize(self) -> dict:
        result = self._call(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "kb-core-ui-harness", "version": "0.1.0"},
            },
        )
        self._write_message({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return result

    def call_tool(self, name: str, arguments: dict) -> Any:
        result = self._call("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise McpProtocolError(f"tool {name!r} returned isError: {result}")
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            text = content[0]["text"]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return content

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


def start_mcp_process(argv: list[str], cwd: Path) -> McpSession:
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    return McpSession(proc)
