# Chat memory bridge — design

Status: approved, not implemented
Date: 2026-08-31
Scope: sub-project 1 of 2. Bots-as-chat-tools is a separate spec.

## Problem

Chat turns persist to FalkorDB and nowhere else. `ChatManager` writes each turn
through `ChatHistoryStore.write_turn` into `ChatThread` and `ChatTurn` nodes
(`rag/persistence.py:126`, `rag/falkordb_adapter.py:717`), and those turns are
readable only by opening the thread that owns them. There is no way to ask
"what did we already establish about the ingestion coordinator?" across threads.

The repository already has a vector memory store — a `memories` table with
embeddings, cosine search, and a REST surface (`memory/store.py:112`,
`server/app.py:110-113`). Nothing in `rag/` writes to it.

This design makes each chat turn also land in a searchable memory store,
without weakening workspace isolation and without changing what the chat
workflow answers.

## Constraints that shape the design

**The `memories` schema is a cross-language contract.** `memory/store.py:1`
states the schema text is copied verbatim from `internal/memory/store.go` so a
`memory.db` written by the Go binary opens unchanged in Python, with embeddings
byte-identical to Go's `encodeVec`. Adding a column to `memories` breaks that:
a Go-created database will not have the column, and Go's
`CREATE TABLE IF NOT EXISTS` will not add it.

**`memories` is global; chat is workspace-scoped.** The table has no workspace
column and `/api/memory/search` takes no workspace parameter. The project
invariant is "Every read and write is workspace-scoped server-side." Writing
chat turns into the global table would let a caller in workspace `beta` search
up answers produced in workspace `alpha` — the exact leak
`python/tests/test_rag_mvp_isolation.py` exists to prevent, reached around the
RAG layer instead of through it.

**Embedding can be a slow network call.** `embedder_from_env()` returns the
offline `HashingEmbedder` by default, but returns `HTTPEmbedder` when
`KB_CORE_UI_EMBED_URL` and `KB_CORE_UI_EMBED_MODEL` are set. `HTTPEmbedder.embed`
makes a request with a 30-second timeout and **returns a zero vector on any
failure** (`memory/embedder.py:155-185`), which would otherwise store a row that
can never match a query.

## Decisions

| Decision | Choice | Rejected alternative and why |
|---|---|---|
| Where chat memories live | New `chat_memories` table in the same `memory.db` | Reusing `memories` with a `source` prefix makes isolation a string convention; adding `workspace_id` to `memories` breaks the Go schema contract |
| Recall | Write-only archive | Feeding memory back into retrieval changes what evidence and citations mean and lets a wrong answer compound; out of scope here |
| Write timing | Best-effort, off the request path | A synchronous write adds up to 30s of latency per turn under `HTTPEmbedder`; a mandatory write lets a flaky embedding endpoint take the chatbot down |
| Seam | `memory_sink` collaborator on `ChatManager` | The HTTP layer would need the same call in three handlers and silently drops turns if one is missed; folding it into `ChatHistoryStore` gives that class two jobs |

## Component 1 — `memory/chat_store.py`

A new module with its own schema. `memory/store.py` is not modified.

```sql
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
```

Go ignores tables it does not know about, so `memory.db` stays readable by the
Go binary and the `memories` contract is untouched.

Field semantics:

- `title` — the user query, truncated to 200 characters.
- `text` — the answer, followed by one line listing each citation as
  `source_id:source_location`, so lexical search matches file paths as well as
  prose. `HashingEmbedder` is lexical, not semantic, so the exact tokens stored
  determine what is findable.
- `source` — `chat://<workspace_id>/<thread_id>/<turn_id>`, used for provenance
  and for the UI to link an entry back to its thread.
- `embedder` and `dim` — recorded per row, and search skips rows written by a
  different embedder, matching `Store.search`'s rule that scores across
  embedders are meaningless (`memory/store.py:181`).

The unique index on `(workspace_id, turn_id)` makes a retried write idempotent
rather than duplicating an entry.

Public API — **every method takes `workspace_id` first and every statement
filters on it**, so no method is capable of reading across workspaces:

```python
@dataclass
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

    def to_json_dict(self) -> dict: ...


@dataclass
class ChatMemoryHit:
    entry: ChatMemoryEntry
    score: float


class ChatMemoryStore:
    def add(self, workspace_id, thread_id, turn_id, seq, title, text, at) -> ChatMemoryEntry | None
    def search(self, workspace_id, query, k=5) -> list[ChatMemoryHit]
    def list(self, workspace_id, thread_id="") -> list[ChatMemoryEntry]
    def get(self, workspace_id, entry_id) -> ChatMemoryEntry | None
    def remove(self, workspace_id, entry_id) -> bool
    def delete_thread(self, workspace_id, thread_id) -> int
    def delete_workspace(self, workspace_id) -> int
    def count(self, workspace_id) -> int
```

`ChatMemoryEntry` is a distinct type rather than a reuse of `memory.store.Entry`,
because `Entry` has no `thread_id` or `turn_id` and the UI needs both to link an
entry back to its thread. `Entry`'s JSON shape is also part of the existing
`/api/memory` contract and must not shift.

`add` returns `None` and records nothing when the embedder produces an all-zero
vector, rather than storing a permanently unmatchable row.

Encoding, cosine scoring, and the `MIN_SCORE` floor are imported from
`memory/store.py` and `memory/embedder.py` rather than reimplemented, so scores
mean the same thing in both surfaces.

## Component 2 — the sink

`ChatManager.__init__` gains `memory_sink=None`. The default is a no-op object,
so every existing test, the RAG-disabled path, and the harness fake stack are
unaffected.

Protocol:

```python
class ChatMemorySink(Protocol):
    def record(self, workspace_id, thread_id, turn_id, seq, query, response) -> None
    def delete_thread(self, workspace_id, thread_id) -> None
    def delete_workspace(self, workspace_id) -> None
    def drain_errors(self) -> list[str]
    def close(self) -> None
```

Two implementations:

- `SyncChatMemorySink` — writes inline. Used by unit tests and the harness so
  assertions are deterministic.
- `ThreadedChatMemorySink` — one worker thread draining a bounded
  `queue.Queue(maxsize=256)`. On a full queue it drops the oldest pending write
  and counts the drop as an error rather than blocking the chat path. `close()`
  drains and joins with a timeout. The server owns it and closes it on shutdown.

### Call sites

`ChatManager` writes a turn in exactly two places, which is why the sink lives
here rather than in the HTTP handlers:

- `rag/chat_manager.py:347` — the non-streaming `ask` path.
- `rag/chat_manager.py:440` — the streaming path.

`record` is called immediately after `write_turn` returns, using the
`PersistedTurn` it produced for `turn_id` and `seq`. FalkorDB remains the source
of truth; chat memory is derived from it. If the FalkorDB write fails, no memory
entry is written.

The sink receives the query and the `ChatResponse`, and is the component that
composes them into the stored `title` and `text` described above. Composition
lives in the sink rather than in `ChatMemoryStore` so the store stays a plain
persistence boundary with no knowledge of the chat contract.

### Failure policy

The sink never raises into the chat path. Failures accumulate on the sink;
`ChatManager` calls `sink.drain_errors()` while assembling each response and
appends whatever it returns to that response's `errors` list. Because the
threaded sink writes after the answer has already been returned, a given turn's
own write failure surfaces on a subsequent turn rather than its own — acceptable
for an archive, and the reason `drain_errors` returns and clears rather than
being read per turn.

`errors` is already a list of strings in the frozen T11 contract, so the wire
shape does not change.

## Component 3 — deletion symmetry

Without this, a deleted workspace leaves its answers searchable. Two existing
call sites gain a sink call:

- `rag/chat_manager.py:592` (`delete_thread`) → `sink.delete_thread(...)`
- `rag/chat_manager.py:600` (`cleanup_workspace`, reached from
  `rag/manager.py:42` `delete_workspace`) → `sink.delete_workspace(...)`

Deletes are synchronous even on the threaded sink: `delete_thread` and
`delete_workspace` drain the pending queue before executing, so a write that was
already queued cannot land after the delete that was meant to remove it.

## Component 4 — routes

Registered inside the existing `workspace_manager is not None` block in
`server/app.py`, alongside the other `/api/rag/workspaces/...` routes. This
preserves invariant V13 with no extra code: with GraphRAG disabled the block does
not run and these routes 404, which the existing
`test_disabled_rag_keeps_the_base_ui_and_hides_every_rag_route` already asserts
the shape of.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/rag/workspaces/{id}/memory?thread_id=` | List entries for the workspace, optionally one thread |
| GET | `/api/rag/workspaces/{id}/memory/search?q=&k=` | Cosine search within the workspace |
| DELETE | `/api/rag/workspaces/{id}/memory/{entry_id}` | Remove one entry |

Every handler resolves the workspace through the registry first, so an unknown
workspace 404s before any query runs, matching the other chat routes.

The existing `/api/memory`, `/api/memory/search`, `/api/memory` POST, and
`/api/memory/{id}` DELETE routes are unchanged and keep serving the global,
Go-compatible `memories` table.

## Component 5 — UI

`web/src/pages/MemoryView.tsx` gains a workspace chat-memory section, rendered
only when GraphRAG is enabled and a workspace is selected. It lists entries with
their query, answer excerpt, and timestamp, supports search against the new
search route, and links each entry to its thread in `WorkspaceChatView`.

The existing global memory list and its controls stay as they are. The two
surfaces are visually separated because they are different stores with different
scoping rules, and merging them in the UI would imply a shared search that does
not exist.

## Error handling summary

| Failure | Behavior |
|---|---|
| Embedder returns zero vector | Entry skipped, error recorded, chat unaffected |
| Embedding endpoint slow | Chat answer returns immediately; the write completes or fails on the worker thread |
| SQLite write error | Recorded on the sink, surfaced in a later response's `errors` |
| Queue full | Oldest pending write dropped and counted; chat never blocks |
| FalkorDB turn write fails | No memory write attempted |
| Unknown workspace on a memory route | 404 before any query |

## Testing

Unit — `python/tests/test_chat_memory_store.py`:
schema creation leaves `memories` intact and a Go-shaped `memories` row still
reads; re-adding the same `turn_id` does not duplicate; every read method
filters by workspace; an all-zero embedding is skipped; `delete_thread` and
`delete_workspace` remove only their own rows.

Unit — `python/tests/test_rag_chat_memory.py`:
`ChatManager` with a `SyncChatMemorySink` writes exactly one entry per turn on
both the `ask` and streaming paths; a sink that raises does not fail the answer
and its error appears in a later `errors` list; deleting a thread and deleting a
workspace cascade; a default `ChatManager` with no sink behaves exactly as today.

Isolation — extend `python/tests/test_rag_mvp_isolation.py` with a case asserting
that a search in one workspace never returns another's chat memory, since that
file is already the composed-leak guard.

HTTP — the three new routes 404 with GraphRAG disabled and 404 for an unknown
workspace; search results are workspace-scoped.

Harness — a new required stage `chat_memory_persistence` in
`harness/harness/rag_workflow.py`, added to `REQUIRED_STAGES`: real ingestion
into two workspaces, ask in each, assert entries land with correct provenance,
assert search is scoped, assert deleting a workspace clears its entries and
leaves the other's. Run against the fake backend and against pinned
`falkordb/falkordb:v4.20.4`.

Browser — start the dev server, ingest a workspace, ask questions in two
workspaces, confirm entries appear in the Memory view and link back to their
threads, restart the server and confirm the entries persist, delete a workspace
and confirm its entries disappear while the other's remain.

## Out of scope

- Recall: the chat workflow does not read memory back. `rag/workflow.py` is not
  modified by this spec.
- Bots: covered by a separate spec.
- Unioning `chat_memories` with the global `memories` table in one search.
- Migrating existing FalkorDB chat turns into memory. Only turns written after
  this ships are archived.
