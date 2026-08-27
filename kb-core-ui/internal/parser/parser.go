// Package parser turns source files into graph.FileGraph values using
// tree-sitter grammars. Each language file (golang.go, typescript.go,
// python.go) implements extraction for one family of grammars; this file
// holds the registry and small tree-walking helpers shared across all of
// them.
package parser

import (
	"fmt"
	"path/filepath"
	"strings"

	sitter "github.com/smacker/go-tree-sitter"

	"kb-core-ui/internal/graph"
)

// ParseFunc parses one file's source into a FileGraph.
type ParseFunc func(filePath string, src []byte) (*graph.FileGraph, error)

var byExt = map[string]ParseFunc{
	".go":  ParseGo,
	".ts":  ParseTypeScript,
	".tsx": ParseTSX,
	".js":  ParseJavaScript,
	".jsx": ParseJavaScript,
	".mjs": ParseJavaScript,
	".py":  ParsePython,
}

// SupportedExtensions lists every file extension a parser is registered for.
func SupportedExtensions() []string {
	exts := make([]string, 0, len(byExt))
	for ext := range byExt {
		exts = append(exts, ext)
	}
	return exts
}

// LanguageFor returns the language label used in Symbol.Language for a path,
// and false if no parser handles it.
func LanguageFor(path string) (string, bool) {
	switch filepath.Ext(path) {
	case ".go":
		return "go", true
	case ".ts":
		return "typescript", true
	case ".tsx":
		return "tsx", true
	case ".js", ".mjs", ".jsx":
		return "javascript", true
	case ".py":
		return "python", true
	default:
		return "", false
	}
}

// ParseFile dispatches to the right ParseFunc by extension.
func ParseFile(filePath string, src []byte) (*graph.FileGraph, error) {
	fn, ok := byExt[filepath.Ext(filePath)]
	if !ok {
		return nil, fmt.Errorf("parser: no parser registered for %s", filePath)
	}
	return fn(filePath, src)
}

// symbolID builds a stable, repo-unique symbol id from a file path and a
// dotted qualified name (e.g. "Server.Start", "add").
func symbolID(filePath, qualifiedName string) string {
	return filePath + ":" + qualifiedName
}

// nodeText returns the source slice covered by n.
func nodeText(n *sitter.Node, src []byte) string {
	if n == nil {
		return ""
	}
	return n.Content(src)
}

// walk visits every descendant of n (n included) whose Type() is in kinds,
// calling fn for each. It does not descend past nodes with a false return
// from fn's caller — callers that want to stop at nested function
// boundaries should check node types themselves inside fn.
func walk(n *sitter.Node, kinds map[string]bool, fn func(*sitter.Node)) {
	if n == nil {
		return
	}
	if kinds[n.Type()] {
		fn(n)
	}
	for i := 0; i < int(n.ChildCount()); i++ {
		walk(n.Child(i), kinds, fn)
	}
}

// leadingComment collects contiguous "comment"-typed previous siblings of n
// (the common shape for // and /** */ comments in Go/TS/JS grammars),
// stopping at the first gap of more than one blank line, and returns their
// text with comment markers stripped.
func leadingComment(n *sitter.Node, src []byte) string {
	if n == nil || n.Parent() == nil {
		return ""
	}
	var lines []string
	cur := n.PrevSibling()
	lastRow := int(n.StartPoint().Row)
	for cur != nil && cur.Type() == "comment" {
		if lastRow-int(cur.EndPoint().Row) > 1 {
			break
		}
		lines = append([]string{cleanComment(nodeText(cur, src))}, lines...)
		lastRow = int(cur.StartPoint().Row)
		cur = cur.PrevSibling()
	}
	return strings.TrimSpace(strings.Join(lines, "\n"))
}

func cleanComment(s string) string {
	s = strings.TrimSpace(s)
	s = strings.TrimPrefix(s, "/**")
	s = strings.TrimPrefix(s, "/*")
	s = strings.TrimSuffix(s, "*/")
	s = strings.TrimPrefix(s, "//")
	s = strings.TrimPrefix(s, "///")
	lines := strings.Split(s, "\n")
	for i, l := range lines {
		l = strings.TrimSpace(l)
		l = strings.TrimPrefix(l, "* ")
		l = strings.TrimPrefix(l, "*")
		lines[i] = l
	}
	return strings.TrimSpace(strings.Join(lines, "\n"))
}

// line1 converts a tree-sitter 0-indexed row to a 1-indexed line number.
func line1(p sitter.Point) int {
	return int(p.Row) + 1
}

// fieldChildren returns every child of n whose field name is field, in
// order. Needed because grammars sometimes repeat a field (e.g.
// "const a, b = 1, 2" has two "name" fields on one const_spec) and
// ChildByFieldName only ever returns the first.
func fieldChildren(n *sitter.Node, field string) []*sitter.Node {
	var out []*sitter.Node
	if n == nil {
		return out
	}
	for i := 0; i < int(n.ChildCount()); i++ {
		if n.FieldNameForChild(i) == field {
			out = append(out, n.Child(i))
		}
	}
	return out
}

// namedChildren returns every named child of n, in order.
func namedChildren(n *sitter.Node) []*sitter.Node {
	var out []*sitter.Node
	if n == nil {
		return out
	}
	for i := 0; i < int(n.NamedChildCount()); i++ {
		out = append(out, n.NamedChild(i))
	}
	return out
}
