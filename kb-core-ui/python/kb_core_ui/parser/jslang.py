from __future__ import annotations

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from kb_core_ui.models import (
    EDGE_CALLS,
    KIND_CLASS,
    KIND_CONST,
    KIND_FUNCTION,
    KIND_INTERFACE,
    KIND_METHOD,
    KIND_VARIABLE,
    FileGraph,
    Param,
    Symbol,
    UnresolvedCall,
)
from kb_core_ui.parser.common import (
    header_line,
    leading_comment,
    line1,
    named_children,
    node_text,
    symbol_id,
    walk,
)

JS_LANGUAGE = Language(tree_sitter_javascript.language())
TS_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
TSX_LANGUAGE = Language(tree_sitter_typescript.language_tsx())

_CALL_KINDS = {"call_expression"}


def parse_typescript(file_path: str, src: bytes) -> FileGraph:
    return _parse(file_path, src, TS_LANGUAGE, "typescript")


def parse_tsx(file_path: str, src: bytes) -> FileGraph:
    return _parse(file_path, src, TSX_LANGUAGE, "tsx")


def parse_javascript(file_path: str, src: bytes) -> FileGraph:
    return _parse(file_path, src, JS_LANGUAGE, "javascript")


def _parse(file_path: str, src: bytes, language: Language, lang_name: str) -> FileGraph:
    tree = Parser(language).parse(src)
    fg = FileGraph(file_path=file_path, language=lang_name)
    for top in named_children(tree.root_node):
        _decl(top, src, file_path, lang_name, "", fg)
    return fg


def _decl(n: Node, src: bytes, file_path: str, lang: str, parent_id: str, fg: FileGraph) -> None:
    if n.type == "export_statement":
        decl = n.child_by_field_name("declaration")
        if decl is not None:
            _decl(decl, src, file_path, lang, parent_id, fg)

    elif n.type in ("function_declaration", "generator_function_declaration"):
        sym, calls = _js_func(
            n, src, file_path, lang, n.child_by_field_name("name"), parent_id, KIND_FUNCTION, ""
        )
        fg.symbols.append(sym)
        fg.unresolved_calls.extend(calls)

    elif n.type == "class_declaration":
        name = node_text(n.child_by_field_name("name"), src)
        class_id = symbol_id(file_path, name)
        fg.symbols.append(
            Symbol(
                id=class_id,
                name=name,
                kind=KIND_CLASS,
                file_path=file_path,
                start_line=line1(n.start_point),
                end_line=line1(n.end_point),
                signature=header_line(n, src),
                language=lang,
                doc=leading_comment(n, src),
                parent_id=parent_id,
            )
        )
        for member in named_children(n.child_by_field_name("body")):
            _class_member(member, src, file_path, lang, class_id, name, fg)

    elif n.type == "interface_declaration":
        name = node_text(n.child_by_field_name("name"), src)
        iface_id = symbol_id(file_path, name)
        fg.symbols.append(
            Symbol(
                id=iface_id,
                name=name,
                kind=KIND_INTERFACE,
                file_path=file_path,
                start_line=line1(n.start_point),
                end_line=line1(n.end_point),
                signature=header_line(n, src),
                language=lang,
                doc=leading_comment(n, src),
                parent_id=parent_id,
            )
        )
        for member in named_children(n.child_by_field_name("body")):
            if member.type != "method_signature":
                continue
            mname = node_text(member.child_by_field_name("name"), src)
            fg.symbols.append(
                Symbol(
                    id=symbol_id(file_path, f"{name}.{mname}"),
                    name=mname,
                    kind=KIND_METHOD,
                    file_path=file_path,
                    start_line=line1(member.start_point),
                    end_line=line1(member.end_point),
                    signature=node_text(member, src).strip(),
                    params=_js_params(member.child_by_field_name("parameters"), src),
                    returns=_js_returns(member.child_by_field_name("return_type"), src),
                    receiver=name,
                    parent_id=iface_id,
                    language=lang,
                )
            )

    elif n.type in ("lexical_declaration", "variable_declaration"):
        is_const = node_text(n, src).startswith("const")
        for decl in named_children(n):
            if decl.type != "variable_declarator":
                continue
            name = node_text(decl.child_by_field_name("name"), src)
            value = decl.child_by_field_name("value")
            if value is not None and value.type in (
                "arrow_function",
                "function_expression",
                "function",
            ):
                sym, calls = _js_func(
                    value,
                    src,
                    file_path,
                    lang,
                    decl.child_by_field_name("name"),
                    parent_id,
                    KIND_FUNCTION,
                    "",
                )
                # The span covers the whole declaration, not just the lambda.
                sym.start_line, sym.end_line = line1(n.start_point), line1(n.end_point)
                fg.symbols.append(sym)
                fg.unresolved_calls.extend(calls)
                continue
            fg.symbols.append(
                Symbol(
                    id=symbol_id(file_path, name),
                    name=name,
                    kind=KIND_CONST if is_const else KIND_VARIABLE,
                    file_path=file_path,
                    start_line=line1(n.start_point),
                    end_line=line1(n.end_point),
                    signature=node_text(n, src).strip(),
                    returns=_non_empty_param(node_text(decl.child_by_field_name("type"), src)),
                    language=lang,
                    doc=leading_comment(n, src),
                    parent_id=parent_id,
                )
            )


def _class_member(
    member: Node, src: bytes, file_path: str, lang: str, class_id: str, class_name: str, fg: FileGraph
) -> None:
    if member.type == "method_definition":
        sym, calls = _js_func(
            member,
            src,
            file_path,
            lang,
            member.child_by_field_name("name"),
            class_id,
            KIND_METHOD,
            class_name,
        )
        fg.symbols.append(sym)
        fg.unresolved_calls.extend(calls)
    elif member.type in ("public_field_definition", "field_definition"):
        name = node_text(member.child_by_field_name("name"), src)
        if not name:
            return
        fg.symbols.append(
            Symbol(
                id=symbol_id(file_path, f"{class_name}.{name}"),
                name=name,
                kind=KIND_VARIABLE,
                file_path=file_path,
                start_line=line1(member.start_point),
                end_line=line1(member.end_point),
                signature=node_text(member, src).strip(),
                returns=_non_empty_param(node_text(member.child_by_field_name("type"), src)),
                receiver=class_name,
                parent_id=class_id,
                language=lang,
            )
        )


def _js_func(
    n: Node,
    src: bytes,
    file_path: str,
    lang: str,
    name_node: Node | None,
    parent_id: str,
    kind: str,
    receiver: str,
) -> tuple[Symbol, list[UnresolvedCall]]:
    name = node_text(name_node, src)
    qualified_name = f"{receiver}.{name}" if receiver else name
    sym_id = symbol_id(file_path, qualified_name)

    sym = Symbol(
        id=sym_id,
        name=name,
        kind=kind,
        file_path=file_path,
        start_line=line1(n.start_point),
        end_line=line1(n.end_point),
        signature=header_line(n, src),
        params=_js_params(n.child_by_field_name("parameters"), src),
        returns=_js_returns(n.child_by_field_name("return_type"), src),
        receiver=receiver,
        parent_id=parent_id,
        language=lang,
        doc=leading_comment(n, src),
    )

    calls: list[UnresolvedCall] = []
    body = n.child_by_field_name("body")
    if body is not None:

        def visit(call: Node) -> None:
            fn = call.child_by_field_name("function")
            if fn is None:
                return
            if fn.type == "identifier":
                target, qualified = node_text(fn, src), False
            elif fn.type == "member_expression":
                target, qualified = node_text(fn.child_by_field_name("property"), src), True
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


def _js_params(pl: Node | None, src: bytes) -> list[Param] | None:
    out: list[Param] = []
    for p in named_children(pl):
        if p.type in ("required_parameter", "optional_parameter"):
            typ = node_text(p.child_by_field_name("type"), src).removeprefix(":")
            out.append(
                Param(name=node_text(p.child_by_field_name("pattern"), src), type=typ.strip())
            )
        elif p.type == "identifier":
            out.append(Param(name=node_text(p, src)))
    return out or None


def _js_returns(rt: Node | None, src: bytes) -> list[Param] | None:
    if rt is None:
        return None
    return _non_empty_param(node_text(rt, src).removeprefix(":").strip())


def _non_empty_param(typ: str) -> list[Param] | None:
    return [Param(type=typ)] if typ else None
