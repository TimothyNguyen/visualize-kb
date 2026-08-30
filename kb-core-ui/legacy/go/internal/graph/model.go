// Package graph defines the language-agnostic symbol/edge model that every
// parser produces and every consumer (store, server, mcp) shares. Field
// names mirror API_CONTRACT.md exactly — keep them in sync.
package graph

// SymbolKind classifies a node in the code graph.
type SymbolKind string

const (
	KindModule    SymbolKind = "module"
	KindPackage   SymbolKind = "package"
	KindClass     SymbolKind = "class"
	KindInterface SymbolKind = "interface"
	KindFunction  SymbolKind = "function"
	KindMethod    SymbolKind = "method"
	KindConst     SymbolKind = "const"
	KindVariable  SymbolKind = "variable"
	// KindRoute is a synthetic node: not a declaration in source, but a
	// framework route-registration call site (e.g. Go's
	// mux.HandleFunc("GET /api/tree", handler)). Its Name is the route
	// pattern; an EdgeHandles edge points at the handler function.
	KindRoute SymbolKind = "route"
)

// EdgeKind classifies a relationship between two symbols.
type EdgeKind string

const (
	EdgeCalls      EdgeKind = "calls"
	EdgeReferences EdgeKind = "references"
	EdgeContains   EdgeKind = "contains"
	EdgeImplements EdgeKind = "implements"
	EdgeExtends    EdgeKind = "extends"
	// EdgeHandles connects a KindRoute node to the function that handles it.
	EdgeHandles EdgeKind = "handles"
)

// Param is one parameter or return value: a name paired with a rendered
// type string (empty when the source language has no static type for it).
type Param struct {
	Name string `json:"name"`
	Type string `json:"type"`
}

// SymbolRef is the lightweight identity of a symbol, cheap to pass around
// in lists (file trees, call/caller lists, graph nodes).
type SymbolRef struct {
	ID        string     `json:"id"`
	Name      string     `json:"name"`
	Kind      SymbolKind `json:"kind"`
	FilePath  string     `json:"filePath"`
	StartLine int        `json:"startLine"`
	EndLine   int        `json:"endLine"`
}

// Symbol is the full record for one declaration in the graph.
type Symbol struct {
	SymbolRef
	Signature string  `json:"signature"`
	Params    []Param `json:"params"`
	Returns   []Param `json:"returns"`
	Receiver  string  `json:"receiver,omitempty"`
	ParentID  string  `json:"parentId,omitempty"`
	Language  string  `json:"language"`
	Doc       string  `json:"doc,omitempty"`
}

// Edge is a directed relationship between two symbol IDs.
type Edge struct {
	Source string   `json:"source"`
	Target string   `json:"target"`
	Kind   EdgeKind `json:"kind"`
}

// UnresolvedCall is a call/reference site found during single-file parsing
// whose target symbol isn't known yet — the builder resolves it once every
// file in the repo has been parsed (a function can call one declared in a
// file parsed later).
type UnresolvedCall struct {
	FromID     string   // caller symbol ID (always known — it's in the same file)
	TargetName string   // bare identifier or dotted/selector name as written at the call site
	Kind       EdgeKind // usually EdgeCalls, sometimes EdgeReferences/EdgeImplements/EdgeExtends
	// Qualified is true for a method/selector call site (e.g. "resp.Body.Close()"
	// -> TargetName "Close"). Such names collide constantly with unrelated
	// local methods sharing the same name (Close, Get, Add, String, ...) —
	// the true receiver is almost always an external/stdlib type this
	// tool never parses, so the builder only resolves qualified calls
	// against an unambiguous same-file/same-directory match, never a
	// repo-wide "only one with this name" guess. Bare function calls
	// (Qualified false) collide far less often and keep the repo-wide
	// fallback.
	Qualified bool
}

// FileGraph is everything one parser produced for a single source file.
type FileGraph struct {
	FilePath        string
	Language        string
	Symbols         []Symbol
	UnresolvedCalls []UnresolvedCall
}

// Graph is the fully resolved, repo-wide result: every symbol and every
// edge that could be resolved between them.
type Graph struct {
	Symbols map[string]Symbol // by ID
	Edges   []Edge
}

// TreeNode mirrors API_CONTRACT.md's file tree shape.
type TreeNode struct {
	Path     string      `json:"path"`
	Name     string      `json:"name"`
	Type     string      `json:"type"` // "dir" | "file"
	Language string      `json:"language,omitempty"`
	Children []*TreeNode `json:"children,omitempty"`
}
