from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.errors import ManifestError
from harness.manifest import discover_fixtures, load_manifest


def _write_manifest(tmp_path: Path, operations: list[dict], name: str = "sample") -> Path:
    fixture_dir = tmp_path / name
    (fixture_dir / "repo").mkdir(parents=True)
    (fixture_dir / "repo" / "placeholder.txt").write_text("x", encoding="utf-8")
    manifest_path = fixture_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"name": name, "repo": "repo", "operations": operations}), encoding="utf-8"
    )
    return manifest_path


def test_load_manifest_happy_path(tmp_path: Path):
    path = _write_manifest(tmp_path, [{"id": "op1", "kind": "cli", "command": "parse"}])
    fixture = load_manifest(path)
    assert fixture.name == "sample"
    assert fixture.repo_dir.is_dir()
    assert [op.id for op in fixture.operations] == ["op1"]


def test_load_manifest_missing_repo_dir_raises(tmp_path: Path):
    fixture_dir = tmp_path / "broken"
    fixture_dir.mkdir()
    manifest_path = fixture_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"name": "broken", "repo": "nope", "operations": [{"id": "a", "kind": "cli", "command": "parse"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_missing_id_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(_write_manifest(tmp_path, [{"kind": "cli", "command": "parse"}]))


def test_load_manifest_invalid_kind_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(_write_manifest(tmp_path, [{"id": "a", "kind": "bogus"}]))


@pytest.mark.parametrize(
    "op",
    [
        {"id": "a", "kind": "cli"},
        {"id": "a", "kind": "rest", "method": "GET"},
        {"id": "a", "kind": "rest", "route": "/x"},
        {"id": "a", "kind": "mcp"},
    ],
)
def test_load_manifest_missing_kind_specific_field_raises(tmp_path: Path, op: dict):
    with pytest.raises(ManifestError):
        load_manifest(_write_manifest(tmp_path, [op]))


def test_load_manifest_invalid_capture_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(tmp_path, [{"id": "a", "kind": "cli", "command": "parse", "capture": "bogus"}])
        )


def test_load_manifest_unknown_normalizer_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(
                tmp_path, [{"id": "a", "kind": "cli", "command": "parse", "normalizers": ["not_real"]}]
            )
        )


def test_load_manifest_invalid_ignore_field_pattern_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(
                tmp_path, [{"id": "a", "kind": "cli", "command": "parse", "ignore_fields": ["no-dollar-sign"]}]
            )
        )


def test_load_manifest_duplicate_ids_raise(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(
                tmp_path,
                [
                    {"id": "dup", "kind": "cli", "command": "parse"},
                    {"id": "dup", "kind": "cli", "command": "parse"},
                ],
            )
        )


def test_load_manifest_no_operations_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(_write_manifest(tmp_path, []))


def test_load_manifest_parses_setup_operations(tmp_path: Path):
    path = _write_manifest(
        tmp_path,
        [
            {
                "id": "main",
                "kind": "cli",
                "command": "memory_list",
                "setup": [{"id": "seed", "kind": "cli", "command": "memory_add"}],
            }
        ],
    )
    fixture = load_manifest(path)
    assert fixture.operations[0].setup[0].id == "seed"


def test_load_manifest_parses_fs_replace_setup_operation(tmp_path: Path):
    path = _write_manifest(
        tmp_path,
        [
            {
                "id": "main",
                "kind": "rest",
                "method": "GET",
                "route": "/api/graph",
                "setup": [
                    {"id": "mutate", "kind": "fs", "fs_op": "replace", "path": "a.go", "find": "A", "replace": "B"}
                ],
            }
        ],
    )
    fixture = load_manifest(path)
    setup_op = fixture.operations[0].setup[0]
    assert setup_op.fs_op == "replace"
    assert setup_op.path == "a.go"
    assert setup_op.find == "A"
    assert setup_op.replace == "B"


def test_load_manifest_parses_fs_delete_setup_operation(tmp_path: Path):
    path = _write_manifest(
        tmp_path,
        [
            {
                "id": "main",
                "kind": "rest",
                "method": "GET",
                "route": "/api/graph",
                "setup": [{"id": "rm", "kind": "fs", "fs_op": "delete", "path": "b.go"}],
            }
        ],
    )
    fixture = load_manifest(path)
    assert fixture.operations[0].setup[0].fs_op == "delete"


def test_load_manifest_fs_kind_at_top_level_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(tmp_path, [{"id": "a", "kind": "fs", "fs_op": "delete", "path": "a.go"}])
        )


@pytest.mark.parametrize(
    "fs_op",
    [
        {"id": "a", "kind": "fs"},
        {"id": "a", "kind": "fs", "fs_op": "bogus", "path": "a.go"},
        {"id": "a", "kind": "fs", "fs_op": "delete"},
        {"id": "a", "kind": "fs", "fs_op": "replace", "path": "a.go"},
        {"id": "a", "kind": "fs", "fs_op": "replace", "path": "a.go", "find": "A"},
    ],
)
def test_load_manifest_invalid_fs_operation_raises(tmp_path: Path, fs_op: dict):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(
                tmp_path,
                [{"id": "main", "kind": "cli", "command": "parse", "setup": [fs_op]}],
            )
        )


@pytest.mark.parametrize("capture", ["stdout_stderr_exit", "status_text_body"])
def test_load_manifest_accepts_t1_capture_kinds(tmp_path: Path, capture: str):
    path = _write_manifest(
        tmp_path, [{"id": "a", "kind": "cli", "command": "help_root", "capture": capture}]
    )
    assert load_manifest(path).operations[0].capture == capture


def test_load_manifest_parses_mcp_list_kind(tmp_path: Path):
    path = _write_manifest(tmp_path, [{"id": "a", "kind": "mcp_list", "capture": "json_result"}])
    assert load_manifest(path).operations[0].kind == "mcp_list"


def test_load_manifest_parses_raw_body_on_rest(tmp_path: Path):
    path = _write_manifest(
        tmp_path,
        [{"id": "a", "kind": "rest", "method": "POST", "route": "/api/memory", "raw_body": "{not json"}],
    )
    assert load_manifest(path).operations[0].raw_body == "{not json"


def test_load_manifest_raw_body_with_params_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(
                tmp_path,
                [
                    {
                        "id": "a",
                        "kind": "rest",
                        "method": "POST",
                        "route": "/api/memory",
                        "raw_body": "{not json",
                        "params": {"kind": "rule"},
                    }
                ],
            )
        )


def test_load_manifest_raw_body_on_non_rest_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(tmp_path, [{"id": "a", "kind": "cli", "command": "parse", "raw_body": "x"}])
        )


def test_load_manifest_parses_expect_error_on_mcp(tmp_path: Path):
    path = _write_manifest(
        tmp_path, [{"id": "a", "kind": "mcp", "tool": "get_symbol", "expect_error": True}]
    )
    assert load_manifest(path).operations[0].expect_error is True


def test_load_manifest_expect_error_on_non_mcp_raises(tmp_path: Path):
    with pytest.raises(ManifestError):
        load_manifest(
            _write_manifest(
                tmp_path,
                [{"id": "a", "kind": "rest", "method": "GET", "route": "/x", "expect_error": True}],
            )
        )


def test_discover_fixtures_finds_smoke_fixture():
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    fixtures = discover_fixtures(fixtures_dir)
    names = [f.name for f in fixtures]
    assert "smoke" in names
    smoke = next(f for f in fixtures if f.name == "smoke")
    assert len(smoke.operations) == 5


def test_discover_fixtures_raises_when_none_found(tmp_path: Path):
    with pytest.raises(ManifestError):
        discover_fixtures(tmp_path)
