package memory

import (
	"hash/fnv"
	"math"
	"strings"
	"unicode"
)

// Embedder turns text into a fixed-length unit vector so memories can be
// compared by cosine similarity. It's an interface so a neural backend
// (OpenAI, a local ONNX model, ...) can be swapped in later without
// touching the store.
type Embedder interface {
	Embed(text string) []float32
	// Dim is the vector length; all vectors from one embedder share it.
	Dim() int
	// Name identifies the embedder in stored metadata, so a DB embedded
	// with one model isn't silently mixed with another.
	Name() string
}

// HashingEmbedder is the default, fully-offline embedder: the "hashing
// trick" (feature hashing) over word unigrams + bigrams + character
// trigrams, with sublinear term-frequency weighting and L2 normalization.
//
// It is LEXICAL, not neural — it matches on shared vocabulary, not deep
// semantics ("login" won't match "authenticate"). That is a deliberate
// tradeoff: it needs no model download, no API key, and no dependencies, and
// it works well for the kind of text this memory holds (codebase rules,
// lessons, business-logic notes) which tend to reuse domain vocabulary.
// Include the relevant terms when you write a memory. Swap in a neural
// Embedder for true semantic recall.
type HashingEmbedder struct {
	dim int
}

// NewHashingEmbedder returns a HashingEmbedder of the given dimension
// (512 is a good default: enough to keep hash collisions low for this
// corpus size without bloating storage).
func NewHashingEmbedder(dim int) *HashingEmbedder {
	if dim <= 0 {
		dim = 512
	}
	return &HashingEmbedder{dim: dim}
}

func (e *HashingEmbedder) Dim() int { return e.dim }

// Name is versioned: it changes whenever the tokenization/weighting changes
// the vectors, because Search only compares entries embedded by the same
// Name. v2 added light stemming so morphological variants (resolve/
// resolved, package/packages) match at the word level. Bumping it means old
// entries must be re-added — acceptable for a rebuildable local store.
func (e *HashingEmbedder) Name() string { return "hashing-v2" }

var stopwords = map[string]bool{
	"the": true, "a": true, "an": true, "and": true, "or": true, "of": true,
	"to": true, "in": true, "is": true, "it": true, "for": true, "on": true,
	"with": true, "as": true, "by": true, "at": true, "be": true, "this": true,
	"that": true, "are": true, "was": true, "will": true, "if": true, "not": true,
}

// Feature weights. Word unigrams/bigrams carry the real signal; character
// trigrams only help with morphology (plural/tense) so they contribute at a
// fraction of the weight — at equal weight their hash collisions gave even
// nonsense queries a misleadingly high similarity floor.
const (
	wordWeight    = 1.0
	trigramWeight = 0.25
)

// trigramMinLen skips trigrams for very short tokens, where they're almost
// all noise.
const trigramMinLen = 4

// Embed hashes weighted features into the vector, applies sublinear TF, then
// L2 normalizes so cosine similarity == dot product.
func (e *HashingEmbedder) Embed(text string) []float32 {
	weights := make(map[uint32]float64)

	tokens := tokenize(text)
	for i, tok := range tokens {
		add(weights, tok, e.dim, wordWeight)
		// Word bigram with the previous token, to capture short phrases.
		if i > 0 {
			add(weights, tokens[i-1]+" "+tok, e.dim, wordWeight)
		}
		// Character trigrams make it robust to morphology
		// ("handler"/"handlers"/"handling" share trigrams), at low weight.
		if len(tok) >= trigramMinLen {
			for _, tri := range charTrigrams(tok) {
				add(weights, "#"+tri, e.dim, trigramWeight)
			}
		}
	}

	vec := make([]float32, e.dim)
	var sumSq float64
	for idx, sum := range weights {
		// Sublinear damping on the accumulated weight per bucket.
		w := 1 + math.Log(sum)
		vec[idx] = float32(w)
		sumSq += w * w
	}
	if sumSq > 0 {
		norm := float32(math.Sqrt(sumSq))
		for i := range vec {
			vec[i] /= norm
		}
	}
	return vec
}

// add accumulates weight into the hashed bucket for feature f.
func add(weights map[uint32]float64, f string, dim int, weight float64) {
	h := fnv.New32a()
	h.Write([]byte(f))
	idx := h.Sum32() % uint32(dim)
	weights[idx] += weight
}

func tokenize(text string) []string {
	fields := strings.FieldsFunc(strings.ToLower(text), func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsNumber(r)
	})
	out := make([]string, 0, len(fields))
	for _, f := range fields {
		if len(f) < 2 || stopwords[f] {
			continue
		}
		out = append(out, stem(f))
	}
	return out
}

// stem is a deliberately crude, conservative stemmer: it collapses the
// common plural/tense/gerund suffixes and a trailing 'e' so that
// morphological variants map to one token — "resolve", "resolved",
// "resolves", "resolving" all become "resolv"; "package"/"packages" both
// become "packag". It's applied identically to stored text and queries, so
// only internal consistency matters, not linguistic correctness. This lets
// full-weight WORD features (not just the noisy low-weight char trigrams)
// bridge morphology, which materially improves retrieval — without it, a
// query about "resolved packages" fails to match a rule about "resolve
// package".
func stem(w string) string {
	for _, suf := range []string{"ing", "edly", "ed", "es", "s"} {
		if len(w)-len(suf) >= 3 && strings.HasSuffix(w, suf) {
			w = w[:len(w)-len(suf)]
			break
		}
	}
	if len(w) > 3 && strings.HasSuffix(w, "e") {
		w = w[:len(w)-1]
	}
	return w
}

func charTrigrams(tok string) []string {
	if len(tok) < 3 {
		return nil
	}
	r := []rune(tok)
	out := make([]string, 0, len(r)-2)
	for i := 0; i+3 <= len(r); i++ {
		out = append(out, string(r[i:i+3]))
	}
	return out
}

// Cosine returns the cosine similarity of two vectors of equal length.
// Vectors from an Embedder are already unit-length, so this is their dot
// product, but it normalizes defensively in case one isn't.
func Cosine(a, b []float32) float64 {
	if len(a) != len(b) {
		return 0
	}
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return dot / (math.Sqrt(na) * math.Sqrt(nb))
}
