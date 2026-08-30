package parser

import (
	"context"
	"strings"

	sitter "github.com/smacker/go-tree-sitter"
	"github.com/smacker/go-tree-sitter/javascript"
	"github.com/smacker/go-tree-sitter/typescript/tsx"
	"github.com/smacker/go-tree-sitter/typescript/typescript"

	"kb-core-ui/internal/graph"
)

var jsCallKinds = map[string]bool{"call_expression": true}

func ParseTypeScript(filePath string, src []byte) (*graph.FileGraph, error) {
	return parseJSFamily(filePath, src, typescript.GetLanguage(), "typescript")
}

func ParseTSX(filePath string, src []byte) (*graph.FileGraph, error) {
	return parseJSFamily(filePath, src, tsx.GetLanguage(), "tsx")
}

func ParseJavaScript(filePath string, src []byte) (*graph.FileGraph, error) {
	return parseJSFamily(filePath, src, javascript.GetLanguage(), "javascript")
}

func parseJSFamily(filePath string, src []byte, lang *sitter.Language, langName string) (*graph.FileGraph, error) {
	p := sitter.NewParser()
	p.SetLanguage(lang)
	tree, err := p.ParseCtx(context.Background(), nil, src)
	if err != nil {
		return nil, err
	}

	fg := &graph.FileGraph{FilePath: filePath, Language: langName}
	for _, top := range namedChildren(tree.RootNode()) {
		jsDecl(top, src, filePath, langName, "", fg)
	}
	return fg, nil
}

// jsDecl handles one top-level (or class-body) statement, unwrapping
// export_statement wrappers, and appends whatever symbols/calls it finds
// onto fg. parentID is set when called for members of a class/interface body.
func jsDecl(n *sitter.Node, src []byte, filePath, lang, parentID string, fg *graph.FileGraph) {
	switch n.Type() {
	case "export_statement":
		if decl := n.ChildByFieldName("declaration"); decl != nil {
			jsDecl(decl, src, filePath, lang, parentID, fg)
		}

	case "function_declaration", "generator_function_declaration":
		sym, calls := jsFunc(n, src, filePath, lang, n.ChildByFieldName("name"), parentID, graph.KindFunction, "")
		fg.Symbols = append(fg.Symbols, sym)
		fg.UnresolvedCalls = append(fg.UnresolvedCalls, calls...)

	case "class_declaration":
		name := nodeText(n.ChildByFieldName("name"), src)
		id := symbolID(filePath, name)
		fg.Symbols = append(fg.Symbols, graph.Symbol{
			SymbolRef: graph.SymbolRef{
				ID: id, Name: name, Kind: graph.KindClass, FilePath: filePath,
				StartLine: line1(n.StartPoint()), EndLine: line1(n.EndPoint()),
			},
			Signature: jsHeaderLine(n, src),
			Language:  lang,
			Doc:       leadingComment(n, src),
			ParentID:  parentID,
		})
		if body := n.ChildByFieldName("body"); body != nil {
			for _, member := range namedChildren(body) {
				jsClassMember(member, src, filePath, lang, id, name, fg)
			}
		}

	case "interface_declaration":
		name := nodeText(n.ChildByFieldName("name"), src)
		id := symbolID(filePath, name)
		fg.Symbols = append(fg.Symbols, graph.Symbol{
			SymbolRef: graph.SymbolRef{
				ID: id, Name: name, Kind: graph.KindInterface, FilePath: filePath,
				StartLine: line1(n.StartPoint()), EndLine: line1(n.EndPoint()),
			},
			Signature: jsHeaderLine(n, src),
			Language:  lang,
			Doc:       leadingComment(n, src),
			ParentID:  parentID,
		})
		if body := n.ChildByFieldName("body"); body != nil {
			for _, member := range namedChildren(body) {
				if member.Type() != "method_signature" {
					continue
				}
				mname := nodeText(member.ChildByFieldName("name"), src)
				fg.Symbols = append(fg.Symbols, graph.Symbol{
					SymbolRef: graph.SymbolRef{
						ID: symbolID(filePath, name+"."+mname), Name: mname, Kind: graph.KindMethod, FilePath: filePath,
						StartLine: line1(member.StartPoint()), EndLine: line1(member.EndPoint()),
					},
					Signature: strings.TrimSpace(nodeText(member, src)),
					Params:    jsParams(member.ChildByFieldName("parameters"), src),
					Returns:   jsReturns(member.ChildByFieldName("return_type"), src),
					Receiver:  name,
					ParentID:  id,
					Language:  lang,
				})
			}
		}

	case "lexical_declaration", "variable_declaration":
		isConst := strings.HasPrefix(nodeText(n, src), "const")
		for _, decl := range namedChildren(n) {
			if decl.Type() != "variable_declarator" {
				continue
			}
			name := nodeText(decl.ChildByFieldName("name"), src)
			value := decl.ChildByFieldName("value")
			if value != nil && (value.Type() == "arrow_function" || value.Type() == "function_expression" || value.Type() == "function") {
				sym, calls := jsFunc(value, src, filePath, lang, decl.ChildByFieldName("name"), parentID, graph.KindFunction, "")
				sym.StartLine, sym.EndLine = line1(n.StartPoint()), line1(n.EndPoint())
				fg.Symbols = append(fg.Symbols, sym)
				fg.UnresolvedCalls = append(fg.UnresolvedCalls, calls...)
				continue
			}
			kind := graph.KindVariable
			if isConst {
				kind = graph.KindConst
			}
			typ := nodeText(decl.ChildByFieldName("type"), src)
			fg.Symbols = append(fg.Symbols, graph.Symbol{
				SymbolRef: graph.SymbolRef{
					ID: symbolID(filePath, name), Name: name, Kind: kind, FilePath: filePath,
					StartLine: line1(n.StartPoint()), EndLine: line1(n.EndPoint()),
				},
				Signature: strings.TrimSpace(nodeText(n, src)),
				Returns:   nonEmptyParam(typ),
				Language:  lang,
				Doc:       leadingComment(n, src),
				ParentID:  parentID,
			})
		}
	}
}

func jsClassMember(member *sitter.Node, src []byte, filePath, lang, classID, className string, fg *graph.FileGraph) {
	switch member.Type() {
	case "method_definition":
		sym, calls := jsFunc(member, src, filePath, lang, member.ChildByFieldName("name"), classID, graph.KindMethod, className)
		fg.Symbols = append(fg.Symbols, sym)
		fg.UnresolvedCalls = append(fg.UnresolvedCalls, calls...)
	case "public_field_definition", "field_definition":
		name := nodeText(member.ChildByFieldName("name"), src)
		if name == "" {
			return
		}
		typ := nodeText(member.ChildByFieldName("type"), src)
		fg.Symbols = append(fg.Symbols, graph.Symbol{
			SymbolRef: graph.SymbolRef{
				ID: symbolID(filePath, className+"."+name), Name: name, Kind: graph.KindVariable, FilePath: filePath,
				StartLine: line1(member.StartPoint()), EndLine: line1(member.EndPoint()),
			},
			Signature: strings.TrimSpace(nodeText(member, src)),
			Returns:   nonEmptyParam(typ),
			Receiver:  className,
			ParentID:  classID,
			Language:  lang,
		})
	}
}

// jsFunc builds a function/method Symbol plus its outgoing calls. nameNode
// is the identifier/property_identifier node holding the declared name.
func jsFunc(n *sitter.Node, src []byte, filePath, lang string, nameNode *sitter.Node, parentID string, kind graph.SymbolKind, receiver string) (graph.Symbol, []graph.UnresolvedCall) {
	name := nodeText(nameNode, src)
	qualified := name
	if receiver != "" {
		qualified = receiver + "." + name
	}
	id := symbolID(filePath, qualified)

	sym := graph.Symbol{
		SymbolRef: graph.SymbolRef{
			ID: id, Name: name, Kind: kind, FilePath: filePath,
			StartLine: line1(n.StartPoint()), EndLine: line1(n.EndPoint()),
		},
		Signature: jsHeaderLine(n, src),
		Params:    jsParams(n.ChildByFieldName("parameters"), src),
		Returns:   jsReturns(n.ChildByFieldName("return_type"), src),
		Receiver:  receiver,
		ParentID:  parentID,
		Language:  lang,
		Doc:       leadingComment(n, src),
	}

	var calls []graph.UnresolvedCall
	if body := n.ChildByFieldName("body"); body != nil {
		walk(body, jsCallKinds, func(call *sitter.Node) {
			fn := call.ChildByFieldName("function")
			if fn == nil {
				return
			}
			target := ""
			qualified := false
			switch fn.Type() {
			case "identifier":
				target = nodeText(fn, src)
			case "member_expression":
				target = nodeText(fn.ChildByFieldName("property"), src)
				qualified = true
			}
			if target != "" {
				calls = append(calls, graph.UnresolvedCall{FromID: id, TargetName: target, Kind: graph.EdgeCalls, Qualified: qualified})
			}
		})
	}
	return sym, calls
}

func jsParams(pl *sitter.Node, src []byte) []graph.Param {
	var out []graph.Param
	for _, p := range namedChildren(pl) {
		switch p.Type() {
		case "required_parameter", "optional_parameter":
			name := nodeText(p.ChildByFieldName("pattern"), src)
			typ := strings.TrimPrefix(nodeText(p.ChildByFieldName("type"), src), ":")
			out = append(out, graph.Param{Name: name, Type: strings.TrimSpace(typ)})
		case "identifier":
			out = append(out, graph.Param{Name: nodeText(p, src)})
		}
	}
	return out
}

func jsReturns(rt *sitter.Node, src []byte) []graph.Param {
	if rt == nil {
		return nil
	}
	typ := strings.TrimSpace(strings.TrimPrefix(nodeText(rt, src), ":"))
	return nonEmptyParam(typ)
}

func nonEmptyParam(typ string) []graph.Param {
	if typ == "" {
		return nil
	}
	return []graph.Param{{Type: typ}}
}

// jsHeaderLine returns the declaration up to its body, single-lined, for use
// as a rendered signature.
func jsHeaderLine(n *sitter.Node, src []byte) string {
	body := n.ChildByFieldName("body")
	end := n.EndByte()
	if body != nil {
		end = body.StartByte()
	}
	sig := strings.TrimSpace(string(src[n.StartByte():end]))
	return strings.Join(strings.Fields(sig), " ")
}
