from __future__ import annotations

from pathlib import Path

from harness.manifest import Operation
from harness.operations import execute_operation
from harness.runner import RunContext


def _ctx(fixture_root: Path) -> RunContext:
    return RunContext(
        run_id="test",
        engine_name="go",
        root=fixture_root.parent,
        fixture_root=fixture_root,
        db_path=fixture_root.parent / "db" / "graph.db",
        work_dir=fixture_root.parent / "work",
    )


def test_fs_replace_mutates_file_content(tmp_path: Path):
    (tmp_path / "hello.go").write_text("func Add(a, b int) int { return a + b }", encoding="utf-8")
    op = Operation(id="mutate", kind="fs", fs_op="replace", path="hello.go", find="Add", replace="AddTwo")
    result = execute_operation(None, _ctx(tmp_path), op, None, None)
    assert result is None
    assert (tmp_path / "hello.go").read_text(encoding="utf-8") == "func AddTwo(a, b int) int { return a + b }"


def test_fs_delete_removes_file(tmp_path: Path):
    target = tmp_path / "b.go"
    target.write_text("package multi", encoding="utf-8")
    op = Operation(id="rm", kind="fs", fs_op="delete", path="b.go")
    execute_operation(None, _ctx(tmp_path), op, None, None)
    assert not target.exists()


def test_fs_delete_missing_file_does_not_raise(tmp_path: Path):
    op = Operation(id="rm", kind="fs", fs_op="delete", path="does-not-exist.go")
    execute_operation(None, _ctx(tmp_path), op, None, None)
