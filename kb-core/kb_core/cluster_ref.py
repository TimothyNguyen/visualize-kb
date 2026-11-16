"""Member-side cluster marker: `<member>/kb-core-out/cluster-ref.json`.

A repo that belongs to one or more clusters carries this marker so that commands
run *from inside the member* can find the cluster without being told where it
lives. It is what makes bare `--cluster` work.

Stdlib only, and deliberately so: this module is imported on the git-hook nudge
path, where pulling in networkx would add hundreds of milliseconds to every
commit. `security.sanitize_label` is lazy-imported for display strings only.

Every read is fail-open. A missing, corrupt, oversized, or self-contradictory
marker degrades to "this repo is in no cluster" — the marker is a convenience
index, and refusing to answer a query because a hint file is malformed would be
worse than not having the hint.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CLUSTER_REF_NAME = "cluster-ref.json"
CLUSTER_REF_VERSION = 1

# A marker is a handful of short strings per cluster. Anything at megabyte scale
# is not a marker — it is a mistake or something hostile — and parsing it would
# stall the hook path this module exists to keep fast.
_MAX_REF_BYTES = 1024 * 1024

_SPEC_NAMES = ("cluster.json", "cluster.yaml", "cluster.yml")


def normalize_git_url(url: str | None) -> str:
    """Comparable form of a git remote URL.

    `git@github.com:org/repo.git`, `https://github.com/org/repo.git`, and
    `https://github.com/org/repo/` all name the same repository, so all three
    must compare equal — otherwise sibling discovery matches on nothing.
    Non-URL values (a local path, an empty string) pass through casefolded.
    """
    if not url:
        return ""
    text = str(url).strip()
    if text.startswith("git+"):
        text = text[4:]
    # scp-style: git@host:org/repo -> host/org/repo
    if "://" not in text and "@" in text and ":" in text:
        _, _, rest = text.partition("@")
        host, _, path = rest.partition(":")
        text = f"{host}/{path}"
    else:
        for scheme in ("https://", "http://", "ssh://", "git://", "file://"):
            if text.startswith(scheme):
                text = text[len(scheme) :]
                break
        # ssh://git@host/org/repo -> host/org/repo
        if "@" in text.split("/", 1)[0]:
            text = text.split("@", 1)[1]
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    return text.casefold()


def origin_url(repo_dir: Path) -> str:
    """`origin` remote URL of `repo_dir`, read straight from `.git/config`.

    Parsed rather than shelled out to: `git remote get-url` costs a process spawn
    per candidate directory, and discovery scans every sibling.
    """
    config = Path(repo_dir) / ".git" / "config"
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    in_origin = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_origin = line.replace(" ", "").replace('"', "").lower() == "[remoteorigin]"
            continue
        if in_origin and line.lower().startswith("url"):
            _, _, value = line.partition("=")
            return value.strip()
    return ""


def ref_path(out_dir: Path) -> Path:
    return Path(out_dir) / CLUSTER_REF_NAME


def load_cluster_refs(out_dir: Path) -> list[dict]:
    """Cluster entries recorded in `out_dir`'s marker, or `[]` on any problem."""
    path = ref_path(out_dir)
    try:
        if path.stat().st_size > _MAX_REF_BYTES:
            return []
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, dict) or payload.get("version") != CLUSTER_REF_VERSION:
        return []
    clusters = payload.get("clusters")
    if not isinstance(clusters, list):
        return []

    refs = [c for c in clusters if isinstance(c, dict) and c.get("cluster_name")]
    names = [str(c["cluster_name"]) for c in refs]
    if len(names) != len(set(names)):
        # Two entries claiming the same cluster means `--cluster NAME` has no
        # single answer. Rather than pick one arbitrarily, report no clusters so
        # the user gets the explicit "not in a cluster" path.
        return []
    return refs


def select_cluster_ref(refs: list[dict], name: str | None = None) -> dict | None:
    """Pick the entry `--cluster [NAME]` means, or None if that is ambiguous."""
    if not refs:
        return None
    if name:
        for ref in refs:
            if str(ref.get("cluster_name")) == name:
                return ref
        return None
    return refs[0] if len(refs) == 1 else None


def member_count(ref: dict) -> int:
    """Number of repos in the cluster, preferring the actual member list."""
    members = ref.get("members")
    if isinstance(members, list) and members:
        return len(members)
    try:
        return int(ref.get("member_count") or 0)
    except (TypeError, ValueError):
        return 0


def cluster_hint_line(refs: list[dict]) -> str:
    """One-line nudge appended to a miss on the member's own graph.

    Empty string when there is nothing to suggest, so callers can append
    unconditionally.
    """
    if not refs:
        return ""
    from kb_core.security import sanitize_label

    if len(refs) == 1:
        ref = refs[0]
        name = sanitize_label(str(ref.get("cluster_name", "")))
        count = member_count(ref)
        return (
            f"Hint: this repo is a member of cluster '{name}' ({count} repos). "
            f"Re-run with --cluster to search the whole cluster."
        )
    names = ", ".join(sorted(sanitize_label(str(r.get("cluster_name", ""))) for r in refs))
    return (
        f"Hint: this repo is a member of {len(refs)} clusters ({names}). "
        f"Re-run with --cluster <NAME> to search one of them."
    )


def unresolvable_message(ref: dict) -> str:
    """Actionable error for a cluster whose directory could not be located."""
    from kb_core.security import sanitize_label

    name = sanitize_label(str(ref.get("cluster_name", "")))
    hint = str(ref.get("dir_hint") or "")
    where = f" (last seen at {sanitize_label(hint)})" if hint else ""
    return (
        f"Cannot locate the directory for cluster '{name}'{where}. "
        f"Run the query from the cluster directory, or pass "
        f"--graph <cluster-dir>/kb-core-out/graph.json."
    )


def _is_cluster_dir(candidate: Path) -> bool:
    return any((candidate / name).is_file() for name in _SPEC_NAMES)


def _spec_name_at(candidate: Path) -> str:
    """Declared cluster name at `candidate`, or "" when unreadable.

    Only `cluster.json` is parsed — YAML would mean importing pyyaml on the hook
    path. A YAML-only cluster still resolves by dir_hint, origin URL, or
    directory name.
    """
    try:
        payload = json.loads((candidate / "cluster.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ""
    return str(payload.get("name", "")) if isinstance(payload, dict) else ""


def _matches(candidate: Path, ref: dict) -> bool:
    if not _is_cluster_dir(candidate):
        return False
    wanted_url = normalize_git_url(ref.get("cluster_url"))
    if wanted_url and normalize_git_url(origin_url(candidate)) == wanted_url:
        return True
    name = str(ref.get("cluster_name", ""))
    if not name:
        return False
    return _spec_name_at(candidate) == name or candidate.name == name


def resolve_cluster_dir(ref: dict, member_root: Path) -> Path | None:
    """Directory holding the cluster spec, or None.

    `dir_hint` is stored relative to the member so a checkout that moves as a
    unit (a monorepo of siblings cloned somewhere else, a CI workspace) keeps
    working. A hint that no longer points at a cluster is not an error — repos
    get moved independently — so resolution falls through to scanning the
    member's siblings for a cluster whose origin URL or name matches.
    """
    member_root = Path(member_root)
    hint = ref.get("dir_hint")
    if hint:
        candidate = Path(os.path.normpath(member_root / str(hint)))
        if _matches(candidate, ref):
            return candidate

    parent = member_root.parent
    matches = []
    try:
        siblings = sorted(p for p in parent.iterdir() if p.is_dir())
    except OSError:
        siblings = []
    for candidate in siblings:
        if candidate == member_root:
            continue
        if _matches(candidate, ref):
            matches.append(candidate)
    # Exactly one match or nothing: two directories both claiming to be the
    # cluster is precisely the case where guessing produces a silently wrong
    # answer, so it resolves to None and the caller prints the explicit path.
    return matches[0] if len(matches) == 1 else None


def _relative_hint(cluster_dir: Path, member_root: Path) -> str:
    try:
        return Path(os.path.relpath(cluster_dir, member_root)).as_posix()
    except ValueError:
        # Different drives on Windows — no relative form exists.
        return Path(cluster_dir).as_posix()


def build_ref_entry(
    *,
    cluster_name: str,
    cluster_dir: Path,
    member_root: Path,
    self_tag: str,
    members: list[dict],
    built_at: str,
    cluster_url: str = "",
) -> dict:
    return {
        "cluster_name": cluster_name,
        "cluster_url": cluster_url,
        "self_tag": self_tag,
        "member_count": len(members),
        "members": members,
        "built_at": built_at,
        "dir_hint": _relative_hint(cluster_dir, member_root),
    }


def upsert_cluster_ref(out_dir: Path, entry: dict) -> Path:
    """Add or replace `entry`'s cluster in `out_dir`'s marker.

    Replaces by `cluster_name`, so a repo in several clusters accumulates
    entries rather than having the last build erase the others.
    """
    from kb_core.paths import write_json_atomic

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = str(entry.get("cluster_name", ""))
    kept = [r for r in load_cluster_refs(out_dir) if str(r.get("cluster_name")) != name]
    kept.append(entry)
    kept.sort(key=lambda r: str(r.get("cluster_name", "")))
    path = ref_path(out_dir)
    write_json_atomic(path, {"version": CLUSTER_REF_VERSION, "clusters": kept}, indent=2)
    return path


def remove_cluster_ref(out_dir: Path, cluster_name: str) -> bool:
    """Drop one cluster from the marker. Returns whether anything was removed."""
    from kb_core.paths import write_json_atomic

    out_dir = Path(out_dir)
    existing = load_cluster_refs(out_dir)
    kept = [r for r in existing if str(r.get("cluster_name")) != str(cluster_name)]
    if len(kept) == len(existing):
        return False
    path = ref_path(out_dir)
    if kept:
        write_json_atomic(path, {"version": CLUSTER_REF_VERSION, "clusters": kept}, indent=2)
    else:
        try:
            path.unlink()
        except OSError:
            pass
    return True
