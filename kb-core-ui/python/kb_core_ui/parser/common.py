"""Tree-walking helpers shared by every language extractor — the Python side
of internal/parser/parser.go.

Node text is sliced out of the raw source bytes rather than read from a
decoded string, because tree-sitter reports byte offsets and Go's
Node.Content does the same slicing. Anywhere the Go code truncates by length
it is truncating bytes, so those spots stay on bytes here too.
"""

from __future__ import annotations

from typing import Callable, Iterable

from tree_sitter import Node


def symbol_id(file_path: str, qualified_name: str) -> str:
    return f"{file_path}:{qualified_name}"


def node_text(n: Node | None, src: bytes) -> str:
    if n is None:
        return ""
    return src[n.start_byte : n.end_byte].decode("utf-8", "replace")


def line1(point) -> int:
    return point[0] + 1


def named_children(n: Node | None) -> list[Node]:
    if n is None:
        return []
    return list(n.named_children)


def field_children(n: Node | None, field: str) -> list[Node]:
    """Every child of n under the given field name. ChildByFieldName only
    returns the first, but grammars repeat fields — "const a, b = 1, 2" is one
    const_spec with two "name" children."""
    if n is None:
        return []
    return [
        child
        for i, child in enumerate(n.children)
        if n.field_name_for_child(i) == field
    ]


def walk(n: Node | None, kinds: Iterable[str], fn: Callable[[Node], None]) -> None:
    if n is None:
        return
    kinds = set(kinds)
    stack = [n]
    while stack:
        cur = stack.pop()
        if cur.type in kinds:
            fn(cur)
        stack.extend(reversed(cur.children))


def clean_comment(s: str) -> str:
    s = s.strip()
    for prefix in ("/**", "/*"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    if s.endswith("*/"):
        s = s[:-2]
    if s.startswith("//"):
        s = s[2:]
    lines = s.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("* "):
            line = line[2:]
        elif line.startswith("*"):
            line = line[1:]
        lines[i] = line
    return "\n".join(lines).strip()


def _is_trailing(comment: Node) -> bool:
    """A comment sharing its opening line with the declaration before it belongs
    to that declaration, not to the one after it. The Go grammar pinned by the
    binary nests such comments out of sibling range; the newer grammar leaves
    them as plain siblings, so they have to be rejected explicitly."""
    prev = comment.prev_sibling
    return prev is not None and prev.end_point[0] == comment.start_point[0]


def leading_comment(n: Node | None, src: bytes) -> str:
    """Contiguous "comment" previous siblings, stopping at the first gap wider
    than one blank line."""
    if n is None or n.parent is None:
        return ""
    lines: list[str] = []
    cur = n.prev_sibling
    last_row = n.start_point[0]
    while cur is not None and cur.type == "comment":
        if last_row - cur.end_point[0] > 1 or _is_trailing(cur):
            break
        lines.insert(0, clean_comment(node_text(cur, src)))
        last_row = cur.start_point[0]
        cur = cur.prev_sibling
    return "\n".join(lines).strip()


def header_line(n: Node, src: bytes) -> str:
    """The declaration up to its body, collapsed to a single line."""
    end = n.child_by_field_name("body")
    end_byte = end.start_byte if end is not None else n.end_byte
    sig = src[n.start_byte : end_byte].decode("utf-8", "replace").strip()
    return " ".join(sig.split())
