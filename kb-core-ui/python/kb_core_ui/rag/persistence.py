"""Workspace-scoped chat thread/turn persistence (T10).

A "thread" is a workspace-scoped conversation; a "turn" is one complete
question/answer exchange. A turn is only ever persisted after
``ChatWorkflow.ask()`` has returned a finished :class:`ChatResponse` --
``ChatHistoryStore.write_turn`` only accepts that already-complete type, so
there is no code path that can persist an incremental/streamed delta as a
complete turn (V10). This keeps T11's later SSE work safe to compose: it can
only ever call ``write_turn`` once it has assembled a full ``ChatResponse``.

This module never opens a second database client -- it is built exclusively
on top of :class:`~kb_core_ui.rag.falkordb_adapter.FalkorDBAdapter`'s own
upsert/delete primitives (``write_chat_turn``, ``list_chat_turns``,
``trim_chat_turns``, ``delete_chat_thread``, ``delete_all_chat_threads``).

Thread identity is always workspace-bound (V11): the storage key mixes the
adapter's ``workspace_id`` with the caller-supplied local thread id, so a
bare caller-supplied id alone can never address another workspace's history.
Because ``FalkorDBAdapter`` also already selects one FalkorDB graph per
workspace (C3), isolation is enforced at two independent layers -- this
module additionally tags every stored thread/turn with an explicit
``workspace_id`` property so isolation holds even against a hypothetical
backend that is not graph-partitioned (defense-in-depth, mirrored by
``FakeChatBackend`` in this module's fake adapter, which is intentionally
*not* partitioned by workspace so tests exercise the key-based isolation
directly).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any, Protocol
from uuid import uuid4

from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.workflow import ChatResponse

_THREAD_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")


class PersistenceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_thread_id(thread_id: str) -> str:
    if not _THREAD_ID.fullmatch(thread_id):
        raise PersistenceError(
            "thread id must start with a lowercase letter or digit and contain only "
            "lowercase letters, digits, hyphens, or underscores (max 128)"
        )
    return thread_id


def thread_key(workspace_id: str, thread_id: str) -> str:
    """Compose the storage identity for a thread.

    Always workspace-bound -- never a bare caller-supplied global id (V11).
    """

    validate_thread_id(thread_id)
    return f"{workspace_id}::{thread_id}"


@dataclass(frozen=True)
class PersistedTurn:
    turn_id: str
    thread_id: str
    workspace_id: str
    seq: int
    query: str
    response: dict[str, Any]
    created_at: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "thread_id": self.thread_id,
            "workspace_id": self.workspace_id,
            "seq": self.seq,
            "query": self.query,
            "response": self.response,
            "created_at": self.created_at,
        }


class ChatThreadAdapter(Protocol):
    """Narrow subset of ``FalkorDBAdapter`` this store depends on. Deliberately
    not a generic write-any-Cypher surface -- only fixed, named operations."""

    workspace_id: str

    def write_chat_turn(
        self,
        thread_key: str,
        thread_id: str,
        turn_id: str,
        query_text: str,
        response_json: str,
        created_at: str,
    ) -> int: ...

    def list_chat_turns(self, thread_key: str) -> list[Any]: ...

    def trim_chat_turns(self, thread_key: str, cutoff_seq: int) -> None: ...

    def delete_chat_thread(self, thread_key: str) -> None: ...

    def delete_all_chat_threads(self) -> int: ...


class ChatHistoryStore:
    """Workspace-scoped chat thread/turn persistence bound to one adapter
    (one FalkorDB graph per workspace -- C3)."""

    def __init__(self, adapter: ChatThreadAdapter, *, config: RagConfig | None = None):
        self.adapter = adapter
        self.max_turns = config.max_thread_turns if config is not None else 0

    def write_turn(self, thread_id: str, query: str, response: ChatResponse) -> PersistedTurn:
        """Atomically append one *complete* turn.

        ``response`` must already be a finished ``ChatResponse`` -- there is
        no incremental/delta write path and no arbitrary dict/kwargs
        acceptance, so a partial streamed answer or a smuggled extra field
        (e.g. a provider secret) structurally cannot enter persisted state.
        """

        if not isinstance(response, ChatResponse):
            raise PersistenceError(
                "write_turn requires a finished ChatResponse instance, not "
                f"{type(response).__name__!r}"
            )
        key = thread_key(self.adapter.workspace_id, thread_id)
        turn_id = uuid4().hex
        created_at = _now()
        response_payload = response.to_json_dict()
        seq = self.adapter.write_chat_turn(
            key,
            thread_id,
            turn_id,
            query,
            json.dumps(response_payload, sort_keys=True, ensure_ascii=False),
            created_at,
        )
        if self.max_turns and seq > self.max_turns:
            self.adapter.trim_chat_turns(key, seq - self.max_turns)
        return PersistedTurn(
            turn_id=turn_id,
            thread_id=thread_id,
            workspace_id=self.adapter.workspace_id,
            seq=seq,
            query=query,
            response=response_payload,
            created_at=created_at,
        )

    def list_turns(self, thread_id: str) -> list[PersistedTurn]:
        key = thread_key(self.adapter.workspace_id, thread_id)
        rows = self.adapter.list_chat_turns(key)
        turns = [
            PersistedTurn(
                turn_id=str(row[0]),
                thread_id=thread_id,
                workspace_id=self.adapter.workspace_id,
                seq=int(row[1]),
                query=str(row[2]),
                response=json.loads(row[3]),
                created_at=str(row[4]),
            )
            for row in rows
        ]
        turns.sort(key=lambda turn: turn.seq)
        return turns

    def delete_thread(self, thread_id: str) -> None:
        key = thread_key(self.adapter.workspace_id, thread_id)
        self.adapter.delete_chat_thread(key)

    def cleanup_workspace(self) -> int:
        """Delete every thread/turn owned by this store's workspace only.

        Never touches another workspace's threads: the adapter this store
        wraps is bound to exactly one workspace (C3).
        """

        return self.adapter.delete_all_chat_threads()


# --------------------------------------------------------------------------- #
# Deterministic fake adapter for tests (no FalkorDB required)
# --------------------------------------------------------------------------- #


class FakeChatBackend:
    """Shared, intentionally workspace-*unpartitioned* in-memory backend.

    Multiple :class:`FakeChatThreadAdapter` instances bound to different
    workspace ids can share one backend to prove that isolation comes from
    the workspace-bound ``thread_key`` itself, not merely from picking a
    different backend/graph per workspace.
    """

    def __init__(self) -> None:
        self.threads: dict[str, dict[str, Any]] = {}
        self.turns: dict[str, list[dict[str, Any]]] = {}


class FakeChatThreadAdapter:
    """Deterministic in-memory :class:`ChatThreadAdapter` used by default
    tests. Mirrors ``FalkorDBAdapter``'s chat persistence semantics without a
    database. No external API key or FalkorDB connection needed."""

    def __init__(self, workspace_id: str, *, backend: FakeChatBackend | None = None):
        self.workspace_id = workspace_id
        self.backend = backend if backend is not None else FakeChatBackend()

    def write_chat_turn(
        self,
        thread_key: str,
        thread_id: str,
        turn_id: str,
        query_text: str,
        response_json: str,
        created_at: str,
    ) -> int:
        thread = self.backend.threads.setdefault(
            thread_key,
            {
                "workspace_id": self.workspace_id,
                "thread_id": thread_id,
                "created_at": created_at,
                "next_seq": 0,
            },
        )
        thread["next_seq"] += 1
        seq = thread["next_seq"]
        self.backend.turns.setdefault(thread_key, []).append(
            {
                "id": turn_id,
                "seq": seq,
                "query": query_text,
                "response_json": response_json,
                "created_at": created_at,
            }
        )
        return seq

    def list_chat_turns(self, thread_key: str) -> list[Any]:
        return [
            (row["id"], row["seq"], row["query"], row["response_json"], row["created_at"])
            for row in self.backend.turns.get(thread_key, [])
        ]

    def trim_chat_turns(self, thread_key: str, cutoff_seq: int) -> None:
        rows = self.backend.turns.get(thread_key, [])
        self.backend.turns[thread_key] = [row for row in rows if row["seq"] > cutoff_seq]

    def delete_chat_thread(self, thread_key: str) -> None:
        self.backend.threads.pop(thread_key, None)
        self.backend.turns.pop(thread_key, None)

    def delete_all_chat_threads(self) -> int:
        owned = [
            key
            for key, meta in self.backend.threads.items()
            if meta["workspace_id"] == self.workspace_id
        ]
        for key in owned:
            self.backend.threads.pop(key, None)
            self.backend.turns.pop(key, None)
        return len(owned)
