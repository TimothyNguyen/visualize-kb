"""Vector memory: the Python side of internal/memory/.

Semantic store of non-code knowledge — codebase rules, lessons learned,
business-logic notes — kept separate from the code graph and retrieved by
cosine similarity rather than by name.
"""

from kb_core_ui.memory.embedder import (
    Embedder,
    HashingEmbedder,
    HTTPEmbedder,
    cosine,
    embedder_from_env,
)
from kb_core_ui.memory.chat_store import (
    ChatMemoryEntry,
    ChatMemoryHit,
    ChatMemoryStore,
)
from kb_core_ui.memory.store import (
    KIND_BUSINESS,
    KIND_LESSON,
    KIND_OVERVIEW,
    KIND_REF,
    KIND_RULE,
    MIN_SCORE,
    VALID_KINDS,
    Entry,
    Hit,
    Store,
    now,
)

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "HTTPEmbedder",
    "cosine",
    "embedder_from_env",
    "Entry",
    "Hit",
    "Store",
    "ChatMemoryEntry",
    "ChatMemoryHit",
    "ChatMemoryStore",
    "now",
    "MIN_SCORE",
    "VALID_KINDS",
    "KIND_RULE",
    "KIND_LESSON",
    "KIND_BUSINESS",
    "KIND_OVERVIEW",
    "KIND_REF",
]
