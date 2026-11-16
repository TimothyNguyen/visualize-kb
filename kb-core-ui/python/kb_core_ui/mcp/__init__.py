"""MCP service — the Python side of internal/mcp/.

Split so the parity-critical parts stay separate: protocol.py is the
JSON-RPC-over-stdio transport, tools.py reproduces the tool-schema shapes
mark3labs/mcp-go generates, and server.py is the handler port.
"""

from kb_core_ui.mcp.protocol import PROTOCOL_VERSION, serve_stdio
from kb_core_ui.mcp.server import Server

__all__ = ["Server", "serve_stdio", "PROTOCOL_VERSION"]
