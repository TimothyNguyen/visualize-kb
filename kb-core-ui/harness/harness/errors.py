from __future__ import annotations


class HarnessError(Exception):
    """Base class for all harness errors."""


class ManifestError(HarnessError):
    """A fixture manifest is malformed or references an unknown normalizer."""


class EngineError(HarnessError):
    """An engine binary is missing, failed to start, or a command template
    has an unresolved placeholder."""


class McpProtocolError(EngineError):
    """An MCP server returned a JSON-RPC error or an isError tool result."""
