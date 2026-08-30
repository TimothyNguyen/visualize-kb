"""Compose several repository graphs into one cluster graph.

A cluster is a directory holding a `cluster.json` spec that names member repos
and declares the cross-repo links between them — the calls, mirrored files and
shared queues that no single-repo extraction can see because the other end of
the edge lives in a different checkout.

`build_cluster` resolves each member, loads its graph, namespaces it by tag,
composes the lot into one directed graph, materialises the declared links, and
writes `graph.json` / `cluster-manifest.json` / `CLUSTER_REPORT.md` into the
cluster's own `kb-core-out/`. Every member also gets a `cluster-ref.json` marker
so `--cluster` works from inside any of them.

Composition is directed end to end. An undirected intermediate canonicalises
endpoint order by node insertion, which reverses roughly half of the caller →
callee edges — the exact relationship a blast-radius query depends on.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from kb_core.cluster_ref import normalize_git_url, origin_url

SCHEMA_VERSION = 1

# Reserved for the hub nodes a `shared_resource` link creates. A member tagged
# `cluster` would produce ids indistinguishable from them.
RESERVED_TAG = "cluster"

DEFAULT_MEMBER_GRAPH = "kb-core-out/graph.json"
SPEC_NAMES = ("cluster.json", "cluster.yaml", "cluster.yml")
LOCAL_CONFIG_NAME = "cluster.local.json"

# Declared link type -> the graph relation it becomes. `shared_resource` is
# absent: it is not a direct edge but a hub node plus one `uses` edge per
# referent, so it has no single relation.
LINK_RELATIONS = {
    "api_call": "calls_api",
    "mirrored_file": "mirrors",
    "depends_on": "depends_on",
    "references": "references",
}
SHARED_RESOURCE = "shared_resource"
LINK_TYPES = (*LINK_RELATIONS, SHARED_RESOURCE)
SHARED_RESOURCE_RELATION = "uses"

ON_MISSING_MODES = ("warn", "create", "error")
DIRECTIONS = ("forward", "both")
GRAPH_MODES = ("simple", "multi")

SELECTOR_KINDS = ("id", "file", "label")


class ClusterSpecError(ValueError):
    """A cluster spec is malformed, or its members cannot be resolved."""


class AmbiguousSelectorError(ClusterSpecError):
    """A link selector matched more than one node, so the link is undecidable."""


@dataclass
class ClusterMember:
    tag: str
    url: str = ""
    path: str = ""
    graph: str = DEFAULT_MEMBER_GRAPH


@dataclass
class ClusterLink:
    type: str
    from_: dict | None = None
    to: dict | None = None
    name: str = ""
    kind: str = ""
    referents: list[dict] = field(default_factory=list)
    on_missing: str = ""
    direction: str = "forward"
    note: str = ""


@dataclass
class ClusterSpec:
    name: str
    members: list[ClusterMember] = field(default_factory=list)
    links: list[ClusterLink] = field(default_factory=list)
    default_on_missing: str = "warn"
    auto_link_externals: bool = True
    auto_link_packages: bool = False
    graph_mode: str = "simple"
    search_roots: list[str] = field(default_factory=list)
    url: str = ""

    def member(self, tag: str) -> ClusterMember | None:
        for m in self.members:
            if m.tag == tag:
                return m
        return None

    @property
    def tags(self) -> list[str]:
        return [m.tag for m in self.members]


@dataclass
class LinkReport:
    type: str
    status: str  # linked | created | skipped | duplicate
    detail: str
    edges_added: int = 0


@dataclass
class MemberComposition:
    tag: str
    path: Path
    graph_path: Path
    nodes: int
    edges: int
    community_offset: int


# --------------------------------------------------------------------------
# Spec I/O
# --------------------------------------------------------------------------


def validate_member_tag(tag) -> str:
    if not isinstance(tag, str) or not tag.strip():
        raise ClusterSpecError("Each member needs a non-empty string 'tag'.")
    tag = tag.strip()
    if "::" in tag:
        raise ClusterSpecError(
            f"Member tag {tag!r} contains '::', which separates the tag from the "
            f"node id in every composed node. Choose a tag without it."
        )
    if tag == RESERVED_TAG:
        raise ClusterSpecError(
            f"Member tag {RESERVED_TAG!r} is reserved for shared-resource hub "
            f"nodes. Use --as <tag> to pick a different name."
        )
    if any(c in tag for c in "/\\"):
        raise ClusterSpecError(f"Member tag {tag!r} cannot contain a path separator.")
    return tag


def find_spec_file(cluster_dir: Path) -> Path | None:
    for name in SPEC_NAMES:
        candidate = Path(cluster_dir) / name
        if candidate.is_file():
            return candidate
    return None


def _read_spec_payload(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ClusterSpecError(
                f"{path.name} is YAML but pyyaml is not installed. "
                f"Install it with 'pip install pyyaml', or rename the spec to "
                f"cluster.json and convert it to JSON."
            ) from exc
        payload = yaml.safe_load(text)
    else:
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise ClusterSpecError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClusterSpecError(f"{path.name} must contain a JSON/YAML object at the top level.")
    return payload


def _parse_selector(raw, where: str) -> dict:
    """Normalise a link endpoint into `{'member': tag, 'kind': ..., 'value': ...}`.

    Accepts the explicit object form (`{"member": "a", "label": "f()"}`) and the
    compact string form (`"a:label:f()"`). The compact form splits at most twice
    so a selector value may itself contain colons — which file paths on Windows
    and Rust paths like `mod::f` routinely do.
    """
    if isinstance(raw, str):
        parts = raw.split(":", 2)
        if len(parts) != 3:
            raise ClusterSpecError(
                f"{where}: selector {raw!r} must be 'MEMBER:KIND:VALUE' "
                f"(KIND is one of {', '.join(SELECTOR_KINDS)}), or an object "
                f"like {{\"member\": \"tag\", \"label\": \"name\"}}."
            )
        member, kind, value = parts
        raw = {"member": member, kind: value}
    if not isinstance(raw, dict):
        raise ClusterSpecError(f"{where}: selector must be an object or a string, got {type(raw).__name__}.")

    member = raw.get("member") or raw.get("tag")
    if not isinstance(member, str) or not member.strip():
        raise ClusterSpecError(f"{where}: selector needs a 'member' tag naming which repo it points into.")
    present = [k for k in SELECTOR_KINDS if raw.get(k)]
    if len(present) != 1:
        raise ClusterSpecError(
            f"{where}: selector needs exactly one of {', '.join(SELECTOR_KINDS)}, got "
            f"{present or 'none'}."
        )
    kind = present[0]
    return {"member": member.strip(), "kind": kind, "value": str(raw[kind])}


def _parse_link(raw, index: int) -> ClusterLink:
    where = f"links[{index}]"
    if not isinstance(raw, dict):
        raise ClusterSpecError(f"{where} must be an object.")
    ltype = raw.get("type")
    if ltype not in LINK_TYPES:
        raise ClusterSpecError(
            f"{where}: unknown link type {ltype!r}. Supported: {', '.join(sorted(LINK_TYPES))}."
        )
    on_missing = raw.get("on_missing") or ""
    if on_missing and on_missing not in ON_MISSING_MODES:
        raise ClusterSpecError(
            f"{where}: on_missing must be one of {', '.join(ON_MISSING_MODES)}, got {on_missing!r}."
        )
    direction = raw.get("direction") or "forward"
    if direction not in DIRECTIONS:
        raise ClusterSpecError(
            f"{where}: direction must be one of {', '.join(DIRECTIONS)}, got {direction!r}."
        )

    link = ClusterLink(
        type=ltype,
        name=str(raw.get("name") or ""),
        kind=str(raw.get("kind") or ""),
        on_missing=on_missing,
        direction=direction,
        note=str(raw.get("note") or ""),
    )
    if ltype == SHARED_RESOURCE:
        if not link.name:
            raise ClusterSpecError(f"{where}: a shared_resource link needs a 'name' to identify the resource.")
        referents = raw.get("referents")
        if not isinstance(referents, list) or not referents:
            raise ClusterSpecError(
                f"{where}: a shared_resource link needs a non-empty 'referents' list of selectors."
            )
        link.referents = [_parse_selector(r, f"{where}.referents[{i}]") for i, r in enumerate(referents)]
        link.kind = link.kind or "resource"
    else:
        if raw.get("from") is None or raw.get("to") is None:
            raise ClusterSpecError(f"{where}: a {ltype} link needs both 'from' and 'to' selectors.")
        link.from_ = _parse_selector(raw["from"], f"{where}.from")
        link.to = _parse_selector(raw["to"], f"{where}.to")
    return link


def load_spec(cluster_dir: Path) -> ClusterSpec:
    cluster_dir = Path(cluster_dir)
    path = find_spec_file(cluster_dir)
    if path is None:
        raise ClusterSpecError(
            f"No cluster spec in {cluster_dir}. Expected one of {', '.join(SPEC_NAMES)}. "
            f"Run 'kb-core cluster init' there first."
        )
    payload = _read_spec_payload(path)

    version = payload.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ClusterSpecError(
            f"{path.name} declares schema_version {version!r}, but this kb-core "
            f"understands version {SCHEMA_VERSION}. Upgrade kb-core, or fix the spec."
        )

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ClusterSpecError(f"{path.name} needs a non-empty string 'name'.")

    raw_members = payload.get("members", [])
    if not isinstance(raw_members, list):
        raise ClusterSpecError(f"{path.name}: 'members' must be a list.")
    members: list[ClusterMember] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_members):
        if not isinstance(raw, dict):
            raise ClusterSpecError(f"{path.name}: members[{i}] must be an object.")
        tag = validate_member_tag(raw.get("tag"))
        if tag in seen:
            raise ClusterSpecError(
                f"{path.name}: duplicate member tag {tag!r}. Every member needs a "
                f"unique tag — it namespaces that repo's node ids."
            )
        seen.add(tag)
        members.append(
            ClusterMember(
                tag=tag,
                url=str(raw.get("url") or ""),
                path=str(raw.get("path") or ""),
                graph=str(raw.get("graph") or DEFAULT_MEMBER_GRAPH),
            )
        )

    raw_links = payload.get("links", [])
    if not isinstance(raw_links, list):
        raise ClusterSpecError(f"{path.name}: 'links' must be a list.")
    links = [_parse_link(raw, i) for i, raw in enumerate(raw_links)]

    defaults = payload.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ClusterSpecError(f"{path.name}: 'defaults' must be an object.")
    default_on_missing = defaults.get("on_missing", "warn")
    if default_on_missing not in ON_MISSING_MODES:
        raise ClusterSpecError(
            f"{path.name}: defaults.on_missing must be one of {', '.join(ON_MISSING_MODES)}, "
            f"got {default_on_missing!r}."
        )

    auto_links = payload.get("auto_links", {})
    if not isinstance(auto_links, dict):
        raise ClusterSpecError(f"{path.name}: 'auto_links' must be an object.")

    graph_mode = payload.get("graph_mode", "simple")
    if graph_mode not in GRAPH_MODES:
        raise ClusterSpecError(
            f"{path.name}: graph_mode must be one of {', '.join(GRAPH_MODES)}, got {graph_mode!r}."
        )

    search_roots = payload.get("search_roots", [])
    if not isinstance(search_roots, list):
        raise ClusterSpecError(f"{path.name}: 'search_roots' must be a list of directory paths.")

    spec = ClusterSpec(
        name=name.strip(),
        members=members,
        links=links,
        default_on_missing=default_on_missing,
        auto_link_externals=bool(auto_links.get("externals", True)),
        auto_link_packages=bool(auto_links.get("packages", False)),
        graph_mode=graph_mode,
        search_roots=[str(r) for r in search_roots],
        url=str(payload.get("url") or ""),
    )

    known = set(spec.tags)
    for i, link in enumerate(spec.links):
        for sel in _link_selectors(link):
            if sel["member"] not in known:
                raise ClusterSpecError(
                    f"links[{i}]: selector names member {sel['member']!r}, which is not in "
                    f"this cluster. Members: {', '.join(sorted(known)) or '(none)'}."
                )
    return spec


def _link_selectors(link: ClusterLink) -> list[dict]:
    if link.type == SHARED_RESOURCE:
        return list(link.referents)
    return [s for s in (link.from_, link.to) if s]


def _selector_to_dict(sel: dict) -> dict:
    return {"member": sel["member"], sel["kind"]: sel["value"]}


def spec_to_dict(spec: ClusterSpec) -> dict:
    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "name": spec.name,
        "members": [
            {k: v for k, v in
             (("tag", m.tag), ("url", m.url), ("path", m.path), ("graph", m.graph))
             if v}
            for m in spec.members
        ],
        "links": [],
        "defaults": {"on_missing": spec.default_on_missing},
        "auto_links": {
            "externals": spec.auto_link_externals,
            "packages": spec.auto_link_packages,
        },
        "graph_mode": spec.graph_mode,
    }
    if spec.url:
        payload["url"] = spec.url
    if spec.search_roots:
        payload["search_roots"] = list(spec.search_roots)
    for link in spec.links:
        entry: dict = {"type": link.type}
        if link.type == SHARED_RESOURCE:
            entry["name"] = link.name
            if link.kind:
                entry["kind"] = link.kind
            entry["referents"] = [_selector_to_dict(s) for s in link.referents]
        else:
            entry["from"] = _selector_to_dict(link.from_ or {})
            entry["to"] = _selector_to_dict(link.to or {})
            if link.name:
                entry["name"] = link.name
        if link.on_missing:
            entry["on_missing"] = link.on_missing
        if link.direction != "forward":
            entry["direction"] = link.direction
        if link.note:
            entry["note"] = link.note
        payload["links"].append(entry)
    return payload


def save_spec(cluster_dir: Path, spec: ClusterSpec) -> Path:
    from kb_core.paths import write_json_atomic

    cluster_dir = Path(cluster_dir)
    cluster_dir.mkdir(parents=True, exist_ok=True)
    path = find_spec_file(cluster_dir)
    if path is not None and path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ClusterSpecError(
                f"Cannot rewrite {path.name}: pyyaml is not installed. "
                f"Install it with 'pip install pyyaml'."
            ) from exc
        from kb_core.paths import write_text_atomic

        write_text_atomic(path, yaml.safe_dump(spec_to_dict(spec), sort_keys=False))
        return path
    path = cluster_dir / "cluster.json"
    write_json_atomic(path, spec_to_dict(spec), indent=2)
    return path


def load_local_config(cluster_dir: Path) -> dict:
    """Machine-local member paths, never committed. Fail-open on a bad file."""
    path = Path(cluster_dir) / LOCAL_CONFIG_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {"paths": {}}
    if not isinstance(payload, dict):
        return {"paths": {}}
    paths = payload.get("paths")
    return {"paths": paths if isinstance(paths, dict) else {}}


def save_local_config(cluster_dir: Path, config: dict) -> Path:
    from kb_core.paths import write_json_atomic

    path = Path(cluster_dir) / LOCAL_CONFIG_NAME
    write_json_atomic(path, {"paths": config.get("paths", {})}, indent=2)
    return path


# --------------------------------------------------------------------------
# Member resolution
# --------------------------------------------------------------------------


def _norm(path) -> Path:
    # abspath, not resolve: resolve() dereferences symlinks, and a checkout
    # reached through a symlinked worktree would then report source paths under
    # the real location, which no longer match what the member's own graph
    # recorded. Absolute rather than merely normalized because callers compare
    # and relativize these — with `--dir .`, `cluster_dir.parent` otherwise
    # collapses back to `.` and two spellings of one directory compare unequal.
    return Path(os.path.abspath(str(path)))


def _looks_like_repo(candidate: Path) -> bool:
    return candidate.is_dir() and (candidate / ".git").exists()


def resolve_member_path(
    spec: ClusterSpec,
    member: ClusterMember,
    cluster_dir: Path,
    local_config: dict | None = None,
) -> Path | None:
    """Where `member` is checked out, or None.

    Precedence, most explicit first: the machine-local override, the spec's own
    path hint, a scan of the declared search roots, then sibling directories of
    the cluster matched by normalized origin URL.
    """
    cluster_dir = _norm(cluster_dir)
    local_config = local_config or {"paths": {}}

    override = local_config.get("paths", {}).get(member.tag)
    if override:
        candidate = _norm(cluster_dir / str(override))
        if candidate.is_dir():
            return candidate

    if member.path:
        candidate = _norm(cluster_dir / member.path)
        if candidate.is_dir():
            return candidate

    wanted = normalize_git_url(member.url)
    search_dirs: list[Path] = []
    for root in spec.search_roots:
        root_path = _norm(cluster_dir / root)
        try:
            search_dirs.extend(sorted(p for p in root_path.iterdir() if p.is_dir()))
        except OSError:
            continue
    try:
        search_dirs.extend(sorted(p for p in cluster_dir.parent.iterdir() if p.is_dir()))
    except OSError:
        pass

    by_name = [p for p in search_dirs if p.name == member.tag and p.is_dir()]
    if len(by_name) == 1:
        return _norm(by_name[0])

    if wanted:
        by_url = [p for p in search_dirs if _looks_like_repo(p) and normalize_git_url(origin_url(p)) == wanted]
        # Deduplicate: search_roots and the sibling scan can surface the same dir.
        unique = sorted({str(_norm(p)) for p in by_url})
        if len(unique) == 1:
            return Path(unique[0])
    return None


def member_graph_path(member: ClusterMember, member_path: Path) -> Path:
    return _norm(Path(member_path) / (member.graph or DEFAULT_MEMBER_GRAPH))


def resolve_all_members(spec: ClusterSpec, cluster_dir: Path) -> dict[str, Path]:
    """Locate every member, or raise with the specific fix for the first failure."""
    cluster_dir = _norm(cluster_dir)
    if not spec.members:
        raise ClusterSpecError(
            f"Cluster {spec.name!r} has no members. Add one with "
            f"'kb-core cluster add <path-or-url>'."
        )
    local_config = load_local_config(cluster_dir)
    resolved: dict[str, Path] = {}
    for member in spec.members:
        path = resolve_member_path(spec, member, cluster_dir, local_config)
        if path is None:
            raise ClusterSpecError(
                f"Cannot find member {member.tag!r} on this machine. "
                f"Point at it with 'kb-core cluster locate {member.tag} <path>'."
            )
        if _norm(path) == cluster_dir:
            raise ClusterSpecError(
                f"Member {member.tag!r} resolves to the cluster directory itself. "
                f"A cluster cannot contain itself; move the spec to its own directory."
            )
        graph_path = member_graph_path(member, path)
        if not graph_path.is_file():
            raise ClusterSpecError(
                f"Member {member.tag!r} at {path} has no graph at {graph_path}. "
                f"Run 'kb-core extract .' in {path} first."
            )
        resolved[member.tag] = _norm(path)
    return resolved


# --------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------


def compose_members(
    spec: ClusterSpec, resolved: dict[str, Path]
) -> tuple[nx.Graph, list[MemberComposition]]:
    """Namespace every member graph by tag and compose them into one graph."""
    from kb_core.build import load_graph_json, merge_prefixed_into, prefix_graph_for_global, promote_to_multidigraph

    multi = spec.graph_mode == "multi"
    if multi:
        from kb_core.multigraph_compat import require_multigraph_capabilities

        require_multigraph_capabilities()

    G: nx.Graph = nx.MultiDiGraph() if multi else nx.DiGraph()
    G.graph["cluster"] = spec.name
    G.graph["directed"] = True
    stats: list[MemberComposition] = []
    community_offset = 0

    # Tag order, not spec order: composition must not depend on which member the
    # user happened to add first, or two machines building the same cluster get
    # different community ids.
    for member in sorted(spec.members, key=lambda m: m.tag):
        member_path = resolved[member.tag]
        graph_path = member_graph_path(member, member_path)
        try:
            member_graph = load_graph_json(graph_path, preserve_type=True, directed=True)
        except Exception as exc:
            raise ClusterSpecError(
                f"Member {member.tag!r} graph at {graph_path} could not be read: {exc}. "
                f"Re-run 'kb-core extract .' in {member_path}."
            ) from exc

        if multi:
            member_graph = promote_to_multidigraph(member_graph)

        prefixed = prefix_graph_for_global(member_graph, member.tag, community_offset=community_offset)
        if spec.auto_link_externals:
            merge_prefixed_into(G, prefixed)
        else:
            G = nx.compose(G, prefixed)

        local_cids = [
            d["local_community"] if "local_community" in d else d.get("community")
            for _, d in prefixed.nodes(data=True)
        ]
        highest = max((c for c in local_cids if isinstance(c, int)), default=-1)
        stats.append(
            MemberComposition(
                tag=member.tag,
                path=member_path,
                graph_path=graph_path,
                nodes=member_graph.number_of_nodes(),
                edges=member_graph.number_of_edges(),
                community_offset=community_offset,
            )
        )
        community_offset += highest + 1

    return G, stats


def communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Rebuild the `{community_id: [node_ids]}` view from node attributes."""
    communities: dict[int, list[str]] = {}
    for node, data in G.nodes(data=True):
        cid = data.get("community")
        if isinstance(cid, int):
            communities.setdefault(cid, []).append(str(node))
    for members in communities.values():
        members.sort()
    return communities


# --------------------------------------------------------------------------
# Selector resolution and linking
# --------------------------------------------------------------------------


class _SelectorIndex:
    """Per-member lookup tables, built once per cluster build."""

    def __init__(self, G: nx.Graph):
        self.by_local_id: dict[tuple[str, str], list[str]] = {}
        self.by_label: dict[tuple[str, str], list[str]] = {}
        self.by_label_ci: dict[tuple[str, str], list[str]] = {}
        self.sourced: dict[str, list[tuple[str, str]]] = {}
        self.externals: dict[tuple[str, str], list[str]] = {}
        for node, data in G.nodes(data=True):
            repo = str(data.get("repo") or "")
            if not repo:
                continue
            node = str(node)
            local_id = str(data.get("local_id") or node.split("::", 1)[-1])
            self.by_local_id.setdefault((repo, local_id), []).append(node)
            label = str(data.get("label") or "")
            source_file = str(data.get("source_file") or "")
            if label:
                self.by_label.setdefault((repo, label), []).append(node)
                self.by_label_ci.setdefault((repo, label.casefold()), []).append(node)
                if not source_file:
                    self.externals.setdefault((repo, label.casefold()), []).append(node)
            if source_file:
                self.sourced.setdefault(repo, []).append((source_file, node))

    def _file_matches(self, G: nx.Graph, repo: str, query: str) -> list[str]:
        wanted = query.replace("\\", "/").strip("/").casefold()
        hits = [
            node
            for source_file, node in self.sourced.get(repo, [])
            if _path_suffix_match(source_file, wanted)
        ]
        if len(hits) <= 1:
            return hits
        # A file selector means "the file", not every symbol declared in it. The
        # file-level node is anchored at L1 and labelled with the basename — L1
        # alone is not enough, since a symbol declared on the first line shares
        # it. Mirrors affected._prefer_file_node.
        basename = wanted.rsplit("/", 1)[-1]
        at_l1 = [n for n in hits if str(G.nodes[n].get("source_location") or "") == "L1"]
        named = [n for n in at_l1 if str(G.nodes[n].get("label") or "").casefold() == basename]
        for narrowed in (named, at_l1):
            if len(narrowed) == 1:
                return narrowed
        return hits


def _path_suffix_match(source_file: str, wanted: str) -> bool:
    """Suffix match on whole path segments, so 'x.py' never matches 'prefix_x.py'."""
    normalized = source_file.replace("\\", "/").strip("/").casefold()
    if normalized == wanted:
        return True
    return normalized.endswith("/" + wanted)


def resolve_selector(G: nx.Graph, index: _SelectorIndex, sel: dict, where: str) -> str | None:
    """The single node a selector names, or None when it matches nothing."""
    member, kind, value = sel["member"], sel["kind"], sel["value"]
    if kind == "id":
        hits = index.by_local_id.get((member, value), [])
    elif kind == "file":
        hits = index._file_matches(G, member, value)
    else:
        hits = (
            index.by_label.get((member, value))
            or index.by_label_ci.get((member, value.casefold()))
            or index.externals.get((member, value.casefold()))
            or []
        )
    if not hits:
        return None
    if len(hits) > 1:
        sample = ", ".join(sorted(hits)[:4])
        raise AmbiguousSelectorError(
            f"{where}: selector {kind}={value!r} in member {member!r} matches "
            f"{len(hits)} nodes ({sample}...). Narrow it with an 'id' selector."
        )
    return hits[0]


def _create_placeholder(G: nx.Graph, sel: dict) -> str:
    """Mint an external stand-in so a declared link survives a not-yet-extracted end."""
    from kb_core.ids import normalize_id

    member, value = sel["member"], sel["value"]
    node_id = f"{member}::declared::{normalize_id(value)}"
    if node_id not in G:
        G.add_node(
            node_id,
            label=value,
            file_type="external",
            repo=member,
            local_id=f"declared::{normalize_id(value)}",
            origin="cluster_spec",
        )
    return node_id


def _link_attrs(link: ClusterLink, relation: str) -> dict:
    attrs = {
        "relation": relation,
        "confidence": "DECLARED",
        "origin": "cluster_spec",
        "cluster_link": link.type,
    }
    if link.name:
        attrs["cluster_link_name"] = link.name
    if link.note:
        attrs["context"] = link.note
    return attrs


def _add_link_edge(
    G: nx.Graph, src: str, tgt: str, attrs: dict, *, multi: bool, where: str
) -> int:
    """Materialise one declared edge, refusing silent overwrites. Returns 1 or 0."""
    attrs = dict(attrs, _src=src, _tgt=tgt)
    if multi:
        from kb_core.build import stable_edge_key

        key = stable_edge_key(src, tgt, attrs)
        if G.has_edge(src, tgt, key):
            raise ClusterSpecError(
                f"{where}: this exact link is declared twice "
                f"({src} -[{attrs['relation']}]-> {tgt}). Remove the duplicate."
            )
        G.add_edge(src, tgt, key=key, **attrs)
        return 1
    if G.has_edge(src, tgt):
        existing = str(G.edges[src, tgt].get("relation") or "")
        if existing != attrs["relation"]:
            raise ClusterSpecError(
                f"{where}: {src} -> {tgt} already carries relation {existing!r}, and a "
                f"simple cluster graph holds one relation per node pair. Set "
                f"\"graph_mode\": \"multi\" in the spec to keep both."
            )
        return 0
    G.add_edge(src, tgt, **attrs)
    return 1


def _resolve_endpoint(
    G: nx.Graph,
    index: _SelectorIndex,
    sel: dict,
    where: str,
    on_missing: str,
    reports: list[LinkReport],
    link: ClusterLink,
) -> str | None:
    node = resolve_selector(G, index, sel, where)
    if node is not None:
        return node
    described = f"{sel['kind']}={sel['value']!r} in member {sel['member']!r}"
    if on_missing == "error":
        raise ClusterSpecError(
            f"{where}: selector {described} matches nothing. Re-run 'kb-core extract .' "
            f"in that repo, fix the selector, or set \"on_missing\": \"warn\" on this link."
        )
    if on_missing == "create":
        reports.append(LinkReport(link.type, "created", f"{where}: created placeholder for {described}"))
        return _create_placeholder(G, sel)
    reports.append(LinkReport(link.type, "skipped", f"{where}: selector {described} matches nothing"))
    return None


def apply_spec_links(G: nx.Graph, spec: ClusterSpec) -> list[LinkReport]:
    """Materialise every declared cross-repo link. Returns one report per link."""
    reports: list[LinkReport] = []
    index = _SelectorIndex(G)
    multi = G.is_multigraph()

    for i, link in enumerate(spec.links):
        where = f"links[{i}]"
        on_missing = link.on_missing or spec.default_on_missing

        if link.type == SHARED_RESOURCE:
            reports.append(_apply_shared_resource(G, index, link, where, on_missing, reports, multi))
            continue

        relation = LINK_RELATIONS[link.type]
        src = _resolve_endpoint(G, index, link.from_, f"{where}.from", on_missing, reports, link)
        tgt = _resolve_endpoint(G, index, link.to, f"{where}.to", on_missing, reports, link)
        if src is None or tgt is None:
            continue
        if src == tgt:
            reports.append(LinkReport(link.type, "skipped", f"{where}: both ends resolve to {src}"))
            continue

        added = _add_link_edge(G, src, tgt, _link_attrs(link, relation), multi=multi, where=where)
        if link.direction == "both":
            # A real reverse edge, not a flag: a traversal that only walks
            # out-edges must see the hop from either side.
            added += _add_link_edge(G, tgt, src, _link_attrs(link, relation), multi=multi, where=where)
        reports.append(
            LinkReport(link.type, "linked", f"{where}: {src} -[{relation}]-> {tgt}", edges_added=added)
        )
    return reports


def _apply_shared_resource(
    G: nx.Graph,
    index: _SelectorIndex,
    link: ClusterLink,
    where: str,
    on_missing: str,
    reports: list[LinkReport],
    multi: bool,
) -> LinkReport:
    from kb_core.ids import normalize_id

    hub_id = f"{RESERVED_TAG}::{normalize_id(link.kind or 'resource')}_{normalize_id(link.name)}"
    if hub_id not in G:
        G.add_node(
            hub_id,
            label=link.name,
            file_type="external",
            repo=RESERVED_TAG,
            local_id=hub_id.split("::", 1)[1],
            resource_kind=link.kind or "resource",
            origin="cluster_spec",
        )
    added = 0
    linked = 0
    for j, sel in enumerate(link.referents):
        node = _resolve_endpoint(
            G, index, sel, f"{where}.referents[{j}]", on_missing, reports, link
        )
        if node is None:
            continue
        added += _add_link_edge(
            G, node, hub_id, _link_attrs(link, SHARED_RESOURCE_RELATION),
            multi=multi, where=f"{where}.referents[{j}]",
        )
        linked += 1
    return LinkReport(
        link.type, "linked", f"{where}: {linked} referent(s) -> {hub_id}", edges_added=added
    )


def apply_auto_package_links(G: nx.Graph) -> list[LinkReport]:
    """Join a repo's declared dependency to the repo that provides it.

    Driven by the `package_key` / `dependency_keys` attributes that
    `manifest_ingest` stamps on package-manifest nodes. A dependency naming a
    package that another member of the cluster actually publishes is the one
    unambiguous cross-repo edge derivable without a spec declaration.
    """
    providers: dict[str, list[str]] = {}
    for node, data in G.nodes(data=True):
        key = data.get("package_key")
        if key:
            providers.setdefault(str(key), []).append(str(node))

    reports: list[LinkReport] = []
    multi = G.is_multigraph()
    added = 0
    for node, data in sorted(G.nodes(data=True), key=lambda item: str(item[0])):
        deps = data.get("dependency_keys")
        if not isinstance(deps, list):
            continue
        consumer_repo = data.get("repo")
        for dep in sorted({str(d) for d in deps}):
            candidates = [
                p for p in providers.get(dep, [])
                if G.nodes[p].get("repo") != consumer_repo
            ]
            if len(candidates) != 1:
                # Zero providers is the normal case (a third-party dependency);
                # two or more means the cluster cannot say which repo is meant,
                # and guessing would invent an edge the user never declared.
                continue
            provider = candidates[0]
            if G.has_edge(str(node), provider):
                continue
            attrs = {
                "relation": "depends_on",
                "confidence": "INFERRED",
                "origin": "cluster_auto_packages",
                "package_key": dep,
                "_src": str(node),
                "_tgt": provider,
            }
            if multi:
                from kb_core.build import stable_edge_key

                G.add_edge(str(node), provider, key=stable_edge_key(str(node), provider, attrs), **attrs)
            else:
                G.add_edge(str(node), provider, **attrs)
            added += 1
    if added:
        reports.append(LinkReport("auto_packages", "linked", f"{added} package dependency edge(s)", added))
    return reports


# --------------------------------------------------------------------------
# Member markers
# --------------------------------------------------------------------------


def _member_ref_out_dir(member_path: Path) -> Path:
    from kb_core.paths import KB_CORE_OUT_NAME

    return Path(member_path) / KB_CORE_OUT_NAME


def check_member_ref_conflicts(
    spec: ClusterSpec, cluster_dir: Path, resolved: dict[str, Path]
) -> None:
    """Refuse to write markers that would shadow a different cluster of the same name.

    Two unrelated clusters both called "platform" would otherwise make
    `--cluster platform` resolve to whichever one built last, from inside a repo
    that belongs to both.
    """
    from kb_core.cluster_ref import load_cluster_refs

    cluster_dir = _norm(cluster_dir)
    for tag, member_path in sorted(resolved.items()):
        for ref in load_cluster_refs(_member_ref_out_dir(member_path)):
            if str(ref.get("cluster_name")) != spec.name:
                continue
            hint = ref.get("dir_hint")
            if not hint:
                continue
            previous = _norm(Path(member_path) / str(hint))
            if previous != cluster_dir and find_spec_file(previous) is not None:
                raise ClusterSpecError(
                    f"Member {tag!r} already belongs to a different cluster also named "
                    f"{spec.name!r} at {previous}. Rename one of them — '--cluster {spec.name}' "
                    f"cannot resolve to both."
                )


def write_member_refs(
    spec: ClusterSpec, cluster_dir: Path, resolved: dict[str, Path], built_at: str
) -> list[Path]:
    from kb_core.cluster_ref import build_ref_entry, upsert_cluster_ref

    members = [{"tag": m.tag, "url": m.url} for m in sorted(spec.members, key=lambda m: m.tag)]
    written: list[Path] = []
    for tag, member_path in sorted(resolved.items()):
        entry = build_ref_entry(
            cluster_name=spec.name,
            cluster_dir=Path(cluster_dir),
            member_root=Path(member_path),
            self_tag=tag,
            members=members,
            built_at=built_at,
            cluster_url=spec.url,
        )
        written.append(upsert_cluster_ref(_member_ref_out_dir(member_path), entry))
    return written


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def check_cluster(cluster_dir: Path) -> tuple[ClusterSpec, dict[str, Path]]:
    """Validate the spec and locate every member, writing nothing.

    Raises `ClusterSpecError` with the specific fix. Suitable for CI.
    """
    spec = load_spec(cluster_dir)
    resolved = resolve_all_members(spec, cluster_dir)
    check_member_ref_conflicts(spec, cluster_dir, resolved)
    return spec, resolved


def _report_markdown(
    spec: ClusterSpec,
    stats: list[MemberComposition],
    reports: list[LinkReport],
    G: nx.Graph,
    built_at: str,
    shared_types: int,
) -> str:
    lines = [
        f"# Cluster: {spec.name}",
        "",
        f"Built {built_at} · {G.number_of_nodes()} nodes · {G.number_of_edges()} edges "
        f"· graph_mode `{spec.graph_mode}`",
        "",
        "## Members",
        "",
        "| Tag | Nodes | Edges | Path |",
        "| --- | ----: | ----: | ---- |",
    ]
    for s in stats:
        lines.append(f"| `{s.tag}` | {s.nodes} | {s.edges} | `{s.path}` |")
    lines += ["", "## Cross-repo links", ""]
    if not reports:
        lines.append("No links declared. Add a `links` entry to `cluster.json`.")
    else:
        for r in reports:
            lines.append(f"- **{r.type}** ({r.status}, +{r.edges_added}): {r.detail}")
    lines += ["", "## Shared type declarations", "", f"{shared_types} `same_type_as` edge(s) added.", ""]
    return "\n".join(lines)


def build_cluster(
    cluster_dir: Path,
    *,
    force: bool = False,
    no_links: bool = False,
    write_refs: bool = True,
) -> dict:
    """Compose the cluster and write its graph, manifest, report and markers."""
    from kb_core.cross_repo_types import link_shared_type_declarations
    from kb_core.export import to_json
    from kb_core.paths import KB_CORE_OUT_NAME, write_json_atomic, write_text_atomic

    cluster_dir = _norm(cluster_dir)
    spec, resolved = check_cluster(cluster_dir)
    built_at = datetime.now(timezone.utc).isoformat()

    G, stats = compose_members(spec, resolved)
    shared_types = link_shared_type_declarations(G)

    reports: list[LinkReport] = []
    if not no_links:
        reports.extend(apply_spec_links(G, spec))
        if spec.auto_link_packages:
            reports.extend(apply_auto_package_links(G))

    out_dir = cluster_dir / KB_CORE_OUT_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_path = out_dir / "graph.json"
    if not to_json(G, communities_from_graph(G), str(graph_path), force=force):
        raise ClusterSpecError(
            f"Refused to overwrite {graph_path} because the new cluster graph is "
            f"smaller than the existing one. Re-run with --force if a member was "
            f"intentionally removed."
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": spec.name,
        "built_at": built_at,
        "graph_mode": spec.graph_mode,
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "shared_type_edges": shared_types,
        "members": [
            {
                "tag": s.tag,
                "path": str(s.path),
                "graph": str(s.graph_path),
                "nodes": s.nodes,
                "edges": s.edges,
                "community_offset": s.community_offset,
            }
            for s in stats
        ],
        "links": [
            {"type": r.type, "status": r.status, "detail": r.detail, "edges_added": r.edges_added}
            for r in reports
        ],
    }
    write_json_atomic(out_dir / "cluster-manifest.json", manifest, indent=2)
    write_text_atomic(
        out_dir / "CLUSTER_REPORT.md",
        _report_markdown(spec, stats, reports, G, built_at, shared_types),
    )

    refs: list[Path] = []
    if write_refs:
        refs = write_member_refs(spec, cluster_dir, resolved, built_at)

    return {
        "name": spec.name,
        "graph_path": graph_path,
        "manifest_path": out_dir / "cluster-manifest.json",
        "report_path": out_dir / "CLUSTER_REPORT.md",
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "members": len(stats),
        "links": reports,
        "refs_written": refs,
        "shared_type_edges": shared_types,
    }
