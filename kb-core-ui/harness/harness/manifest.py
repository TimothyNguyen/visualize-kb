from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from harness.canonical import NORMALIZERS
from harness.errors import ManifestError

_VALID_KINDS = {"cli", "rest", "mcp"}
_VALID_CAPTURES = {"stdout_exit", "json_body_status", "json_result"}


@dataclass(frozen=True)
class Operation:
    id: str
    kind: str
    command: str | None = None
    args: dict[str, str] = field(default_factory=dict)
    method: str | None = None
    route: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    tool: str | None = None
    capture: str = "stdout_exit"
    normalizers: list[str] = field(default_factory=list)
    ignore_fields: list[str] = field(default_factory=list)
    setup: list["Operation"] = field(default_factory=list)


@dataclass(frozen=True)
class Fixture:
    name: str
    manifest_path: Path
    repo_dir: Path
    operations: list[Operation]


def _parse_operation(raw: dict, manifest_path: Path) -> Operation:
    op_id = raw.get("id")
    if not op_id:
        raise ManifestError(f"{manifest_path}: operation missing 'id'")

    kind = raw.get("kind")
    if kind not in _VALID_KINDS:
        raise ManifestError(f"{manifest_path}: operation {op_id!r} has invalid kind {kind!r}")

    if kind == "cli" and not raw.get("command"):
        raise ManifestError(f"{manifest_path}: cli operation {op_id!r} missing 'command'")
    if kind == "rest" and (not raw.get("method") or not raw.get("route")):
        raise ManifestError(f"{manifest_path}: rest operation {op_id!r} missing 'method'/'route'")
    if kind == "mcp" and not raw.get("tool"):
        raise ManifestError(f"{manifest_path}: mcp operation {op_id!r} missing 'tool'")

    capture = raw.get("capture", "stdout_exit")
    if capture not in _VALID_CAPTURES:
        raise ManifestError(f"{manifest_path}: operation {op_id!r} has invalid capture {capture!r}")

    normalizers = raw.get("normalizers", [])
    for name in normalizers:
        if name not in NORMALIZERS:
            raise ManifestError(
                f"{manifest_path}: operation {op_id!r} references unknown normalizer {name!r}"
            )

    ignore_fields = raw.get("ignore_fields", [])
    for pattern in ignore_fields:
        if not pattern or not pattern.startswith("$"):
            raise ManifestError(
                f"{manifest_path}: operation {op_id!r} has invalid ignore_fields pattern {pattern!r}"
            )

    setup_raw = raw.get("setup", [])
    setup = [_parse_operation(s, manifest_path) for s in setup_raw]

    return Operation(
        id=op_id,
        kind=kind,
        command=raw.get("command"),
        args=raw.get("args", {}),
        method=raw.get("method"),
        route=raw.get("route"),
        params=raw.get("params", {}),
        tool=raw.get("tool"),
        capture=capture,
        normalizers=normalizers,
        ignore_fields=ignore_fields,
        setup=setup,
    )


def load_manifest(path: Path) -> Fixture:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{path}: failed to read/parse manifest: {exc}") from exc

    name = raw.get("name")
    if not name:
        raise ManifestError(f"{path}: manifest missing 'name'")

    repo_rel = raw.get("repo")
    if not repo_rel:
        raise ManifestError(f"{path}: manifest missing 'repo'")
    repo_dir = (path.parent / repo_rel).resolve()
    if not repo_dir.is_dir():
        raise ManifestError(f"{path}: repo dir {repo_dir} does not exist")

    operations_raw = raw.get("operations", [])
    if not operations_raw:
        raise ManifestError(f"{path}: manifest has no operations")
    operations = [_parse_operation(op, path) for op in operations_raw]

    seen_ids = set()
    for op in operations:
        if op.id in seen_ids:
            raise ManifestError(f"{path}: duplicate operation id {op.id!r}")
        seen_ids.add(op.id)

    return Fixture(name=name, manifest_path=path, repo_dir=repo_dir, operations=operations)


def discover_fixtures(fixtures_dir: Path) -> list[Fixture]:
    fixtures_dir = Path(fixtures_dir)
    manifests = sorted(fixtures_dir.glob("*/manifest.json"))
    if not manifests:
        raise ManifestError(f"no manifest.json found under {fixtures_dir}")
    return [load_manifest(p) for p in manifests]
