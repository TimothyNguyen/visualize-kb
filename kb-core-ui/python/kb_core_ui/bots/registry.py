"""The built-in bot roster — a copy of internal/bots/registry.go.

Every string here reaches the web dashboard through GET /api/bots, so it is
compared byte for byte against the Go original.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArgDef:
    name: str
    label: str
    required: bool = False
    placeholder: str = ""
    is_bool: bool = False

    def to_json_dict(self) -> dict:
        out: dict = {"name": self.name, "label": self.label, "required": self.required}
        if self.placeholder:
            out["placeholder"] = self.placeholder
        if self.is_bool:
            out["bool"] = True
        return out


@dataclass(frozen=True)
class Def:
    name: str
    title: str
    description: str
    kind: str
    needs_auth: bool = False
    args: tuple[ArgDef, ...] = ()
    # How the bot is invoked as `kb-core-ui bot <subcommand>`, and which arg
    # names are passed positionally rather than as flags. Execution details,
    # not API — Go keeps both unexported.
    subcommand: str = ""
    positional: tuple[str, ...] = ()

    def to_json_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "kind": self.kind,
            "needsAuth": self.needs_auth,
            "args": [a.to_json_dict() for a in self.args] if self.args else None,
        }


# Order here is the display order.
REGISTRY: list[Def] = [
    Def(
        name="doctor",
        title="Doctor",
        description="Preflight: verify the whole orchestration chain — python, gh, claude, and kb-core-ui's MCP server all connect.",
        # It shells to python, but from the UI's view it needs no args and no auth.
        kind="go-native",
        needs_auth=False,
        subcommand="doctor",
    ),
    Def(
        name="graph-sync",
        title="Graph Sync",
        description="Re-index the code graph and check its integrity (dangling edges, resolution quality). No AI, no auth.",
        kind="go-native",
        needs_auth=False,
        subcommand="graph-sync",
    ),
    Def(
        name="pr-review",
        title="PR Review",
        description="Review an open PR's diff for breaking changes, quality, duplication, rewrites, pattern-mismatch, and cross-boundary contract mismatches. Posts a comment (or use dry-run).",
        kind="python",
        needs_auth=True,
        args=(
            ArgDef("pr_number", "PR number", required=True, placeholder="e.g. 12"),
            ArgDef("dry_run", "Dry run (print instead of posting)", is_bool=True),
        ),
        subcommand="pr-review",
        positional=("pr_number",),
    ),
    Def(
        name="commit-check",
        title="Commit Check",
        description="Review a single commit's diff (same dimensions as PR review) — run after committing, before pushing.",
        kind="python",
        needs_auth=True,
        args=(ArgDef("ref", "Commit ref", placeholder="HEAD"),),
        subcommand="commit-check",
        positional=("ref",),
    ),
    Def(
        name="test-writer",
        title="Test Writer",
        description="Generate test cases for a function or file, using the graph to cover real callers and edge cases. Prints tests (add 'true' to write the file).",
        kind="python",
        needs_auth=True,
        args=(
            ArgDef(
                "target",
                "Symbol or file",
                required=True,
                placeholder="e.g. BuildFlat or internal/graph/builder.go",
            ),
            ArgDef("write", "Write file to disk", is_bool=True),
        ),
        subcommand="test-writer",
        positional=("target",),
    ),
    Def(
        name="anomaly-scan",
        title="Anomaly Detector",
        description="Scan the whole codebase for anomalies: possible breakages, cross-boundary contract mismatches, duplication, and rule violations (from memory).",
        kind="python",
        needs_auth=True,
        args=(ArgDef("focus", "Focus area (optional)", placeholder="e.g. the server package"),),
        subcommand="anomaly-scan",
    ),
    Def(
        name="feature-verdict",
        title="Feature Verdict",
        description="Plan a proposed feature against this codebase: rules it might break, code to reuse, optimal options, a PRD, and tests to keep current behavior safe.",
        kind="python",
        needs_auth=True,
        args=(
            ArgDef(
                "feature",
                "Feature description",
                required=True,
                placeholder="e.g. add a REST endpoint to delete a symbol",
            ),
        ),
        subcommand="feature-verdict",
        positional=("feature",),
    ),
    Def(
        name="triage",
        title="Support Triage",
        description="Correlate a GitHub issue to the code via the graph + memory and suggest fixes with file:line references. (Intercom source planned — needs auth.)",
        kind="python",
        needs_auth=True,
        args=(
            ArgDef("issue", "GitHub issue number", required=True, placeholder="e.g. 7"),
            ArgDef("comment", "Post as issue comment", is_bool=True),
        ),
        subcommand="triage",
        positional=("issue",),
    ),
]


def lookup(name: str) -> Def | None:
    for d in REGISTRY:
        if d.name == name:
            return d
    return None
