"""Shared fixtures for the cluster tests: fake member repos with real graphs.

Member graphs are written directly rather than extracted. Extraction is slow,
and none of these tests are about the extractor — they need a member whose node
ids, source files and communities are known exactly so a composition assertion
can name them.
"""
from __future__ import annotations

import json
from pathlib import Path


def write_member(
    root: Path,
    tag: str,
    *,
    nodes: list[dict] | None = None,
    links: list[dict] | None = None,
    origin: str = "",
    multigraph: bool = False,
) -> Path:
    """Create `<root>/<tag>/` as a member repo with a kb-core-out/graph.json."""
    repo = Path(root) / tag
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "lib.py").write_text("def start():\n    parse()\n", encoding="utf-8")

    if nodes is None:
        nodes = [
            {"id": "src_lib", "label": "lib.py", "file_type": "code",
             "source_file": "src/lib.py", "source_location": "L1", "community": 0},
            {"id": "src_lib_start", "label": "start()", "file_type": "code",
             "source_file": "src/lib.py", "source_location": "L1", "community": 0},
            {"id": "src_lib_parse", "label": "parse()", "file_type": "code",
             "source_file": "src/lib.py", "source_location": "L5", "community": 1},
        ]
    if links is None:
        links = [
            {"source": "src_lib", "target": "src_lib_start",
             "relation": "contains", "confidence": "EXTRACTED",
             "source_file": "src/lib.py", "source_location": "L1"},
            {"source": "src_lib_start", "target": "src_lib_parse",
             "relation": "calls", "confidence": "EXTRACTED",
             "source_file": "src/lib.py", "source_location": "L2"},
        ]

    out = repo / "kb-core-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(
        json.dumps({
            "directed": True, "multigraph": multigraph, "graph": {},
            "nodes": nodes, "links": links,
        }, indent=2),
        encoding="utf-8",
    )

    git = repo / ".git"
    git.mkdir(exist_ok=True)
    config = '[core]\n\trepositoryformatversion = 0\n'
    if origin:
        config += f'[remote "origin"]\n\turl = {origin}\n'
    (git / "config").write_text(config, encoding="utf-8")
    return repo


def write_spec(cluster_dir: Path, payload: dict) -> Path:
    cluster_dir = Path(cluster_dir)
    cluster_dir.mkdir(parents=True, exist_ok=True)
    path = cluster_dir / "cluster.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def two_member_cluster(tmp_path: Path, **spec_extra) -> Path:
    """`<tmp>/cluster` with members `alpha` and `beta` beside it, both resolvable."""
    write_member(tmp_path, "alpha")
    write_member(tmp_path, "beta")
    cluster_dir = tmp_path / "cluster"
    payload = {
        "schema_version": 1,
        "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
    }
    payload.update(spec_extra)
    write_spec(cluster_dir, payload)
    return cluster_dir
