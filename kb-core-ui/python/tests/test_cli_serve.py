"""What `serve` opens.

The chat archive shares one SQLite file with the global memory store. These
tests hold that sharing to its contract: two tables, one file, neither store
disturbing the other.
"""

from __future__ import annotations

from kb_core_ui.gotime import now


def test_serving_shares_one_memory_file_between_both_stores(tmp_path):
    from kb_core_ui.cli.root import open_chat_memory, open_memory

    memory = open_memory(str(tmp_path))
    chat_memory = open_chat_memory(str(tmp_path))
    try:
        memory.add("note", "kept", "kept body", "", now())
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
