"""The language-agnostic symbol/edge model shared by parser, store, server
and mcp — the Python side of internal/graph/model.go.

`to_json_dict` reproduces Go's encoding/json semantics rather than dumping
`asdict()`: `omitempty` drops empty strings entirely, while a nil slice
serializes as `null` and an empty slice as `[]`. Both distinctions are
compared byte-for-byte by the parity harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KIND_MODULE = "module"
KIND_PACKAGE = "package"
KIND_CLASS = "class"
KIND_INTERFACE = "interface"
KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_CONST = "const"
KIND_VARIABLE = "variable"
KIND_ROUTE = "route"

EDGE_CALLS = "calls"
EDGE_REFERENCES = "references"
EDGE_CONTAINS = "contains"
EDGE_IMPLEMENTS = "implements"
EDGE_EXTENDS = "extends"
EDGE_HANDLES = "handles"


@dataclass
class Param:
    name: str = ""
    type: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type}


@dataclass
class SymbolRef:
    id: str = ""
    name: str = ""
    kind: str = ""
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "filePath": self.file_path,
            "startLine": self.start_line,
            "endLine": self.end_line,
        }


@dataclass
class Symbol(SymbolRef):
    signature: str = ""
    params: list[Param] | None = None
    returns: list[Param] | None = None
    receiver: str = ""
    parent_id: str = ""
    language: str = ""
    doc: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        out = super().to_json_dict()
        out["signature"] = self.signature
        out["params"] = None if self.params is None else [p.to_json_dict() for p in self.params]
        out["returns"] = None if self.returns is None else [p.to_json_dict() for p in self.returns]
        if self.receiver:
            out["receiver"] = self.receiver
        if self.parent_id:
            out["parentId"] = self.parent_id
        out["language"] = self.language
        if self.doc:
            out["doc"] = self.doc
        return out


@dataclass
class Edge:
    source: str
    target: str
    kind: str

    def to_json_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclass
class UnresolvedCall:
    from_id: str
    target_name: str
    kind: str
    # True for a selector call site ("resp.Body.Close()" -> "Close"). Such
    # names collide constantly with unrelated same-named local methods, so
    # the builder resolves them only against an unambiguous same-file or
    # same-directory match, never a repo-wide guess.
    qualified: bool = False


@dataclass
class FileGraph:
    file_path: str
    language: str
    symbols: list[Symbol] = field(default_factory=list)
    unresolved_calls: list[UnresolvedCall] = field(default_factory=list)


@dataclass
class Graph:
    symbols: dict[str, Symbol] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)


@dataclass
class TreeNode:
    path: str
    name: str
    type: str  # "dir" | "file"
    language: str = ""
    children: list["TreeNode"] | None = None

    def to_json_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"path": self.path, "name": self.name, "type": self.type}
        if self.language:
            out["language"] = self.language
        if self.children:
            out["children"] = [c.to_json_dict() for c in self.children]
        return out
