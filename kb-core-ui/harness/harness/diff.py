from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence


@dataclass(frozen=True)
class DiffEntry:
    path: str
    kind: str  # "value_mismatch" | "type_mismatch" | "missing_in_candidate" | "extra_in_candidate"
    oracle: Any
    candidate: Any


@dataclass(frozen=True)
class DiffResult:
    case_id: str
    equal: bool
    entries: list[DiffEntry] = field(default_factory=list)
    ignored: list[DiffEntry] = field(default_factory=list)


def _child_path(path: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}"


def diff_values(oracle: Any, candidate: Any, path: str = "$") -> Iterator[DiffEntry]:
    if isinstance(oracle, dict) and isinstance(candidate, dict):
        for key in oracle:
            child = _child_path(path, key)
            if key not in candidate:
                yield DiffEntry(child, "missing_in_candidate", oracle[key], None)
            else:
                yield from diff_values(oracle[key], candidate[key], child)
        for key in candidate:
            if key not in oracle:
                yield DiffEntry(_child_path(path, key), "extra_in_candidate", None, candidate[key])
        return

    if isinstance(oracle, list) and isinstance(candidate, list):
        common = min(len(oracle), len(candidate))
        for i in range(common):
            yield from diff_values(oracle[i], candidate[i], _child_path(path, i))
        for i in range(common, len(oracle)):
            yield DiffEntry(_child_path(path, i), "missing_in_candidate", oracle[i], None)
        for i in range(common, len(candidate)):
            yield DiffEntry(_child_path(path, i), "extra_in_candidate", None, candidate[i])
        return

    if type(oracle) is not type(candidate):
        yield DiffEntry(path, "type_mismatch", oracle, candidate)
        return

    if oracle != candidate:
        yield DiffEntry(path, "value_mismatch", oracle, candidate)


def path_matches(pattern: str, path: str) -> bool:
    escaped = re.escape(pattern)
    escaped = escaped.replace(re.escape("[*]"), r"\[\d+\]")
    star = re.escape("*")
    if escaped.endswith(star):
        escaped = escaped[: -len(star)] + ".*"
    return re.fullmatch(escaped, path) is not None


def apply_ignore_allowlist(
    entries: list[DiffEntry], ignore_fields: Sequence[str]
) -> tuple[list[DiffEntry], list[DiffEntry]]:
    remaining: list[DiffEntry] = []
    ignored: list[DiffEntry] = []
    for entry in entries:
        if any(path_matches(pattern, entry.path) for pattern in ignore_fields):
            ignored.append(entry)
        else:
            remaining.append(entry)
    return remaining, ignored


def diff_case(case_id: str, oracle: Any, candidate: Any, ignore_fields: Sequence[str]) -> DiffResult:
    all_entries = list(diff_values(oracle, candidate))
    remaining, ignored = apply_ignore_allowlist(all_entries, ignore_fields)
    return DiffResult(case_id=case_id, equal=not remaining, entries=remaining, ignored=ignored)
