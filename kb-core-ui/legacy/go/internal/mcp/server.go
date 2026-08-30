// Package mcp exposes the code graph to AI agents over the Model Context
// Protocol: instead of grepping/reading whole files, an agent calls these
// tools to search symbols, inspect a function's signature and doc, and
// walk its callers/callees — the same data the web visualizer renders,
// available directly to the model.
package mcp

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"

	"kb-core-ui/internal/memory"
	"kb-core-ui/internal/store"
)

// New builds an MCP server backed by the code graph s (resolving file-slice
// reads against repoRoot) and, if mem is non-nil, the vector memory —
// letting an agent pull relevant codebase rules/lessons in the same
// session it navigates the graph.
func New(s *store.Store, repoRoot string, mem *memory.Store) *server.MCPServer {
	srv := server.NewMCPServer("kb-core-ui", "0.1.0",
		server.WithToolCapabilities(true),
	)

	srv.AddTool(mcp.NewTool("search_symbol",
		mcp.WithDescription("Search the code graph for symbols (functions, methods, classes, consts, vars) by name substring. Use this instead of grepping files to find where something is declared."),
		mcp.WithString("query", mcp.Required(), mcp.Description("Substring to match against symbol names, case-insensitive")),
		mcp.WithString("kind", mcp.Description("Optional filter: module, package, class, interface, function, method, const, variable")),
	), searchSymbolHandler(s))

	srv.AddTool(mcp.NewTool("get_symbol",
		mcp.WithDescription("Get full detail for one symbol by id: signature, params, returns, doc comment, file path and line range. Use this before reading a file to see if the graph already answers the question."),
		mcp.WithString("id", mcp.Required(), mcp.Description("Symbol id, e.g. from search_symbol or get_file_symbols")),
	), getSymbolHandler(s))

	srv.AddTool(mcp.NewTool("get_file_symbols",
		mcp.WithDescription("List the top-level symbols (functions, classes, consts, vars) declared in one file, with their ids and line ranges — a table of contents for the file without reading it."),
		mcp.WithString("path", mcp.Required(), mcp.Description("Repo-relative file path")),
	), getFileSymbolsHandler(s))

	srv.AddTool(mcp.NewTool("get_callees",
		mcp.WithDescription("List what a symbol calls or references — trace execution forward from a function."),
		mcp.WithString("id", mcp.Required(), mcp.Description("Symbol id")),
	), getCalleesHandler(s))

	srv.AddTool(mcp.NewTool("get_callers",
		mcp.WithDescription("List what calls or references a symbol — trace execution backward to a function, e.g. to find every caller before changing its signature."),
		mcp.WithString("id", mcp.Required(), mcp.Description("Symbol id")),
	), getCallersHandler(s))

	srv.AddTool(mcp.NewTool("get_file_slice",
		mcp.WithDescription("Read exact source lines from a file by line range — use this instead of reading the whole file once get_symbol/get_file_symbols gives you the line range you need."),
		mcp.WithString("file", mcp.Required(), mcp.Description("Repo-relative file path")),
		mcp.WithNumber("start", mcp.Required(), mcp.Description("1-indexed start line, inclusive")),
		mcp.WithNumber("end", mcp.Required(), mcp.Description("1-indexed end line, inclusive")),
	), getFileSliceHandler(s, repoRoot))

	srv.AddTool(mcp.NewTool("get_tree",
		mcp.WithDescription("Get the repo's file tree as indexed by kb-core-ui."),
	), getTreeHandler(s))

	srv.AddTool(mcp.NewTool("get_stats",
		mcp.WithDescription("Get repo-wide counts: files, symbols, edges, and a per-language breakdown."),
	), getStatsHandler(s))

	if mem != nil {
		srv.AddTool(mcp.NewTool("memory_search",
			mcp.WithDescription("Semantically search kb-core-ui's vector memory for the codebase RULES, LESSONS, business-logic notes, and overviews most relevant to a task. Call this before making changes to learn the project's primary rules and past lessons — it holds knowledge that is NOT in the code itself."),
			mcp.WithString("query", mcp.Required(), mcp.Description("What you want relevant rules/lessons about, in natural language")),
			mcp.WithString("kind", mcp.Description("Optional filter: rule, lesson, business, overview, reference")),
		), memorySearchHandler(mem))

		srv.AddTool(mcp.NewTool("memory_add",
			mcp.WithDescription("Store a new lesson, rule, business-logic note, or overview in kb-core-ui's vector memory so it can be recalled later. Use this to persist something important learned during a task (e.g. a non-obvious rule, a bug's root cause) for future sessions."),
			mcp.WithString("kind", mcp.Required(), mcp.Description("rule, lesson, business, overview, or reference")),
			mcp.WithString("title", mcp.Required(), mcp.Description("Short title")),
			mcp.WithString("text", mcp.Required(), mcp.Description("The knowledge to remember")),
			mcp.WithString("source", mcp.Description("Where it came from (optional)")),
		), memoryAddHandler(mem))
	}

	return srv
}

func searchSymbolHandler(s *store.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		q := mcp.ParseString(req, "query", "")
		kind := mcp.ParseString(req, "kind", "")
		results, err := s.Search(q, kind)
		if err != nil {
			return mcp.NewToolResultErrorFromErr("search failed", err), nil
		}
		return jsonResult(results)
	}
}

func getSymbolHandler(s *store.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := mcp.ParseString(req, "id", "")
		sym, ok, err := s.Symbol(id)
		if err != nil {
			return mcp.NewToolResultErrorFromErr("lookup failed", err), nil
		}
		if !ok {
			return mcp.NewToolResultError(fmt.Sprintf("no symbol with id %q", id)), nil
		}
		return jsonResult(sym)
	}
}

func getFileSymbolsHandler(s *store.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		path := mcp.ParseString(req, "path", "")
		syms, err := s.SymbolsInFile(path)
		if err != nil {
			return mcp.NewToolResultErrorFromErr("lookup failed", err), nil
		}
		return jsonResult(syms)
	}
}

func getCalleesHandler(s *store.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := mcp.ParseString(req, "id", "")
		calls, err := s.Calls(id)
		if err != nil {
			return mcp.NewToolResultErrorFromErr("lookup failed", err), nil
		}
		return jsonResult(calls)
	}
}

func getCallersHandler(s *store.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		id := mcp.ParseString(req, "id", "")
		callers, err := s.Callers(id)
		if err != nil {
			return mcp.NewToolResultErrorFromErr("lookup failed", err), nil
		}
		return jsonResult(callers)
	}
}

func getFileSliceHandler(s *store.Store, repoRoot string) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		file := mcp.ParseString(req, "file", "")
		start := mcp.ParseInt(req, "start", 1)
		end := mcp.ParseInt(req, "end", start)
		if start < 1 || end < start {
			return mcp.NewToolResultError("invalid start/end line range"), nil
		}

		full := filepath.Join(repoRoot, filepath.FromSlash(file))
		if !strings.HasPrefix(full, filepath.Clean(repoRoot)+string(filepath.Separator)) {
			return mcp.NewToolResultError("file path escapes repo root"), nil
		}
		data, err := os.ReadFile(full)
		if err != nil {
			return mcp.NewToolResultErrorFromErr("read failed", err), nil
		}
		all := strings.Split(string(data), "\n")
		if start > len(all) {
			return mcp.NewToolResultText(""), nil
		}
		if end > len(all) {
			end = len(all)
		}
		return mcp.NewToolResultText(strings.Join(all[start-1:end], "\n")), nil
	}
}

func getTreeHandler(s *store.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		tree, err := s.Tree()
		if err != nil {
			return mcp.NewToolResultErrorFromErr("lookup failed", err), nil
		}
		return jsonResult(tree)
	}
}

func getStatsHandler(s *store.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		stats, err := s.Stats()
		if err != nil {
			return mcp.NewToolResultErrorFromErr("lookup failed", err), nil
		}
		return jsonResult(stats)
	}
}

func memorySearchHandler(mem *memory.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		query := mcp.ParseString(req, "query", "")
		kind := mcp.ParseString(req, "kind", "")
		hits, err := mem.Search(query, memory.Kind(kind), 5)
		if err != nil {
			return mcp.NewToolResultErrorFromErr("memory search failed", err), nil
		}
		return jsonResult(hits)
	}
}

func memoryAddHandler(mem *memory.Store) server.ToolHandlerFunc {
	return func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		kind := mcp.ParseString(req, "kind", "")
		title := mcp.ParseString(req, "title", "")
		text := mcp.ParseString(req, "text", "")
		source := mcp.ParseString(req, "source", "")
		if !validMemoryKind(kind) {
			return mcp.NewToolResultError("invalid kind (want: rule, lesson, business, overview, reference)"), nil
		}
		e, err := mem.Add(memory.Kind(kind), title, text, source, time.Now())
		if err != nil {
			return mcp.NewToolResultErrorFromErr("memory add failed", err), nil
		}
		return jsonResult(e)
	}
}

func validMemoryKind(k string) bool {
	switch memory.Kind(k) {
	case memory.KindRule, memory.KindLesson, memory.KindBusiness, memory.KindOverview, memory.KindRef:
		return true
	}
	return false
}

func jsonResult(v any) (*mcp.CallToolResult, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return mcp.NewToolResultErrorFromErr("marshal failed", err), nil
	}
	return mcp.NewToolResultText(string(b)), nil
}
