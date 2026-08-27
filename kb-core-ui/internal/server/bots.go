package server

import (
	"encoding/json"
	"net/http"
	"strings"

	"kb-core-ui/internal/bots"
)

// handleBots serves GET /api/bots — the static bot roster.
func (s *Server) handleBots(w http.ResponseWriter, r *http.Request) {
	// bots.Registry has unexported fields, but its exported ones carry the
	// json tags the contract needs. Normalize Args to a non-nil slice so it
	// marshals as "[]" not "null" — the contract types it as BotArg[] and
	// the dashboard .map()s over it unconditionally.
	defs := make([]bots.Def, len(bots.Registry))
	copy(defs, bots.Registry)
	for i := range defs {
		if defs[i].Args == nil {
			defs[i].Args = []bots.ArgDef{}
		}
	}
	writeJSON(w, defs)
}

// handleBotRun serves POST /api/bots/:name/run.
func (s *Server) handleBotRun(w http.ResponseWriter, r *http.Request) {
	// Path is /api/bots/<name>/run — parse it manually since ServeMux
	// can't express "wildcard then literal suffix".
	rest := strings.TrimPrefix(r.URL.Path, "/api/bots/")
	name, suffix, ok := strings.Cut(rest, "/")
	if !ok || suffix != "run" || name == "" {
		writeError(w, http.StatusNotFound, "not found")
		return
	}

	var body struct {
		Args map[string]string `json:"args"`
	}
	if r.Body != nil {
		// An empty body is fine (bots with no args); ignore EOF.
		_ = json.NewDecoder(r.Body).Decode(&body)
	}

	run, err := s.runner.Start(name, body.Args)
	if err != nil {
		switch err.(type) {
		case bots.ErrUnknownBot:
			writeError(w, http.StatusNotFound, err.Error())
		case bots.ErrMissingArg:
			writeError(w, http.StatusBadRequest, err.Error())
		default:
			writeError(w, http.StatusInternalServerError, err.Error())
		}
		return
	}
	writeJSON(w, run)
}

// handleBotRuns serves GET /api/bots/runs — run summaries, newest first.
func (s *Server) handleBotRuns(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, nonNil(s.runner.List()))
}

// handleBotRunByID serves GET /api/bots/runs/:id — one run with full output.
func (s *Server) handleBotRunByID(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/api/bots/runs/")
	if id == "" {
		writeError(w, http.StatusBadRequest, "missing run id")
		return
	}
	run, ok := s.runner.Get(id)
	if !ok {
		writeError(w, http.StatusNotFound, "run not found: "+id)
		return
	}
	writeJSON(w, run)
}
