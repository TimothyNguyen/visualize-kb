"""Text-to-vector embedders — the Python side of internal/memory/embedder.go
and neural.go.

Feature weights accumulate in float64 and the vector is stored as float32,
matching Go's types exactly: the stored blob is compared byte for byte against
what the Go binary writes.

Lengths are measured in UTF-8 bytes wherever Go's len() is, since len() on a
Go string counts bytes while Python's len() counts characters.
"""

from __future__ import annotations

import math
import os
from typing import Protocol

import numpy as np

_FNV_OFFSET = 2166136261
_FNV_PRIME = 16777619
_UINT32 = 0xFFFFFFFF

STOPWORDS = {
    "the", "a", "an", "and", "or", "of",
    "to", "in", "is", "it", "for", "on",
    "with", "as", "by", "at", "be", "this",
    "that", "are", "was", "will", "if", "not",
}

# Word unigrams/bigrams carry the real signal. Character trigrams only help
# with morphology, and at equal weight their hash collisions gave even
# nonsense queries a misleadingly high similarity floor.
WORD_WEIGHT = 1.0
TRIGRAM_WEIGHT = 0.25

# Below this token length trigrams are almost all noise.
TRIGRAM_MIN_LEN = 4


class Embedder(Protocol):
    def embed(self, text: str) -> np.ndarray: ...
    def dim(self) -> int: ...
    def name(self) -> str: ...


def fnv1a32(data: bytes) -> int:
    h = _FNV_OFFSET
    for byte in data:
        h = ((h ^ byte) * _FNV_PRIME) & _UINT32
    return h


def stem(w: str) -> str:
    """Crude and conservative: collapses common plural/tense/gerund suffixes
    and a trailing 'e' so morphological variants map to one token. Applied
    identically to stored text and queries, so only internal consistency
    matters, not linguistic correctness."""
    for suf in ("ing", "edly", "ed", "es", "s"):
        if len(w.encode()) - len(suf) >= 3 and w.endswith(suf):
            w = w[: len(w) - len(suf)]
            break
    if len(w.encode()) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    for ch in text.lower():
        if ch.isalpha() or ch.isnumeric():
            current.append(ch)
        elif current:
            fields.append("".join(current))
            current = []
    if current:
        fields.append("".join(current))
    return [stem(f) for f in fields if len(f.encode()) >= 2 and f not in STOPWORDS]


def char_trigrams(tok: str) -> list[str]:
    if len(tok.encode()) < 3:
        return []
    return [tok[i : i + 3] for i in range(len(tok) - 2)]


class HashingEmbedder:
    """The default, fully-offline embedder: the hashing trick over word
    unigrams + bigrams + character trigrams, with sublinear term-frequency
    weighting and L2 normalization.

    It is LEXICAL, not neural — it matches on shared vocabulary, not deep
    semantics ("login" won't match "authenticate"), in exchange for needing no
    model, key or network.
    """

    def __init__(self, dim: int = 512):
        self._dim = dim if dim > 0 else 512

    def dim(self) -> int:
        return self._dim

    def name(self) -> str:
        # Versioned: Search only compares entries embedded under the same
        # name, and v2 added the stemming that changed every vector.
        return "hashing-v2"

    def _add(self, weights: dict[int, float], feature: str, weight: float) -> None:
        idx = fnv1a32(feature.encode()) % self._dim
        weights[idx] = weights.get(idx, 0.0) + weight

    def embed(self, text: str) -> np.ndarray:
        weights: dict[int, float] = {}
        tokens = tokenize(text)
        for i, tok in enumerate(tokens):
            self._add(weights, tok, WORD_WEIGHT)
            if i > 0:
                self._add(weights, tokens[i - 1] + " " + tok, WORD_WEIGHT)
            if len(tok.encode()) >= TRIGRAM_MIN_LEN:
                for tri in char_trigrams(tok):
                    self._add(weights, "#" + tri, TRIGRAM_WEIGHT)

        vec = np.zeros(self._dim, dtype=np.float32)
        sum_sq = 0.0
        # Go ranges over a map here, so its summation order — and therefore
        # the last bits of sum_sq — is already nondeterministic. Sorting keeps
        # this side reproducible.
        for idx in sorted(weights):
            w = 1 + math.log(weights[idx])
            vec[idx] = np.float32(w)
            sum_sq += w * w
        if sum_sq > 0:
            vec /= np.float32(math.sqrt(sum_sq))
        return vec


class HTTPEmbedder:
    """Calls any OpenAI-compatible /embeddings endpoint. Returns a zero vector
    on any failure so a transient outage degrades to "no match" rather than
    crashing a bot mid-run."""

    def __init__(self, base_url: str, model: str, api_key: str, dim: int):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self._dim = dim

    def dim(self) -> int:
        return self._dim

    def name(self) -> str:
        return "http:" + self.model

    def embed(self, text: str) -> np.ndarray:
        import json
        import sys
        import urllib.error
        import urllib.request

        zero = np.zeros(self._dim, dtype=np.float32)
        body = json.dumps({"model": self.model, "input": text}).encode()
        req = urllib.request.Request(
            self.base_url + "/embeddings", data=body, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                out = json.load(resp)
        except urllib.error.HTTPError as exc:
            print(f"memory: embedding endpoint returned {exc.code} {exc.reason}", file=sys.stderr)
            return zero
        except OSError as exc:
            print(f"memory: embedding request failed: {exc}", file=sys.stderr)
            return zero
        except ValueError as exc:
            print(f"memory: bad embedding response: {exc}", file=sys.stderr)
            return zero
        data = out.get("data") or []
        if not data:
            print("memory: bad embedding response: <nil>", file=sys.stderr)
            return zero
        return np.asarray(data[0]["embedding"], dtype=np.float32)


def embedder_from_env() -> Embedder:
    """The one place deciding which embedder the CLI/server/bots use, so
    switching to neural embeddings needs env vars rather than a code change.
    A memory.db is embedder-specific: entries record which embedder produced
    them and Search only compares within the same one."""
    url = os.environ.get("KB_CORE_UI_EMBED_URL", "")
    model = os.environ.get("KB_CORE_UI_EMBED_MODEL", "")
    if not url or not model:
        return HashingEmbedder(512)
    dim = 768
    raw = os.environ.get("KB_CORE_UI_EMBED_DIM", "")
    if raw:
        parsed = _parse_dim(raw)
        if parsed is not None:
            dim = parsed
    return HTTPEmbedder(url, model, os.environ.get("KB_CORE_UI_EMBED_KEY", ""), dim)


def _parse_dim(s: str) -> int | None:
    # Go uses Sscanf("%d"), which reads a leading integer and ignores trailing
    # junk rather than rejecting it.
    i = 0
    if i < len(s) and s[i] in "+-":
        i += 1
    start = i
    while i < len(s) and s[i].isdigit():
        i += 1
    if i == start:
        return None
    n = int(s[:i])
    return n if n > 0 else None


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Vectors from an Embedder are already unit-length so this is their dot
    product, but it normalizes defensively in case one isn't."""
    if len(a) != len(b):
        return 0.0
    # Summed sequentially rather than with np.dot: BLAS reorders the additions
    # and the last bits would differ from Go's naive loop, which is visible
    # once the score is serialized into a REST response.
    dot = na = nb = 0.0
    for x, y in zip(a.tolist(), b.tolist()):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
