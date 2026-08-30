package server

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"kb-core-ui/internal/memory"
)

func validMemKind(k string) bool {
	switch memory.Kind(k) {
	case "": // empty means "no filter" for list/search
		return true
	case memory.KindRule, memory.KindLesson, memory.KindBusiness, memory.KindOverview, memory.KindRef:
		return true
	}
	return false
}

// handleMemoryList serves GET /api/memory?kind=.
func (s *Server) handleMemoryList(w http.ResponseWriter, r *http.Request) {
	kind := r.URL.Query().Get("kind")
	if !validMemKind(kind) {
		writeError(w, http.StatusBadRequest, "invalid kind")
		return
	}
	entries, err := s.memory.List(memory.Kind(kind))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, nonNil(entries))
}

// handleMemorySearch serves GET /api/memory/search?q=&kind=&top=.
func (s *Server) handleMemorySearch(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	kind := r.URL.Query().Get("kind")
	if !validMemKind(kind) {
		writeError(w, http.StatusBadRequest, "invalid kind")
		return
	}
	top := 5
	if t := r.URL.Query().Get("top"); t != "" {
		if n, err := strconv.Atoi(t); err == nil && n > 0 {
			top = n
		}
	}
	hits, err := s.memory.Search(q, memory.Kind(kind), top)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, nonNil(hits))
}

// handleMemoryAdd serves POST /api/memory.
func (s *Server) handleMemoryAdd(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Kind   string `json:"kind"`
		Title  string `json:"title"`
		Text   string `json:"text"`
		Source string `json:"source"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if body.Title == "" || body.Text == "" {
		writeError(w, http.StatusBadRequest, "title and text are required")
		return
	}
	// An empty kind is a valid filter for search, but a real entry needs one.
	if body.Kind == "" || !validMemKind(body.Kind) {
		writeError(w, http.StatusBadRequest, "invalid kind (want: rule, lesson, business, overview, reference)")
		return
	}
	e, err := s.memory.Add(memory.Kind(body.Kind), body.Title, body.Text, body.Source, time.Now())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, e)
}

// handleMemoryDelete serves DELETE /api/memory/:id.
func (s *Server) handleMemoryDelete(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/api/memory/")
	if id == "" {
		writeError(w, http.StatusBadRequest, "missing id")
		return
	}
	removed, err := s.memory.Remove(id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if !removed {
		writeError(w, http.StatusNotFound, "no memory with id "+id)
		return
	}
	writeJSON(w, map[string]bool{"removed": true})
}
