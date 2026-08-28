from __future__ import annotations

import tree_sitter_go
from tree_sitter import Language, Node, Parser

from kb_core_ui.models import (
    EDGE_CALLS,
    EDGE_HANDLES,
    KIND_CLASS,
    KIND_CONST,
    KIND_FUNCTION,
    KIND_INTERFACE,
    KIND_METHOD,
    KIND_ROUTE,
    KIND_VARIABLE,
    FileGraph,
    Param,
    Symbol,
    UnresolvedCall,
)
from kb_core_ui.parser.common import (
    field_children,
    leading_comment,
    line1,
    named_children,
    node_text,
    symbol_id,
    walk,
)

GO_LANGUAGE = Language(tree_sitter_go.language())

_CALL_KINDS = {"call_expression"}

# net/http ServeMux (and gorilla/mux-alike) registration methods. Framework
# routers (chi, gin, echo) aren't covered.
_ROUTE_METHODS = {"HandleFunc", "Handle"}


def parse_go(file_path: str, src: bytes) -> FileGraph:
    tree = Parser(GO_LANGUAGE).parse(src)
    fg = FileGraph(file_path=file_path, language="go")

    for decl in named_children(tree.root_node):
        if decl.type == "function_declaration":
            sym, calls = _go_func(decl, src, file_path, "")
            fg.symbols.append(sym)
            fg.unresolved_calls.extend(calls)

        elif decl.type == "method_declaration":
            recv = _receiver_type(decl.child_by_field_name("receiver"), src)
            sym, calls = _go_func(decl, src, file_path, recv)
            fg.symbols.append(sym)
            fg.unresolved_calls.extend(calls)

        elif decl.type == "type_declaration":
            for spec in named_children(decl):
                if spec.type != "type_spec":
                    continue
                name = node_text(spec.child_by_field_name("name"), src)
                typ = spec.child_by_field_name("type")
                kind = KIND_INTERFACE if typ is not None and typ.type == "interface_type" else KIND_CLASS
                raw = src[decl.start_byte : decl.end_byte]
                fg.symbols.append(
                    Symbol(
                        id=symbol_id(file_path, name),
                        name=name,
                        kind=kind,
                        file_path=file_path,
                        start_line=line1(decl.start_point),
                        end_line=line1(decl.end_point),
                        signature=raw[:200].decode("utf-8", "replace").strip(),
                        language="go",
                        doc=leading_comment(decl, src),
                    )
                )

        elif decl.type in ("const_declaration", "var_declaration"):
            kind = KIND_CONST if decl.type == "const_declaration" else KIND_VARIABLE
            fg.symbols.extend(_go_specs(decl, src, file_path, kind))

    route_syms, route_calls = _go_routes(tree.root_node, src, file_path)
    fg.symbols.extend(route_syms)
    fg.unresolved_calls.extend(route_calls)
    return fg


def _go_routes(root: Node, src: bytes, file_path: str) -> tuple[list[Symbol], list[UnresolvedCall]]:
    """Route registrations live inside setup-function bodies rather than at top
    level, so this walks the whole tree and emits a synthetic route symbol
    linked to its handler through the same cross-file resolution everything
    else uses."""
    syms: list[Symbol] = []
    calls: list[UnresolvedCall] = []

    def visit(call: Node) -> None:
        fn = call.child_by_field_name("function")
        if fn is None or fn.type != "selector_expression":
            return
        if node_text(fn.child_by_field_name("field"), src) not in _ROUTE_METHODS:
            return
        args = call.child_by_field_name("arguments")
        if args is None or args.named_child_count != 2:
            return
        pattern_node = args.named_child(0)
        if pattern_node.type not in ("interpreted_string_literal", "raw_string_literal"):
            return
        pattern = node_text(pattern_node, src).strip('"`')

        handler = args.named_child(1)
        if handler.type == "identifier":
            handler_name = node_text(handler, src)
            qualified = False
        elif handler.type == "selector_expression":
            handler_name = node_text(handler.child_by_field_name("field"), src)
            qualified = True
        else:
            return  # inline func literal — no named handler to link

        route_id = symbol_id(file_path, f"route:{pattern}:{line1(call.start_point)}")
        syms.append(
            Symbol(
                id=route_id,
                name=pattern,
                kind=KIND_ROUTE,
                file_path=file_path,
                start_line=line1(call.start_point),
                end_line=line1(call.end_point),
                signature=node_text(call, src).strip(),
                language="go",
            )
        )
        calls.append(
            UnresolvedCall(
                from_id=route_id, target_name=handler_name, kind=EDGE_HANDLES, qualified=qualified
            )
        )

    walk(root, _CALL_KINDS, visit)
    return syms, calls


def _receiver_type(recv: Node | None, src: bytes) -> str:
    for p in named_children(recv):
        if p.type != "parameter_declaration":
            continue
        t = p.child_by_field_name("type")
        if t is None:
            continue
        name = node_text(t, src)
        return name[1:] if name.startswith("*") else name
    return ""


def _go_func(
    decl: Node, src: bytes, file_path: str, recv_type: str
) -> tuple[Symbol, list[UnresolvedCall]]:
    name = node_text(decl.child_by_field_name("name"), src)
    qualified_name = f"{recv_type}.{name}" if recv_type else name

    # Go's nil-vs-empty slice distinction survives into the JSON contract, so
    # an empty list has to collapse back to None.
    params: list[Param] = []
    for p in named_children(decl.child_by_field_name("parameters")):
        if p.type not in ("parameter_declaration", "variadic_parameter_declaration"):
            continue
        typ = node_text(p.child_by_field_name("type"), src)
        names = field_children(p, "name")
        if names:
            params.extend(Param(name=node_text(n, src), type=typ) for n in names)
        else:
            params.append(Param(name="", type=typ))

    returns: list[Param] = []
    res = decl.child_by_field_name("result")
    if res is not None:
        if res.type == "parameter_list":
            for p in named_children(res):
                typ = node_text(p.child_by_field_name("type"), src) or node_text(p, src)
                returns.append(Param(name=node_text(p.child_by_field_name("name"), src), type=typ))
        else:
            returns.append(Param(type=node_text(res, src)))

    sym_id = symbol_id(file_path, qualified_name)
    sym = Symbol(
        id=sym_id,
        name=name,
        kind=KIND_METHOD if recv_type else KIND_FUNCTION,
        file_path=file_path,
        start_line=line1(decl.start_point),
        end_line=line1(decl.end_point),
        signature=_go_signature(decl, src),
        params=params or None,
        returns=returns or None,
        receiver=recv_type,
        parent_id=symbol_id(file_path, recv_type) if recv_type else "",
        language="go",
        doc=leading_comment(decl, src),
    )

    calls: list[UnresolvedCall] = []
    body = decl.child_by_field_name("body")
    if body is not None:

        def visit(call: Node) -> None:
            fn = call.child_by_field_name("function")
            if fn is None:
                return
            if fn.type == "identifier":
                target, qualified = node_text(fn, src), False
            elif fn.type == "selector_expression":
                target, qualified = node_text(fn.child_by_field_name("field"), src), True
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


def _go_signature(decl: Node, src: bytes) -> str:
    body = decl.child_by_field_name("body")
    end = body.start_byte if body is not None else decl.end_byte
    return src[decl.start_byte : end].decode("utf-8", "replace").strip()


def _go_specs(decl: Node, src: bytes, file_path: str, kind: str) -> list[Symbol]:
    spec_type = "var_spec" if kind == KIND_VARIABLE else "const_spec"
    out: list[Symbol] = []
    for spec in named_children(decl):
        if spec.type != spec_type:
            continue
        doc = leading_comment(spec, src) or leading_comment(decl, src)
        for name_node in field_children(spec, "name"):
            name = node_text(name_node, src)
            out.append(
                Symbol(
                    id=symbol_id(file_path, name),
                    name=name,
                    kind=kind,
                    file_path=file_path,
                    start_line=line1(spec.start_point),
                    end_line=line1(spec.end_point),
                    signature=node_text(spec, src).strip(),
                    language="go",
                    doc=doc,
                )
            )
    return out
