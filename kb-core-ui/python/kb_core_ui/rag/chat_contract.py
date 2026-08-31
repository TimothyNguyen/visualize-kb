"""Lightweight chat transport contract shared with the base HTTP server.

This module intentionally has no LangGraph or FalkorDB dependency so the
local graph UI can start without installing the optional RAG extra.
"""

SSE_EVENT_QUEUED = "queued"
SSE_EVENT_HEARTBEAT = "heartbeat"
SSE_EVENT_TOKEN = "token"
SSE_EVENT_COMPLETED = "completed"
SSE_EVENT_CANCELLED = "cancelled"
SSE_EVENT_ERROR = "error"

TERMINAL_SSE_EVENTS = frozenset(
    {SSE_EVENT_COMPLETED, SSE_EVENT_CANCELLED, SSE_EVENT_ERROR}
)


class ChatManagerError(RuntimeError):
    """HTTP-safe chat error carrying a status code and sanitized message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
