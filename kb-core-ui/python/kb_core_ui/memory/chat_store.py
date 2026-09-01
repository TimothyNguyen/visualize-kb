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

from kb_core_ui.errors import KbError
from kb_core_ui.gotime import GoTime, normalize, now
from kb_core_ui.memory.embedder import Embedder, cosine, embedder_from_env
from kb_core_ui.memory.store import MIN_SCORE, decode_vec, encode_vec

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


def _make_chat_id(workspace_id: str, turn_id: str) -> str:
    """Derived rather than random so re-recording a turn replaces its row
    instead of racing the unique index on (workspace_id, turn_id)."""

    return f"chat-{workspace_id}-{turn_id}"


def _chat_source(workspace_id: str, thread_id: str, turn_id: str) -> str:
    return f"chat://{workspace_id}/{thread_id}/{turn_id}"


@dataclass(frozen=True)
class ChatMemoryEntry:
    id: str = ""
    workspace_id: str = ""
    thread_id: str = ""
    turn_id: str = ""
    seq: int = 0
    title: str = ""
    text: str = ""
    source: str = ""
    created_at: str = ""

    def to_json_dict(self) -> dict:
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
    score: float = 0.0

    def to_json_dict(self) -> dict:
        return {"entry": self.entry.to_json_dict(), "score": self.score}


def _scan(row: tuple) -> tuple[ChatMemoryEntry, str, bytes]:
    entry = ChatMemoryEntry(
        id=row[0],
        workspace_id=row[1],
        thread_id=row[2],
        turn_id=row[3],
        seq=int(row[4]),
        title=row[5],
        text=row[6],
        source=row[7],
        created_at=normalize(row[8]),
    )
    return entry, row[9], row[11]


class ChatMemoryStore:
    def __init__(self, path: str, embedder: Embedder | None = None):
        self.embedder = embedder if embedder is not None else embedder_from_env()
        self._lock = threading.RLock()
        try:
            self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        except sqlite3.Error as exc:
            raise KbError(f"chat memory: open {path}: {exc}") from None
        try:
            self.db.executescript(SCHEMA)
        except sqlite3.Error as exc:
            self.db.close()
            raise KbError(f"chat memory: schema: {exc}") from None

    def close(self) -> None:
        with self._lock:
            self.db.close()

    def add(
        self,
        workspace_id: str,
        thread_id: str,
        turn_id: str,
        seq: int,
        title: str,
        text: str,
        at: GoTime | None = None,
    ) -> ChatMemoryEntry | None:
        if not workspace_id or not turn_id:
            return None
        stamp = at if at is not None else now()
        entry = ChatMemoryEntry(
            id=_make_chat_id(workspace_id, turn_id),
            workspace_id=workspace_id,
            thread_id=thread_id,
            turn_id=turn_id,
            seq=int(seq),
            title=title,
            text=text,
            source=_chat_source(workspace_id, thread_id, turn_id),
            created_at=stamp.format(),
        )
        vec = self.embedder.embed(title + "\n" + text)
        with self._lock:
            self.db.execute(
                f"INSERT OR REPLACE INTO chat_memories({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.workspace_id,
                    entry.thread_id,
                    entry.turn_id,
                    entry.seq,
                    entry.title,
                    entry.text,
                    entry.source,
                    entry.created_at,
                    self.embedder.name(),
                    self.embedder.dim(),
                    encode_vec(vec),
                ),
            )
        return entry

    def list(self, workspace_id: str, thread_id: str = "") -> list[ChatMemoryEntry]:
        sql = f"SELECT {_COLUMNS} FROM chat_memories WHERE workspace_id = ?"
        args: tuple = (workspace_id,)
        if thread_id:
            sql += " AND thread_id = ?"
            args = (workspace_id, thread_id)
        sql += " ORDER BY created_at DESC, rowid DESC"
        with self._lock:
            rows = self.db.execute(sql, args).fetchall()
        return [_scan(row)[0] for row in rows]

    def search(self, workspace_id: str, query: str, k: int = 0) -> list[ChatMemoryHit]:
        """Brute-force cosine scan inside one workspace, the same shape as
        Store.search. The workspace filter is in SQL, not in the loop, so a
        scoring change can never widen it."""

        if k <= 0:
            k = 5
        if not query.strip():
            return []
        qvec = self.embedder.embed(query)
        with self._lock:
            rows = self.db.execute(
                f"SELECT {_COLUMNS} FROM chat_memories WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchall()

        hits: list[ChatMemoryHit] = []
        for row in rows:
            entry, emb_name, blob = _scan(row)
            # Scores across different embedders are meaningless.
            if emb_name != self.embedder.name():
                continue
            hits.append(ChatMemoryHit(entry, cosine(qvec, decode_vec(blob))))

        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits if h.score >= MIN_SCORE][:k]

    def delete_thread(self, workspace_id: str, thread_id: str) -> int:
        with self._lock:
            cur = self.db.execute(
                "DELETE FROM chat_memories WHERE workspace_id = ? AND thread_id = ?",
                (workspace_id, thread_id),
            )
        return int(cur.rowcount)

    def delete_workspace(self, workspace_id: str) -> int:
        with self._lock:
            cur = self.db.execute(
                "DELETE FROM chat_memories WHERE workspace_id = ?", (workspace_id,)
            )
        return int(cur.rowcount)

    def count(self, workspace_id: str) -> int:
        with self._lock:
            row = self.db.execute(
                "SELECT COUNT(*) FROM chat_memories WHERE workspace_id = ?", (workspace_id,)
            ).fetchone()
        return int(row[0])
