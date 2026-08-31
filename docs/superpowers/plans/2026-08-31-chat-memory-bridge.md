# Chat Memory Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every GraphRAG chat turn is archived into the SQLite memory database as a workspace-scoped, embedded, searchable record, without changing the frozen chat wire contract and without ever blocking or failing a chat response.

**Architecture:** A new `chat_memories` table lives in the existing `memory.db` alongside the frozen `memories` table (Go's `internal/memory/store.go` reads only `memories` and ignores unknown tables). A new `ChatMemoryStore` owns that table and reuses the existing `Embedder` and `cosine` from `kb_core_ui.memory`. A `ChatMemorySink` protocol is injected into `ChatManager` and `WorkspaceManager`; the manager calls `record(...)` next to each existing `write_turn(...)` call and `delete_thread` / `delete_workspace` next to each existing history deletion. Sink failures are captured, drained, and appended to the response's `errors` list — never raised. Three new read/delete routes hang off the existing `handle_rag_workspaces` path table so they vanish automatically when GraphRAG is disabled.

**Tech Stack:** Python 3.11 stdlib (`sqlite3`, `threading`, `queue`, `dataclasses`), numpy (already a dependency via `memory/embedder.py`), the project's hand-rolled `Server` router (no web framework), React 18 + TypeScript + Vitest for the web surface, and the project's Python harness (`kb-core-ui/harness`).

**Spec:** `docs/superpowers/specs/2026-08-31-chat-memory-bridge-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- Browser never connects to FalkorDB or provider APIs directly.
- Every read and write is workspace-scoped server-side.
- User values never become raw graph names, labels, relationships, property names, or Cypher fragments.
- Existing Graph, Bots, Memory, REST, MCP, SQLite, and static `graph.json` paths continue working with GraphRAG disabled.
- Secrets stay server-only and never enter API health payloads, frontend bundles, logs, reports, citations, or persisted checkpoints.
- FalkorDB reference projects inform design only. Do not copy their APIs and do not add either GitHub repository as runtime dependency.
- Never place FalkorDB URL, credentials, or provider keys in Vite environment. Frontend talks only to the backend contract from T11.
- CopilotKit telemetry is disabled; the hosted CopilotKit control plane is out of scope.
- The `memories` table is a byte-level cross-language contract with Go. Do not add, remove, reorder, or retype any of its columns. Do not read or write it from any new code.
- The T11 chat wire shape is frozen. `chat_contract_payload` output keys do not change. `errors` stays a list of strings; `error` stays a string.
- Error strings that reach the wire contain only `exc.__class__.__name__`. Full detail goes to `sys.stderr`, mirroring `memory/embedder.py:HTTPEmbedder`.
- A chat memory write must never block a chat response and must never turn a successful chat turn into a failure.
- New JSON payload keys use snake_case (`created_at`, `workspace_id`, `thread_id`, `turn_id`, `seq`) to match the other RAG surfaces. The global memory surface's `createdAt` is a separate frozen shape; do not change it and do not copy it.

## Per-Task Workflow (non-negotiable, from `docs/CLAUDE-RAG-HANDOFF.md`)

Apply to every task below:

1. Read the task's requirements and the cited spec constraints.
2. Add contract/unit tests first and run them red.
3. Implement through existing boundaries rather than parallel abstractions.
4. Run the affected suites.
5. Commit the task separately. Do not combine tasks into one commit. **Do not push unless explicitly requested.**

Commit message trailer for every commit in this plan:

```
Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
```

## Verification Commands

Windows paths. Run from the repository root unless noted.

```powershell
# Python suite (run from kb-core-ui/python)
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest -q

# Harness unit suite (run from kb-core-ui/harness)
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m pytest -q

# Harness composed workflow, deterministic fake backend (run from kb-core-ui/harness)
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m harness rag --backend fake --report .harness-work/rag/fake.json

# Web
pnpm -C kb-core-ui/web test
pnpm -C kb-core-ui/web lint
pnpm -C kb-core-ui/web build

# Before each commit
git -C "C:\Users\quynh\OneDrive\Desktop\swe-workspace\visualize-kb" diff --check
git -C "C:\Users\quynh\OneDrive\Desktop\swe-workspace\visualize-kb" status --short
```

## Spec Correction (read before Task 4)

The design document's Component 3 says `cleanup_workspace` is "reached from `rag/manager.py:42` `delete_workspace`". That is wrong. `WorkspaceManager.delete_workspace` marks the registry deleting, deletes the FalkorDB graph, and removes the registry entry — it never touches `ChatManager`. Left alone, deleting a workspace would leave its `chat_memories` rows in SQLite, searchable forever. Task 4 corrects this by injecting the same sink into `WorkspaceManager`. This plan supersedes the spec on that point.

## File Structure

**Create:**

- `kb-core-ui/python/kb_core_ui/memory/chat_store.py` — `ChatMemoryEntry`, `ChatMemoryHit`, `ChatMemoryStore`. Owns the `chat_memories` table, its DDL, its lock, and its embedding search. Knows nothing about chat, HTTP, or workspaces beyond the `workspace_id` string it filters on.
- `kb-core-ui/python/kb_core_ui/rag/chat_memory.py` — `ChatMemorySink` protocol, `NullChatMemorySink`, `SyncChatMemorySink`, `ThreadedChatMemorySink`, and the three pure `compose_*` functions. Translates a chat turn into the store's vocabulary and owns the never-raise policy.
- `kb-core-ui/python/tests/test_chat_memory_store.py` — store-level tests.
- `kb-core-ui/python/tests/test_rag_chat_memory_sink.py` — sink-level tests (composition, sync sink, threaded sink).
- `kb-core-ui/python/tests/test_rag_chat_memory_http.py` — route-level tests.

**Modify:**

- `kb-core-ui/python/kb_core_ui/memory/__init__.py` — export the three new names.
- `kb-core-ui/python/kb_core_ui/rag/__init__.py` — export the sink names through the lazy `_OPTIONAL_EXPORTS` map.
- `kb-core-ui/python/kb_core_ui/rag/chat_manager.py` — accept the sink; record at the two `write_turn` sites; drain errors at the two payload sites; forward the two deletions.
- `kb-core-ui/python/kb_core_ui/rag/manager.py` — accept the sink; cascade `delete_workspace`.
- `kb-core-ui/python/kb_core_ui/server/app.py` — accept `chat_memory`; add `_handle_chat_memory` to the `handle_rag_workspaces` path table.
- `kb-core-ui/python/kb_core_ui/cli/root.py` — open the store, build the sink, wire both managers, close on shutdown.
- `kb-core-ui/python/tests/test_rag_chat_manager.py` — sink integration cases.
- `kb-core-ui/python/tests/test_rag_mvp_isolation.py` — cross-workspace chat-memory isolation.
- `kb-core-ui/web/src/api/workspaces.ts` — types plus three functions.
- `kb-core-ui/web/src/api/workspaces.test.ts` — URL/shape assertions.
- `kb-core-ui/web/src/pages/MemoryView.tsx` — a workspace chat-memory section.
- `kb-core-ui/harness/harness/rag_workflow.py` — the `chat_memory_persistence` stage, in `REQUIRED_STAGES` and in `stages`.
- `docs/CLAUDE-RAG-HANDOFF.md` — a result section for this work.

`spec/rag-chatbot-manager-SPEC.md` has no row for this work. Do not add one and do not change its T-table markers; this plan's checkboxes are the markers.

---

### Task 1: ChatMemoryStore

**Files:**
- Create: `kb-core-ui/python/kb_core_ui/memory/chat_store.py`
- Modify: `kb-core-ui/python/kb_core_ui/memory/__init__.py`
- Test: `kb-core-ui/python/tests/test_chat_memory_store.py`

**Interfaces:**
- Consumes: from `kb_core_ui.memory.embedder` — `Embedder` (protocol with `name() -> str`, `dim() -> int`, `embed(text: str) -> np.ndarray`), `HashingEmbedder`, `cosine(a, b) -> float`. From `kb_core_ui.memory.store` — `MIN_SCORE: float = 0.07`, `encode_vec(v) -> bytes`, `decode_vec(b) -> np.ndarray`, `make_id() -> str`, `now() -> str`.
- Produces:
  - `ChatMemoryEntry` dataclass: `id: str`, `workspace_id: str`, `thread_id: str`, `turn_id: str`, `seq: int`, `title: str`, `text: str`, `source: str`, `created_at: str`, with `to_json_dict() -> dict[str, object]` emitting exactly those keys in snake_case.
  - `ChatMemoryHit` dataclass: `entry: ChatMemoryEntry`, `score: float`, with `to_json_dict() -> dict[str, object]` emitting `{"entry": ..., "score": ...}`.
  - `ChatMemoryStore(path: str, embedder: Embedder | None = None)` with methods, every one taking `workspace_id` first:
    - `add(workspace_id, thread_id, turn_id, seq, title, text, at="") -> ChatMemoryEntry | None`
    - `search(workspace_id, query, k=5) -> list[ChatMemoryHit]`
    - `list(workspace_id, thread_id="") -> list[ChatMemoryEntry]`
    - `get(workspace_id, entry_id) -> ChatMemoryEntry | None`
    - `remove(workspace_id, entry_id) -> bool`
    - `delete_thread(workspace_id, thread_id) -> int`
    - `delete_workspace(workspace_id) -> int`
    - `count(workspace_id) -> int`
    - `close() -> None`

- [ ] **Step 1: Read the existing store you are imitating**

Read `kb-core-ui/python/kb_core_ui/memory/store.py` end to end. Note four things you will reuse verbatim: `MIN_SCORE` at line 30, `encode_vec` / `decode_vec` at lines 92-97, `make_id` at line 75, and the `search` loop at lines 165-190 that skips any row whose recorded embedder name differs from the live embedder's name. Do not import `Store` itself and do not touch the `memories` table.

- [ ] **Step 2: Write the failing tests**

Create `kb-core-ui/python/tests/test_chat_memory_store.py`:

```python
"""ChatMemoryStore owns the chat_memories table.

Every assertion here is about isolation or about the frozen memories table
staying untouched -- those are the two ways this store can break the system it
shares a database file with.
"""

from __future__ import annotations

import sqlite3

import pytest

from kb_core_ui.memory import ChatMemoryStore, Store


@pytest.fixture()
def store(tmp_path):
    s = ChatMemoryStore(str(tmp_path / "memory.db"))
    try:
        yield s
    finally:
        s.close()


def _add(store, workspace_id, thread_id="t1", turn_id="turn-1", seq=1, title="q", text="a"):
    return store.add(workspace_id, thread_id, turn_id, seq, title, text)


def test_an_added_entry_comes_back_with_its_identity_intact(store):
    entry = _add(store, "alpha", title="what is the graph", text="the graph is a graph")
    assert entry is not None
    assert entry.workspace_id == "alpha"
    assert entry.thread_id == "t1"
    assert entry.turn_id == "turn-1"
    assert entry.seq == 1
    assert entry.title == "what is the graph"
    assert entry.created_at
    assert store.get("alpha", entry.id) == entry


def test_a_search_returns_only_the_asking_workspaces_rows(store):
    _add(store, "alpha", turn_id="a1", text="alpha knows about parsers")
    _add(store, "beta", turn_id="b1", text="beta knows about parsers")

    hits = store.search("alpha", "parsers", k=10)

    assert hits
    assert {hit.entry.workspace_id for hit in hits} == {"alpha"}


def test_reading_another_workspaces_entry_by_id_returns_nothing(store):
    entry = _add(store, "alpha", turn_id="a1")
    assert entry is not None

    assert store.get("beta", entry.id) is None
    assert store.remove("beta", entry.id) is False
    assert store.get("alpha", entry.id) is not None


def test_the_same_turn_id_recorded_twice_stays_one_row(store):
    first = _add(store, "alpha", turn_id="dupe", text="first")
    second = _add(store, "alpha", turn_id="dupe", text="second")

    assert first is not None and second is not None
    assert store.count("alpha") == 1
    assert store.get("alpha", second.id).text == "second"


def test_the_same_turn_id_in_two_workspaces_stays_two_rows(store):
    _add(store, "alpha", turn_id="shared")
    _add(store, "beta", turn_id="shared")

    assert store.count("alpha") == 1
    assert store.count("beta") == 1


def test_deleting_a_thread_leaves_the_other_thread_and_the_other_workspace(store):
    _add(store, "alpha", thread_id="keep", turn_id="a1")
    _add(store, "alpha", thread_id="drop", turn_id="a2")
    _add(store, "beta", thread_id="drop", turn_id="b1")

    assert store.delete_thread("alpha", "drop") == 1
    assert [e.thread_id for e in store.list("alpha")] == ["keep"]
    assert store.count("beta") == 1


def test_deleting_a_workspace_leaves_the_other_workspace(store):
    _add(store, "alpha", turn_id="a1")
    _add(store, "beta", turn_id="b1")

    assert store.delete_workspace("alpha") == 1
    assert store.count("alpha") == 0
    assert store.count("beta") == 1


def test_listing_is_newest_first_and_filterable_by_thread(store):
    _add(store, "alpha", thread_id="t1", turn_id="a1", seq=1)
    _add(store, "alpha", thread_id="t1", turn_id="a2", seq=2)
    _add(store, "alpha", thread_id="t2", turn_id="a3", seq=1)

    assert [e.turn_id for e in store.list("alpha")] == ["a3", "a2", "a1"]
    assert [e.turn_id for e in store.list("alpha", "t1")] == ["a2", "a1"]


def test_the_frozen_memories_table_is_untouched(tmp_path):
    path = str(tmp_path / "memory.db")
    legacy = Store(path)
    try:
        legacy.add("note", "kept", "kept body", "")
    finally:
        legacy.close()

    chat = ChatMemoryStore(path)
    try:
        chat.add("alpha", "t1", "turn-1", 1, "q", "a")
    finally:
        chat.close()

    conn = sqlite3.connect(path)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"memories", "chat_memories"} <= names
        assert conn.execute("SELECT count(*) FROM memories").fetchone()[0] == 1
    finally:
        conn.close()

    reopened = Store(path)
    try:
        assert [e.title for e in reopened.list()] == ["kept"]
    finally:
        reopened.close()


def test_json_keys_are_snake_case(store):
    entry = _add(store, "alpha")
    assert entry is not None

    payload = entry.to_json_dict()

    assert set(payload) == {
        "id",
        "workspace_id",
        "thread_id",
        "turn_id",
        "seq",
        "title",
        "text",
        "source",
        "created_at",
    }
```

- [ ] **Step 3: Run the tests to verify they fail**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_chat_memory_store.py -q
```

Expected: FAIL with `ImportError: cannot import name 'ChatMemoryStore' from 'kb_core_ui.memory'`.

- [ ] **Step 4: Write the store**

Create `kb-core-ui/python/kb_core_ui/memory/chat_store.py`:

```python
"""Workspace-scoped archive of chat turns.

This table shares memory.db with `memories`, which is a byte-level contract
with the Go reader in internal/memory/store.go. It is a separate table for
exactly that reason: chat rows need a workspace column, and `memories` cannot
grow one. Go ignores tables it does not know about.

Unlike `Store`, this one carries its own lock. `Store` is serialized by the
REST layer's lock in server/app.py, but the threaded sink writes here from a
worker thread that never holds that lock.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass

from .embedder import Embedder, HashingEmbedder, cosine
from .store import MIN_SCORE, decode_vec, encode_vec, make_id, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_memories (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    thread_id    TEXT NOT NULL,
    turn_id      TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    title        TEXT NOT NULL,
    text         TEXT NOT NULL,
    source       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    embedder     TEXT NOT NULL,
    dim          INTEGER NOT NULL,
    embedding    BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_memories_workspace ON chat_memories(workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_memories_turn ON chat_memories(workspace_id, turn_id);
"""

_COLUMNS = (
    "id, workspace_id, thread_id, turn_id, seq, title, text, source, "
    "created_at, embedder, dim, embedding"
)


@dataclass(frozen=True)
class ChatMemoryEntry:
    id: str
    workspace_id: str
    thread_id: str
    turn_id: str
    seq: int
    title: str
    text: str
    source: str
    created_at: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "seq": self.seq,
            "title": self.title,
            "text": self.text,
            "source": self.source,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ChatMemoryHit:
    entry: ChatMemoryEntry
    score: float

    def to_json_dict(self) -> dict[str, object]:
        return {"entry": self.entry.to_json_dict(), "score": self.score}


def _entry(row: tuple) -> ChatMemoryEntry:
    return ChatMemoryEntry(
        id=row[0],
        workspace_id=row[1],
        thread_id=row[2],
        turn_id=row[3],
        seq=int(row[4]),
        title=row[5],
        text=row[6],
        source=row[7],
        created_at=row[8],
    )


class ChatMemoryStore:
    def __init__(self, path: str, embedder: Embedder | None = None):
        self.embedder = embedder or HashingEmbedder()
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def add(
        self,
        workspace_id: str,
        thread_id: str,
        turn_id: str,
        seq: int,
        title: str,
        text: str,
        at: str = "",
    ) -> ChatMemoryEntry | None:
        if not workspace_id or not turn_id:
            return None
        created = at or now()
        source = f"chat://{workspace_id}/{thread_id}/{turn_id}"
        vec = self.embedder.embed(f"{title}\n{text}")
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM chat_memories WHERE workspace_id = ? AND turn_id = ?",
                (workspace_id, turn_id),
            ).fetchone()
            entry_id = row[0] if row else make_id()
            self.conn.execute(
                f"INSERT OR REPLACE INTO chat_memories ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    workspace_id,
                    thread_id,
                    turn_id,
                    int(seq),
                    title,
                    text,
                    source,
                    created,
                    self.embedder.name(),
                    self.embedder.dim(),
                    encode_vec(vec),
                ),
            )
        return ChatMemoryEntry(
            id=entry_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            turn_id=turn_id,
            seq=int(seq),
            title=title,
            text=text,
            source=source,
            created_at=created,
        )

    def get(self, workspace_id: str, entry_id: str) -> ChatMemoryEntry | None:
        with self._lock:
            row = self.conn.execute(
                f"SELECT {_COLUMNS} FROM chat_memories WHERE workspace_id = ? AND id = ?",
                (workspace_id, entry_id),
            ).fetchone()
        return _entry(row) if row else None

    def list(self, workspace_id: str, thread_id: str = "") -> list[ChatMemoryEntry]:
        query = f"SELECT {_COLUMNS} FROM chat_memories WHERE workspace_id = ?"
        params: tuple = (workspace_id,)
        if thread_id:
            query += " AND thread_id = ?"
            params = (workspace_id, thread_id)
        query += " ORDER BY created_at DESC, rowid DESC"
        with self._lock:
            rows = self.conn.execute(query, params).fetchall()
        return [_entry(row) for row in rows]

    def search(self, workspace_id: str, query: str, k: int = 5) -> list[ChatMemoryHit]:
        if not query.strip():
            return []
        needle = self.embedder.embed(query)
        name = self.embedder.name()
        with self._lock:
            rows = self.conn.execute(
                f"SELECT {_COLUMNS} FROM chat_memories WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchall()
        hits: list[ChatMemoryHit] = []
        for row in rows:
            if row[9] != name:
                continue
            score = cosine(needle, decode_vec(row[11]))
            if score < MIN_SCORE:
                continue
            hits.append(ChatMemoryHit(_entry(row), score))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[: max(1, k)]

    def remove(self, workspace_id: str, entry_id: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM chat_memories WHERE workspace_id = ? AND id = ?",
                (workspace_id, entry_id),
            )
        return cur.rowcount > 0

    def delete_thread(self, workspace_id: str, thread_id: str) -> int:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM chat_memories WHERE workspace_id = ? AND thread_id = ?",
                (workspace_id, thread_id),
            )
        return int(cur.rowcount)

    def delete_workspace(self, workspace_id: str) -> int:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM chat_memories WHERE workspace_id = ?",
                (workspace_id,),
            )
        return int(cur.rowcount)

    def count(self, workspace_id: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT count(*) FROM chat_memories WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        return int(row[0])
```

- [ ] **Step 5: Export the new names**

In `kb-core-ui/python/kb_core_ui/memory/__init__.py`, add the import next to the existing `from .store import ...` line and add the three names to `__all__`:

```python
from .chat_store import ChatMemoryEntry, ChatMemoryHit, ChatMemoryStore
```

- [ ] **Step 6: Run the tests to verify they pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_chat_memory_store.py tests/test_memory_store.py -q
```

Expected: PASS. The existing memory suite must stay green — that is the Go-contract check.

- [ ] **Step 7: Commit**

```bash
git add kb-core-ui/python/kb_core_ui/memory/chat_store.py kb-core-ui/python/kb_core_ui/memory/__init__.py kb-core-ui/python/tests/test_chat_memory_store.py
git commit -m "feat(memory): add workspace-scoped chat memory store"
```

---

### Task 2: Sink protocol and synchronous sink

**Files:**
- Create: `kb-core-ui/python/kb_core_ui/rag/chat_memory.py`
- Modify: `kb-core-ui/python/kb_core_ui/rag/__init__.py`
- Test: `kb-core-ui/python/tests/test_rag_chat_memory_sink.py`

**Interfaces:**
- Consumes: `ChatMemoryStore` from Task 1. `PersistedTurn` from `kb_core_ui.rag.persistence` (fields `turn_id`, `thread_id`, `workspace_id`, `seq`, `query`, `response`, `created_at`). `ChatResponse` from `kb_core_ui.rag.workflow` (field `citations: list[dict]`, each with `source_id` and `source_location` keys; field `answer: str`).
- Produces:
  - `TITLE_LIMIT: int = 200`
  - `compose_title(query: str) -> str`
  - `compose_text(answer: str, citations: list[dict]) -> str`
  - `compose_source(workspace_id: str, thread_id: str, turn_id: str) -> str`
  - `ChatMemorySink` — a `typing.Protocol` with `record(turn) -> None`, `delete_thread(workspace_id, thread_id) -> None`, `delete_workspace(workspace_id) -> None`, `drain_errors() -> list[str]`, `close() -> None`.
  - `NullChatMemorySink()` — every method a no-op, `drain_errors()` returns `[]`.
  - `SyncChatMemorySink(store: ChatMemoryStore)` — implements the protocol, catches every `Exception`, and additionally exposes `note_error(message: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `kb-core-ui/python/tests/test_rag_chat_memory_sink.py`:

```python
"""The sink is the layer that is allowed to fail.

Everything below is either about what a turn becomes in the archive, or about
proving that a broken store degrades the response instead of breaking it.
"""

from __future__ import annotations

import pytest

from kb_core_ui.memory import ChatMemoryStore
from kb_core_ui.rag.chat_memory import (
    NullChatMemorySink,
    SyncChatMemorySink,
    compose_source,
    compose_text,
    compose_title,
)
from kb_core_ui.rag.persistence import PersistedTurn
from kb_core_ui.rag.workflow import ChatResponse


def _response(answer="an answer", citations=None):
    return ChatResponse(
        workspace_id="alpha",
        query_id="q1",
        answer=answer,
        citations=citations if citations is not None else [],
        evidence=[],
        degraded=False,
        insufficient_evidence=False,
        strategy="hybrid",
        errors=[],
        timings={},
    )


def _turn(response=None, turn_id="turn-1", thread_id="t1", seq=1, query="a question"):
    return PersistedTurn(
        turn_id=turn_id,
        thread_id=thread_id,
        workspace_id="alpha",
        seq=seq,
        query=query,
        response=response or _response(),
        created_at="2026-08-31T00:00:00Z",
    )


@pytest.fixture()
def store(tmp_path):
    s = ChatMemoryStore(str(tmp_path / "memory.db"))
    try:
        yield s
    finally:
        s.close()


def test_a_long_query_is_truncated_for_the_title():
    assert compose_title("x" * 500) == "x" * 200
    assert compose_title("  spaced  ") == "spaced"


def test_the_text_carries_the_answer_then_one_line_per_citation():
    text = compose_text(
        "the answer",
        [
            {"source_id": "repo", "source_location": "src/a.py:L1"},
            {"source_id": "repo", "source_location": "src/b.py:L2"},
        ],
    )
    assert text.splitlines() == ["the answer", "repo:src/a.py:L1", "repo:src/b.py:L2"]


def test_a_citation_without_a_location_does_not_produce_a_dangling_line():
    assert compose_text("answer", [{"source_id": "repo"}]).splitlines() == ["answer", "repo:"]


def test_the_source_uri_names_the_workspace_thread_and_turn():
    assert compose_source("alpha", "t1", "turn-1") == "chat://alpha/t1/turn-1"


def test_recording_a_turn_puts_it_in_the_store(store):
    sink = SyncChatMemorySink(store)

    sink.record(_turn(_response("the graph is a graph")))

    entries = store.list("alpha")
    assert [e.turn_id for e in entries] == ["turn-1"]
    assert entries[0].title == "a question"
    assert entries[0].text.startswith("the graph is a graph")
    assert sink.drain_errors() == []


def test_a_broken_store_yields_an_error_string_not_an_exception(store):
    sink = SyncChatMemorySink(store)
    store.close()

    sink.record(_turn())

    errors = sink.drain_errors()
    assert len(errors) == 1
    assert errors[0].startswith("chat_memory:")
    assert sink.drain_errors() == []


def test_an_error_string_never_carries_the_exception_detail(store):
    sink = SyncChatMemorySink(store)
    store.close()

    sink.record(_turn())

    message = sink.drain_errors()[0]
    assert "ProgrammingError" in message
    assert "memory.db" not in message
    assert "closed database" not in message


def test_deleting_a_thread_removes_only_that_thread(store):
    sink = SyncChatMemorySink(store)
    sink.record(_turn(turn_id="a1", thread_id="keep"))
    sink.record(_turn(turn_id="a2", thread_id="drop"))

    sink.delete_thread("alpha", "drop")

    assert [e.thread_id for e in store.list("alpha")] == ["keep"]


def test_deleting_a_workspace_empties_it(store):
    sink = SyncChatMemorySink(store)
    sink.record(_turn())

    sink.delete_workspace("alpha")

    assert store.count("alpha") == 0


def test_the_null_sink_accepts_everything_and_reports_nothing():
    sink = NullChatMemorySink()

    sink.record(_turn())
    sink.delete_thread("alpha", "t1")
    sink.delete_workspace("alpha")
    sink.close()

    assert sink.drain_errors() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_memory_sink.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'kb_core_ui.rag.chat_memory'`.

- [ ] **Step 3: Write the sink**

Create `kb-core-ui/python/kb_core_ui/rag/chat_memory.py`:

```python
"""Bridge from a persisted chat turn to the SQLite chat archive.

The archive is best-effort by design: a chat turn that answered correctly must
not be reported as failed because a secondary write did not land. Every failure
here becomes a string in the response's `errors` list instead of an exception.

Those strings reach the browser, so they carry the exception's class name and
nothing else. Detail goes to stderr, the same split memory/embedder.py uses.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from kb_core_ui.memory import ChatMemoryStore

    from .persistence import PersistedTurn

TITLE_LIMIT = 200


def compose_title(query: str) -> str:
    return query.strip()[:TITLE_LIMIT]


def compose_text(answer: str, citations: list[dict]) -> str:
    lines = [answer.strip()]
    for citation in citations:
        source_id = str(citation.get("source_id", ""))
        location = str(citation.get("source_location", ""))
        lines.append(f"{source_id}:{location}")
    return "\n".join(lines)


def compose_source(workspace_id: str, thread_id: str, turn_id: str) -> str:
    return f"chat://{workspace_id}/{thread_id}/{turn_id}"


@runtime_checkable
class ChatMemorySink(Protocol):
    def record(self, turn: "PersistedTurn") -> None: ...

    def delete_thread(self, workspace_id: str, thread_id: str) -> None: ...

    def delete_workspace(self, workspace_id: str) -> None: ...

    def drain_errors(self) -> list[str]: ...

    def close(self) -> None: ...


class NullChatMemorySink:
    """What a server without a memory database injects."""

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
        self.note_error(f"{action} failed ({exc.__class__.__name__})")

    def record(self, turn: "PersistedTurn") -> None:
        try:
            self._store.add(
                turn.workspace_id,
                turn.thread_id,
                turn.turn_id,
                turn.seq,
                compose_title(turn.query),
                compose_text(turn.response.answer, turn.response.citations),
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
        return None
```

Note: `SyncChatMemorySink.close()` does not close the store. The store's owner (the CLI, Task 7) closes it.

- [ ] **Step 4: Export the new names**

In `kb-core-ui/python/kb_core_ui/rag/__init__.py`, add these entries to the `_OPTIONAL_EXPORTS` map and to `__all__`, following the existing entries' exact format:

```python
    "ChatMemorySink": ("kb_core_ui.rag.chat_memory", "ChatMemorySink"),
    "NullChatMemorySink": ("kb_core_ui.rag.chat_memory", "NullChatMemorySink"),
    "SyncChatMemorySink": ("kb_core_ui.rag.chat_memory", "SyncChatMemorySink"),
```

- [ ] **Step 5: Run the tests to verify they pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_memory_sink.py tests/test_rag_optional_dependencies.py -q
```

Expected: PASS. `test_rag_optional_dependencies.py` guards the lazy export map — it must stay green.

- [ ] **Step 6: Commit**

```bash
git add kb-core-ui/python/kb_core_ui/rag/chat_memory.py kb-core-ui/python/kb_core_ui/rag/__init__.py kb-core-ui/python/tests/test_rag_chat_memory_sink.py
git commit -m "feat(rag): add best-effort chat memory sink"
```

---

### Task 3: Wire the sink into ChatManager

**Files:**
- Modify: `kb-core-ui/python/kb_core_ui/rag/chat_manager.py`
- Test: `kb-core-ui/python/tests/test_rag_chat_manager.py`

**Interfaces:**
- Consumes: `ChatMemorySink`, `NullChatMemorySink` from Task 2.
- Produces: `ChatManager(..., chat_memory_sink: ChatMemorySink | None = None)`. When `None`, a `NullChatMemorySink` is used, so every existing caller keeps working unchanged. The manager gains one private helper, `_with_sink_errors(payload: dict) -> dict`.

- [ ] **Step 1: Read the four seams you are editing**

Open `kb-core-ui/python/kb_core_ui/rag/chat_manager.py` and locate:
- `__init__` around line 186 — keyword-only parameters ending in `sleep: Callable[[float], None] = time.sleep`.
- `ask` around line 346 — the `if thread_id: ... write_turn(...)` block, and around line 355 the `payload = chat_contract_payload(...)` / `_cache_query` / `return payload` sequence.
- the streaming method around line 435 — the same `write_turn` under a cancellation guard, and around line 475 the payload/`_cache_query`/`yield SSE_EVENT_COMPLETED, payload` sequence.
- `delete_thread` around line 587 and `delete_all_threads` around line 596.

`write_turn` returns a `PersistedTurn`; today its return value is discarded at both sites. You will bind it.

- [ ] **Step 2: Write the failing tests**

Append to `kb-core-ui/python/tests/test_rag_chat_manager.py`. Reuse that file's existing `_manager` / `_config` / `_registry` helpers; `_manager` already forwards `**kwargs` to `ChatManager`.

```python
class _RecordingSink:
    """Stands in for SyncChatMemorySink so a test can assert on the calls
    without a database. `errors` is what the sink will hand back on drain."""

    def __init__(self, errors=None):
        self.recorded = []
        self.deleted_threads = []
        self.deleted_workspaces = []
        self._errors = list(errors or [])

    def record(self, turn):
        self.recorded.append(turn)

    def delete_thread(self, workspace_id, thread_id):
        self.deleted_threads.append((workspace_id, thread_id))

    def delete_workspace(self, workspace_id):
        self.deleted_workspaces.append(workspace_id)

    def drain_errors(self):
        drained, self._errors = self._errors, []
        return drained

    def close(self):
        return None


class _ExplodingSink(_RecordingSink):
    def record(self, turn):
        raise RuntimeError("sink is broken")


def test_asking_with_a_thread_records_the_turn_in_the_sink(tmp_path):
    sink = _RecordingSink()
    manager = _manager(tmp_path, chat_memory_sink=sink)

    manager.ask("alpha", "a question", thread_id="t1")

    assert [turn.thread_id for turn in sink.recorded] == ["t1"]
    assert sink.recorded[0].query == "a question"


def test_asking_without_a_thread_records_nothing(tmp_path):
    sink = _RecordingSink()
    manager = _manager(tmp_path, chat_memory_sink=sink)

    manager.ask("alpha", "a question")

    assert sink.recorded == []


def test_a_sink_error_rides_out_on_the_response_errors_list(tmp_path):
    sink = _RecordingSink(errors=["chat_memory: record failed (OperationalError)"])
    manager = _manager(tmp_path, chat_memory_sink=sink)

    payload = manager.ask("alpha", "a question", thread_id="t1")

    assert "chat_memory: record failed (OperationalError)" in payload["errors"]
    assert payload["answer"]


def test_a_sink_that_raises_does_not_break_the_answer(tmp_path):
    manager = _manager(tmp_path, chat_memory_sink=_ExplodingSink())

    payload = manager.ask("alpha", "a question", thread_id="t1")

    assert payload["answer"]
    assert any("chat_memory" in error for error in payload["errors"])


def test_the_wire_shape_does_not_change_when_a_sink_is_attached(tmp_path):
    without = _manager(tmp_path / "a").ask("alpha", "a question", thread_id="t1")
    with_sink = _manager(tmp_path / "b", chat_memory_sink=_RecordingSink()).ask(
        "alpha", "a question", thread_id="t1"
    )

    assert set(without) == set(with_sink)


def test_streaming_a_turn_records_it_once(tmp_path):
    sink = _RecordingSink()
    manager = _manager(tmp_path, chat_memory_sink=sink)

    events = list(manager.stream("alpha", "a question", thread_id="t1"))

    assert len(sink.recorded) == 1
    completed = [payload for name, payload in events if name == SSE_EVENT_COMPLETED]
    assert completed


def test_deleting_a_thread_reaches_the_sink(tmp_path):
    sink = _RecordingSink()
    manager = _manager(tmp_path, chat_memory_sink=sink)
    manager.ask("alpha", "a question", thread_id="t1")

    manager.delete_thread("alpha", "t1")

    assert sink.deleted_threads == [("alpha", "t1")]


def test_deleting_all_threads_reaches_the_sink_as_a_workspace_delete(tmp_path):
    sink = _RecordingSink()
    manager = _manager(tmp_path, chat_memory_sink=sink)

    manager.delete_all_threads("alpha")

    assert sink.deleted_workspaces == ["alpha"]
```

If `SSE_EVENT_COMPLETED` and `stream` are not already imported/used in that test file, import `SSE_EVENT_COMPLETED` from `kb_core_ui.rag.chat_manager` and check the real streaming method's name before writing the call.

- [ ] **Step 3: Run the tests to verify they fail**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_manager.py -q -k sink
```

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'chat_memory_sink'`.

- [ ] **Step 4: Accept the sink in `__init__`**

Add the parameter to the keyword-only block, after `sleep`:

```python
        chat_memory_sink: "ChatMemorySink | None" = None,
```

and in the body:

```python
        self.chat_memory_sink = chat_memory_sink or NullChatMemorySink()
```

Import at module top:

```python
from .chat_memory import ChatMemorySink, NullChatMemorySink
```

- [ ] **Step 5: Add the record helper and the drain helper**

Add both as private methods on `ChatManager`:

```python
    def _record_memory(self, turn) -> None:
        try:
            self.chat_memory_sink.record(turn)
        except Exception as exc:  # a sink must never break a turn
            print(f"chat memory sink raised: {exc}", file=sys.stderr)
            self._sink_errors.append(f"chat_memory: record failed ({exc.__class__.__name__})")

    def _with_sink_errors(self, payload: dict) -> dict:
        drained = self._sink_errors + list(self.chat_memory_sink.drain_errors())
        self._sink_errors = []
        if drained:
            payload["errors"] = list(payload.get("errors", ())) + drained
        return payload
```

Initialize `self._sink_errors: list[str] = []` in `__init__` and add `import sys` at the top if it is not already there.

`_with_sink_errors` builds a NEW list. Do not mutate `response.errors` in place — that list belongs to the workflow.

- [ ] **Step 6: Record at both write sites**

In `ask`, change the write block to bind the returned turn:

```python
            if thread_id:
                turn = self.history_store_factory(adapter).write_turn(thread_id, query, response)
                self._record_memory(turn)
            return response
```

In the streaming method, do the same under the existing cancellation guard:

```python
                    if (
                        thread_id
                        and not self._is_cancelled(qid)
                        and response.answer != CANCELLED_TEXT
                    ):
                        turn = self.history_store_factory(adapter).write_turn(
                            thread_id, query, response
                        )
                        self._record_memory(turn)
```

- [ ] **Step 7: Drain at both payload sites**

In `ask`:

```python
        payload = self._with_sink_errors(chat_contract_payload(response.to_json_dict()))
```

In the streaming method, apply the same wrapper to the payload built before `yield SSE_EVENT_COMPLETED, payload`. Both keep their existing `self._cache_query(qid, workspace_id, payload)` call, unchanged and after the wrapper.

- [ ] **Step 8: Forward both deletions**

In `delete_thread`, after the existing history-store call:

```python
        self.chat_memory_sink.delete_thread(workspace_id, thread_id)
```

In `delete_all_threads`, after the existing `cleanup_workspace` call:

```python
        self.chat_memory_sink.delete_workspace(workspace_id)
```

Both go after the primary deletion, inside the same method, before the return.

- [ ] **Step 9: Run the tests to verify they pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_manager.py tests/test_rag_chat_http.py -q
```

Expected: PASS, including every pre-existing case in both files. `test_rag_chat_http.py` is the frozen-contract guard.

- [ ] **Step 10: Commit**

```bash
git add kb-core-ui/python/kb_core_ui/rag/chat_manager.py kb-core-ui/python/tests/test_rag_chat_manager.py
git commit -m "feat(rag): archive chat turns through the memory sink"
```

---

### Task 4: Cascade workspace deletion (spec correction)

**Files:**
- Modify: `kb-core-ui/python/kb_core_ui/rag/manager.py:17-46`
- Test: `kb-core-ui/python/tests/test_rag_workspace_manager.py`

**Why:** `WorkspaceManager.delete_workspace` marks the registry deleting, deletes the FalkorDB graph, and removes the registry entry. It never reaches `ChatManager`, so `ChatManager.delete_all_threads` is not on that path. Without this task, deleting a workspace leaves its `chat_memories` rows in SQLite, searchable forever, violating the workspace-scoping invariant.

**Interfaces:**
- Consumes: `ChatMemorySink` from Task 2.
- Produces: `WorkspaceManager(registry, config, *, adapter_factory=None, ingestion_coordinator=None, max_context_records=200, chat_memory_sink: ChatMemorySink | None = None)`.

- [ ] **Step 1: Write the failing test**

Add to `kb-core-ui/python/tests/test_rag_workspace_manager.py` (if that file does not exist, create it and copy the `_registry` / `_config` helpers from `tests/test_rag_chat_manager.py`):

```python
def test_deleting_a_workspace_also_clears_its_chat_memories(tmp_path):
    sink = _RecordingSink()
    manager = _workspace_manager(tmp_path, chat_memory_sink=sink)

    manager.delete_workspace("alpha")

    assert sink.deleted_workspaces == ["alpha"]


def test_a_sink_that_raises_does_not_block_workspace_deletion(tmp_path):
    class _Exploding(_RecordingSink):
        def delete_workspace(self, workspace_id):
            raise RuntimeError("sink is broken")

    manager = _workspace_manager(tmp_path, chat_memory_sink=_Exploding())

    result = manager.delete_workspace("alpha")

    assert result["deleted"] is True
```

Define `_RecordingSink` in this file the same way Task 3 defined it, or import it if the suite already shares a conftest helper. Define `_workspace_manager(tmp_path, **kwargs)` to build a `WorkspaceRegistry` in `tmp_path`, create workspace `alpha`, and return `WorkspaceManager(registry, config, adapter_factory=_FakeAdapter, **kwargs)`.

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_workspace_manager.py -q -k memories
```

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'chat_memory_sink'`.

- [ ] **Step 3: Accept the sink and cascade**

In `kb-core-ui/python/kb_core_ui/rag/manager.py`, add to the keyword-only parameters of `__init__`:

```python
        chat_memory_sink: "ChatMemorySink | None" = None,
```

and in the body:

```python
        self.chat_memory_sink = chat_memory_sink or NullChatMemorySink()
```

Then change `delete_workspace`:

```python
    def delete_workspace(self, workspace_id: str) -> dict[str, object]:
        self.registry.mark_deleting(workspace_id)
        self._with_adapter(workspace_id, lambda adapter: adapter.delete_graph())
        self.registry.remove_workspace(workspace_id)
        self.chat_memory_sink.delete_workspace(workspace_id)
        return {"workspace_id": workspace_id, "deleted": True}
```

The sink's own `delete_workspace` already swallows store failures. It cannot swallow a sink that is itself broken, so guard the call:

```python
        try:
            self.chat_memory_sink.delete_workspace(workspace_id)
        except Exception as exc:  # archive cleanup must not block deletion
            print(f"chat memory workspace cleanup raised: {exc}", file=sys.stderr)
```

Add `import sys` and the `from .chat_memory import ChatMemorySink, NullChatMemorySink` import at the top.

- [ ] **Step 4: Run the tests to verify they pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_workspace_manager.py tests/test_rag_workspaces.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kb-core-ui/python/kb_core_ui/rag/manager.py kb-core-ui/python/tests/test_rag_workspace_manager.py
git commit -m "fix(rag): clear chat memories when a workspace is deleted"
```

---

### Task 5: Threaded sink

**Files:**
- Modify: `kb-core-ui/python/kb_core_ui/rag/chat_memory.py`
- Modify: `kb-core-ui/python/kb_core_ui/rag/__init__.py`
- Test: `kb-core-ui/python/tests/test_rag_chat_memory_sink.py`

**Why:** `record` embeds text. With `HTTPEmbedder` configured, that is a network call with a 30-second timeout sitting on the request thread of a chat turn that has already produced its answer. The threaded sink moves it off that thread.

**Interfaces:**
- Consumes: `SyncChatMemorySink` from Task 2.
- Produces: `ThreadedChatMemorySink(inner: SyncChatMemorySink, *, maxsize: int = 256, timeout: float = 5.0)` implementing `ChatMemorySink`. Deletes block until the worker has drained past them, up to `timeout`. `record` never blocks. Queue overflow drops the oldest queued record and reports it through `inner.note_error`.

- [ ] **Step 1: Write the failing tests**

Append to `kb-core-ui/python/tests/test_rag_chat_memory_sink.py`:

```python
def test_a_recorded_turn_lands_in_the_store_without_the_caller_waiting(store):
    sink = ThreadedChatMemorySink(SyncChatMemorySink(store))
    try:
        sink.record(_turn())
        sink.flush(timeout=5.0)
    finally:
        sink.close()

    assert store.count("alpha") == 1


def test_a_delete_queued_after_a_write_wins(store):
    """FIFO ordering is the whole guarantee: a queued write must not land after
    the delete that was meant to remove it."""

    sink = ThreadedChatMemorySink(SyncChatMemorySink(store))
    try:
        sink.record(_turn(turn_id="a1"))
        sink.record(_turn(turn_id="a2"))
        sink.delete_workspace("alpha")
    finally:
        sink.close()

    assert store.count("alpha") == 0


def test_deleting_a_thread_waits_for_the_worker(store):
    sink = ThreadedChatMemorySink(SyncChatMemorySink(store))
    try:
        sink.record(_turn(turn_id="a1", thread_id="drop"))
        sink.delete_thread("alpha", "drop")

        assert store.count("alpha") == 0
    finally:
        sink.close()


def test_store_errors_from_the_worker_surface_on_a_later_drain(store):
    sink = ThreadedChatMemorySink(SyncChatMemorySink(store))
    try:
        store.close()
        sink.record(_turn())
        sink.flush(timeout=5.0)

        errors = sink.drain_errors()
    finally:
        sink.close()

    assert any(error.startswith("chat_memory:") for error in errors)


def test_a_full_queue_drops_the_oldest_and_says_so(store):
    sink = ThreadedChatMemorySink(SyncChatMemorySink(store), maxsize=1)
    sink.pause()
    try:
        sink.record(_turn(turn_id="a1"))
        sink.record(_turn(turn_id="a2"))
        sink.record(_turn(turn_id="a3"))
    finally:
        sink.resume()
        sink.close()

    assert any("dropped" in error for error in sink.drain_errors())
    assert store.count("alpha") <= 2


def test_closing_twice_is_safe(store):
    sink = ThreadedChatMemorySink(SyncChatMemorySink(store))
    sink.close()
    sink.close()
```

Add `ThreadedChatMemorySink` to the imports at the top of the file.

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_memory_sink.py -q -k "worker or queue or closing"
```

Expected: FAIL with `ImportError: cannot import name 'ThreadedChatMemorySink'`.

- [ ] **Step 3: Write the threaded sink**

Append to `kb-core-ui/python/kb_core_ui/rag/chat_memory.py`:

```python
import queue
import threading
from dataclasses import dataclass, field


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
        self._thread = threading.Thread(
            target=self._run, name="chat-memory-sink", daemon=True
        )
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
```

`_Work` with no subclass is the flush and pause markers' type; the worker's `isinstance` chain falls through it and only sets `done`. `pause` / `resume` exist so a test can hold the worker still while it fills the queue; nothing in production calls them.

- [ ] **Step 4: Export the name**

In `kb-core-ui/python/kb_core_ui/rag/__init__.py`, add to `_OPTIONAL_EXPORTS` and `__all__`:

```python
    "ThreadedChatMemorySink": ("kb_core_ui.rag.chat_memory", "ThreadedChatMemorySink"),
```

- [ ] **Step 5: Run the tests to verify they pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_memory_sink.py -q
```

Expected: PASS, all cases including Task 2's.

- [ ] **Step 6: Commit**

```bash
git add kb-core-ui/python/kb_core_ui/rag/chat_memory.py kb-core-ui/python/kb_core_ui/rag/__init__.py kb-core-ui/python/tests/test_rag_chat_memory_sink.py
git commit -m "feat(rag): move chat memory writes off the request thread"
```

---

### Task 6: HTTP routes

**Files:**
- Modify: `kb-core-ui/python/kb_core_ui/server/app.py`
- Test: `kb-core-ui/python/tests/test_rag_chat_memory_http.py`

**Interfaces:**
- Consumes: `ChatMemoryStore` from Task 1.
- Produces: `Server(store, repo_root, web_dir="", runner=None, memory=None, workspace_manager=None, chat_manager=None, chat_memory=None)` and three routes:
  - `GET  /api/rag/workspaces/{workspace_id}/memory` — optional `thread` query parameter. Returns `{"workspace_id": ..., "entries": [<ChatMemoryEntry.to_json_dict()>]}`.
  - `GET  /api/rag/workspaces/{workspace_id}/memory/search?q=...&top=5` — returns `{"workspace_id": ..., "hits": [<ChatMemoryHit.to_json_dict()>]}`.
  - `DELETE /api/rag/workspaces/{workspace_id}/memory` — optional `thread` query parameter. Deletes that thread, or the whole workspace when `thread` is absent. Returns `{"workspace_id": ..., "deleted": <int>}`.

  All three return 404 when `chat_memory` is `None` or when the workspace is unknown to the registry.

- [ ] **Step 1: Read the dispatch you are extending**

Open `kb-core-ui/python/kb_core_ui/server/app.py` and read `handle_rag_workspaces` (around lines 401-478). Note the `parts` split, the line

```python
        if len(parts) >= 2 and parts[1] == "chat":
            return self._handle_chat(req, workspace_id, parts[2:])
```

and the shared exception mapping at the end of the method. Read the existing memory handlers around lines 324-387 for the `_atoi` and `write_error` idioms. New routes go into this path table — not into the mux.

- [ ] **Step 2: Write the failing tests**

Create `kb-core-ui/python/tests/test_rag_chat_memory_http.py`:

```python
"""The chat memory routes.

Two things are load-bearing here: the routes are workspace-scoped on the
server, and they do not exist at all when GraphRAG is off.
"""

from __future__ import annotations

import json

from kb_core_ui.memory import ChatMemoryStore
from kb_core_ui.rag import ChatManager, RagConfig, SyncChatMemorySink, WorkspaceRegistry
from kb_core_ui.server import Server
from kb_core_ui.store import Store

from test_server import request


def _app(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    for workspace_id, name in (("alpha", "Alpha"), ("beta", "Beta")):
        registry.create(workspace_id, name)
    config = RagConfig.from_env(
        {
            "RAG_ENABLE": "true",
            "FALKORDB_URL": "falkor://fake:6379",
            "RAG_LLM_PROVIDER": "harness-fake",
            "RAG_LLM_MODEL": "harness-fake",
            "RAG_EMBEDDING_MODEL": "harness-fake",
        }
    )
    chat_memory = ChatMemoryStore(str(tmp_path / "memory.db"))
    chat_memory.add("alpha", "t1", "turn-1", 1, "alpha question", "alpha answer about parsers")
    chat_memory.add("alpha", "t2", "turn-2", 1, "second question", "second answer")
    chat_memory.add("beta", "t1", "turn-3", 1, "beta question", "beta answer about parsers")

    store = Store(str(tmp_path / "graph.db"))
    workspace_manager = type("WM", (), {"registry": registry, "config": config})()
    chat_manager = ChatManager(
        registry, config, chat_memory_sink=SyncChatMemorySink(chat_memory)
    )
    app = Server(
        store,
        str(tmp_path),
        workspace_manager=workspace_manager,
        chat_manager=chat_manager,
        chat_memory=chat_memory,
    )
    return app, store, chat_memory


def test_listing_returns_only_this_workspaces_entries(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "GET", "/api/rag/workspaces/alpha/memory")

        assert status == 200
        assert body["workspace_id"] == "alpha"
        assert {entry["turn_id"] for entry in body["entries"]} == {"turn-1", "turn-2"}
    finally:
        memory.close()
        store.close()


def test_listing_can_be_narrowed_to_one_thread(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "GET", "/api/rag/workspaces/alpha/memory?thread=t2")

        assert status == 200
        assert [entry["turn_id"] for entry in body["entries"]] == ["turn-2"]
    finally:
        memory.close()
        store.close()


def test_search_never_crosses_a_workspace_boundary(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(
            app, "GET", "/api/rag/workspaces/alpha/memory/search?q=parsers&top=10"
        )

        assert status == 200
        assert body["hits"]
        assert {hit["entry"]["workspace_id"] for hit in body["hits"]} == {"alpha"}
        assert "beta answer" not in json.dumps(body)
    finally:
        memory.close()
        store.close()


def test_deleting_a_thread_leaves_the_rest(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "DELETE", "/api/rag/workspaces/alpha/memory?thread=t1")

        assert status == 200
        assert body["deleted"] == 1
        assert memory.count("alpha") == 1
        assert memory.count("beta") == 1
    finally:
        memory.close()
        store.close()


def test_deleting_without_a_thread_empties_the_workspace_only(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "DELETE", "/api/rag/workspaces/alpha/memory")

        assert status == 200
        assert body["deleted"] == 2
        assert memory.count("alpha") == 0
        assert memory.count("beta") == 1
    finally:
        memory.close()
        store.close()


def test_an_unknown_workspace_is_refused(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        assert request(app, "GET", "/api/rag/workspaces/gamma/memory")[0] == 404
        assert request(app, "GET", "/api/rag/workspaces/gamma/memory/search?q=x")[0] == 404
        assert request(app, "DELETE", "/api/rag/workspaces/gamma/memory")[0] == 404
    finally:
        memory.close()
        store.close()


def test_a_server_without_chat_memory_hides_the_routes(tmp_path):
    """No web_dir: the SPA fallback would answer 200 and hide this."""

    store = Store(str(tmp_path / "graph.db"))
    try:
        app = Server(store, str(tmp_path))

        assert request(app, "GET", "/api/rag/workspaces/alpha/memory")[0] == 404
        assert request(app, "GET", "/api/rag/workspaces/alpha/memory/search?q=x")[0] == 404
    finally:
        store.close()
```

- [ ] **Step 3: Run the tests to verify they fail**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_memory_http.py -q
```

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'chat_memory'`.

- [ ] **Step 4: Accept the store on the Server**

Add `chat_memory=None` to `Server.__init__`'s signature after `chat_manager=None`, and `self.chat_memory = chat_memory` in the body.

- [ ] **Step 5: Add the dispatch**

In `handle_rag_workspaces`, directly after the `chat` dispatch line:

```python
        if len(parts) >= 2 and parts[1] == "memory":
            return self._handle_chat_memory(req, workspace_id, parts[2:])
```

The workspace-existence check that already guards the surrounding method covers these routes; do not add a second one. The shared exception mapping at the end of the method covers them too.

- [ ] **Step 6: Add the handler**

Add next to `_handle_chat`:

```python
    def _handle_chat_memory(self, req, workspace_id: str, sub: list[str]):
        memory = self.chat_memory
        if memory is None:
            return write_error(404, "not found")
        leaf = sub[0] if sub else ""

        if leaf == "" and req.method == "GET":
            thread = req.query.get("thread", "")
            entries = memory.list(workspace_id, thread)
            return write_json(
                200,
                {
                    "workspace_id": workspace_id,
                    "entries": [entry.to_json_dict() for entry in entries],
                },
            )

        if leaf == "" and req.method == "DELETE":
            thread = req.query.get("thread", "")
            if thread:
                deleted = memory.delete_thread(workspace_id, thread)
            else:
                deleted = memory.delete_workspace(workspace_id)
            return write_json(200, {"workspace_id": workspace_id, "deleted": deleted})

        if leaf == "search" and req.method == "GET":
            query = req.query.get("q", "")
            top = _atoi(req.query.get("top", "")) or 5
            hits = memory.search(workspace_id, query, top)
            return write_json(
                200,
                {"workspace_id": workspace_id, "hits": [hit.to_json_dict() for hit in hits]},
            )

        return write_error(404, "not found")
```

Match the surrounding code exactly for how a request's method, query parameters, and JSON response are actually accessed — read a neighboring handler first and copy its idiom rather than the shapes sketched above (`req.query.get`, `write_json`) if they differ.

- [ ] **Step 7: Run the tests to verify they pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_chat_memory_http.py tests/test_server.py tests/test_rag_chat_http.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add kb-core-ui/python/kb_core_ui/server/app.py kb-core-ui/python/tests/test_rag_chat_memory_http.py
git commit -m "feat(server): expose workspace chat memory routes"
```

---

### Task 7: CLI wiring

**Files:**
- Modify: `kb-core-ui/python/kb_core_ui/cli/root.py:172-174, 434-480, 683-705`
- Test: `kb-core-ui/python/tests/test_cli_serve.py`

**Interfaces:**
- Consumes: `ChatMemoryStore` (Task 1), `SyncChatMemorySink` / `ThreadedChatMemorySink` (Tasks 2 and 5).
- Produces:
  - `open_chat_memory(repo_root: str) -> ChatMemoryStore` — mirrors `open_memory`: `ensure_db_dir(repo_root)` then `ChatMemoryStore(memory_db_path(repo_root))`. Same file as the global memory store, different table.
  - `_default_workspace_manager(repo_root: str, chat_memory_sink=None) -> WorkspaceManager` — the new parameter defaults to `None` so `_workspace_leaf`'s single-positional-argument call at line ~700 keeps working unchanged.

- [ ] **Step 1: Write the failing test**

Add to `kb-core-ui/python/tests/test_cli_serve.py` (create it with the suite's existing CLI helpers if absent):

```python
def test_serving_shares_one_memory_file_between_both_stores(tmp_path):
    from kb_core_ui.cli.root import open_chat_memory, open_memory

    memory = open_memory(str(tmp_path))
    chat_memory = open_chat_memory(str(tmp_path))
    try:
        memory.add("note", "kept", "kept body", "")
        chat_memory.add("alpha", "t1", "turn-1", 1, "q", "a")

        assert [entry.title for entry in memory.list()] == ["kept"]
        assert chat_memory.count("alpha") == 1
    finally:
        chat_memory.close()
        memory.close()


def test_the_default_workspace_manager_still_takes_one_argument(tmp_path):
    from kb_core_ui.cli.root import _default_workspace_manager

    manager = _default_workspace_manager(str(tmp_path))

    assert manager.chat_memory_sink is not None
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_cli_serve.py -q
```

Expected: FAIL with `ImportError: cannot import name 'open_chat_memory'`.

- [ ] **Step 3: Add the opener**

Next to `open_memory` around line 172:

```python
def open_chat_memory(repo_root: str) -> ChatMemoryStore:
    ensure_db_dir(repo_root)
    return ChatMemoryStore(memory_db_path(repo_root))
```

Import `ChatMemoryStore` alongside the existing `MemoryStore` import.

- [ ] **Step 4: Thread the sink through the workspace manager factory**

```python
def _default_workspace_manager(repo_root: str, chat_memory_sink=None) -> WorkspaceManager:
    registry = WorkspaceRegistry(workspace_registry_path(repo_root))
    config = RagConfig.from_env(os.environ)
    coordinator = None
    if config.enabled:
        from kb_core_ui.rag.coordinator import IngestionCoordinator

        coordinator = IngestionCoordinator.for_config(registry, config)
    return WorkspaceManager(
        registry,
        config,
        ingestion_coordinator=coordinator,
        chat_memory_sink=chat_memory_sink,
    )
```

- [ ] **Step 5: Wire `_run_serve`**

In `_run_serve` (around lines 434-480), open the chat memory store next to the existing memory store, build one sink, and pass it to all three consumers:

```python
    chat_memory = open_chat_memory(repo_root)
    chat_memory_sink = ThreadedChatMemorySink(SyncChatMemorySink(chat_memory))
```

Pass `chat_memory_sink=chat_memory_sink` into the `ChatManager(...)` construction (around line 459) and into the `_default_workspace_manager(...)` call. Pass `chat_memory=chat_memory` into `Server(...)`.

Extend the existing `finally` block, closing the sink before the store it writes to:

```python
    finally:
        chat_memory_sink.close()
        chat_memory.close()
        if memory is not None:
            memory.close()
        store.close()
```

- [ ] **Step 6: Run the tests to verify they pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest -q
```

Expected: PASS, the whole Python suite.

- [ ] **Step 7: Commit**

```bash
git add kb-core-ui/python/kb_core_ui/cli/root.py kb-core-ui/python/tests/test_cli_serve.py
git commit -m "feat(cli): open the chat memory store when serving"
```

---

### Task 8: Composed isolation sweep

**Files:**
- Modify: `kb-core-ui/python/tests/test_rag_mvp_isolation.py`

**Why:** Tasks 1 and 6 each prove workspace scoping in isolation. This file exists to catch leaks that only appear in the wiring — two live workspaces, one server, one chat manager, one history backend. Now also one chat memory database.

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: no new production interface. Extends `_app(tmp_path)` in the test file to return the chat memory store as a third element.

- [ ] **Step 1: Write the failing tests**

In `kb-core-ui/python/tests/test_rag_mvp_isolation.py`, extend `_app` so both workspaces share one `ChatMemoryStore` and one sink, then return it:

```python
def _app(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    for workspace_id, name in (("alpha", "Alpha"), ("beta", "Beta")):
        registry.create(workspace_id, name)
        registry.add_source(
            workspace_id, f"{workspace_id}-repo", "local_repo", f"fixture://{workspace_id}"
        )
    config = _config()
    backend = FakeChatBackend()

    def history_store_factory(adapter: _ScopedAdapter) -> ChatHistoryStore:
        return ChatHistoryStore(
            FakeChatThreadAdapter(adapter.workspace_id, backend=backend), config=config
        )

    # One store and one sink for both workspaces: if a row were not scoped,
    # alpha's turns would surface in beta's search here.
    chat_memory = ChatMemoryStore(str(tmp_path / "memory.db"))
    chat_manager = ChatManager(
        registry,
        config,
        adapter_factory=_ScopedAdapter,
        history_store_factory=history_store_factory,
        chat_memory_sink=SyncChatMemorySink(chat_memory),
    )
    store = Store(str(tmp_path / "graph.db"))
    workspace_manager = type("WM", (), {"registry": registry, "config": config})()
    app = Server(
        store,
        str(tmp_path),
        workspace_manager=workspace_manager,
        chat_manager=chat_manager,
        chat_memory=chat_memory,
    )
    return app, store, chat_memory
```

Update every existing test's unpacking from `app, store = _app(tmp_path)` to `app, store, chat_memory = _app(tmp_path)` and add `chat_memory.close()` to each `finally` before `store.close()`. Import `ChatMemoryStore` from `kb_core_ui.memory` and `SyncChatMemorySink` from `kb_core_ui.rag`.

Then append:

```python
def test_a_chat_turn_becomes_a_searchable_memory_in_its_own_workspace(tmp_path):
    app, store, chat_memory = _app(tmp_path)
    try:
        _ask(app, "alpha", thread_id="t1", query="what owns the graph records")

        status, body, _ = request(
            app, "GET", "/api/rag/workspaces/alpha/memory/search?q=graph%20records&top=10"
        )

        assert status == 200
        assert body["hits"]
        assert {hit["entry"]["workspace_id"] for hit in body["hits"]} == {"alpha"}
    finally:
        chat_memory.close()
        store.close()


def test_one_workspaces_memory_search_never_returns_the_others_turn(tmp_path):
    app, store, chat_memory = _app(tmp_path)
    try:
        _ask(app, "alpha", thread_id="t1", query="alpha question about graph records")
        _ask(app, "beta", thread_id="t1", query="beta question about graph records")

        alpha = request(app, "GET", "/api/rag/workspaces/alpha/memory")[1]
        beta = request(app, "GET", "/api/rag/workspaces/beta/memory")[1]

        assert [entry["title"] for entry in alpha["entries"]] == [
            "alpha question about graph records"
        ]
        assert "beta question" not in json.dumps(alpha)
        assert "alpha question" not in json.dumps(beta)
    finally:
        chat_memory.close()
        store.close()


def test_deleting_a_thread_clears_its_memories_and_leaves_the_other_workspace(tmp_path):
    app, store, chat_memory = _app(tmp_path)
    try:
        _ask(app, "alpha", thread_id="shared", query="alpha question")
        _ask(app, "beta", thread_id="shared", query="beta question")

        assert request(app, "DELETE", "/api/rag/workspaces/alpha/chat/threads/shared")[0] == 200

        assert chat_memory.count("alpha") == 0
        assert chat_memory.count("beta") == 1
    finally:
        chat_memory.close()
        store.close()
```

Also extend `test_disabled_rag_keeps_the_base_ui_and_hides_every_rag_route`'s 404 list with the two new paths:

```python
            "/api/rag/workspaces/alpha/memory",
            "/api/rag/workspaces/alpha/memory/search?q=x",
```

- [ ] **Step 2: Run the tests to verify they fail, then pass**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_mvp_isolation.py -q
```

Expected first: FAIL on the three new cases. If Tasks 1-7 are complete, they should pass without any production change; if one fails, the leak is in the wiring, which is exactly what this file is for. Fix the wiring, not the test.

- [ ] **Step 3: Commit**

```bash
git add kb-core-ui/python/tests/test_rag_mvp_isolation.py
git commit -m "test(rag): cover chat memory in the isolation sweep"
```

---

### Task 9: Web surface

**Files:**
- Modify: `kb-core-ui/web/src/api/workspaces.ts`
- Modify: `kb-core-ui/web/src/api/workspaces.test.ts`
- Modify: `kb-core-ui/web/src/pages/MemoryView.tsx`

**Interfaces:**
- Consumes: the three routes from Task 6.
- Produces, in `workspaces.ts`:
  ```ts
  export interface ChatMemoryEntry {
    id: string;
    workspace_id: string;
    thread_id: string;
    turn_id: string;
    seq: number;
    title: string;
    text: string;
    source: string;
    created_at: string;
  }

  export interface ChatMemoryHit {
    entry: ChatMemoryEntry;
    score: number;
  }

  export function listChatMemories(workspaceId: string, threadId?: string): Promise<ChatMemoryEntry[]>;
  export function searchChatMemories(workspaceId: string, query: string, top?: number): Promise<ChatMemoryHit[]>;
  export function deleteChatMemories(workspaceId: string, threadId?: string): Promise<number>;
  ```

- [ ] **Step 1: Write the failing tests**

Append to `kb-core-ui/web/src/api/workspaces.test.ts`, following that file's existing `mockResponse` idiom:

```ts
describe('chat memory', () => {
  it('lists a workspace without a thread filter', async () => {
    const fetchMock = mockResponse({ workspace_id: 'alpha', entries: [] });

    await listChatMemories('alpha');

    expect(fetchMock).toHaveBeenCalledWith('/api/rag/workspaces/alpha/memory', expect.anything());
  });

  it('lists one thread', async () => {
    const fetchMock = mockResponse({ workspace_id: 'alpha', entries: [] });

    await listChatMemories('alpha', 't 1');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/rag/workspaces/alpha/memory?thread=t+1',
      expect.anything(),
    );
  });

  it('escapes the search query and passes top', async () => {
    const fetchMock = mockResponse({ workspace_id: 'alpha', hits: [] });

    await searchChatMemories('alpha', 'graph records', 10);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/rag/workspaces/alpha/memory/search?q=graph+records&top=10',
      expect.anything(),
    );
  });

  it('returns the hits', async () => {
    mockResponse({
      workspace_id: 'alpha',
      hits: [{ entry: { id: 'm1', title: 'q' }, score: 0.5 }],
    });

    const hits = await searchChatMemories('alpha', 'q');

    expect(hits).toHaveLength(1);
    expect(hits[0].score).toBe(0.5);
  });

  it('deletes a thread and returns the count', async () => {
    const fetchMock = mockResponse({ workspace_id: 'alpha', deleted: 2 });

    const deleted = await deleteChatMemories('alpha', 't1');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/rag/workspaces/alpha/memory?thread=t1',
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(deleted).toBe(2);
  });
});
```

Match the exact query-string encoding the existing tests assert (`getWorkspaceContext` builds its URL with `URLSearchParams`, which encodes a space as `+`). If your implementation encodes differently, fix the implementation to use `URLSearchParams`, not the test.

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
pnpm -C kb-core-ui/web test -- workspaces
```

Expected: FAIL, `listChatMemories is not a function` / import error.

- [ ] **Step 3: Add the client functions**

In `kb-core-ui/web/src/api/workspaces.ts`, after `getWorkspaceContext`:

```ts
export async function listChatMemories(
  workspaceId: string,
  threadId?: string,
): Promise<ChatMemoryEntry[]> {
  const params = new URLSearchParams();
  if (threadId) params.set('thread', threadId);
  const suffix = params.toString() ? `?${params}` : '';
  const body = await workspaceRequest<{ entries: ChatMemoryEntry[] }>(
    `/${encodeURIComponent(workspaceId)}/memory${suffix}`,
  );
  return body.entries ?? [];
}

export async function searchChatMemories(
  workspaceId: string,
  query: string,
  top = 5,
): Promise<ChatMemoryHit[]> {
  const params = new URLSearchParams({ q: query, top: String(top) });
  const body = await workspaceRequest<{ hits: ChatMemoryHit[] }>(
    `/${encodeURIComponent(workspaceId)}/memory/search?${params}`,
  );
  return body.hits ?? [];
}

export async function deleteChatMemories(
  workspaceId: string,
  threadId?: string,
): Promise<number> {
  const params = new URLSearchParams();
  if (threadId) params.set('thread', threadId);
  const suffix = params.toString() ? `?${params}` : '';
  const body = await workspaceRequest<{ deleted: number }>(
    `/${encodeURIComponent(workspaceId)}/memory${suffix}`,
    { method: 'DELETE' },
  );
  return body.deleted ?? 0;
}
```

Add the two interfaces near the file's other exported types. `workspaceRequest` already prefixes `${SERVICE_API_BASE}/rag/workspaces` and already throws `ApiRequestError` on a non-OK response — do not add a second error path.

- [ ] **Step 4: Add the MemoryView section**

In `kb-core-ui/web/src/pages/MemoryView.tsx`, add a chat-memory section below the existing global memory list. It needs its own workspace selector, because workspace selection in this app is component-local (`WorkspaceChatView.tsx:31-81` does the same thing: `listWorkspaces()`, then default to `items[0].id`).

```tsx
function ChatMemorySection() {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const [query, setQuery] = useState('');
  const [entries, setEntries] = useState<ChatMemoryEntry[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listWorkspaces()
      .then((items) => {
        if (cancelled) return;
        setWorkspaces(items);
        setWorkspaceId((current) => current || (items[0]?.id ?? ''));
      })
      .catch(() => {
        if (!cancelled) setUnavailable(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!workspaceId) return undefined;
    let cancelled = false;
    const trimmed = query.trim();
    const timer = window.setTimeout(() => {
      const pending = trimmed
        ? searchChatMemories(workspaceId, trimmed, 20).then((hits) =>
            hits.map((hit) => hit.entry),
          )
        : listChatMemories(workspaceId);
      pending
        .then((items) => {
          if (!cancelled) setEntries(items);
        })
        .catch(() => {
          if (!cancelled) setEntries([]);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [workspaceId, query, reloadToken]);

  async function clearThread(threadId: string) {
    await deleteChatMemories(workspaceId, threadId);
    setReloadToken((token) => token + 1);
  }

  if (unavailable || workspaces.length === 0) {
    return (
      <section className="memory-section">
        <h2>Chat memory</h2>
        <p className="memory-empty">No workspaces. Chat memory appears once GraphRAG is on.</p>
      </section>
    );
  }

  return (
    <section className="memory-section">
      <h2>Chat memory</h2>
      <div className="memory-controls">
        <select
          value={workspaceId}
          onChange={(event) => setWorkspaceId(event.target.value)}
          aria-label="Workspace"
        >
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>
              {workspace.name}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={query}
          placeholder="Search this workspace's chat history"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      {entries.length === 0 ? (
        <p className="memory-empty">Nothing archived yet.</p>
      ) : (
        <ul className="memory-list">
          {entries.map((entry) => (
            <li key={entry.id} className="memory-card">
              <h3>{entry.title}</h3>
              <pre>{entry.text}</pre>
              <footer>
                <span>{formatTime(entry.created_at)}</span>
                <span>{entry.source}</span>
                <button type="button" onClick={() => clearThread(entry.thread_id)}>
                  Clear thread
                </button>
              </footer>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

Render `<ChatMemorySection />` below the existing global memory list in this file's default export. Import `listWorkspaces`, `listChatMemories`, `searchChatMemories`, `deleteChatMemories`, and the `ChatMemoryEntry` and `WorkspaceSummary` types from `../api/workspaces`. Reuse this file's existing `SEARCH_DEBOUNCE_MS` and `formatTime` rather than redefining them; if `MemoryCard`'s props already fit `ChatMemoryEntry`, use it in place of the inline `<li>` body.

Do not add a new CSS file; extend `MemoryView.css`, which this file already imports. Reuse the existing class names where they exist — check the stylesheet before inventing `memory-section`, `memory-controls`, `memory-empty`, or `memory-list`.

- [ ] **Step 5: Run the checks**

```powershell
pnpm -C kb-core-ui/web test
pnpm -C kb-core-ui/web lint
pnpm -C kb-core-ui/web build
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add kb-core-ui/web/src/api/workspaces.ts kb-core-ui/web/src/api/workspaces.test.ts kb-core-ui/web/src/pages/MemoryView.tsx kb-core-ui/web/src/pages/MemoryView.css
git commit -m "feat(web): browse and search workspace chat memories"
```

---

### Task 10: Harness stage

**Files:**
- Modify: `kb-core-ui/harness/harness/rag_workflow.py:60-82` (`REQUIRED_STAGES`), the stage body near line 1483, and the `stages` tuple near line 1695
- Test: `kb-core-ui/harness/tests/test_rag_workflow.py`

**Why:** The harness is the gate that proves the composed system works against a real backend. `harness/tests/test_rag_workflow.py:23` asserts the report's stage names equal `list(REQUIRED_STAGES)`, so a stage that is declared but not run — or run but not declared — fails the suite.

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: a stage named `chat_memory_persistence` returning a dict with keys `transport`, `workspaces`, `alpha_entries`, `alpha_hits`, `beta_entries_after_alpha_delete`, `alpha_entries_after_workspace_delete`.

- [ ] **Step 1: Declare the stage**

In `REQUIRED_STAGES`, add `"chat_memory_persistence"` immediately after `"mvp_isolation_sweep"`. The tuple goes from 21 entries to 22.

- [ ] **Step 2: Run the harness suite to verify it fails**

```powershell
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m pytest -q
```

Expected: FAIL — the report's stage list no longer equals `REQUIRED_STAGES`, because the stage is declared but not registered.

- [ ] **Step 3: Write the stage**

Add after `mvp_isolation_sweep_stage`, in `kb-core-ui/harness/harness/rag_workflow.py`:

```python
    def chat_memory_persistence_stage() -> dict[str, Any]:
        """A chat turn has to land in SQLite as well as FalkorDB, scoped to the
        workspace that produced it, and has to disappear when that workspace is
        deleted -- deletion runs through WorkspaceManager, which is the path a
        real caller takes and the one that used to miss the archive entirely."""

        config = _config(backend)
        registry = WorkspaceRegistry(str(work_dir / "chat-memory-workspaces.json"))

        def adapter_factory(selected_workspace_id: str):
            driver = state.get("driver") if backend == "fake" else None
            return FalkorDBAdapter(config, selected_workspace_id, driver=driver)

        chat_memory = ChatMemoryStore(str(work_dir / "chat-memory.db"))
        sink = SyncChatMemorySink(chat_memory)
        manager = WorkspaceManager(
            registry,
            config,
            adapter_factory=adapter_factory,
            ingestion_coordinator=IngestionCoordinator(
                registry, adapter_factory=adapter_factory, embeddings=_HarnessEmbeddings()
            ),
            chat_memory_sink=sink,
        )
        chat = ChatManager(
            registry,
            config,
            adapter_factory=adapter_factory,
            embeddings=state["embeddings"],
            sleep=lambda _seconds: None,
            chat_memory_sink=sink,
        )

        tenants = {}
        for tenant in ("alpha", "beta"):
            source_dir = work_dir / f"chatmem-{tenant}"
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / "graph.json").write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "id": f"{tenant}/store.py:Store",
                                "label": f"{tenant.capitalize()}Store",
                                "file_type": "code",
                                "source_location": f"{tenant}/store.py:L1",
                                "doc": f"{tenant} owns these graph records.",
                                "_origin": "ast",
                            }
                        ],
                        "links": [],
                    }
                ),
                encoding="utf-8",
            )
            workspace_id = f"chatmem-{tenant}"
            source_id = f"{tenant}-repo"
            manager.create_workspace(workspace_id, f"Chat memory {tenant}")
            manager.add_source(workspace_id, source_id, "local_repo", str(source_dir))
            run = manager.start_ingestion(workspace_id, source_id)
            if run["status"] != "succeeded":
                raise WorkflowFailure(f"{workspace_id} ingestion failed: {run!r}")
            tenants[tenant] = {"workspace_id": workspace_id, "source_id": source_id}

        alpha, beta = tenants["alpha"], tenants["beta"]
        store = Store(str(work_dir / "chat-memory-graph.db"))
        app = Server(
            store,
            str(work_dir),
            workspace_manager=manager,
            chat_manager=chat,
            chat_memory=chat_memory,
        )

        def call(method: str, url: str, payload: dict[str, Any] | None = None):
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url, data=body, method=method, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read().decode("utf-8"))

        try:
            with _serving(app, "rag-chat-memory") as origin:
                def memory_url(workspace_id: str, leaf: str = "") -> str:
                    return f"{origin}/api/rag/workspaces/{workspace_id}/memory{leaf}"

                for tenant, values in tenants.items():
                    status, answered = call(
                        "POST",
                        f"{origin}/api/rag/workspaces/{values['workspace_id']}/chat",
                        {
                            "query": "graph records",
                            "thread_id": "t1",
                            "query_id": f"chatmem-{tenant}",
                        },
                    )
                    if status != 200:
                        raise WorkflowFailure(f"{tenant} chat failed: {status} {answered!r}")
                    if any("chat_memory" in error for error in answered["errors"]):
                        raise WorkflowFailure(f"{tenant} archive reported an error: {answered!r}")

                status, listed = call("GET", memory_url(alpha["workspace_id"]))
                if status != 200 or len(listed["entries"]) != 1:
                    raise WorkflowFailure(f"alpha turn was not archived: {status} {listed!r}")
                if listed["entries"][0]["workspace_id"] != alpha["workspace_id"]:
                    raise WorkflowFailure(f"archived row is not alpha's: {listed!r}")

                status, found = call(
                    "GET", memory_url(alpha["workspace_id"], "/search?q=graph+records&top=10")
                )
                if status != 200 or not found["hits"]:
                    raise WorkflowFailure(f"alpha archive is not searchable: {found!r}")
                foreign = [
                    hit
                    for hit in found["hits"]
                    if hit["entry"]["workspace_id"] != alpha["workspace_id"]
                ]
                if foreign:
                    raise WorkflowFailure(f"alpha search crossed a workspace: {foreign!r}")

                manager.delete_workspace(alpha["workspace_id"])

                alpha_left = chat_memory.count(alpha["workspace_id"])
                if alpha_left:
                    raise WorkflowFailure(
                        f"deleting alpha left {alpha_left} archived rows behind"
                    )
                status, beta_left = call("GET", memory_url(beta["workspace_id"]))
                if status != 200 or len(beta_left["entries"]) != 1:
                    raise WorkflowFailure(f"deleting alpha touched beta: {beta_left!r}")

                manager.delete_workspace(beta["workspace_id"])
        finally:
            chat_memory.close()
            store.close()

        return {
            "transport": "http",
            "workspaces": [alpha["workspace_id"], beta["workspace_id"]],
            "alpha_entries": len(listed["entries"]),
            "alpha_hits": len(found["hits"]),
            "beta_entries_after_alpha_delete": len(beta_left["entries"]),
            "alpha_entries_after_workspace_delete": alpha_left,
        }
```

Add the imports this stage needs at the top of `rag_workflow.py`: `ChatMemoryStore` from `kb_core_ui.memory`, `SyncChatMemorySink` from `kb_core_ui.rag`.

- [ ] **Step 4: Register the stage**

In the `stages` tuple near line 1695, add the entry for `chat_memory_persistence_stage` immediately after the `mvp_isolation_sweep` entry, matching the surrounding entries' exact shape.

- [ ] **Step 5: Run the harness**

```powershell
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m pytest -q
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m harness rag --backend fake --report .harness-work/rag/fake.json
```

Expected: both pass, the report lists 22 stages, and no required stage is skipped.

- [ ] **Step 6: Commit**

```bash
git add kb-core-ui/harness/harness/rag_workflow.py
git commit -m "test(harness): gate chat memory persistence and cleanup"
```

---

### Task 11: Full regression and live browser pass

**Files:**
- Modify: `docs/CLAUDE-RAG-HANDOFF.md`

- [ ] **Step 1: Run every suite**

```powershell
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest -q
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m pytest -q
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m harness rag --backend fake --report .harness-work/rag/fake.json
pnpm -C kb-core-ui/web test
pnpm -C kb-core-ui/web lint
pnpm -C kb-core-ui/web build
```

All must pass before continuing.

- [ ] **Step 2: Run the pinned FalkorDB workflow**

FalkorDB read/write behavior did not change in this plan, but `WorkspaceManager.delete_workspace` did, and that method deletes graphs. Run it:

```powershell
docker run --rm -d -p 127.0.0.1:6380:6379 --name kb-falkor falkordb/falkordb:v4.20.4
cd kb-core-ui/harness; ..\..\.venv-ui\Scripts\python.exe -m harness rag --backend falkordb --report .harness-work/rag/falkordb.json
docker stop kb-falkor
```

Use the exact backend flag value the harness expects — check `harness/__main__.py`'s argument parser before running. Expected: all 22 stages pass.

- [ ] **Step 3: Verify with GraphRAG disabled**

```powershell
$env:RAG_ENABLE = "false"
cd kb-core-ui/python; ..\..\.venv-ui\Scripts\python.exe -m pytest tests/test_rag_mvp_isolation.py -q
Remove-Item Env:\RAG_ENABLE
```

Expected: PASS, including `test_disabled_rag_keeps_the_base_ui_and_hides_every_rag_route` with its two new memory paths.

- [ ] **Step 4: Live browser pass**

Start the server and exercise the feature by hand. Check each of these and write down what you saw:

1. Open a workspace chat, ask a question, get an answer. The answer's `errors` list is empty.
2. Open the Memory page. The new workspace section lists that turn, with the question as its title and the answer in its body.
3. Search the section for a word from the answer. The turn comes back.
4. Switch the workspace selector to a second workspace. The first workspace's turn is gone from the list and does not come back from a search.
5. Delete the chat thread from the chat view. The turn disappears from the memory section.
6. Confirm the global memory list on the same page is unchanged throughout.
7. Open the browser devtools network tab. No request goes anywhere but the backend, and no response body carries a FalkorDB URL, a credential, or a provider key.

If you cannot run a browser, say so explicitly in the result section rather than marking this step done.

- [ ] **Step 5: Record the result**

Add a section to `docs/CLAUDE-RAG-HANDOFF.md` describing what landed: the `chat_memories` table, the sink, the three routes, the `WorkspaceManager` deletion correction, and the new harness stage. State plainly that recall is not implemented — the archive is write-only and nothing reads it back into a prompt.

- [ ] **Step 6: Commit**

```bash
git diff --check
git status --short
git add docs/CLAUDE-RAG-HANDOFF.md
git commit -m "docs(rag): record the chat memory bridge"
```

Do not push.

---

## Out of Scope

Named here so no task quietly grows to include them:

- Recall. Nothing reads `chat_memories` back into a prompt. The archive is write-only.
- Bots as chat tools. That is the next sub-project and needs its own security design — bots spawn subprocesses (`runner.py:69`), so a model-chosen bot invocation is a prompt-injection-to-command-execution path.
- Unioning `chat_memories` with `memories` in any single query or view.
- Migrating chat turns that were persisted before this work.
- Changing the `memories` table, its Go reader, or the global memory routes.
