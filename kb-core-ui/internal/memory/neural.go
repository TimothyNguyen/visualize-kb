package memory

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

// HTTPEmbedder calls any OpenAI-compatible `/embeddings` endpoint, giving
// the memory true semantic recall (matching "function calls" to "call
// edges resolve") instead of the lexical HashingEmbedder's vocabulary
// overlap. It intentionally speaks the widely-implemented OpenAI embeddings
// shape so it works against OpenAI, Azure, or a fully-local server like
// Ollama (`http://localhost:11434/v1`) or llama.cpp — no specific vendor
// required.
type HTTPEmbedder struct {
	baseURL string // e.g. https://api.openai.com/v1 or http://localhost:11434/v1
	model   string
	apiKey  string
	dim     int
	client  *http.Client
}

// NewHTTPEmbedder builds an HTTP embedder. dim must match the model's
// output dimension (stored so the DB can reject mismatched vectors).
func NewHTTPEmbedder(baseURL, model, apiKey string, dim int) *HTTPEmbedder {
	return &HTTPEmbedder{
		baseURL: baseURL,
		model:   model,
		apiKey:  apiKey,
		dim:     dim,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (e *HTTPEmbedder) Dim() int     { return e.dim }
func (e *HTTPEmbedder) Name() string { return "http:" + e.model }

// Embed returns the model's embedding, or a zero vector on error (so a
// transient endpoint failure degrades to "no match" rather than crashing a
// bot mid-run). Errors are surfaced on stderr for visibility.
func (e *HTTPEmbedder) Embed(text string) []float32 {
	body, _ := json.Marshal(map[string]any{"model": e.model, "input": text})
	req, err := http.NewRequest(http.MethodPost, e.baseURL+"/embeddings", bytes.NewReader(body))
	if err != nil {
		return make([]float32, e.dim)
	}
	req.Header.Set("Content-Type", "application/json")
	if e.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+e.apiKey)
	}
	resp, err := e.client.Do(req)
	if err != nil {
		fmt.Fprintf(os.Stderr, "memory: embedding request failed: %v\n", err)
		return make([]float32, e.dim)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "memory: embedding endpoint returned %s\n", resp.Status)
		return make([]float32, e.dim)
	}
	var out struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil || len(out.Data) == 0 {
		fmt.Fprintf(os.Stderr, "memory: bad embedding response: %v\n", err)
		return make([]float32, e.dim)
	}
	return out.Data[0].Embedding
}

// EmbedderFromEnv returns an HTTPEmbedder when KB_CORE_UI_EMBED_URL is set,
// else the offline lexical default. This is the one place that decides which
// embedder the CLI/server/bots use, so switching to neural embeddings is a
// matter of exporting a few env vars — no code change:
//
//	KB_CORE_UI_EMBED_URL   e.g. http://localhost:11434/v1  (required to enable)
//	KB_CORE_UI_EMBED_MODEL e.g. nomic-embed-text           (required to enable)
//	KB_CORE_UI_EMBED_KEY   API key, if the endpoint needs one (optional)
//	KB_CORE_UI_EMBED_DIM   model output dimension           (default 768)
//
// NOTE: a memory.db is embedder-specific — entries store which embedder
// produced them and Search only compares within the same embedder, so
// switching embedders means re-adding entries (or keeping a separate DB).
func EmbedderFromEnv() Embedder {
	url := os.Getenv("KB_CORE_UI_EMBED_URL")
	model := os.Getenv("KB_CORE_UI_EMBED_MODEL")
	if url == "" || model == "" {
		return NewHashingEmbedder(512)
	}
	dim := 768
	if d := os.Getenv("KB_CORE_UI_EMBED_DIM"); d != "" {
		if n, err := parseDim(d); err == nil {
			dim = n
		}
	}
	return NewHTTPEmbedder(url, model, os.Getenv("KB_CORE_UI_EMBED_KEY"), dim)
}

func parseDim(s string) (int, error) {
	var n int
	_, err := fmt.Sscanf(s, "%d", &n)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("invalid dim %q", s)
	}
	return n, nil
}
