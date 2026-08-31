"""Bridge from a persisted chat turn to the SQLite chat archive.

The archive is best-effort by design: a chat turn that answered correctly must
not be reported as failed because a secondary write did not land. Every failure
here becomes a string in the response's `errors` list instead of an exception.

Those strings reach the browser, so they carry the exception's class name and
nothing else. Detail goes to stderr, the same split memory/embedder.py uses for
a failed embedding.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Iterable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from kb_core_ui.memory import ChatMemoryStore

    from .persistence import PersistedTurn

TITLE_LIMIT = 200


def compose_title(query: str) -> str:
    return query.strip()[:TITLE_LIMIT]


def compose_text(answer: str, citations: Iterable[dict[str, Any]]) -> str:
    """Answer first, then one `source_id:source_location` line per citation.

    The citation lines are what make an archived turn findable by where its
    evidence came from, not only by what it said.
    """

    lines = [answer.strip()]
    for citation in citations:
        source_id = str(citation.get("source_id", ""))
        location = str(citation.get("source_location", ""))
        lines.append(f"{source_id}:{location}")
    return "\n".join(lines)


@runtime_checkable
class ChatMemorySink(Protocol):
    def record(self, turn: "PersistedTurn") -> None: ...

    def delete_thread(self, workspace_id: str, thread_id: str) -> None: ...

    def delete_workspace(self, workspace_id: str) -> None: ...

    def drain_errors(self) -> list[str]: ...

    def close(self) -> None: ...


class NullChatMemorySink:
    """What a server without a memory database injects, so every call site can
    stay unconditional."""

    def record(self, turn: "PersistedTurn") -> None:
        return None

    def delete_thread(self, workspace_id: str, thread_id: str) -> None:
        return None

    def delete_workspace(self, workspace_id: str) -> None:
        return None

    def drain_errors(self) -> list[str]:
        return []

    def close(self) -> None:
        return None


class SyncChatMemorySink:
    def __init__(self, store: "ChatMemoryStore"):
        self._store = store
        self._errors: list[str] = []

    def note_error(self, message: str) -> None:
        self._errors.append(f"chat_memory: {message}")

    def _failed(self, action: str, exc: Exception) -> None:
        print(f"chat memory {action} failed: {exc}", file=sys.stderr)
        # Only the class name: this string is echoed to the browser, and a raw
        # sqlite message carries the database path.
        self.note_error(f"{action} failed ({exc.__class__.__name__})")

    def record(self, turn: "PersistedTurn") -> None:
        try:
            response = turn.response
            self._store.add(
                turn.workspace_id,
                turn.thread_id,
                turn.turn_id,
                turn.seq,
                compose_title(turn.query),
                compose_text(
                    str(response.get("answer", "")), response.get("citations") or ()
                ),
            )
        except Exception as exc:  # best-effort archive; never fail the turn
            self._failed("record", exc)

    def delete_thread(self, workspace_id: str, thread_id: str) -> None:
        try:
            self._store.delete_thread(workspace_id, thread_id)
        except Exception as exc:  # best-effort archive; never fail the delete
            self._failed("delete_thread", exc)

    def delete_workspace(self, workspace_id: str) -> None:
        try:
            self._store.delete_workspace(workspace_id)
        except Exception as exc:  # best-effort archive; never fail the delete
            self._failed("delete_workspace", exc)

    def drain_errors(self) -> list[str]:
        drained, self._errors = self._errors, []
        return drained

    def close(self) -> None:
        # The store's owner opened it and closes it; a sink is only a writer.
        return None
