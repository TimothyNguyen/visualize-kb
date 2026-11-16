package store

import (
	"sort"
	"strings"

	"kb-core-ui/internal/graph"
)

// Tree builds the nested file tree from every indexed file path.
func (s *Store) Tree() (*graph.TreeNode, error) {
	rows, err := s.db.Query(`SELECT path, language FROM files ORDER BY path`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	root := &graph.TreeNode{Path: "", Name: "", Type: "dir"}
	dirs := map[string]*graph.TreeNode{"": root}

	for rows.Next() {
		var path, lang string
		if err := rows.Scan(&path, &lang); err != nil {
			return nil, err
		}
		parent := ensureDir(root, dirs, dirOf(path))
		parent.Children = append(parent.Children, &graph.TreeNode{
			Path: path, Name: baseOf(path), Type: "file", Language: lang,
		})
	}
	return root, rows.Err()
}

func ensureDir(root *graph.TreeNode, dirs map[string]*graph.TreeNode, path string) *graph.TreeNode {
	if d, ok := dirs[path]; ok {
		return d
	}
	parent := ensureDir(root, dirs, dirOf(path))
	node := &graph.TreeNode{Path: path, Name: baseOf(path), Type: "dir"}
	parent.Children = append(parent.Children, node)
	dirs[path] = node
	return node
}

func dirOf(path string) string {
	if i := strings.LastIndexByte(path, '/'); i >= 0 {
		return path[:i]
	}
	return ""
}

func baseOf(path string) string {
	if i := strings.LastIndexByte(path, '/'); i >= 0 {
		return path[i+1:]
	}
	return path
}

// SymbolsInFile returns the top-level (non-member) symbols declared in path.
func (s *Store) SymbolsInFile(path string) ([]graph.SymbolRef, error) {
	rows, err := s.db.Query(`SELECT id, name, kind, file_path, start_line, end_line FROM symbols
		WHERE file_path = ? AND parent_id = '' ORDER BY start_line`, path)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanRefs(rows)
}

// Symbol returns the full record for one symbol id, or ok=false if absent.
func (s *Store) Symbol(id string) (graph.Symbol, bool, error) {
	row := s.db.QueryRow(`SELECT id, file_path, name, kind, start_line, end_line, signature, params_json, returns_json, receiver, parent_id, language, doc
		FROM symbols WHERE id = ?`, id)
	sym, err := scanSymbol(row)
	if err != nil {
		if strings.Contains(err.Error(), "no rows") {
			return graph.Symbol{}, false, nil
		}
		return graph.Symbol{}, false, err
	}
	return sym, true, nil
}

// Members returns direct children of a class/interface symbol.
func (s *Store) Members(id string) ([]graph.SymbolRef, error) {
	rows, err := s.db.Query(`SELECT id, name, kind, file_path, start_line, end_line FROM symbols
		WHERE parent_id = ? ORDER BY start_line`, id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanRefs(rows)
}

// EdgeWithSymbol pairs an edge with the symbol at its other end, for the
// /symbols/:id/calls and /callers endpoints.
type EdgeWithSymbol struct {
	Edge   graph.Edge      `json:"edge"`
	Symbol graph.SymbolRef `json:"symbol"`
}

// Calls returns outgoing edges from id (what it calls/references).
func (s *Store) Calls(id string) ([]EdgeWithSymbol, error) {
	return s.edgesJoined(`SELECT e.source, e.target, e.kind, s.id, s.name, s.kind, s.file_path, s.start_line, s.end_line
		FROM edges e JOIN symbols s ON s.id = e.target WHERE e.source = ?`, id)
}

// Callers returns incoming edges to id (what calls/references it).
func (s *Store) Callers(id string) ([]EdgeWithSymbol, error) {
	return s.edgesJoined(`SELECT e.source, e.target, e.kind, s.id, s.name, s.kind, s.file_path, s.start_line, s.end_line
		FROM edges e JOIN symbols s ON s.id = e.source WHERE e.target = ?`, id)
}

func (s *Store) edgesJoined(query, id string) ([]EdgeWithSymbol, error) {
	rows, err := s.db.Query(query, id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []EdgeWithSymbol
	for rows.Next() {
		var ews EdgeWithSymbol
		var edgeKind, symKind string
		if err := rows.Scan(&ews.Edge.Source, &ews.Edge.Target, &edgeKind,
			&ews.Symbol.ID, &ews.Symbol.Name, &symKind, &ews.Symbol.FilePath, &ews.Symbol.StartLine, &ews.Symbol.EndLine); err != nil {
			return nil, err
		}
		ews.Edge.Kind = graph.EdgeKind(edgeKind)
		ews.Symbol.Kind = graph.SymbolKind(symKind)
		out = append(out, ews)
	}
	return out, rows.Err()
}

// FullGraph returns every symbol and edge in the repo.
func (s *Store) FullGraph() ([]graph.SymbolRef, []graph.Edge, error) {
	rows, err := s.db.Query(`SELECT id, name, kind, file_path, start_line, end_line FROM symbols`)
	if err != nil {
		return nil, nil, err
	}
	nodes, err := scanRefs(rows)
	rows.Close()
	if err != nil {
		return nil, nil, err
	}

	erows, err := s.db.Query(`SELECT source, target, kind FROM edges`)
	if err != nil {
		return nil, nil, err
	}
	defer erows.Close()
	var edges []graph.Edge
	for erows.Next() {
		var e graph.Edge
		var kind string
		if err := erows.Scan(&e.Source, &e.Target, &kind); err != nil {
			return nil, nil, err
		}
		e.Kind = graph.EdgeKind(kind)
		edges = append(edges, e)
	}
	return nodes, edges, erows.Err()
}

// Subgraph returns the BFS neighborhood of center out to depth hops,
// traversing edges in both directions.
func (s *Store) Subgraph(center string, depth int) ([]graph.SymbolRef, []graph.Edge, error) {
	visited := map[string]bool{center: true}
	frontier := []string{center}
	edgeSet := map[graph.Edge]bool{}

	for d := 0; d < depth && len(frontier) > 0; d++ {
		var next []string
		for _, id := range frontier {
			rows, err := s.db.Query(`SELECT source, target, kind FROM edges WHERE source = ? OR target = ?`, id, id)
			if err != nil {
				return nil, nil, err
			}
			for rows.Next() {
				var e graph.Edge
				var kind string
				if err := rows.Scan(&e.Source, &e.Target, &kind); err != nil {
					rows.Close()
					return nil, nil, err
				}
				e.Kind = graph.EdgeKind(kind)
				edgeSet[e] = true
				other := e.Target
				if other == id {
					other = e.Source
				}
				if !visited[other] {
					visited[other] = true
					next = append(next, other)
				}
			}
			rows.Close()
		}
		frontier = next
	}

	ids := make([]string, 0, len(visited))
	for id := range visited {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	nodes := make([]graph.SymbolRef, 0, len(ids))
	for _, id := range ids {
		row := s.db.QueryRow(`SELECT id, name, kind, file_path, start_line, end_line FROM symbols WHERE id = ?`, id)
		var ref graph.SymbolRef
		var kind string
		if err := row.Scan(&ref.ID, &ref.Name, &kind, &ref.FilePath, &ref.StartLine, &ref.EndLine); err != nil {
			continue
		}
		ref.Kind = graph.SymbolKind(kind)
		nodes = append(nodes, ref)
	}

	edges := make([]graph.Edge, 0, len(edgeSet))
	for e := range edgeSet {
		edges = append(edges, e)
	}
	return nodes, edges, nil
}

// Search does a case-insensitive substring match on symbol name, optionally
// filtered by kind, ranking exact/prefix matches first.
func (s *Store) Search(q, kind string) ([]graph.SymbolRef, error) {
	query := `SELECT id, name, kind, file_path, start_line, end_line FROM symbols WHERE name LIKE ?`
	args := []any{"%" + q + "%"}
	if kind != "" {
		query += ` AND kind = ?`
		args = append(args, kind)
	}
	query += ` LIMIT 200`
	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	refs, err := scanRefs(rows)
	if err != nil {
		return nil, err
	}
	ql := strings.ToLower(q)
	sort.SliceStable(refs, func(i, j int) bool {
		return rank(refs[i].Name, ql) < rank(refs[j].Name, ql)
	})
	return refs, nil
}

func rank(name, ql string) int {
	nl := strings.ToLower(name)
	switch {
	case nl == ql:
		return 0
	case strings.HasPrefix(nl, ql):
		return 1
	default:
		return 2
	}
}

// Stats returns repo-wide counts for the UI header.
type Stats struct {
	Files     int
	Symbols   int
	Edges     int
	Languages map[string]int
}

func (s *Store) Stats() (Stats, error) {
	var st Stats
	st.Languages = map[string]int{}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM files`).Scan(&st.Files); err != nil {
		return st, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM symbols`).Scan(&st.Symbols); err != nil {
		return st, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM edges`).Scan(&st.Edges); err != nil {
		return st, err
	}
	rows, err := s.db.Query(`SELECT language, COUNT(*) FROM files GROUP BY language`)
	if err != nil {
		return st, err
	}
	defer rows.Close()
	for rows.Next() {
		var lang string
		var n int
		if err := rows.Scan(&lang, &n); err != nil {
			return st, err
		}
		st.Languages[lang] = n
	}
	return st, rows.Err()
}

// Health is a graph-integrity + resolution-quality report, produced by the
// graph-sync bot's "check graph" step.
type Health struct {
	Files              int
	Symbols            int
	Edges              int
	UnresolvedCalls    int // call sites that couldn't be linked to a symbol
	ResolvedCalls      int // "calls"/"handles" edges (i.e. resolved call sites)
	ResolutionRate     float64
	DanglingEdges      int         // edges whose source or target symbol no longer exists
	TopUnresolvedFiles []FileCount // files with the most unresolved calls (parse-gap hotspots)
}

// FileCount pairs a file path with a count, for hotspot reporting.
type FileCount struct {
	Path  string
	Count int
}

// Health computes graph integrity and call-resolution quality metrics.
// DanglingEdges should always be 0 for a graph built by this tool (the
// builder only emits edges between known symbols) — a non-zero count means
// the DB was corrupted or written by something else, which is exactly the
// kind of thing the graph-sync bot exists to catch.
func (s *Store) Health() (Health, error) {
	var h Health
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM files`).Scan(&h.Files); err != nil {
		return h, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM symbols`).Scan(&h.Symbols); err != nil {
		return h, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM edges`).Scan(&h.Edges); err != nil {
		return h, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM unresolved_calls`).Scan(&h.UnresolvedCalls); err != nil {
		return h, err
	}
	// A resolved call is an edge of kind 'calls' or 'handles' — those come
	// from call sites. 'contains'/'implements'/'extends' are structural,
	// not call-site resolutions, so they don't count toward the rate.
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM edges WHERE kind IN ('calls','handles')`).Scan(&h.ResolvedCalls); err != nil {
		return h, err
	}
	totalCallSites := h.ResolvedCalls + h.UnresolvedCalls
	if totalCallSites > 0 {
		h.ResolutionRate = float64(h.ResolvedCalls) / float64(totalCallSites)
	}

	if err := s.db.QueryRow(`
		SELECT COUNT(*) FROM edges e
		WHERE NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = e.source)
		   OR NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = e.target)
	`).Scan(&h.DanglingEdges); err != nil {
		return h, err
	}

	rows, err := s.db.Query(`
		SELECT file_path, COUNT(*) AS n FROM unresolved_calls
		GROUP BY file_path ORDER BY n DESC LIMIT 5
	`)
	if err != nil {
		return h, err
	}
	defer rows.Close()
	for rows.Next() {
		var fc FileCount
		if err := rows.Scan(&fc.Path, &fc.Count); err != nil {
			return h, err
		}
		h.TopUnresolvedFiles = append(h.TopUnresolvedFiles, fc)
	}
	return h, rows.Err()
}

func scanRefs(rows interface {
	Next() bool
	Scan(dest ...any) error
}) ([]graph.SymbolRef, error) {
	var out []graph.SymbolRef
	for rows.Next() {
		var ref graph.SymbolRef
		var kind string
		if err := rows.Scan(&ref.ID, &ref.Name, &kind, &ref.FilePath, &ref.StartLine, &ref.EndLine); err != nil {
			return nil, err
		}
		ref.Kind = graph.SymbolKind(kind)
		out = append(out, ref)
	}
	return out, nil
}
