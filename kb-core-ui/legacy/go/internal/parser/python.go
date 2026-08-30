package parser

import (
	"context"
	"strings"

	sitter "github.com/smacker/go-tree-sitter"
	"github.com/smacker/go-tree-sitter/python"

	"kb-core-ui/internal/graph"
)

var pyCallKinds = map[string]bool{"call": true}

func ParsePython(filePath string, src []byte) (*graph.FileGraph, error) {
	p := sitter.NewParser()
	p.SetLanguage(python.GetLanguage())
	tree, err := p.ParseCtx(context.Background(), nil, src)
	if err != nil {
		return nil, err
	}

	fg := &graph.FileGraph{FilePath: filePath, Language: "python"}
	for _, top := range namedChildren(tree.RootNode()) {
		switch top.Type() {
		case "function_definition":
			sym, calls := pyFunc(top, src, filePath, "", "")
			fg.Symbols = append(fg.Symbols, sym)
			fg.UnresolvedCalls = append(fg.UnresolvedCalls, calls...)

		case "class_definition":
			name := nodeText(top.ChildByFieldName("name"), src)
			id := symbolID(filePath, name)
			fg.Symbols = append(fg.Symbols, graph.Symbol{
				SymbolRef: graph.SymbolRef{
					ID: id, Name: name, Kind: graph.KindClass, FilePath: filePath,
					StartLine: line1(top.StartPoint()), EndLine: line1(top.EndPoint()),
				},
				Signature: pyHeaderLine(top, src),
				Language:  "python",
				Doc:       pyDocstring(top.ChildByFieldName("body"), src),
			})
			if body := top.ChildByFieldName("body"); body != nil {
				for _, member := range namedChildren(body) {
					if member.Type() != "function_definition" {
						continue
					}
					sym, calls := pyFunc(member, src, filePath, id, name)
					fg.Symbols = append(fg.Symbols, sym)
					fg.UnresolvedCalls = append(fg.UnresolvedCalls, calls...)
				}
			}

		case "expression_statement":
			if len(namedChildren(top)) != 1 {
				continue
			}
			assign := namedChildren(top)[0]
			if assign.Type() != "assignment" {
				continue
			}
			left := assign.ChildByFieldName("left")
			if left == nil || left.Type() != "identifier" {
				continue
			}
			name := nodeText(left, src)
			kind := graph.KindVariable
			if name == strings.ToUpper(name) && strings.ToUpper(name) != strings.ToLower(name) {
				kind = graph.KindConst
			}
			typ := nodeText(assign.ChildByFieldName("type"), src)
			fg.Symbols = append(fg.Symbols, graph.Symbol{
				SymbolRef: graph.SymbolRef{
					ID: symbolID(filePath, name), Name: name, Kind: kind, FilePath: filePath,
					StartLine: line1(top.StartPoint()), EndLine: line1(top.EndPoint()),
				},
				Signature: strings.TrimSpace(nodeText(top, src)),
				Returns:   nonEmptyParam(typ),
				Language:  "python",
			})
		}
	}
	return fg, nil
}

func pyFunc(n *sitter.Node, src []byte, filePath, parentID, receiver string) (graph.Symbol, []graph.UnresolvedCall) {
	name := nodeText(n.ChildByFieldName("name"), src)
	qualified := name
	kind := graph.KindFunction
	if receiver != "" {
		qualified = receiver + "." + name
		kind = graph.KindMethod
	}
	id := symbolID(filePath, qualified)

	var params []graph.Param
	if pl := n.ChildByFieldName("parameters"); pl != nil {
		for _, p := range namedChildren(pl) {
			switch p.Type() {
			case "typed_parameter":
				pname := ""
				for _, c := range namedChildren(p) {
					if c.Type() == "identifier" {
						pname = nodeText(c, src)
						break
					}
				}
				params = append(params, graph.Param{Name: pname, Type: nodeText(p.ChildByFieldName("type"), src)})
			case "identifier":
				if nodeText(p, src) == "self" || nodeText(p, src) == "cls" {
					continue
				}
				params = append(params, graph.Param{Name: nodeText(p, src)})
			case "default_parameter", "typed_default_parameter":
				pname := nodeText(p.ChildByFieldName("name"), src)
				params = append(params, graph.Param{Name: pname, Type: nodeText(p.ChildByFieldName("type"), src)})
			}
		}
	}

	returns := nonEmptyParam(nodeText(n.ChildByFieldName("return_type"), src))

	sym := graph.Symbol{
		SymbolRef: graph.SymbolRef{
			ID: id, Name: name, Kind: kind, FilePath: filePath,
			StartLine: line1(n.StartPoint()), EndLine: line1(n.EndPoint()),
		},
		Signature: pyHeaderLine(n, src),
		Params:    params,
		Returns:   returns,
		Receiver:  receiver,
		ParentID:  parentID,
		Language:  "python",
		Doc:       pyDocstring(n.ChildByFieldName("body"), src),
	}

	var calls []graph.UnresolvedCall
	if body := n.ChildByFieldName("body"); body != nil {
		walk(body, pyCallKinds, func(call *sitter.Node) {
			fn := call.ChildByFieldName("function")
			if fn == nil {
				return
			}
			target := ""
			qualified := false
			switch fn.Type() {
			case "identifier":
				target = nodeText(fn, src)
			case "attribute":
				target = nodeText(fn.ChildByFieldName("attribute"), src)
				qualified = true
			}
			if target != "" {
				calls = append(calls, graph.UnresolvedCall{FromID: id, TargetName: target, Kind: graph.EdgeCalls, Qualified: qualified})
			}
		})
	}
	return sym, calls
}

func pyHeaderLine(n *sitter.Node, src []byte) string {
	body := n.ChildByFieldName("body")
	end := n.EndByte()
	if body != nil {
		end = body.StartByte()
	}
	sig := strings.TrimSpace(string(src[n.StartByte():end]))
	sig = strings.TrimSuffix(sig, ":")
	return strings.Join(strings.Fields(sig), " ")
}

// pyDocstring returns the text of a leading string-expression statement in
// a function/class body, Python's docstring convention.
func pyDocstring(body *sitter.Node, src []byte) string {
	if body == nil || body.NamedChildCount() == 0 {
		return ""
	}
	first := body.NamedChild(0)
	if first.Type() != "expression_statement" || first.NamedChildCount() == 0 {
		return ""
	}
	strNode := first.NamedChild(0)
	if strNode.Type() != "string" {
		return ""
	}
	text := nodeText(strNode, src)
	text = strings.Trim(text, "\"'")
	text = strings.TrimPrefix(text, "\"\"")
	text = strings.TrimSuffix(text, "\"\"")
	return strings.TrimSpace(text)
}
