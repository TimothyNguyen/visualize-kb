"""`kb-core cluster ...` subcommands.

Manual argv walk rather than argparse, matching the rest of `kb_core.cli`:
one parser style across the tool, and help tokens are handled before anything
touches the filesystem so `--help` never has a side effect.
"""

from __future__ import annotations

import sys
from pathlib import Path

USAGE = """Usage: kb-core cluster <command>

  init [DIR] --name NAME          Create a cluster spec in DIR (default: .)
  add <path-or-url> [--as TAG]    Add a member repo to the cluster
  remove <TAG>                    Remove a member
  locate <TAG> <PATH>             Record where a member lives on this machine
  build [--force] [--no-links]    Compose the members into one cluster graph
  check                           Validate the spec and members (exit 1 on error)
  status                          Show members and whether each resolves

All commands accept --dir DIR to point at the cluster directory (default: .).
"""

_HELP_TOKENS = ("-h", "--help", "help")


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def _take(args: list[str], index: int, flag: str) -> tuple[str, int]:
    """Value of `--flag VALUE` or `--flag=VALUE`, plus how far to advance."""
    if args[index].startswith(flag + "="):
        return args[index].split("=", 1)[1], 1
    if index + 1 < len(args) and not args[index + 1].startswith("-"):
        return args[index + 1], 2
    _fail(f"{flag} needs a value")
    raise AssertionError  # unreachable; _fail exits


def _parse_flags(args: list[str], flags: tuple[str, ...], bools: tuple[str, ...] = ()) -> tuple[dict, list[str]]:
    values: dict[str, str | bool] = {}
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        matched = False
        for flag in bools:
            if arg == flag:
                values[flag] = True
                i += 1
                matched = True
                break
        if matched:
            continue
        for flag in flags:
            if arg == flag or arg.startswith(flag + "="):
                value, step = _take(args, i, flag)
                values[flag] = value
                i += step
                matched = True
                break
        if matched:
            continue
        if arg.startswith("-"):
            _fail(f"unknown option {arg}\n\n{USAGE}")
        positional.append(arg)
        i += 1
    return values, positional


def _cluster_dir(values: dict) -> Path:
    return Path(str(values.get("--dir") or "."))


def cmd_cluster(argv: list[str]) -> None:
    from kb_core.cluster_graph import ClusterSpecError

    subcmd = argv[0] if argv else ""
    if not subcmd or subcmd in _HELP_TOKENS:
        print(USAGE)
        sys.exit(0 if subcmd in _HELP_TOKENS else 1)
    if any(token in _HELP_TOKENS for token in argv[1:]):
        print(USAGE)
        sys.exit(0)

    handlers = {
        "init": _cmd_init,
        "add": _cmd_add,
        "remove": _cmd_remove,
        "locate": _cmd_locate,
        "build": _cmd_build,
        "check": _cmd_check,
        "status": _cmd_status,
    }
    handler = handlers.get(subcmd)
    if handler is None:
        _fail(f"unknown cluster command {subcmd!r}\n\n{USAGE}")
    try:
        handler(argv[1:])
    except ClusterSpecError as exc:
        _fail(str(exc))


def _cmd_init(args: list[str]) -> None:
    from kb_core.cluster_graph import ClusterSpec, find_spec_file, save_spec

    values, positional = _parse_flags(args, ("--name", "--dir"))
    cluster_dir = Path(positional[0]) if positional else _cluster_dir(values)
    name = str(values.get("--name") or "").strip() or cluster_dir.resolve().name
    if find_spec_file(cluster_dir) is not None:
        _fail(f"{cluster_dir} already contains a cluster spec. Edit it, or pick another directory.")
    path = save_spec(cluster_dir, ClusterSpec(name=name))
    print(f"Created cluster {name!r} at {path}")
    print("Next: kb-core cluster add <path-to-repo>")


def _cmd_add(args: list[str]) -> None:
    from kb_core.cluster_graph import (
        ClusterMember,
        load_spec,
        save_local_config,
        load_local_config,
        save_spec,
        validate_member_tag,
        _norm,
    )
    from kb_core.cluster_ref import origin_url

    values, positional = _parse_flags(args, ("--as", "--dir"))
    if not positional:
        _fail("kb-core cluster add <path-or-url> [--as TAG] [--dir DIR]")
    target = positional[0]
    cluster_dir = _cluster_dir(values)
    spec = load_spec(cluster_dir)

    candidate = Path(target)
    is_path = candidate.exists()
    url = "" if is_path else target
    if is_path:
        url = origin_url(candidate)
    tag = str(values.get("--as") or "").strip()
    if not tag:
        tag = (candidate.name if is_path else target.rstrip("/").rsplit("/", 1)[-1]).removesuffix(".git")
    tag = validate_member_tag(tag)
    if spec.member(tag):
        _fail(f"cluster {spec.name!r} already has a member tagged {tag!r}. Use --as <tag> to pick another name.")

    spec.members.append(ClusterMember(tag=tag, url=url))
    save_spec(cluster_dir, spec)
    if is_path:
        # Record the local checkout separately from the spec: the spec is shared
        # (committed), and an absolute path from one machine is wrong on every
        # other one.
        config = load_local_config(cluster_dir)
        import os

        config.setdefault("paths", {})[tag] = Path(
            os.path.relpath(_norm(candidate), _norm(cluster_dir))
        ).as_posix()
        save_local_config(cluster_dir, config)
    print(f"Added member {tag!r}" + (f" ({url})" if url else ""))


def _cmd_remove(args: list[str]) -> None:
    from kb_core.cluster_graph import load_local_config, load_spec, save_local_config, save_spec

    values, positional = _parse_flags(args, ("--dir",))
    if not positional:
        _fail("kb-core cluster remove <TAG> [--dir DIR]")
    tag = positional[0]
    cluster_dir = _cluster_dir(values)
    spec = load_spec(cluster_dir)
    if not spec.member(tag):
        _fail(f"cluster {spec.name!r} has no member tagged {tag!r}. Members: {', '.join(spec.tags) or '(none)'}")

    referring = [
        i for i, link in enumerate(spec.links)
        for sel in ([link.from_, link.to] if link.type != "shared_resource" else link.referents)
        if sel and sel["member"] == tag
    ]
    if referring:
        _fail(
            f"member {tag!r} is still named by links {sorted(set(referring))}. "
            f"Remove those links from cluster.json first."
        )

    spec.members = [m for m in spec.members if m.tag != tag]
    save_spec(cluster_dir, spec)
    config = load_local_config(cluster_dir)
    if config.get("paths", {}).pop(tag, None) is not None:
        save_local_config(cluster_dir, config)
    print(f"Removed member {tag!r}")


def _cmd_locate(args: list[str]) -> None:
    import os

    from kb_core.cluster_graph import _norm, load_local_config, load_spec, save_local_config

    values, positional = _parse_flags(args, ("--dir",))
    if len(positional) < 2:
        _fail("kb-core cluster locate <TAG> <PATH> [--dir DIR]")
    tag, target = positional[0], positional[1]
    cluster_dir = _cluster_dir(values)
    spec = load_spec(cluster_dir)
    if not spec.member(tag):
        _fail(f"cluster {spec.name!r} has no member tagged {tag!r}. Members: {', '.join(spec.tags) or '(none)'}")
    path = Path(target)
    if not path.is_dir():
        _fail(f"{target} is not a directory")

    config = load_local_config(cluster_dir)
    config.setdefault("paths", {})[tag] = Path(
        os.path.relpath(_norm(path), _norm(cluster_dir))
    ).as_posix()
    save_local_config(cluster_dir, config)
    print(f"Member {tag!r} located at {path}")


def _cmd_build(args: list[str]) -> None:
    from kb_core.cluster_graph import build_cluster

    values, _ = _parse_flags(args, ("--dir",), ("--force", "--no-links", "--no-refs"))
    result = build_cluster(
        _cluster_dir(values),
        force=bool(values.get("--force")),
        no_links=bool(values.get("--no-links")),
        write_refs=not values.get("--no-refs"),
    )
    print(
        f"Built cluster {result['name']!r}: {result['nodes']} nodes, "
        f"{result['edges']} edges from {result['members']} member(s)"
    )
    for report in result["links"]:
        print(f"  {report.type}: {report.status} (+{report.edges_added}) - {report.detail}")
    if result["shared_type_edges"]:
        print(f"  same_type_as: {result['shared_type_edges']} edge(s)")
    print(f"  graph:    {result['graph_path']}")
    print(f"  manifest: {result['manifest_path']}")
    print(f"  report:   {result['report_path']}")
    if result["refs_written"]:
        print(f"  markers:  {len(result['refs_written'])} member(s) updated")


def _cmd_check(args: list[str]) -> None:
    from kb_core.cluster_graph import check_cluster

    values, _ = _parse_flags(args, ("--dir",))
    spec, resolved = check_cluster(_cluster_dir(values))
    print(f"Cluster {spec.name!r}: {len(resolved)} member(s), {len(spec.links)} link(s) - OK")


def _cmd_status(args: list[str]) -> None:
    from kb_core.cluster_graph import (
        load_local_config,
        load_spec,
        member_graph_path,
        resolve_member_path,
    )

    values, _ = _parse_flags(args, ("--dir",))
    cluster_dir = _cluster_dir(values)
    spec = load_spec(cluster_dir)
    local_config = load_local_config(cluster_dir)
    print(f"Cluster {spec.name!r} ({spec.graph_mode} mode), {len(spec.links)} declared link(s)")
    if not spec.members:
        print("  no members - add one with 'kb-core cluster add <path-or-url>'")
        return
    for member in spec.members:
        path = resolve_member_path(spec, member, cluster_dir, local_config)
        if path is None:
            print(f"  {member.tag:<20} UNRESOLVED  (kb-core cluster locate {member.tag} <path>)")
            continue
        graph = member_graph_path(member, path)
        state = "ok" if graph.is_file() else "no graph (run 'kb-core extract .' there)"
        print(f"  {member.tag:<20} {state:<12} {path}")
