"""ChatMemoryStore owns the chat_memories table.

Every assertion here is about isolation or about the frozen memories table
staying untouched -- those are the two ways this store can break the system it
shares a database file with.
"""

from __future__ import annotations

import sqlite3

import pytest

from kb_core_ui.gotime import now
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
    assert entry.source == "chat://alpha/t1/turn-1"
    assert entry.created_at
    assert store.list("alpha") == [entry]


def test_a_search_returns_only_the_asking_workspaces_rows(store):
    _add(store, "alpha", turn_id="a1", text="alpha knows about parsers and parsing")
    _add(store, "beta", turn_id="b1", text="beta knows about parsers and parsing")

    hits = store.search("alpha", "parsers", k=10)

    assert hits
    assert {hit.entry.workspace_id for hit in hits} == {"alpha"}


def test_listing_returns_only_the_asking_workspaces_rows(store):
    _add(store, "alpha", turn_id="a1")
    _add(store, "beta", turn_id="b1")

    assert [e.turn_id for e in store.list("alpha")] == ["a1"]


def test_the_same_turn_id_recorded_twice_stays_one_row(store):
    first = _add(store, "alpha", turn_id="dupe", text="first")
    second = _add(store, "alpha", turn_id="dupe", text="second")

    assert first is not None and second is not None
    assert store.count("alpha") == 1
    assert store.list("alpha")[0].text == "second"


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


def test_a_row_without_a_workspace_or_a_turn_is_refused(store):
    assert store.add("", "t1", "turn-1", 1, "q", "a") is None
    assert store.add("alpha", "t1", "", 1, "q", "a") is None
    assert store.count("alpha") == 0


def test_the_frozen_memories_table_is_untouched(tmp_path):
    path = str(tmp_path / "memory.db")
    legacy = Store(path)
    try:
        legacy.add("note", "kept", "kept body", "", now())
    finally:
        legacy.close()

    chat = ChatMemoryStore(path)
    try:
        chat.add("alpha", "t1", "turn-1", 1, "q", "a")
    finally:
        chat.close()

    conn = sqlite3.connect(path)
    try:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"memories", "chat_memories"} <= names
        assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
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
