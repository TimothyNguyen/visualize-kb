from __future__ import annotations

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from kb_core_ui.models import (
    EDGE_CALLS,
    KIND_CLASS,
    KIND_CONST,
    KIND_FUNCTION,
    KIND_METHOD,
    KIND_VARIABLE,
    FileGraph,
    Param,
    Symbol,
    UnresolvedCall,
)
from kb_core_ui.parser.common import (
    line1,
    named_children,
    node_text,
    symbol_id,
    walk,
)

PY_LANGUAGE = Language(tree_sitter_python.language())

_CALL_KINDS = {"call"}


def non_empty_param(typ: str) -> list[Param] | None:
    return [Param(type=typ)] if typ else None


def parse_python(file_path: str, src: bytes) -> FileGraph:
    tree = Parser(PY_LANGUAGE).parse(src)
    fg = FileGraph(file_path=file_path, language="python")

    for top in named_children(tree.root_node):
        if top.type == "function_definition":
            sym, calls = _py_func(top, src, file_path, "", "")
            fg.symbols.append(sym)
            fg.unresolved_calls.extend(calls)

        elif top.type == "class_definition":
            name = node_text(top.child_by_field_name("name"), src)
            class_id = symbol_id(file_path, name)
            body = top.child_by_field_name("body")
            fg.symbols.append(
                Symbol(
                    id=class_id,
                    name=name,
                    kind=KIND_CLASS,
                    file_path=file_path,
                    start_line=line1(top.start_point),
                    end_line=line1(top.end_point),
                    signature=_py_header_line(top, src),
                    language="python",
                    doc=_docstring(body, src),
                )
            )
            for member in named_children(body):
                if member.type != "function_definition":
                    continue
                sym, calls = _py_func(member, src, file_path, class_id, name)
                fg.symbols.append(sym)
                fg.unresolved_calls.extend(calls)

        elif top.type == "expression_statement":
            children = named_children(top)
            if len(children) != 1 or children[0].type != "assignment":
                continue
            assign = children[0]
            left = assign.child_by_field_name("left")
            if left is None or left.type != "identifier":
                continue
            name = node_text(left, src)
            # ALL_CAPS is Python's constant convention; a name with no cased
            # characters at all (say "__") is not a constant.
            is_const = name == name.upper() and name.upper() != name.lower()
            fg.symbols.append(
                Symbol(
                    id=symbol_id(file_path, name),
                    name=name,
                    kind=KIND_CONST if is_const else KIND_VARIABLE,
                    file_path=file_path,
                    start_line=line1(top.start_point),
                    end_line=line1(top.end_point),
                    signature=node_text(top, src).strip(),
                    returns=non_empty_param(node_text(assign.child_by_field_name("type"), src)),
                    language="python",
                )
            )

    return fg


def _py_func(
    n: Node, src: bytes, file_path: str, parent_id: str, receiver: str
) -> tuple[Symbol, list[UnresolvedCall]]:
    name = node_text(n.child_by_field_name("name"), src)
    qualified_name = f"{receiver}.{name}" if receiver else name
    sym_id = symbol_id(file_path, qualified_name)

    params: list[Param] = []
    for p in named_children(n.child_by_field_name("parameters")):
        if p.type == "typed_parameter":
            pname = next(
                (node_text(c, src) for c in named_children(p) if c.type == "identifier"), ""
            )
            params.append(Param(name=pname, type=node_text(p.child_by_field_name("type"), src)))
        elif p.type == "identifier":
            text = node_text(p, src)
            if text in ("self", "cls"):
                continue
            params.append(Param(name=text))
        elif p.type in ("default_parameter", "typed_default_parameter"):
            params.append(
                Param(
                    name=node_text(p.child_by_field_name("name"), src),
                    type=node_text(p.child_by_field_name("type"), src),
                )
            )

    body = n.child_by_field_name("body")
    sym = Symbol(
        id=sym_id,
        name=name,
        kind=KIND_METHOD if receiver else KIND_FUNCTION,
        file_path=file_path,
        start_line=line1(n.start_point),
        end_line=line1(n.end_point),
        signature=_py_header_line(n, src),
        params=params or None,
        returns=non_empty_param(node_text(n.child_by_field_name("return_type"), src)),
        receiver=receiver,
        parent_id=parent_id,
        language="python",
        doc=_docstring(body, src),
    )

    calls: list[UnresolvedCall] = []
    if body is not None:

        def visit(call: Node) -> None:
            fn = call.child_by_field_name("function")
            if fn is None:
                return
            if fn.type == "identifier":
                target, qualified = node_text(fn, src), False
            elif fn.type == "attribute":
                target, qualified = node_text(fn.child_by_field_name("attribute"), src), True
            else:
                return
            if target:
                calls.append(
                    UnresolvedCall(
                        from_id=sym_id, target_name=target, kind=EDGE_CALLS, qualified=qualified
                    )
                )

        walk(body, _CALL_KINDS, visit)

    return sym, calls


def _py_header_line(n: Node, src: bytes) -> str:
    # Order matters: the trailing ":" is stripped before whitespace collapses,
    # so "def f() :" loses both the colon and the space before it.
    body = n.child_by_field_name("body")
    end = body.start_byte if body is not None else n.end_byte
    sig = src[n.start_byte : end].decode("utf-8", "replace").strip()
    return " ".join(sig.removesuffix(":").split())


def _docstring(body: Node | None, src: bytes) -> str:
    if body is None or body.named_child_count == 0:
        return ""
    first = body.named_child(0)
    if first.type != "expression_statement" or first.named_child_count == 0:
        return ""
    str_node = first.named_child(0)
    if str_node.type != "string":
        return ""
    return node_text(str_node, src).strip("\"'").strip()
