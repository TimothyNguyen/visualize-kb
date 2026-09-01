"""The sink is the layer that is allowed to fail.

Everything below is either about what a turn becomes in the archive, or about
proving that a broken store degrades the response instead of breaking it.
"""

from __future__ import annotations

import threading
import time

import pytest

from kb_core_ui.memory import ChatMemoryStore
from kb_core_ui.rag.chat_memory import (
    NullChatMemorySink,
    SyncChatMemorySink,
    ThreadedChatMemorySink,
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
    ).to_json_dict()


def _turn(response=None, turn_id="turn-1", thread_id="t1", seq=1, query="a question"):
    return PersistedTurn(
        turn_id=turn_id,
        thread_id=thread_id,
        workspace_id="alpha",
        seq=seq,
        query=query,
        response=response if response is not None else _response(),
        created_at="2026-08-31T00:00:00Z",
    )


def _until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition never became true")


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


def test_a_citation_without_a_location_still_names_its_source():
    assert compose_text("answer", [{"source_id": "repo"}]).splitlines() == ["answer", "repo:"]


def test_recording_a_turn_puts_it_in_the_store(store):
    sink = SyncChatMemorySink(store)

    sink.record(_turn(_response("the graph is a graph")))

    entries = store.list("alpha")
    assert [e.turn_id for e in entries] == ["turn-1"]
    assert entries[0].title == "a question"
    assert entries[0].text.startswith("the graph is a graph")
    assert entries[0].source == "chat://alpha/t1/turn-1"
    assert sink.drain_errors() == []


def test_a_recorded_turn_keeps_its_citations(store):
    sink = SyncChatMemorySink(store)

    sink.record(
        _turn(
            _response(
                "answered",
                [{"source_id": "repo", "source_location": "src/a.py:L1"}],
            )
        )
    )

    assert store.list("alpha")[0].text.splitlines() == ["answered", "repo:src/a.py:L1"]


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


def test_a_broken_store_does_not_raise_on_delete(store):
    sink = SyncChatMemorySink(store)
    store.close()

    sink.delete_thread("alpha", "t1")
    sink.delete_workspace("alpha")

    assert len(sink.drain_errors()) == 2


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


def test_a_full_queue_drops_a_write_and_says_so(store):
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


def test_a_full_queue_never_drops_a_delete(store):
    """A dropped write loses a turn from the archive. A dropped delete leaves
    rows the caller asked to remove, and releases the caller as if it had
    worked -- so writes are expendable under pressure and deletes are not."""

    sink = ThreadedChatMemorySink(SyncChatMemorySink(store), maxsize=1)
    sink.pause()
    deleter = threading.Thread(target=lambda: sink.delete_thread("alpha", "t1"))
    try:
        # The first record is taken off the queue immediately and blocks on the
        # paused worker, so the delete behind it is what fills the queue.
        sink.record(_turn(turn_id="a1"))
        deleter.start()
        _until(lambda: sink._queue.qsize() == 1)
        for index in range(5):
            sink.record(_turn(turn_id=f"flood-{index}"))
    finally:
        sink.resume()
        deleter.join(timeout=5)
        sink.close()

    assert store.count("alpha") == 0


def test_closing_twice_is_safe(store):
    sink = ThreadedChatMemorySink(SyncChatMemorySink(store))
    sink.close()
    sink.close()


def test_the_null_sink_accepts_everything_and_reports_nothing():
    sink = NullChatMemorySink()

    sink.record(_turn())
    sink.delete_thread("alpha", "t1")
    sink.delete_workspace("alpha")
    sink.close()

    assert sink.drain_errors() == []
