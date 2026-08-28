"""Port of internal/memory/memory_test.go."""

from __future__ import annotations

import pytest

from kb_core_ui.gotime import GoTime
from kb_core_ui.memory import (
    KIND_BUSINESS,
    KIND_LESSON,
    KIND_OVERVIEW,
    KIND_RULE,
    HashingEmbedder,
    Store,
    cosine,
)
from kb_core_ui.memory.store import make_id


@pytest.fixture
def store(tmp_path):
    with Store(str(tmp_path / "memory.db"), HashingEmbedder(512)) as s:
        yield s


def at(seconds: int = 0) -> GoTime:
    # 2026-01-01T12:00:00Z
    return GoTime(1_767_268_800_000_000_000 + seconds * 1_000_000_000, 0)


def test_embedder_unit_length():
    v = HashingEmbedder(256).embed("the parser resolves call edges by receiver type")
    assert cosine(v, v) >= 0.999
    assert len(v) == 256


def test_embedder_similarity_ranking():
    e = HashingEmbedder(512)
    q = e.embed("how are call graph edges resolved")
    related = e.embed(
        "call edges are resolved by matching the receiver type in the same package"
    )
    unrelated = e.embed("the frontend renders nodes with react flow and dagre layout")
    assert cosine(q, related) > cosine(q, unrelated)


def test_add_and_search(store):
    store.add(
        KIND_RULE,
        "Edge resolution",
        "Call edges resolve by receiver type within the same package; "
        "never cross language families.",
        "test",
        at(0),
    )
    store.add(
        KIND_OVERVIEW,
        "Frontend stack",
        "The web UI is React with @xyflow/react and dagre layout for the graph.",
        "test",
        at(1),
    )
    store.add(
        KIND_LESSON,
        "Nil slices",
        "Zero-param Go functions store params as nil which serializes to JSON null; "
        "normalize to empty slice.",
        "test",
        at(2),
    )

    assert store.count() == 3

    hits = store.search("how do call edges get resolved between packages", "", 5)
    assert hits
    assert hits[0].entry.title == "Edge resolution"
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_search_kind_filter(store):
    store.add(KIND_RULE, "A rule about edges", "edges resolve by receiver", "t", at())
    store.add(KIND_LESSON, "A lesson about edges", "edges once dangled across files", "t", at())

    hits = store.search("edges", KIND_LESSON, 5)
    assert [h.entry.kind for h in hits] == [KIND_LESSON]


def test_get_list_remove(store):
    entry = store.add(
        KIND_BUSINESS, "Pricing tiers", "Free tier caps at 3 repos; paid is unlimited.",
        "spec", at(),
    )

    got = store.get(entry.id)
    assert (got.title, got.kind) == ("Pricing tiers", KIND_BUSINESS)
    assert len(store.list("")) == 1

    assert store.remove(entry.id) is True
    assert store.get(entry.id) is None


def test_stemming_bridges_morphology():
    """The point of the v2 stemmer: a query and a doc sharing only
    morphological variants ("resolved packages" vs "resolve package") must
    still match strongly, so the truly relevant entry decisively beats a
    tangential one that happens to share a raw token."""
    e = HashingEmbedder(512)
    q = e.embed("how are call edges resolved between packages")
    relevant = e.embed(
        "Call edge resolution\n"
        "Call edges resolve by receiver type within the same package."
    )
    tangential = e.embed(
        "What kb-core-ui is\n"
        "kb-core-ui parses a repo into a graph with symbols, call edges, and routes."
    )

    s_rel, s_tan = cosine(q, relevant), cosine(q, tangential)
    assert s_rel > s_tan
    assert s_rel >= 2 * s_tan


def test_search_drops_zero_score(store):
    store.add(KIND_OVERVIEW, "Graph indexing", "tree-sitter parses files into symbols", "t", at())
    assert store.search("xyzzy quux frobnicate", "", 5) == []


def test_created_at_matches_go_rfc3339nano(store):
    """Timestamps are stored the way Go formats a time.Time, which trims
    trailing zeros from the fraction and drops the separator entirely when the
    whole fraction is zero."""
    assert GoTime(1_767_268_800_000_000_000, 0).format() == "2026-01-01T12:00:00Z"
    assert GoTime(1_767_268_800_500_000_000, 0).format() == "2026-01-01T12:00:00.5Z"
    assert GoTime(1_767_268_800_000_000_001, 0).format() == "2026-01-01T12:00:00.000000001Z"
    assert GoTime(1_767_268_800_000_000_000, -4 * 3600).format() == "2026-01-01T08:00:00-04:00"


def test_make_id_slugs_the_title():
    when = at()
    ns = when.unix_nano
    assert make_id(KIND_RULE, "Never Log Secrets!", when) == f"rule-never-log-secrets-{ns}"
    assert make_id(KIND_RULE, "!!!", when) == f"rule-mem-{ns}"
    assert make_id(KIND_RULE, "a" * 50, when) == f"rule-{'a' * 40}-{ns}"
