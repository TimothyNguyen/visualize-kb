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


@dataclass
class _Work:
    done: threading.Event = field(default_factory=threading.Event)


@dataclass
class _Record(_Work):
    turn: object = None


@dataclass
class _DeleteThread(_Work):
    workspace_id: str = ""
    thread_id: str = ""


@dataclass
class _DeleteWorkspace(_Work):
    workspace_id: str = ""


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
        self._gate = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="chat-memory-sink", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                with self._gate:
                    if isinstance(item, _Record):
                        self._inner.record(item.turn)
                    elif isinstance(item, _DeleteThread):
                        self._inner.delete_thread(item.workspace_id, item.thread_id)
                    elif isinstance(item, _DeleteWorkspace):
                        self._inner.delete_workspace(item.workspace_id)
            finally:
                if item is not None:
                    item.done.set()
                self._queue.task_done()

    def _submit(self, item: _Work) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                dropped = self._queue.get_nowait()
                dropped.done.set()
                self._queue.task_done()
                self._inner.note_error("queue full, dropped the oldest pending write")
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                item.done.set()
                self._inner.note_error("queue full, dropped a write")

    def record(self, turn: "PersistedTurn") -> None:
        self._submit(_Record(turn=turn))

    def delete_thread(self, workspace_id: str, thread_id: str) -> None:
        item = _DeleteThread(workspace_id=workspace_id, thread_id=thread_id)
        self._submit(item)
        item.done.wait(self._timeout)

    def delete_workspace(self, workspace_id: str) -> None:
        item = _DeleteWorkspace(workspace_id=workspace_id)
        self._submit(item)
        item.done.wait(self._timeout)

    def flush(self, timeout: float = 5.0) -> None:
        marker = _Work()
        self._submit(marker)
        marker.done.wait(timeout)

    def pause(self) -> None:
        """Test-only: hold the worker still so the queue can be filled."""

        self._gate.acquire()

    def resume(self) -> None:
        if self._gate.locked():
            self._gate.release()

    def drain_errors(self) -> list[str]:
        return self._inner.drain_errors()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=self._timeout)
