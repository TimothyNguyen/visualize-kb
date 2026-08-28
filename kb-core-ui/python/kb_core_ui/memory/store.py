"""Vector-memory persistence — the Python side of internal/memory/store.go.

Schema text is copied verbatim so a memory.db written by the Go binary opens
unchanged, and vice versa. Embeddings are stored as little-endian float32,
byte for byte what Go's encodeVec writes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import numpy as np

from kb_core_ui.errors import KbError
from kb_core_ui.gotime import ZERO_TIME, GoTime, normalize, now
from kb_core_ui.memory.embedder import Embedder, cosine, embedder_from_env

KIND_RULE = "rule"
KIND_LESSON = "lesson"
KIND_BUSINESS = "business"
KIND_OVERVIEW = "overview"
KIND_REF = "reference"

VALID_KINDS = (KIND_RULE, KIND_LESSON, KIND_BUSINESS, KIND_OVERVIEW, KIND_REF)

# Cosine floor below which a result is hash-collision noise rather than a real
# match. Calibrated for the lexical HashingEmbedder, whose genuine weak
# matches land near 0.10 while collision noise sits under ~0.05.
MIN_SCORE = 0.07

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
	id          TEXT PRIMARY KEY,
	kind        TEXT NOT NULL,
	title       TEXT NOT NULL,
	text        TEXT NOT NULL,
	source      TEXT NOT NULL,
	created_at  TEXT NOT NULL,
	embedder    TEXT NOT NULL,
	dim         INTEGER NOT NULL,
	embedding   BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
"""

_COLUMNS = "id, kind, title, text, source, created_at, embedder, dim, embedding"

@dataclass
class Entry:
    id: str = ""
    kind: str = ""
    title: str = ""
    text: str = ""
    source: str = ""
    created_at: str = ZERO_TIME

    def to_json_dict(self) -> dict:
        out = {"id": self.id, "kind": self.kind, "title": self.title, "text": self.text}
        if self.source:
            out["source"] = self.source
        out["createdAt"] = self.created_at
        return out


@dataclass
class Hit:
    entry: Entry = field(default_factory=Entry)
    score: float = 0.0

    def to_json_dict(self) -> dict:
        return {"entry": self.entry.to_json_dict(), "score": self.score}


def make_id(kind: str, title: str, at: GoTime) -> str:
    slug_chars: list[str] = []
    for ch in title:
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            slug_chars.append(ch)
        elif "A" <= ch <= "Z":
            slug_chars.append(chr(ord(ch) + 32))
        elif ch in " -_":
            slug_chars.append("-")
    # Every surviving character is ASCII, so Go's byte-slice truncation and a
    # character slice agree here.
    slug = "".join(slug_chars)[:40].strip("-")
    if not slug:
        slug = "mem"
    return f"{kind}-{slug}-{at.unix_nano}"


def encode_vec(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype="<f4").tobytes()


def decode_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype="<f4")


def _scan(row: tuple) -> tuple[Entry, str, bytes]:
    entry = Entry(
        id=row[0],
        kind=row[1],
        title=row[2],
        text=row[3],
        source=row[4],
        created_at=normalize(row[5]),
    )
    return entry, row[6], row[8]


class Store:
    def __init__(self, path: str, embedder: Embedder | None = None):
        self.embedder = embedder if embedder is not None else embedder_from_env()
        try:
            # check_same_thread=False: `serve` dispatches each request on
            # its own thread, mirroring Go's goroutine-per-connection
            # server. Concurrent use is serialized by the REST layer's
            # lock (server/app.py), not by sqlite3's thread check.
            self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        except sqlite3.Error as exc:
            raise KbError(f"memory: open {path}: {exc}") from None
        try:
            self.db.executescript(SCHEMA)
        except sqlite3.Error as exc:
            self.db.close()
            raise KbError(f"memory: schema: {exc}") from None

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def add(self, kind: str, title: str, text: str, source: str, at: GoTime) -> Entry:
        # Title and body are embedded together: the title carries strong signal.
        vec = self.embedder.embed(title + "\n" + text)
        entry = Entry(
            id=make_id(kind, title, at),
            kind=kind,
            title=title,
            text=text,
            source=source,
            created_at=at.format(),
        )
        self.db.execute(
            f"INSERT INTO memories({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.id,
                entry.kind,
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

    def search(self, query: str, kind: str = "", k: int = 0) -> list[Hit]:
        """Brute-force cosine scan. Fine for the thousands of entries this kind
        of memory holds; swap in an ANN index if it ever grows huge."""
        if k <= 0:
            k = 5
        qvec = self.embedder.embed(query)

        sql = f"SELECT {_COLUMNS} FROM memories"
        args: tuple = ()
        if kind:
            sql += " WHERE kind = ?"
            args = (kind,)

        hits: list[Hit] = []
        for row in self.db.execute(sql, args):
            entry, emb_name, blob = _scan(row)
            # Scores across different embedders are meaningless.
            if emb_name != self.embedder.name():
                continue
            hits.append(Hit(entry, cosine(qvec, decode_vec(blob))))

        # Go uses sort.Slice, which is unstable in general but falls back to
        # insertion sort — stable — below 13 elements, the size any realistic
        # result set has here.
        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits if h.score >= MIN_SCORE][:k]

    def list(self, kind: str = "") -> list[Entry]:
        sql = f"SELECT {_COLUMNS} FROM memories"
        args: tuple = ()
        if kind:
            sql += " WHERE kind = ?"
            args = (kind,)
        sql += " ORDER BY created_at DESC"
        return [_scan(row)[0] for row in self.db.execute(sql, args)]

    def get(self, entry_id: str) -> Entry | None:
        row = self.db.execute(
            f"SELECT {_COLUMNS} FROM memories WHERE id = ?", (entry_id,)
        ).fetchone()
        return None if row is None else _scan(row)[0]

    def remove(self, entry_id: str) -> bool:
        cur = self.db.execute("DELETE FROM memories WHERE id = ?", (entry_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
