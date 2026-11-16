"""Bridge from a persisted chat turn to the SQLite chat archive.

The archive is best-effort by design: a chat turn that answered correctly must
not be reported as failed because a secondary write did not land. Every failure
here becomes a string in the response's `errors` list instead of an exception.

Those strings reach the browser, so they carry the exception's class name and
nothing else. Detail goes to stderr, the same split memory/embedder.py uses for
a failed embedding.
"""

from __future__ import annotations

import queue
import sys
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Protocol

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


class ChatMemorySink(Protocol):
    def record(self, turn: "PersistedTurn") -> None: ...

    def delete_thread(self, workspace_id: str, thread_id: str) -> int: ...

    def delete_workspace(self, workspace_id: str) -> int: ...

    def drain_errors(self, workspace_id: str) -> list[str]: ...

    def close(self) -> None: ...


class NullChatMemorySink:
    """What a server without a memory database injects, so every call site can
    stay unconditional."""

    def record(self, turn: "PersistedTurn") -> None:
        return None

    def delete_thread(self, workspace_id: str, thread_id: str) -> int:
        return 0

    def delete_workspace(self, workspace_id: str) -> int:
        return 0

    def drain_errors(self, workspace_id: str) -> list[str]:
        return []

    def close(self) -> None:
        return None


class SyncChatMemorySink:
    def __init__(self, store: "ChatMemoryStore"):
        self._store = store
        # Keyed by workspace: these strings ride out on a chat response, so one
        # tenant must never be shown a failure another tenant's turn caused.
        # The lock is because a worker thread appends while request threads drain.
        self._errors: dict[str, list[str]] = {}
        self._errors_lock = threading.Lock()

    def note_error(self, workspace_id: str, message: str) -> None:
        with self._errors_lock:
            self._errors.setdefault(workspace_id, []).append(f"chat_memory: {message}")

    def _failed(self, workspace_id: str, action: str, exc: Exception) -> None:
        print(f"chat memory {action} failed: {exc}", file=sys.stderr)
        # Only the class name: this string is echoed to the browser, and a raw
        # sqlite message carries the database path.
        self.note_error(workspace_id, f"{action} failed ({exc.__class__.__name__})")

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
            self._failed(turn.workspace_id, "record", exc)

    def delete_thread(self, workspace_id: str, thread_id: str) -> int:
        try:
            return self._store.delete_thread(workspace_id, thread_id)
        except Exception as exc:  # best-effort archive; never fail the delete
            self._failed(workspace_id, "delete_thread", exc)
            return 0

    def delete_workspace(self, workspace_id: str) -> int:
        try:
            return self._store.delete_workspace(workspace_id)
        except Exception as exc:  # best-effort archive; never fail the delete
            self._failed(workspace_id, "delete_workspace", exc)
            return 0

    def drain_errors(self, workspace_id: str) -> list[str]:
        with self._errors_lock:
            return self._errors.pop(workspace_id, [])

    def close(self) -> None:
        # The store's owner opened it and closes it; a sink is only a writer.
        return None


@dataclass
class _Work:
    done: threading.Event = field(default_factory=threading.Event)
    workspace_id: str = ""


@dataclass
class _Record(_Work):
    turn: object = None


@dataclass
class _Delete(_Work):
    # How many rows the worker removed, carried back to the caller waiting on
    # ``done`` so an HTTP delete can report a count without touching the store.
    deleted: int = 0


@dataclass
class _DeleteThread(_Delete):
    thread_id: str = ""


@dataclass
class _DeleteWorkspace(_Delete):
    pass


class ThreadedChatMemorySink:
    """Runs a SyncChatMemorySink on one worker thread.

    Embedding a turn can be an HTTP call with a 30s timeout. That must not sit
    on the thread of a chat request that has already produced its answer.

    Work is a single FIFO queue, so a delete queued after a write is applied
    after that write -- a queued write can never resurrect a deleted thread.
    Deletes wait for their own item to be processed, bounded by `timeout`, so a
    dead worker degrades into a late delete rather than a hung request.
    """

    def __init__(self, inner: SyncChatMemorySink, *, maxsize: int = 256, timeout: float = 5.0):
        self._inner = inner
        self._timeout = timeout
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="chat-memory-sink", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if isinstance(item, _Record):
                    self._inner.record(item.turn)
                elif isinstance(item, _DeleteThread):
                    item.deleted = self._inner.delete_thread(item.workspace_id, item.thread_id)
                elif isinstance(item, _DeleteWorkspace):
                    item.deleted = self._inner.delete_workspace(item.workspace_id)
            finally:
                if item is not None:
                    item.done.set()
                self._queue.task_done()

    def _submit(self, item: _Work) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            pass

        # Only a write is expendable. Dropping one loses a turn from the
        # archive; dropping a delete leaves rows the caller asked to remove and
        # releases that caller as though it had worked. Nothing already queued
        # is discarded either, because reordering the queue would let a write
        # outlive the delete behind it.
        if isinstance(item, _Record):
            item.done.set()
            self._inner.note_error(item.workspace_id, "queue full, dropped a write")
            return

        try:
            self._queue.put(item, timeout=self._timeout)
        except queue.Full:
            item.done.set()
            self._inner.note_error(
                item.workspace_id, "queue full, gave up waiting to delete"
            )

    def record(self, turn: "PersistedTurn") -> None:
        self._submit(_Record(workspace_id=turn.workspace_id, turn=turn))

    def delete_thread(self, workspace_id: str, thread_id: str) -> int:
        item = _DeleteThread(workspace_id=workspace_id, thread_id=thread_id)
        self._submit(item)
        item.done.wait(self._timeout)
        return item.deleted

    def delete_workspace(self, workspace_id: str) -> int:
        item = _DeleteWorkspace(workspace_id=workspace_id)
        self._submit(item)
        item.done.wait(self._timeout)
        return item.deleted

    def drain_errors(self, workspace_id: str) -> list[str]:
        return self._inner.drain_errors(workspace_id)

    def close(self) -> None:
        if self._closed:
            return
        # Set before queuing the sentinel so nothing new gets in behind it.
        self._closed = True
        try:
            self._queue.put(None, timeout=self._timeout)
        except queue.Full:
            # A worker stalled on a slow archive write must not stall shutdown.
            # It is a daemon thread, so it goes away with the process.
            return
        self._thread.join(timeout=self._timeout)
