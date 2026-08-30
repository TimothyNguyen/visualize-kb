// Package server implements the REST API described in API_CONTRACT.md on
// top of a store.Store, plus (optionally) serving the built web UI.
package server

import (
	"encoding/json"
	"log"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"kb-core-ui/internal/bots"
	"kb-core-ui/internal/memory"
	"kb-core-ui/internal/store"
)

// Server holds everything the HTTP handlers need.
type Server struct {
	store    *store.Store
	repoRoot string
	webDir   string        // optional: built frontend assets to serve at "/"; empty disables it
	runner   *bots.Runner  // optional: enables the bot-control endpoints; nil disables them
	memory   *memory.Store // optional: enables the vector-memory endpoints; nil disables them
	mux      *http.ServeMux
}

// New builds a Server. webDir may be "" (no UI at "/"), runner may be nil
// (no bot endpoints), and mem may be nil (no memory endpoints) — the graph
// API always works regardless.
func New(s *store.Store, repoRoot, webDir string, runner *bots.Runner, mem *memory.Store) *Server {
	srv := &Server{store: s, repoRoot: repoRoot, webDir: webDir, runner: runner, memory: mem, mux: http.NewServeMux()}
	srv.routes()
	return srv
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	withCORS(s.mux).ServeHTTP(w, r)
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /api/tree", s.handleTree)
	s.mux.HandleFunc("GET /api/graph", s.handleGraph)
	s.mux.HandleFunc("GET /api/graph/subgraph", s.handleSubgraph)
	s.mux.HandleFunc("GET /api/search", s.handleSearch)
	s.mux.HandleFunc("GET /api/source", s.handleSource)
	s.mux.HandleFunc("GET /api/stats", s.handleStats)
	s.mux.HandleFunc("GET /api/files/", s.handleFileSymbols)
	s.mux.HandleFunc("GET /api/symbols/", s.handleSymbols)

	if s.runner != nil {
		s.mux.HandleFunc("GET /api/bots", s.handleBots)
		s.mux.HandleFunc("POST /api/bots/", s.handleBotRun) // /api/bots/:name/run
		s.mux.HandleFunc("GET /api/bots/runs", s.handleBotRuns)
		s.mux.HandleFunc("GET /api/bots/runs/", s.handleBotRunByID) // /api/bots/runs/:id
	}

	if s.memory != nil {
		s.mux.HandleFunc("GET /api/memory", s.handleMemoryList)
		s.mux.HandleFunc("GET /api/memory/search", s.handleMemorySearch)
		s.mux.HandleFunc("POST /api/memory", s.handleMemoryAdd)
		s.mux.HandleFunc("DELETE /api/memory/", s.handleMemoryDelete) // /api/memory/:id
	}

	if s.webDir != "" {
		fs := http.FileServer(http.Dir(s.webDir))
		s.mux.Handle("/", spaHandler(s.webDir, fs))
	} else {
		s.mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/" {
				w.Write([]byte("kb-core-ui API server is running. Build web/ and pass --web-dir to serve the UI here.\n"))
				return
			}
			http.NotFound(w, r)
		})
	}
}

// spaHandler serves static files, falling back to index.html for any path
// that isn't a real file — required for a client-side-routed SPA.
func spaHandler(dir string, fs http.Handler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		full := filepath.Join(dir, filepath.Clean(r.URL.Path))
		if info, err := os.Stat(full); err != nil || info.IsDir() {
			http.ServeFile(w, r, filepath.Join(dir, "index.html"))
			return
		}
		fs.ServeHTTP(w, r)
	}
}

func withCORS(h http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		h.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("server: encode response: %v", err)
	}
}

func writeError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

// nonNil ensures an empty result marshals as "[]" rather than "null" — a
// nil Go slice and an empty one are equivalent to callers, but not to JSON
// consumers expecting an array.
func nonNil[T any](s []T) []T {
	if s == nil {
		return []T{}
	}
	return s
}

func (s *Server) handleTree(w http.ResponseWriter, r *http.Request) {
	tree, err := s.store.Tree()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, tree)
}

// handleFileSymbols serves GET /api/files/*path/symbols. Go's ServeMux
// can't express a wildcard followed by a literal suffix, so this parses
// the path manually.
func (s *Server) handleFileSymbols(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path, "/api/files/")
	path, ok := strings.CutSuffix(rest, "/symbols")
	if !ok {
		http.NotFound(w, r)
		return
	}
	path = strings.TrimSuffix(path, "/")
	if path == "" {
		writeError(w, http.StatusBadRequest, "missing file path")
		return
	}
	syms, err := s.store.SymbolsInFile(path)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, nonNil(syms))
}

// handleSymbols serves GET /api/symbols/:id, /api/symbols/:id/members,
// /api/symbols/:id/calls, /api/symbols/:id/callers.
//
// Symbol ids embed a file path (e.g. "internal/parser/parser.go:ParseFile")
// so the client percent-encodes their slashes as %2F to keep the id as one
// path segment. r.URL.Path is already decoded by net/http — using it here
// would silently unescape %2F back to "/" and corrupt the id/suffix split.
// r.URL.EscapedPath() keeps %2F literal so the split is unambiguous; only
// the extracted id segment gets unescaped afterward.
func (s *Server) handleSymbols(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.EscapedPath(), "/api/symbols/")
	idEscaped, suffix, hasSuffix := strings.Cut(rest, "/")
	id, err := url.PathUnescape(idEscaped)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid symbol id encoding")
		return
	}

	switch {
	case !hasSuffix:
		sym, ok, err := s.store.Symbol(id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if !ok {
			writeError(w, http.StatusNotFound, "symbol not found: "+id)
			return
		}
		writeJSON(w, sym)

	case suffix == "members":
		members, err := s.store.Members(id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, nonNil(members))

	case suffix == "calls":
		calls, err := s.store.Calls(id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, nonNil(calls))

	case suffix == "callers":
		callers, err := s.store.Callers(id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, nonNil(callers))

	default:
		http.NotFound(w, r)
	}
}

func (s *Server) handleGraph(w http.ResponseWriter, r *http.Request) {
	nodes, edges, err := s.store.FullGraph()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, map[string]any{"nodes": nonNil(nodes), "edges": nonNil(edges)})
}

func (s *Server) handleSubgraph(w http.ResponseWriter, r *http.Request) {
	symbol := r.URL.Query().Get("symbol")
	if symbol == "" {
		writeError(w, http.StatusBadRequest, "missing symbol query param")
		return
	}
	depth := 2
	if d := r.URL.Query().Get("depth"); d != "" {
		n, err := strconv.Atoi(d)
		if err != nil || n < 1 {
			writeError(w, http.StatusBadRequest, "invalid depth")
			return
		}
		depth = n
	}
	if _, ok, err := s.store.Symbol(symbol); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	} else if !ok {
		writeError(w, http.StatusNotFound, "symbol not found: "+symbol)
		return
	}
	nodes, edges, err := s.store.Subgraph(symbol, depth)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, map[string]any{"nodes": nonNil(nodes), "edges": nonNil(edges), "center": symbol})
}

func (s *Server) handleSearch(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	kind := r.URL.Query().Get("kind")
	results, err := s.store.Search(q, kind)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, nonNil(results))
}

func (s *Server) handleSource(w http.ResponseWriter, r *http.Request) {
	file := r.URL.Query().Get("file")
	if file == "" {
		writeError(w, http.StatusBadRequest, "missing file query param")
		return
	}
	startStr := r.URL.Query().Get("start")
	endStr := r.URL.Query().Get("end")
	start, err1 := strconv.Atoi(startStr)
	end, err2 := strconv.Atoi(endStr)
	if err1 != nil || err2 != nil || start < 1 || end < start {
		writeError(w, http.StatusBadRequest, "invalid start/end")
		return
	}

	full := filepath.Join(s.repoRoot, filepath.FromSlash(file))
	if !strings.HasPrefix(full, filepath.Clean(s.repoRoot)+string(filepath.Separator)) {
		writeError(w, http.StatusBadRequest, "file path escapes repo root")
		return
	}
	data, err := os.ReadFile(full)
	if err != nil {
		writeError(w, http.StatusNotFound, "file not found: "+file)
		return
	}
	all := strings.Split(string(data), "\n")
	if start > len(all) {
		writeJSON(w, map[string]any{"filePath": file, "startLine": start, "lines": []string{}})
		return
	}
	if end > len(all) {
		end = len(all)
	}
	lines := all[start-1 : end]
	writeJSON(w, map[string]any{"filePath": file, "startLine": start, "lines": lines})
}

func (s *Server) handleStats(w http.ResponseWriter, r *http.Request) {
	stats, err := s.store.Stats()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, map[string]any{
		"files": stats.Files, "symbols": stats.Symbols, "edges": stats.Edges, "languages": stats.Languages,
	})
}
