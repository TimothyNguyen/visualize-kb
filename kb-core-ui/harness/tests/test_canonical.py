from __future__ import annotations

import pytest

from harness.canonical import (
    NormalizeContext,
    canonical_dumps,
    canonicalize,
    to_comparable,
)
from harness.errors import ManifestError
from harness.runner import CliResult, RestResult


def _ctx(fixture_root: str = r"C:\tmp\fixture-root") -> NormalizeContext:
    return NormalizeContext(fixture_root=fixture_root, engine="go")


def test_line_endings_normalizer():
    value = {"stdout": "line1\r\nline2\rline3\n"}
    out = canonicalize(value, ["line_endings"], _ctx())
    assert out == {"stdout": "line1\nline2\nline3\n"}


def test_fixture_root_path_normalizer_both_slash_variants():
    root = r"C:\tmp\fixture-root"
    value = {
        "a": r"C:\tmp\fixture-root\hello.go",
        "b": "C:/tmp/fixture-root/hello.go",
    }
    out = canonicalize(value, ["fixture_root_path"], _ctx(root))
    assert out == {"a": r"<FIXTURE_ROOT>\hello.go", "b": "<FIXTURE_ROOT>/hello.go"}


def test_timestamp_normalizer():
    value = "created at 2024-01-02T03:04:05.123456789Z end"
    out = canonicalize(value, ["timestamp"], _ctx())
    assert out == "created at <TIMESTAMP> end"


def test_generated_id_normalizer():
    value = "id=rule-smoke-rule-1706812345123456789 done"
    out = canonicalize(value, ["generated_id"], _ctx())
    assert out == "id=rule-<SLUG>-<NANOTS> done"


def test_key_order_normalizer_sorts_nested_dicts():
    value = {"b": 1, "a": {"z": 1, "y": 2}}
    out = canonicalize(value, ["key_order"], _ctx())
    assert list(out.keys()) == ["a", "b"]
    assert list(out["a"].keys()) == ["y", "z"]


def test_canonicalize_applies_normalizers_in_order():
    value = "path C:\\tmp\\fixture-root\\x.go at 2024-01-02T03:04:05Z\r\n"
    out = canonicalize(value, ["line_endings", "fixture_root_path", "timestamp"], _ctx())
    assert out == "path <FIXTURE_ROOT>\\x.go at <TIMESTAMP>\n"


def test_canonicalize_unknown_normalizer_raises():
    with pytest.raises(ManifestError):
        canonicalize("x", ["not_a_real_normalizer"], _ctx())


def test_canonical_dumps_is_sorted_and_stable():
    a = canonical_dumps({"b": 1, "a": 2})
    b = canonical_dumps({"a": 2, "b": 1})
    assert a == b
    assert a.endswith("\n")


def test_to_comparable_stdout_exit():
    raw = CliResult(argv=["x"], exit_code=0, stdout="hi", stderr="", duration_s=0.1)
    assert to_comparable("stdout_exit", raw) == {"exit_code": 0, "stdout": "hi"}


def test_to_comparable_json_body_status():
    raw = RestResult(status=200, json_body={"ok": True}, text_body='{"ok": true}')
    assert to_comparable("json_body_status", raw) == {"status": 200, "body": {"ok": True}}


def test_to_comparable_json_result():
    raw = {"tree": ["a.go"]}
    assert to_comparable("json_result", raw) == {"result": {"tree": ["a.go"]}}


def test_to_comparable_unknown_capture_raises():
    with pytest.raises(ManifestError):
        to_comparable("not_a_capture", None)


def _edge(source, target, kind):
    return {"source": source, "target": target, "kind": kind}


def test_edge_order_sorts_edge_arrays():
    body = {
        "center": "a.go:Add",
        "edges": [_edge("a.go:B", "a.go:Add", "calls"), _edge("a.go:A", "a.go:Add", "contains")],
        "nodes": [{"id": "a.go:Add"}],
    }
    out = canonicalize(body, ["edge_order"], _ctx())
    assert [e["source"] for e in out["edges"]] == ["a.go:A", "a.go:B"]
    # Non-edge arrays are untouched.
    assert out["nodes"] == [{"id": "a.go:Add"}]
    assert out["center"] == "a.go:Add"


def test_edge_order_leaves_non_edge_dicts_alone():
    body = {"rows": [{"source": "b", "target": "a"}, {"source": "a", "target": "b"}]}
    assert canonicalize(body, ["edge_order"], _ctx()) == body
