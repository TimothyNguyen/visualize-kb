package graph

import "testing"

func TestBuildResolvesCallsAndContains(t *testing.T) {
	files := []*FileGraph{
		{
			FilePath: "a.go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "a.go:Caller", Name: "Caller", Kind: KindFunction}},
				{SymbolRef: SymbolRef{ID: "a.go:Server", Name: "Server", Kind: KindClass}},
				{SymbolRef: SymbolRef{ID: "a.go:Server.Start", Name: "Start", Kind: KindMethod}, ParentID: "a.go:Server"},
			},
			UnresolvedCalls: []UnresolvedCall{
				{FromID: "a.go:Caller", TargetName: "Helper", Kind: EdgeCalls},
			},
		},
		{
			FilePath: "b.go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "b.go:Helper", Name: "Helper", Kind: KindFunction}},
			},
		},
	}

	g := Build(files)

	if len(g.Symbols) != 4 {
		t.Fatalf("expected 4 symbols, got %d", len(g.Symbols))
	}

	var gotCalls, gotContains bool
	for _, e := range g.Edges {
		if e.Source == "a.go:Caller" && e.Target == "b.go:Helper" && e.Kind == EdgeCalls {
			gotCalls = true
		}
		if e.Source == "a.go:Server" && e.Target == "a.go:Server.Start" && e.Kind == EdgeContains {
			gotContains = true
		}
	}
	if !gotCalls {
		t.Errorf("expected resolved calls edge to unique repo-wide match, edges: %+v", g.Edges)
	}
	if !gotContains {
		t.Errorf("expected contains edge from parentID, edges: %+v", g.Edges)
	}
}

func TestResolveParentsAcrossFilesInSamePackage(t *testing.T) {
	// Regression test for a bug the graph-sync bot found in kb-core-ui's own
	// code: a Go type's methods routinely live in different files of the
	// same package than the type declaration. The parser sets a method's
	// ParentID to a same-file guess (queries.go:Store), but the type is in
	// store.go — so the contains edge dangled and the type's member list
	// was split across a phantom parent. BuildFlat must repoint the method
	// to the real type symbol by (directory, receiver name).
	files := []*FileGraph{
		{
			FilePath: "pkg/store.go",
			Language: "go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "pkg/store.go:Store", Name: "Store", Kind: KindClass, FilePath: "pkg/store.go"}, Language: "go"},
				{SymbolRef: SymbolRef{ID: "pkg/store.go:Store.Open", Name: "Open", Kind: KindMethod, FilePath: "pkg/store.go"}, Receiver: "Store", ParentID: "pkg/store.go:Store", Language: "go"},
			},
		},
		{
			FilePath: "pkg/queries.go",
			Language: "go",
			Symbols: []Symbol{
				// Parser's same-file guess — the type isn't in this file.
				{SymbolRef: SymbolRef{ID: "pkg/queries.go:Store.Search", Name: "Search", Kind: KindMethod, FilePath: "pkg/queries.go"}, Receiver: "Store", ParentID: "pkg/queries.go:Store", Language: "go"},
			},
		},
	}

	g := Build(files)

	// The cross-file method must now be parented to the real type symbol.
	if got := g.Symbols["pkg/queries.go:Store.Search"].ParentID; got != "pkg/store.go:Store" {
		t.Fatalf("expected cross-file method reparented to pkg/store.go:Store, got %q", got)
	}

	// No dangling edges: every edge endpoint must exist as a symbol.
	for _, e := range g.Edges {
		if _, ok := g.Symbols[e.Source]; !ok {
			t.Errorf("dangling edge source %q", e.Source)
		}
		if _, ok := g.Symbols[e.Target]; !ok {
			t.Errorf("dangling edge target %q", e.Target)
		}
	}

	// Both methods must be contained by the single real type.
	contained := map[string]bool{}
	for _, e := range g.Edges {
		if e.Kind == EdgeContains && e.Source == "pkg/store.go:Store" {
			contained[e.Target] = true
		}
	}
	if !contained["pkg/store.go:Store.Open"] || !contained["pkg/queries.go:Store.Search"] {
		t.Fatalf("expected both methods contained by pkg/store.go:Store, got %v", contained)
	}
}

func TestResolveCallQualifiedNeverUsesRepoWideFallback(t *testing.T) {
	// Regression test: "resp.Body.Close()" reduces to the bare name "Close"
	// — the receiver (an unparsed stdlib type) is invisible to this tool.
	// Before the Qualified flag, if the repo happened to have exactly one
	// local symbol named "Close" (a common method name), the "unique
	// repo-wide match" fallback wired the stdlib call to it anyway.
	// Bare/unqualified calls (plain "Helper()") keep the fallback — see
	// TestBuildResolvesCallsAndContains.
	files := []*FileGraph{
		{
			FilePath: "a.go",
			Language: "go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "a.go:DoRequest", Name: "DoRequest", Kind: KindFunction, FilePath: "a.go"}, Language: "go"},
			},
			UnresolvedCalls: []UnresolvedCall{
				{FromID: "a.go:DoRequest", TargetName: "Close", Kind: EdgeCalls, Qualified: true},
			},
		},
		{
			FilePath: "store/store.go",
			Language: "go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "store/store.go:Close", Name: "Close", Kind: KindMethod, FilePath: "store/store.go"}, Language: "go"},
			},
		},
	}
	g := Build(files)
	for _, e := range g.Edges {
		if e.Source == "a.go:DoRequest" {
			t.Fatalf("expected qualified call with no same-file/dir match to stay unresolved, got edge to %s", e.Target)
		}
	}
}

func TestResolveCallNeverCrossesLanguageFamilies(t *testing.T) {
	// Regression test: Go's "os.Stat(...)" call site reduces to the bare
	// name "Stat" — same as an unrelated React "Stat" component in the web/
	// frontend. Before the language-family filter, resolveCall's
	// unique-repo-wide-match fallback wired these together into a bogus
	// cross-language edge.
	files := []*FileGraph{
		{
			FilePath: "cmd/common.go",
			Language: "go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "cmd/common.go:resolveRepoPath", Name: "resolveRepoPath", Kind: KindFunction}, Language: "go"},
			},
			UnresolvedCalls: []UnresolvedCall{
				{FromID: "cmd/common.go:resolveRepoPath", TargetName: "Stat", Kind: EdgeCalls},
			},
		},
		{
			FilePath: "web/src/components/Header/Header.tsx",
			Language: "tsx",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "web/src/components/Header/Header.tsx:Stat", Name: "Stat", Kind: KindFunction}, Language: "tsx"},
			},
		},
	}
	g := Build(files)
	for _, e := range g.Edges {
		if e.Source == "cmd/common.go:resolveRepoPath" {
			t.Fatalf("expected os.Stat call to stay unresolved (no Go \"Stat\" symbol exists), got a cross-language edge to %s", e.Target)
		}
	}
}

func TestResolveCallMatchesAcrossJSFamily(t *testing.T) {
	// TypeScript/TSX/JavaScript compile to one runtime and commonly import
	// across those extensions, so calls between them must still resolve.
	files := []*FileGraph{
		{
			FilePath: "web/src/App.tsx",
			Language: "tsx",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "web/src/App.tsx:App", Name: "App", Kind: KindFunction}, Language: "tsx"},
			},
			UnresolvedCalls: []UnresolvedCall{
				{FromID: "web/src/App.tsx:App", TargetName: "helper", Kind: EdgeCalls},
			},
		},
		{
			FilePath: "web/src/utils/helper.ts",
			Language: "typescript",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "web/src/utils/helper.ts:helper", Name: "helper", Kind: KindFunction}, Language: "typescript"},
			},
		},
	}
	g := Build(files)
	for _, e := range g.Edges {
		if e.Source == "web/src/App.tsx:App" && e.Target == "web/src/utils/helper.ts:helper" {
			return
		}
	}
	t.Fatal("expected tsx -> ts call to resolve within the JS family")
}

func TestResolveCallPrefersSameFileThenSameDir(t *testing.T) {
	files := []*FileGraph{
		{
			FilePath: "pkg/a.go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "pkg/a.go:Caller", Name: "Caller", Kind: KindFunction}},
				{SymbolRef: SymbolRef{ID: "pkg/a.go:log", Name: "log", Kind: KindFunction}},
			},
			UnresolvedCalls: []UnresolvedCall{
				{FromID: "pkg/a.go:Caller", TargetName: "log", Kind: EdgeCalls},
			},
		},
		{
			FilePath: "pkg/b.go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "pkg/b.go:log", Name: "log", Kind: KindFunction}},
			},
		},
		{
			FilePath: "other/c.go",
			Symbols: []Symbol{
				{SymbolRef: SymbolRef{ID: "other/c.go:log", Name: "log", Kind: KindFunction}},
			},
		},
	}
	g := Build(files)
	for _, e := range g.Edges {
		if e.Source == "pkg/a.go:Caller" {
			if e.Target != "pkg/a.go:log" {
				t.Fatalf("expected same-file match, got %s", e.Target)
			}
			return
		}
	}
	t.Fatal("expected a resolved edge from Caller")
}
