from __future__ import annotations

from harness.diff import DiffEntry, apply_ignore_allowlist, diff_case, diff_values, path_matches


def test_diff_values_identical_returns_nothing():
    assert list(diff_values({"a": 1, "b": [1, 2]}, {"a": 1, "b": [1, 2]})) == []


def test_diff_values_dict_missing_and_extra_keys():
    entries = list(diff_values({"a": 1, "b": 2}, {"a": 1, "c": 3}))
    kinds = {(e.path, e.kind) for e in entries}
    assert ("$.b", "missing_in_candidate") in kinds
    assert ("$.c", "extra_in_candidate") in kinds


def test_diff_values_list_length_mismatch():
    entries = list(diff_values([1, 2, 3], [1, 2]))
    assert entries == [DiffEntry(path="$[2]", kind="missing_in_candidate", oracle=3, candidate=None)]


def test_diff_values_type_mismatch():
    entries = list(diff_values({"a": 1}, {"a": "1"}))
    assert len(entries) == 1
    assert entries[0].kind == "type_mismatch"


def test_diff_values_value_mismatch_nested():
    entries = list(diff_values({"a": {"b": 1}}, {"a": {"b": 2}}))
    assert len(entries) == 1
    assert entries[0].path == "$.a.b"
    assert entries[0].kind == "value_mismatch"


def test_path_matches_exact():
    assert path_matches("$.a.b", "$.a.b")
    assert not path_matches("$.a.b", "$.a.c")


def test_path_matches_index_wildcard():
    assert path_matches("$.items[*].id", "$.items[3].id")
    assert not path_matches("$.items[*].id", "$.items[3].name")


def test_path_matches_trailing_wildcard():
    assert path_matches("$.meta.*", "$.meta.anything.nested")
    assert not path_matches("$.meta.*", "$.other.anything")


def test_apply_ignore_allowlist_splits_matched_and_unmatched():
    entries = list(diff_values({"a": 1, "b": 2}, {"a": 9, "b": 9}))
    remaining, ignored = apply_ignore_allowlist(entries, ["$.a"])
    assert [e.path for e in ignored] == ["$.a"]
    assert [e.path for e in remaining] == ["$.b"]


def test_diff_case_equal_when_all_diffs_ignored():
    result = diff_case("case1", {"a": 1, "id": "x"}, {"a": 1, "id": "y"}, ["$.id"])
    assert result.equal
    assert result.entries == []
    assert len(result.ignored) == 1


def test_diff_case_not_equal_when_unignored_diff_remains():
    result = diff_case("case1", {"a": 1, "b": 1}, {"a": 1, "b": 2}, ["$.id"])
    assert not result.equal
    assert len(result.entries) == 1
