# Document Knowledge Model — Current State & Target Design

## Current substrate (verified)

- `FileType` enum (`kb_core/detect.py:25-30`): `CODE`, `DOCUMENT`, `PAPER`, `IMAGE`, `VIDEO`.
- `classify_file()` (`detect.py:503-537`, read in full) routes by extension: `DOC_EXTENSIONS` (`.md`/`.mdx`/`.qmd`/`.skill`/`.txt`/`.rst`/`.html`/`.yaml`/`.yml`, `detect.py:45`) → `DOCUMENT` unless `_looks_like_paper()` (`:308`, checked at `:528`) reclassifies it as `PAPER`; `PAPER_EXTENSIONS` (`.pdf`, `:46`) → `PAPER` (except Xcode asset-catalog PDFs, which are vector icons, not papers — `:521-522`); `IMAGE_EXTENSIONS` (`:47`) → `IMAGE`; `OFFICE_EXTENSIONS`/`GOOGLE_WORKSPACE_EXTENSIONS` → `DOCUMENT` (converted via `convert_office_file()` `:721` / `google_workspace.py:convert_google_workspace_file()` `:163`). Package manifests are deliberately excluded from the document path and routed to `CODE` (`:504-510`, bug `#1377`: otherwise a manifest like `apm.yml` would be LLM-extracted as a document and split into duplicate file-anchored nodes alongside its deterministic AST-parsed representation).
- Document/paper files go through the **LLM extraction path**, not AST extraction: `llm.py:extract_files_direct()` (`:1885`) and its semantic-extraction entry (`:1894`, docstring "Extract semantic nodes/edges from a list of files using the given backend") produce generic nodes/edges from document content, cached via `cache.py`'s prompt-fingerprinted semantic cache (`prompt_fingerprint()` `:100`, `save_semantic_cache()` `:1345`, `load_cached()` `:924`) — this is the same mechanism `architecture-current.md` describes for semantic/LLM extraction generally, applied here to non-code file types.
- **Confirmed gap**: no `DESCRIBES`/`RATIONALE_FOR` or any other typed document↔code relation exists anywhere in `kb_core/` — a repo-wide search for these terms and for a `Document`/`DocumentSource` class returned no matches outside an unrelated `source_type`-named field in `google_workspace.py`. Documents extracted today produce generic entity/relation nodes (whatever the LLM extraction schema yields) with no structural distinction between "this is a document," "this is a section of a document," or "this is a claim a document makes about a code entity."

## Gap vs. mission's document-knowledge ask

1. **No document hierarchy.** A markdown file becomes flat extracted nodes, not a `Document` node with `Section` children — so "which section of `ARCHITECTURE.md` describes the cache layer" isn't a graph question today, only a full-text one.
2. **No typed document→code relationships.** Nothing marks "this doc paragraph describes/justifies/documents that function" as a first-class edge; if the LLM extraction happens to produce a same-named entity, it's indistinguishable from a coincidental name match — no `DESCRIBES`/`RATIONALE_FOR` semantics, no confidence/provenance distinguishing "explicitly stated in the doc" from "inferred by extraction."
3. **No provenance fields for documents specifically** — no revision hash, no "this doc section was authored/updated in commit X" (the `source_revision` field proposed in `cross-repo-design.md` for repo identity generalizes to documents too, but nothing wires it up).
4. **Papers (`PAPER` file type) already get PDF text extraction** (`extract_pdf_text()`, `detect.py:540+`), but there's no distinct treatment for a paper's structure (abstract/sections/citations) vs. a plain document's — both currently funnel into the same generic LLM entity-extraction path.

## Target model

```
DocumentSource   - a file classified as DOCUMENT/PAPER (source_type from cross-repo-design.md's identity fields)
  -> Document      - the whole file as one node (today's implicit unit)
    -> Section      - a heading-delimited chunk (new; markdown/rst have headings, PDFs have page/section boundaries)
      -> Claim       - an extracted assertion the document makes, optionally targeting a code entity
```

Typed edges (new relation values, same edge shape as `cross-repo-design.md`'s new cross-repo edges — `relation`/`context`/`confidence`/`confidence_score`/`source_file`/`_src`/`_tgt`, no new schema):

- `DESCRIBES` — a `Section`/`Claim` describes a code entity's behavior.
- `RATIONALE_FOR` — a `Section`/`Claim` explains *why* a code entity exists or was built a certain way (design docs, ADRs).
- `DOCUMENTS_API` — narrower case of `DESCRIBES` for API/interface surfaces specifically, if warranted once real corpora show `DESCRIBES` is too coarse to be useful for query scoping — don't add speculatively.

## Integration point

- `build.py` is where AST-extracted and LLM-extracted nodes are merged into one graph today (per `architecture-current.md`'s pipeline trace) — the `Document`/`Section`/`Claim` hierarchy should be introduced at this same merge point, as an additional node-kind family alongside the existing code-entity kinds, not a parallel pipeline.
- `Section` chunking for markdown/rst can reuse whatever heading-parsing the existing document LLM-extraction prompt already relies on (extraction prompt construction lives under `llm.py`'s document-extraction path — a follow-up should confirm whether heading structure is already visible to the prompt before adding a separate chunker).
- New relation detection (`DESCRIBES`/`RATIONALE_FOR`) follows the same pattern already established by `cross_repo_types.py:link_shared_type_declarations()` (per `cross-repo-design.md`): a dedicated pass, confidence-scored, run after base extraction — not baked into the LLM extraction prompt as unverifiable free-text output.

## Migration path

1. Add `Section` as an intermediate node between `Document` and its extracted entities for markdown/rst files only (most deterministic heading structure) — defer PDF page/section chunking until the markdown case is proven.
2. Add `DESCRIBES` as the first new relation type (mirrors `cross-repo-design.md`'s advice to add one cross-repo edge type at a time, starting with the most deterministic signal) — a document section that names a code entity already present in the graph is the deterministic signal; don't infer `DESCRIBES` from prose similarity alone.
3. `RATIONALE_FOR` and `DOCUMENTS_API` follow only once `DESCRIBES` is validated against real corpora — avoid building the full relation taxonomy speculatively (same caution `architecture-target.md`'s Risks section raises about the mission's broader wishlist).
4. Provenance fields (`source_revision` etc.) reuse `cross-repo-design.md`'s identity model rather than inventing a document-specific version scheme.
