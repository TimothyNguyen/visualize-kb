<p align="center">
  <a href="https://kb-core.com"><img src="https://raw.githubusercontent.com/kb-core/kb_core/v8/docs/logo.png" width="300" height="140" alt="KB Core"/></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/25296?utm_source=repository-badge&amp;utm_medium=badge&amp;utm_campaign=badge-repository-25296" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/repositories/25296" alt="kb-core%2Fkb-core | Trendshift" width="250" height="55"/></a>
</p>

<div align="center">
<details><summary><b>Read this in other languages</b></summary>

🇺🇸 <a href="README.md">English</a> | 🇨🇳 <a href="docs/translations/README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="docs/translations/README.ja-JP.md">日本語</a> | 🇰🇷 <a href="docs/translations/README.ko-KR.md">한국어</a> | 🇩🇪 <a href="docs/translations/README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="docs/translations/README.fr-FR.md">Français</a> | 🇪🇸 <a href="docs/translations/README.es-ES.md">Español</a> | 🇮🇳 <a href="docs/translations/README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="docs/translations/README.pt-BR.md">Português</a> | 🇷🇺 <a href="docs/translations/README.ru-RU.md">Русский</a> | 🇸🇦 <a href="docs/translations/README.ar-SA.md">العربية</a> | 🇮🇷 <a href="docs/translations/README.fa-IR.md">فارسی</a> | 🇮🇹 <a href="docs/translations/README.it-IT.md">Italiano</a> | 🇵🇱 <a href="docs/translations/README.pl-PL.md">Polski</a> | 🇳🇱 <a href="docs/translations/README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="docs/translations/README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="docs/translations/README.uk-UA.md">Українська</a> | 🇻🇳 <a href="docs/translations/README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="docs/translations/README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="docs/translations/README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="docs/translations/README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="docs/translations/README.ro-RO.md">Română</a> | 🇨🇿 <a href="docs/translations/README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="docs/translations/README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="docs/translations/README.da-DK.md">Dansk</a> | 🇳🇴 <a href="docs/translations/README.no-NO.md">Norsk</a> | 🇭🇺 <a href="docs/translations/README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="docs/translations/README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="docs/translations/README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="docs/translations/README.zh-TW.md">繁體中文</a> | 🇵🇭 <a href="docs/translations/README.fil-PH.md">Filipino</a> | 🇮🇱 <a href="docs/translations/README.he-IL.md">עברית</a>

</details>
</div>

<p align="center">
  <a href="https://pypi.org/project/kb-core/"><img src="https://img.shields.io/pypi/v/kb-core" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/kb-core"><img src="https://img.shields.io/pepy/dt/kb-core?color=blue&label=downloads" alt="Downloads"/></a>
  <a href="https://discord.gg/598Ad9zQZ"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://www.youtube.com/@kb-corelabs"><img src="https://img.shields.io/badge/YouTube-KB Core%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://www.linkedin.com/company/kb-core-labs"><img src="https://img.shields.io/badge/LinkedIn-KB Core%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://www.ycombinator.com/companies/kb-core-labs"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
</p>

<p align="center">
  <b>Early access to the kb-core platform is open before the public v1 launch: <a href="https://app.kb-core.com/login">app.kb-core.com</a></b>
</p>

Type `/kb-core` in your AI coding assistant and it maps your entire project (code, docs, PDFs, images, videos) into a **knowledge graph** you can **query instead of grepping** through files.

- **Code maps for free, fully local.** Code is parsed with tree-sitter AST: deterministic, no LLM, nothing leaves your machine. (Docs, PDFs, images and video use your assistant's model, or a configured API key, for a semantic pass.)
- **Every edge is explained.** Each connection is tagged `EXTRACTED` (explicit in the source) or `INFERRED` (resolved by kb-core), so you can tell what was read directly from what was inferred.
- **Not a vector index.** No embeddings, no vector store: a real graph you traverse. Ask a question, trace the path between two things, or explain one concept.

> Want this always-on, updating in the background across your code, docs, and meetings rather than only on demand? That is what we are building at **[kb-core.com](https://kb-core.com)**, and early access is open now at **[app.kb-core.com](https://app.kb-core.com/login)**.

<p align="center">
  <img src="https://raw.githubusercontent.com/kb-core/kb_core/v8/docs/graph-hero.png" alt="kb-core's interactive graph.html showing the FastAPI codebase as a force-directed knowledge graph with a legend of detected communities" width="900">
</p>
<p align="center">
  <em>The FastAPI codebase mapped by kb_core. Every node is a concept, colors are detected communities, and the whole thing is clickable in graph.html.</em>
</p>

**Get started** (30 seconds):

```bash
uv tool install kb-core      # install the CLI (or: pipx install kb-core)
kb-core install               # register the skill with your AI assistant
```

Then, in your AI assistant:

```
/kb-core .
```

That's it. You get **three files**:

```
kb-core-out/
├── graph.html       open in any browser — click nodes, filter, search
├── GRAPH_REPORT.md  the highlights: key concepts, surprising connections, suggested questions
└── graph.json       the full graph — query it anytime without re-reading your files
```

**Works in** Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot, and 15+ more — [pick your platform](#install).

---

## See it in action

<p align="center">
  <img src="https://raw.githubusercontent.com/kb-core/kb_core/v8/docs/demo-path.svg" alt="kb-core path query: a terminal asks for the shortest path between FastAPI and ModelField, and the answer lights up hop by hop across the knowledge graph" width="900">
</p>

Once the graph is built you query it instead of reading files. Real output, kb-core run on the FastAPI codebase shown above:

```text
$ kb-core explain "APIRouter"
Node: APIRouter
  Source:    routing.py L2210
  Community: 2
  Degree:    47

Connections (47):
  --> RequestValidationError [uses] [INFERRED]
  --> Dependant [uses] [INFERRED]
  --> .get() [method] [EXTRACTED]
  <-- __init__.py [imports] [EXTRACTED]
  ...

$ kb-core path "FastAPI" "ModelField"
Shortest path (3 hops):
  FastAPI --uses--> DefaultPlaceholder <--references-- get_request_handler() --references--> ModelField
```

Every edge carries a **confidence tag** (`EXTRACTED` = explicit in the source, `INFERRED` = derived by resolution), so you can tell what was read directly from what was inferred. `kb-core query "<question>"` returns a scoped subgraph for a plain-language question, and `kb-core path A B` traces how any two things connect.

---

## What it does

What you get out of the box:

| Capability | What you get |
|---|---|
| **God nodes** | The most-connected concepts, so you see what everything flows through |
| **Communities** | The graph split into subsystems (Leiden), with LLM-free labels |
| **Cross-file links** | `calls` / `imports` / `inherits` / `mixes_in` resolved across ~40 languages via tree-sitter AST |
| **Query, path, explain** | Ask a question, trace the path between two things, or explain one concept, all against `graph.json` |
| **Rationale + doc refs** | `# NOTE:` / `# WHY:` comments and ADR/RFC citations become first-class nodes linked to the code |
| **Beyond code** | Docs, PDFs, images, and video/audio all map into the same graph |
| **Local-first** | Code is parsed locally with tree-sitter (no LLM, nothing leaves your machine); only the semantic pass over docs/media calls a backend, and only if you configure one |

---

## Benchmarks

| Benchmark | Metric | kb-core | Field |
|---|---|---|---|
| LOCOMO (n=300) | recall@10 | **0.497** | mem0 0.048, supermemory 0.149 |
| LOCOMO (n=300) | QA accuracy | 45.3% | supermemory 49.7%, mem0 27.3% |
| LongMemEval-S (n=50) | QA accuracy | **76%** | tied with dense RAG |
| Graph build | LLM credits | **0** | per-token for most systems |

Every system ran on the same harness with the same model and budgets, scored by a judge blind-validated against a second judge (90.6% agreement, Cohen's kappa 0.81). Full per-system tables, the code-intelligence result, and reproduction commands: **[BENCHMARKS.md](./BENCHMARKS.md)**.

---

## Prerequisites

| Requirement | Minimum | Check | Install |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(recommended)* | any | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(alternative)* | any | `pipx --version` | `pip install pipx` |

**macOS quick install (Homebrew):**
```bash
brew install python@3.12 uv
```

**Windows quick install:**
```powershell
winget install astral-sh.uv
```

**Ubuntu/Debian:**
```bash
sudo apt install python3.12 python3-pip pipx
# or install uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install

> **Official package:** The PyPI package is `kb-core` (double-y). Other `kb-core*` packages on PyPI are not affiliated. The CLI command is still `kb-core`.

**Step 1 — install the package:**

```bash
# Recommended (isolated env; if 'kb-core' isn't found after, run: uv tool update-shell):
uv tool install kb-core

# Alternatives:
pipx install kb-core
pip install kb-core  # may need PATH setup — see note below
```

**Step 2 — register the skill with your AI assistant:**

```bash
kb-core install
```

That's it. Open your AI assistant and type `/kb-core .`

To install the assistant skill into the current repository instead of your user
profile, add `--project`:

```bash
kb-core install --project
kb-core install --project --platform codex
```

Project-scoped installs write under the current directory, for example
`.claude/skills/kb_core/SKILL.md` or `.agents/skills/kb_core/SKILL.md` (plus a
`references/` sidecar the skill loads on demand), and
print a `git add` hint for files that can be committed.
Per-platform commands that support project-scoped installs accept the same flag,
for example `kb-core claude install --project` or `kb-core codex install --project`.

> **PowerShell note:** Use `kb-core .` not `/kb-core .` — the leading slash is a path separator in PowerShell.

> **`kb-core: command not found`?** `uv tool install` / `pipx install` put the `kb-core` command in their tool bin dir (`~/.local/bin`). If your shell can't find it right after install — common on a fresh macOS + zsh setup — that dir isn't on your `PATH` yet: run `uv tool update-shell` (or `pipx ensurepath`), then open a new terminal. With plain `pip`, add `~/.local/bin` (Linux) or `~/Library/Python/3.x/bin` (Mac) to your PATH, or run `python -m kb_core`.

> **Running with `uvx` / `uv tool run` instead of installing?** Name the package, not the command: `uvx --from kb-core kb-core install`. Plain `uvx kb-core …` fails (`No solution found … no versions of kb-core`) because `uv tool run` reads the first word as a *package*, and the package is `kb-core` — the `kb-core` command lives inside it.

> **Avoid `pip install` on Mac/Windows** if possible. The skill resolves Python at runtime from `kb-core-out/.kb_core_python`; if that points to a different environment than where `pip` installed the package, you'll get `ModuleNotFoundError: No module named 'kb-core'`. `uv tool install` and `pipx install` isolate the package in their own env and avoid this entirely.

> **Git hooks and uv tool / pipx:** `kb-core hook install` embeds the current interpreter path directly into the hook scripts at install time, so the post-commit hook fires correctly even in GUI git clients and CI runners where `~/.local/bin` is not on PATH. If you reinstall or upgrade kb-core, re-run `kb-core hook install` to refresh the embedded path.

> **Strict mode (Claude Code):** `kb-core install --project --strict` makes the assistant actually use the graph. The default install *nudges* it to run `kb-core query` before reading files; strict mode *blocks* the first raw source read of a session and redirects it to the graph, then reverts to the nudge (so it fires at most once per session and never gets stuck). Toggle at runtime with `KB_CORE_HOOK_STRICT=1`/`0`; the default install is unchanged (soft nudge).

<details>
<summary><b>Pick your platform</b> (20+ assistants, click to expand)</summary>

| Platform | Install command |
|----------|----------------|
| Claude Code (Linux/Mac) | `kb-core install` |
| Claude Code (Windows) | `kb-core install` (auto-detected) or `kb-core install --platform windows` |
| CodeBuddy | `kb-core install --platform codebuddy` |
| Codex | `kb-core install --platform codex` |
| OpenCode | `kb-core install --platform opencode` |
| Kilo Code | `kb-core install --platform kilo` |
| GitHub Copilot CLI | `kb-core install --platform copilot` |
| VS Code Copilot Chat | `kb-core vscode install` |
| Aider | `kb-core install --platform aider` |
| OpenClaw | `kb-core install --platform claw` |
| Factory Droid | `kb-core install --platform droid` |
| Trae | `kb-core install --platform trae` |
| Trae CN | `kb-core install --platform trae-cn` |
| Gemini CLI | `kb-core install --platform gemini` |
| Hermes | `kb-core install --platform hermes` |
| Kimi Code | `kb-core install --platform kimi` |
| Amp | `kb-core amp install` |
| Agent Skills (cross-framework) | `kb-core install --platform agents` (alias `--platform skills`) |
| Kiro IDE/CLI | `kb-core kiro install` |
| Pi coding agent | `kb-core install --platform pi` |
| Cursor | `kb-core cursor install` |
| Devin CLI | `kb-core devin install` |
| Google Antigravity | `kb-core antigravity install` |

Codex supports multi-agent workflows without a KB Core-specific configuration flag. CodeBuddy uses the same Agent tool and PreToolUse hook mechanism as Claude Code. Factory Droid uses the `Task` tool for parallel subagent dispatch. OpenClaw and Aider use sequential extraction (parallel agent support is still early on those platforms). Trae uses the Agent tool for parallel subagent dispatch and does **not** support `PreToolUse` hooks, so AGENTS.md is the always-on mechanism.

`--platform agents` (alias `--platform skills`) targets the generic cross-framework [Agent-Skills](https://github.com/anthropics/skills) locations: the spec's user-global `~/.agents/skills/` (read by `npx skills` and spec-compliant frameworks) for a global install, and `./.agents/skills/` for a project (`--project`) install. The bare `kb-core install` stays single-platform (Claude Code) by design — use the named `agents` platform when you want the skill discoverable by any framework that reads `.agents/skills`.

> Codex uses `$kb-core` instead of `/kb-core`. Terminal commands keep the `kb-core` form.

### Codex command mapping

Install into current repository with `kb-core codex install --project`. Then use
`$kb-core` for every skill command in Codex:

```text
$kb-core .
$kb-core ./raw --update
$kb-core query "what connects auth to the database?"
$kb-core path "UserService" "DatabasePool"
$kb-core explain "RateLimiter"
$kb-core add https://arxiv.org/abs/1706.03762
```

Run terminal-only commands directly: `kb-core extract`, `kb-core export`,
`kb-core hook`, `kb-core merge-graphs`, `kb-core reflect`, and `kb-core codex
uninstall --project`.

</details>

<details>
<summary><b>Optional extras</b> (install only what you need)</summary>

| Extra | What it adds | Install |
|---|---|---|
| `pdf` | PDF extraction | `uv tool install "kb-core[pdf]"` |
| `office` | `.docx` and `.xlsx` support | `uv tool install "kb-core[office]"` |
| `google` | Google Sheets rendering | `uv tool install "kb-core[google]"` |
| `video` | Video/audio transcription (faster-whisper + yt-dlp) | `uv tool install "kb-core[video]"` |
| `mcp` | MCP stdio server | `uv tool install "kb-core[mcp]"` |
| `neo4j` | Neo4j push support | `uv tool install "kb-core[neo4j]"` |
| `falkordb` | FalkorDB push support | `uv tool install "kb-core[falkordb]"` |
| `svg` | SVG graph export | `uv tool install "kb-core[svg]"` |
| `leiden` | Leiden community detection (Python < 3.13 only) | `uv tool install "kb-core[leiden]"` |
| `ollama` | Ollama local inference | `uv tool install "kb-core[ollama]"` |
| `openai` | OpenAI / OpenAI-compatible APIs | `uv tool install "kb-core[openai]"` |
| `gemini` | Google Gemini API | `uv tool install "kb-core[gemini]"` |
| `anthropic` | Anthropic Claude API (`--backend claude`, uses `ANTHROPIC_API_KEY`) | `uv tool install "kb-core[anthropic]"` |
| `bedrock` | AWS Bedrock (uses IAM, no API key) | `uv tool install "kb-core[bedrock]"` |
| `azure` | Azure OpenAI Service (`--backend azure`, uses `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`) | `uv tool install "kb-core[openai]"` |
| `sql` | SQL schema extraction | `uv tool install "kb-core[sql]"` |
| `postgres` | Live PostgreSQL introspection (`--postgres DSN`) | `uv tool install "kb-core[postgres]"` |
| `dm` | BYOND DreamMaker `.dm`/`.dme` AST extraction (may need a C compiler + `python3-dev` if no wheel matches your platform) | `uv tool install "kb-core[dm]"` |
| `terraform` | Terraform / HCL `.tf`/`.tfvars`/`.hcl` AST extraction | `uv tool install "kb-core[terraform]"` |
| `pascal` | Pascal / Delphi `.pas`/`.dpr`/`.dpk`/`.inc` AST extraction (more accurate `calls`/`inherits` edges; falls back to a regex extractor when absent) | `uv tool install "kb-core[pascal]"` |
| `ocaml` | OCaml `.ml`/`.mli` AST extraction | `uv tool install "kb-core[ocaml]"` |
| `commonlisp` | Common Lisp `.lisp`/`.cl`/`.lsp`/`.asd` AST extraction | `uv tool install "kb-core[commonlisp]"` |
| `chinese` | Chinese query segmentation (jieba) | `uv tool install "kb-core[chinese]"` |
| `all` | Everything above | `uv tool install "kb-core[all]"` |

</details>

---

## Make your assistant always use the graph

Run this once in your project after building a graph:

| Platform | Command |
|----------|---------|
| Claude Code | `kb-core claude install` |
| CodeBuddy | `kb-core codebuddy install` |
| Codex | `kb-core codex install` |
| OpenCode | `kb-core opencode install` |
| Kilo Code | `kb-core kilo install` |
| GitHub Copilot CLI | `kb-core copilot install` |
| VS Code Copilot Chat | `kb-core vscode install` |
| Aider | `kb-core aider install` |
| OpenClaw | `kb-core claw install` |
| Factory Droid | `kb-core droid install` |
| Trae | `kb-core trae install` |
| Trae CN | `kb-core trae-cn install` |
| Cursor | `kb-core cursor install` |
| Gemini CLI | `kb-core gemini install` |
| Hermes | `kb-core hermes install` |
| Kimi Code | `kb-core install --platform kimi` |
| Amp | `kb-core amp install` |
| Agent Skills (cross-framework) | `kb-core agents install` (alias `kb-core skills install`) |
| Kiro IDE/CLI | `kb-core kiro install` |
| Pi coding agent | `kb-core pi install` |
| Devin CLI | `kb-core devin install` |
| Google Antigravity | `kb-core antigravity install` |

This writes a small config file that tells your assistant to consult the knowledge graph for codebase questions, preferring scoped queries like `kb-core query "<question>"` over reading the full report or grepping raw files.

- **Hook platforms** (Claude Code, Gemini CLI): a hook fires automatically before search-style tool calls (and, on Claude Code, before reading source files one by one via the Read/Glob tools) and nudges your assistant toward the graph path.
- **Instruction-file platforms** (Codex, OpenCode, Cursor, etc.): persistent instruction files (`AGENTS.md`, `.cursor/rules/`, etc.) provide the same query-first guidance.

`GRAPH_REPORT.md` is still available for broad architecture review.

**CodeBuddy** does the same two things as Claude Code: writes a `CODEBUDDY.md` section telling CodeBuddy to read `kb-core-out/GRAPH_REPORT.md` before answering architecture questions, and installs `PreToolUse` hooks (`.codebuddy/settings.json`) that fire before Bash search commands and file reads, nudging toward `kb-core query` instead.

**Codex** writes to `AGENTS.md`, which is what actually carries the always-on graph guidance on this platform. `kb-core codex install` also registers a `PreToolUse` hook in `.codex/hooks.json` (`kb-core hook-check`), but that entry is deliberately a **no-op**: Codex Desktop rejects `hookSpecificOutput.additionalContext` on `PreToolUse`, so emitting a nudge there would break Bash tool calls. Unlike Claude Code, where the hook (`kb-core hook-guard`) does the nudging, on Codex the hook fires and intentionally does nothing, and `AGENTS.md` is the always-on mechanism.

**Kilo Code** installs the KB Core skill to `~/.config/kilo/skills/kb_core/SKILL.md` and a native `/kb-core` command to `~/.config/kilo/command/kb_core.md`. `kb-core kilo install` also writes `AGENTS.md` plus a native `tool.execute.before` plugin (`.kilo/plugins/kb_core.js` + `.kilo/kilo.json` or `.kilo/kilo.jsonc` registration) so Kilo gets the same always-on graph reminder behavior through native `.kilo` config.

**Cursor** writes `.cursor/rules/kb_core.mdc` with `alwaysApply: true`, so Cursor includes it in every conversation automatically, no hook needed.

To remove kb-core from all platforms at once: `kb-core uninstall` (add `--purge` to also delete `kb-core-out/`). Or use the per-platform command (e.g. `kb-core claude uninstall`).

---

## What's in the report

- **God nodes** — the most-connected concepts in your project. Everything flows through these.
- **Surprising connections** — links between things that live in different files or modules. Ranked by how unexpected they are.
- **The "why"** — inline comments (`# NOTE:`, `# WHY:`, `# HACK:`), docstrings, and design rationale from docs are extracted as separate nodes linked to the code they explain.
- **Suggested questions** — 4–5 questions the graph is uniquely positioned to answer.
- **Confidence tags** — every inferred relationship is marked `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`. You always know what was found vs guessed.

---

## What files it handles

| Type | Extensions |
|------|-----------|
| Code (37 tree-sitter grammars) | `.py .ts .mts .cts .js .jsx .tsx .mjs .go .rs .java .c .cpp .cc .cxx .h .hpp .cu .cuh .metal .rb .cs .kt .kts .scala .php .swift .lua .luau .toc .zig .ps1 .psm1 .psd1 .ex .exs .m .mm .ml .mli .jl .vue .svelte .astro .groovy .gradle .dart .v .sv .svh .sql .f .f90 .f95 .f03 .f08 .pas .pp .dpr .dpk .lpr .inc .dfm .lfm .lpk .sh .bash .json .dm .dme .dmi .dmm .dmf .sln .slnx .csproj .fsproj .vbproj .xaml .razor .cshtml` (`.dm`/`.dme` requires `uv tool install kb-core[dm]`, `.ml`/`.mli` requires `uv tool install kb-core[ocaml]`; `.mts`/`.cts` reuse the TypeScript grammar, `.cc`/`.cxx` and CUDA `.cu`/`.cuh` and Metal `.metal` reuse the C++ grammar) |
| Salesforce Apex | `.cls .trigger` (regex-based; classes, interfaces, enums, methods, triggers, SOQL/DML edges) |
| Terraform / HCL | `.tf .tfvars .hcl` (requires `uv tool install kb-core[terraform]`) |
| OCaml | `.ml .mli` (requires `uv tool install kb-core[ocaml]`) |
| Common Lisp | `.lisp .cl .lsp .asd` (requires `uv tool install kb-core[commonlisp]`) |
| MCP configs | `.mcp.json` `mcp.json` `mcp_servers.json` `claude_desktop_config.json` — extracts server nodes, package refs, env var requirements |
| Package manifests | `apm.yml` `pyproject.toml` `go.mod` `pom.xml` — one canonical package node per package (by name) plus `depends_on` edges, so a package referenced from many manifests is a single hub |
| Docs | `.md .mdx .qmd .html .txt .rst .yaml .yml` (markdown `[text](./other.md)` links and `[[wikilinks]]` become `references` edges between docs) |
| Office | `.docx .xlsx` (requires `uv tool install kb-core[office]`) |
| Google Workspace | `.gdoc .gsheet .gslides` (opt-in; requires `gws` auth and `--google-workspace`; Sheets need `uv tool install kb-core[google]`) |
| PDFs | `.pdf` |
| Images | `.png .jpg .webp .gif` |
| Video / Audio | `.mp4 .mov .mp3 .wav` and more (requires `uv tool install kb-core[video]`) |
| YouTube / URLs | any video URL (requires `uv tool install kb-core[video]`) |

Code is extracted **locally with no API calls** (AST via tree-sitter). Everything else goes through your AI assistant's model API.

Google Drive for desktop `.gdoc`, `.gsheet`, and `.gslides` files are shortcut
pointers, not document content. To include native Google Docs, Sheets, and Slides
in a headless extraction, install and authenticate the
[`gws` CLI](https://github.com/googleworkspace/cli), then run:

```bash
uv tool install "kb-core[google]"  # needed for Google Sheets table rendering
gws auth login -s drive
kb-core extract ./docs --google-workspace
```

You can also set `KB_CORE_GOOGLE_WORKSPACE=1`. KB Core exports shortcuts into
`kb-core-out/converted/` as Markdown sidecars, then extracts those files.

---

## Common commands

```bash
/kb-core .                        # build graph for current folder
/kb-core ./docs --update          # re-extract only changed files
/kb-core . --cluster-only         # rerun clustering without re-extracting
/kb-core . --cluster-only --resolution 1.5      # more granular communities
/kb-core . --cluster-only --exclude-hubs 99     # suppress utility super-hubs from god-node rankings
/kb-core . --no-viz               # skip the HTML, just the report + JSON
/kb-core . --wiki                 # build a markdown wiki from the graph
kb-core export callflow-html      # Mermaid architecture/call-flow HTML (auto-regenerates on every git commit if hook is installed)

/kb-core query "what connects auth to the database?"
/kb-core path "UserService" "DatabasePool"
/kb-core explain "RateLimiter"

/kb-core add https://arxiv.org/abs/1706.03762   # fetch a paper and add it
/kb-core add <youtube-url>                       # transcribe and add a video

kb-core hook install              # auto-rebuild on git commit
kb-core merge-graphs a.json b.json              # combine two graphs

kb-core prs                       # PR dashboard: CI state, review status, worktree mapping
kb-core prs 42                    # deep dive on PR #42 with graph impact
kb-core prs --triage              # AI ranks your review queue (uses whatever backend is configured)
kb-core prs --conflicts           # PRs sharing graph communities — merge-order risk
```

See the [full command reference](#full-command-reference) below.

---

## Ignoring files

Create a `.kb-coreignore` in your project root — same syntax as `.gitignore`, including `!` negation.

**`.gitignore` is respected automatically.** kb-core reads the `.gitignore` in each directory. If a `.kb-coreignore` is also present, the two are **merged** — `.kb-coreignore` patterns are evaluated last, so they win on conflicts (including `!` negations). Adding a `.kb-coreignore` only ever excludes more; it never re-includes a file your `.gitignore` already excluded. Subdirectory scoping works the same way as git — an ignore file only affects its own subtree.

Pass `--no-gitignore` to `kb-core extract` when git-ignored generated or transpiled code belongs in the graph. This disables `.gitignore` and `.git/info/exclude`; `.kb-coreignore` still applies.

```
# .kb-coreignore
node_modules/
dist/
*.generated.py

# only index src/, ignore everything else
*
!src/
!src/**
```

---

## Team setup

`kb-core-out/` is meant to be committed to git so everyone on the team starts with a map.

**Recommended `.gitignore` additions:**
```
kb-core-out/cost.json        # local only
# kb-core-out/cache/         # optional: commit for speed, skip to keep repo small
```

> `manifest.json` is now portable — keys are stored as relative paths and re-anchored on load, so committing it is safe and avoids a full rebuild on first checkout.

**Workflow:**
1. One person runs `/kb-core .` and commits `kb-core-out/`.
2. Everyone pulls — their assistant reads the graph immediately.
3. Run `kb-core hook install` to auto-rebuild after each commit (AST only, no API cost). This also sets up a git merge driver so `graph.json` is never left with conflict markers — two devs committing in parallel get their graphs union-merged automatically.
4. When docs or papers change, run `/kb-core --update` to refresh those nodes.

---

## Using the graph directly

```bash
# query the graph from the terminal
kb-core query "show the auth flow"
kb-core query "what connects DigestAuth to Response?" --graph kb-core-out/graph.json

# expose the graph as an MCP server (for repeated tool-call access)
python -m kb_core.serve kb-core-out/graph.json
python -m kb_core.serve --graph kb-core-out/graph.json  # --graph flag also accepted

# register with Kimi Code:
kimi mcp add --transport stdio kb-core -- python -m kb_core.serve kb-core-out/graph.json

# or serve over HTTP so a whole team points at one URL (no local kb-core needed):
python -m kb_core.serve kb-core-out/graph.json --transport http --port 8080
python -m kb_core.serve kb-core-out/graph.json --transport http --host 0.0.0.0 --api-key "$SECRET"
```

The MCP server gives your assistant structured access: `query_graph`, `get_node`, `get_neighbors`, `shortest_path`, `list_prs`, `get_pr_impact`, `triage_prs`.

### Shared HTTP server

`--transport stdio` (the default) spawns one local server per developer. `--transport http` serves the same tools over the MCP Streamable HTTP transport, so a single shared process can serve the graph for the whole team — clients point their IDE MCP config at `http://<host>:8080/mcp` instead of running kb-core locally.

| Flag | Default | Purpose |
|---|---|---|
| `--transport {stdio,http}` | `stdio` | Transport to serve on |
| `--host` | `127.0.0.1` | HTTP bind host (use `0.0.0.0` to expose beyond localhost) |
| `--port` | `8080` | HTTP bind port |
| `--api-key` | env `KB_CORE_API_KEY` | Require `Authorization: Bearer <key>` (or `X-API-Key`) |
| `--path` | `/mcp` | HTTP mount path |
| `--json-response` | off | Return plain JSON instead of SSE streams |
| `--stateless` | off | No per-session state (for load-balanced / CI deployments) |
| `--session-timeout` | `3600` | Reap idle stateful sessions after N seconds (`0` disables) |

The default `127.0.0.1` bind is loopback-only. Set `--host 0.0.0.0` **and** `--api-key` together when exposing on a shared host. Run it in a container:

```bash
docker build -t kb-core .
docker run -p 8080:8080 -v "$(pwd)/kb-core-out:/data" kb-core \
  /data/graph.json --transport http --host 0.0.0.0 --api-key "$SECRET"
```

> **WSL / Linux note:** Ubuntu ships `python3`, not `python`. Use a venv to avoid conflicts:
> ```bash
> python3 -m venv .venv && .venv/bin/pip install "kb-core[mcp]"
> ```

---

## Environment variables

These are only needed for **headless / CI extraction** (`kb-core extract`). When running via the `/kb-core` skill inside your IDE, the model API is provided by your IDE session — no extra keys needed.

| Variable | Used for | When required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude (Anthropic) backend | `--backend claude` |
| `ANTHROPIC_BASE_URL` | Anthropic-compatible endpoint URL (LiteLLM proxy, gateways, ...) | `--backend claude` (default: `https://api.anthropic.com`) |
| `ANTHROPIC_MODEL` | Model name for the Claude backend — for custom endpoints, use the model name/alias your server exposes | `--backend claude` (default: `claude-sonnet-4-6`) |
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Google Gemini backend | `--backend gemini` |
| `OPENAI_API_KEY` | OpenAI or OpenAI-compatible APIs | `--backend openai` (local servers accept any non-empty value) |
| `OPENAI_BASE_URL` | OpenAI-compatible server URL (llama.cpp, vLLM, LM Studio, ...) | `--backend openai` (default: `https://api.openai.com/v1`) |
| `OPENAI_MODEL` | Model name for the OpenAI backend — for self-hosted servers, use the model name/alias your server exposes (check its `/v1/models` endpoint), e.g. `LFM2.5-8B-A1B-UD-Q4_K_XL` for llama.cpp | `--backend openai` (default: `gpt-4.1-mini`) |
| `DEEPSEEK_API_KEY` | DeepSeek backend | `--backend deepseek` |
| `MOONSHOT_API_KEY` | Kimi Code backend | `--backend kimi` |
| `OLLAMA_BASE_URL` | Ollama local inference URL | `--backend ollama` (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Ollama model name | `--backend ollama` (default: auto-detect) |
| `KB_CORE_OLLAMA_NUM_CTX` | Override Ollama KV-cache window size | optional — auto-sized by default |
| `KB_CORE_OLLAMA_KEEP_ALIVE` | Minutes to keep Ollama model loaded | optional — set `0` to unload after each chunk |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI Service backend | `--backend azure` |
| `AZURE_OPENAI_ENDPOINT` | Azure resource endpoint URL | `--backend azure` (required alongside API key) |
| `AZURE_OPENAI_API_VERSION` | Azure API version override | optional — default `2024-12-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT` or `KB_CORE_AZURE_MODEL` | Azure deployment name | optional — default `gpt-4o` |
| `AWS_*` / `~/.aws/credentials` | AWS Bedrock — standard credential chain | `--backend bedrock` (no API key, uses IAM) |
| `KB_CORE_MAX_WORKERS` | AST parallelism thread count | optional — also `--max-workers` flag |
| `KB_CORE_MAX_OUTPUT_TOKENS` | Raise output cap for dense corpora | optional — e.g. `32768` for large files |
| `KB_CORE_API_TIMEOUT` | Per-call timeout in seconds for HTTP, claude-cli, Anthropic SDK, and Bedrock backends (default: 600) | optional — also `--api-timeout` flag |
| `KB_CORE_MAX_RETRIES` | How many times to retry a rate-limited (429) request before giving up (default: 6; honors `Retry-After`) | optional — raise for strict per-org limits (e.g. kimi); `0` disables |
| `KB_CORE_MAX_RETRY_DEPTH` | How deep a truncated chunk may be bisected and re-extracted (default: 3, so up to 8x sub-calls for one chunk) | optional — lower it to cap worst-case spend; `0` disables every retry (no bisection, no hollow-response retry), so a chunk costs exactly one call |
| `KB_CORE_FORCE` | Force graph rebuild even with fewer nodes | optional — also `--force` flag |
| `KB_CORE_GOOGLE_WORKSPACE` | Auto-enable Google Workspace export | optional — set to `1` |
| `KB_CORE_TRIAGE_BACKEND` | Backend for `kb-core prs --triage` | optional — auto-detected from available keys |
| `KB_CORE_TRIAGE_MODEL` | Model override for triage | optional — e.g. `claude-opus-4-7` |
| `KB_CORE_QUERY_LOG_ENABLE` | Set to `1` to turn on the local query log at `~/.cache/kb-core-queries.log` (records each query/path/explain question + corpus path). Off by default — nothing is written unless you opt in (#1797) | optional |
| `KB_CORE_QUERY_LOG` | Enable the query log and write it to this path instead of the default | optional — off unless this or `_ENABLE` is set |
| `KB_CORE_QUERY_LOG_DISABLE` | Set to `1` to force the query log off (wins over the enable vars) | optional |
| `KB_CORE_QUERY_LOG_RESPONSES` | When the log is enabled, also record full subgraph responses (off by default) | optional |
| `KB_CORE_MAX_GRAPH_BYTES` | Override the 512 MiB graph.json size cap — e.g. `700MB`, `2GB`, or plain bytes | optional — useful for very large corpora |
| `KB_CORE_MAX_CONTEXTS` | Maximum number of non-default project graphs retained by one multi-project MCP server | optional — default: `8`; invalid values use `8`, and values below `1` use `1` |
| `KB_CORE_LLM_TEMPERATURE` | Override LLM temperature for semantic extraction — e.g. `0.7`, or `none` to omit | optional — auto-omitted for o1/o3/o4/gpt-5 reasoning models |

---

## Privacy

- **Code files** — processed locally via tree-sitter. Nothing leaves your machine. A code-only corpus requires no API key — `kb-core extract` runs fully offline. On a mixed repo, add `--code-only` to index just the code and skip the docs/PDFs/images that would otherwise need an LLM.
- **Video / audio** — transcribed locally with faster-whisper. Nothing leaves your machine.
- **Docs, PDFs, images** — sent to your AI assistant for semantic extraction (via the `/kb-core` skill, using whatever model your IDE session runs). Headless `kb-core extract` requires `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), a running Ollama instance (`OLLAMA_BASE_URL`), AWS credentials via the standard provider chain (Bedrock - no API key needed, uses IAM), or the `claude` CLI binary (Claude Code - no API key needed, uses your Claude subscription). The `--dedup-llm` flag uses the same key.
- **Data residency** — `kb-core extract` auto-detects which provider to use based on which API key is set (priority: Gemini → Kimi → Claude → OpenAI → DeepSeek → Azure → Bedrock → Ollama). For code with data-residency requirements, use `--backend ollama` (fully local) or pass an explicit `--backend` flag. Kimi (`MOONSHOT_API_KEY`) routes to Moonshot AI servers in China.
- **No telemetry**, no usage tracking, no analytics.
- **Query logging** — every `kb-core query`, `kb-core path`, `kb-core explain`, and MCP `query_graph` call is logged to `~/.cache/kb-core-queries.log` in JSON Lines format (timestamp, question, corpus, nodes returned, duration). Full subgraph responses are **not** stored by default. Set `KB_CORE_QUERY_LOG_DISABLE=1` to opt out, or `KB_CORE_QUERY_LOG=/dev/null` to silence without disabling the code path.

---

## Troubleshooting

**`kb-core: command not found` after installing**
The CLI is installed but its bin directory isn't on your shell's `PATH`. Pick the fix for how you installed:
- **uv** (`uv tool install kb-core`): the command lands in uv's tool bin dir (`~/.local/bin`), which a fresh macOS/zsh setup often doesn't have on `PATH`. Run `uv tool update-shell`, then open a new terminal. (Find the dir with `uv tool dir --bin`.)
- **pipx** (`pipx install kb-core`): run `pipx ensurepath`, then open a new terminal.
- **pip** (`pip install kb-core`): pip installs scripts to a user bin dir that may not be on `PATH` — add `~/Library/Python/3.x/bin` (macOS) or `~/.local/bin` (Linux) to your `PATH` in `~/.zshrc`/`~/.bashrc`, or just run `python -m kb_core`.

**`uvx kb-core …` or `uv tool run kb-core …` fails to resolve `kb-core`**
The PyPI package is `kb-core`; `kb-core` is only the command it provides. `uv tool run` treats the first word as a *package name*, so it looks for a package called `kb-core` and reports `No solution found … no versions of kb-core`. Name the package explicitly: `uvx --from kb-core kb-core install` (same as `uv tool run --from kb-core kb-core install`). Or `uv tool install kb-core` once and then call `kb-core` directly.

**`uv run --with kb-core python -m kb_core` silently runs an older install**
`uv run` uses your *system* Python, so if an older `kb-core` also lives there (e.g. a past `pip install kb-core`), Python can find that copy first on `sys.path` and `--with kb-core` won't override it. It runs with no error, but you get the *old* version's behavior — e.g. env overrides like `OPENAI_BASE_URL` are silently ignored, so requests hit the default endpoint and fail with a 401 that looks like a bad key. The fingerprint is a `warning: skill is from kb_core <newer>, package is <older>` line — that means a different install was loaded, not just a stale skill. Check which copy actually loaded:
```bash
python -c "import kb_core; print(kb_core.__file__)"
```
Then run the installed command directly (it uses the uv-managed copy), or drop the stale system copy:
```bash
uvx --from kb-core kb-core extract . --backend openai   # names the package explicitly
pip uninstall kb-core                                    # or remove the old system install
```

**`python -m kb_core` works but `kb-core` command doesn't**
Your shell's `PATH` doesn't include the bin directory the command was installed to. Prefer `uv tool install` / `pipx install` over plain `pip`, then run `uv tool update-shell` / `pipx ensurepath` and open a new terminal (see the install notes above).

**`/kb-core .` causes "path not recognized" in PowerShell**
PowerShell treats a leading `/` as a path separator. Use `kb-core .` (no slash) on Windows.

**Graph has fewer nodes after `--update` or rebuild**
If a refactor deleted files, the old nodes linger. Pass `--force` (or set `KB_CORE_FORCE=1`) to overwrite even when the rebuild has fewer nodes.

**`extract` exits with "extraction was incomplete ... refusing to overwrite"**
When an extraction pass crashes or a walk can't fully read the corpus, the run would be smaller than a complete one, so `kb-core extract` refuses to overwrite a larger existing graph with the partial result (protecting your `graph.json`). Fix the underlying failure and re-run, or pass `--allow-partial` to overwrite anyway.

**Graph has duplicate nodes for the same entity (ghost duplicates)**
Ghost duplicates (same symbol appearing twice — once from AST extraction with a source location, once from semantic extraction without) are now automatically merged at build time. If you see this in a graph built before v0.8.33, run a full re-extract to clean up:
```bash
kb-core extract . --force
```

**Ollama runs out of VRAM / context window exceeded**
The KV-cache window is auto-sized but may be too large for your GPU. Reduce it:
```bash
KB_CORE_OLLAMA_NUM_CTX=8192 kb-core extract ./docs --backend ollama --token-budget 4000
```

**`LLM returned invalid JSON` / `Unterminated string` warnings**
The model's JSON response hit its output-token limit and was cut off mid-string. kb-core auto-recovers (it splits the chunk and re-extracts the halves, and an oversized single document is first sliced at heading/paragraph boundaries so the whole file is still covered), so these warnings are noisy but not data loss. To reduce the churn, raise the output cap or shrink each chunk's output:
```bash
KB_CORE_MAX_OUTPUT_TOKENS=16384 kb-core extract . --mode deep   # lift the cap
kb-core extract . --mode deep --token-budget 4000                # smaller input chunks -> smaller output
```
With a cloud gateway like OpenRouter, prefer `--backend openai` (set `OPENAI_BASE_URL`) over the Ollama shim — it's a cleaner OpenAI-compatible path. If the model has its own max-output ceiling, lowering `--token-budget` is the reliable lever.

**Graph HTML is too large to open in a browser (>5000 nodes)**
Skip HTML generation and use the JSON directly:
```bash
kb-core cluster-only ./my-project --no-viz
kb-core query "..."
```

**`graph.json` has conflict markers after two devs commit at once**
Run `kb-core hook install` — it sets up a git merge driver that union-merges `graph.json` automatically so conflicts never happen.

**Extraction returns empty nodes/edges for docs or PDFs**
Docs, PDFs, and images require an LLM call — code-only corpora need no key. Check that your API key is set and the backend is correct:
```bash
ANTHROPIC_API_KEY=sk-... kb-core extract ./docs --backend claude
```

**Skill version mismatch warning in your IDE**
Your installed kb-core version is different from the skill file. Update:
```bash
uv tool upgrade kb-core
kb-core install  # overwrites the skill file
```

**Claude Code prompt cache invalidated after every `kb-core extract`**
KB Core writes output files (`graph.json`, `kb-core-out/`) into the workspace. If those paths aren't ignored, every write invalidates Claude Code's prompt cache, forcing a full re-upload at cache-write rates on the next turn. Add them to `.claudeignore`:
```text
# .claudeignore
graph.json
kb-core-out/
```

---

## Full command reference

```
/kb-core                          # run on current directory
/kb-core ./raw                    # run on a specific folder
/kb-core ./raw --mode deep        # more aggressive relationship extraction
kb-core extract ./raw --code-only # index code only — local AST, no API key (skips docs/PDFs/images); an `extract` flag, not a skill flag
/kb-core ./raw --update           # re-extract only changed files
/kb-core ./raw --directed         # preserve edge direction
/kb-core ./raw --cluster-only     # rerun clustering on existing graph
/kb-core ./raw --no-viz           # skip HTML visualization
/kb-core ./raw --obsidian         # generate Obsidian vault
/kb-core ./raw --obsidian --obsidian-dir ~/vault  # write into an existing vault (never overwrites your own notes or .obsidian config)
/kb-core ./raw --wiki             # build agent-crawlable markdown wiki
/kb-core ./raw --svg              # export graph.svg
/kb-core ./raw --graphml          # export for Gephi / yEd
/kb-core ./raw --neo4j            # generate cypher.txt for Neo4j
/kb-core ./raw --neo4j-push bolt://localhost:7687
/kb-core ./raw --falkordb         # generate cypher.txt for FalkorDB
/kb-core ./raw --falkordb-push falkordb://localhost:6379
/kb-core ./raw --watch            # auto-sync as files change
/kb-core ./raw --mcp              # start MCP stdio server

/kb-core add https://arxiv.org/abs/1706.03762
/kb-core add <video-url>
/kb-core add https://... --author "Name" --contributor "Name"

/kb-core query "what connects attention to the optimizer?"
/kb-core query "..." --dfs --budget 1500
/kb-core path "DigestAuth" "Response"
/kb-core explain "SwinTransformer"

kb-core save-result --question "Q" --answer "A" --nodes Foo Bar --outcome useful   # record how a Q&A turned out (work memory; outcome ∈ useful|dead_end|corrected)
kb-core reflect                   # aggregate kb-core-out/memory/ outcomes into reflections/LESSONS.md
kb-core reflect --if-stale        # no-op when LESSONS.md is already newer than every input (cheap to run each session)
kb-core reflect --out docs/LESSONS.md    # write the lessons doc somewhere else
kb-core reflect --graph kb-core-out/graph.json  # group lessons by community + write the work-memory overlay (.kb_core_learning.json)
                                   # the overlay tags nodes preferred/tentative/contested (recency-weighted, with provenance);
                                   # kb-core explain / query then show a "Lesson:" hint, flagged "code changed — re-verify" when the source moved on

kb-core uninstall                 # remove from all platforms in one shot
kb-core uninstall --purge         # also delete kb-core-out/
kb-core uninstall --project --platform codex  # remove project-scoped install files only

kb-core hook install              # post-commit + post-checkout hooks
kb-core hook uninstall
kb-core hook status

# always-on assistant instructions - platform-specific
kb-core claude install            # CLAUDE.md + PreToolUse hook (Claude Code)
kb-core claude uninstall
kb-core codebuddy install         # CODEBUDDY.md + PreToolUse hook (CodeBuddy)
kb-core codebuddy uninstall
kb-core codex install             # AGENTS.md + PreToolUse hook in .codex/hooks.json (Codex)
kb-core opencode install          # AGENTS.md + tool.execute.before plugin (OpenCode)
kb-core kilo install              # native Kilo skill + /kb-core command + AGENTS.md + .kilo plugin
kb-core kilo uninstall
kb-core cursor install            # .cursor/rules/kb_core.mdc (Cursor)
kb-core cursor uninstall
kb-core gemini install            # GEMINI.md + BeforeTool hook (Gemini CLI)
kb-core gemini uninstall
kb-core copilot install           # skill file (GitHub Copilot CLI)
kb-core copilot uninstall
kb-core aider install             # AGENTS.md (Aider)
kb-core aider uninstall
kb-core claw install              # AGENTS.md (OpenClaw)
kb-core claw uninstall
kb-core droid install             # AGENTS.md (Factory Droid)
kb-core droid uninstall
kb-core trae install              # AGENTS.md (Trae)
kb-core trae uninstall
kb-core trae-cn install           # AGENTS.md (Trae CN)
kb-core trae-cn uninstall
kb-core hermes install             # AGENTS.md + ~/.hermes/skills/ (Hermes)
kb-core hermes uninstall
kb-core amp install               # skill file (Amp)
kb-core amp uninstall
kb-core agents install            # ~/.agents/skills/ + AGENTS.md (cross-framework; alias: kb-core skills)
kb-core agents uninstall
kb-core kiro install               # .kiro/skills/ + .kiro/steering/kb_core.md (Kiro IDE/CLI)
kb-core kiro uninstall
kb-core pi install                # skill file (Pi coding agent)
kb-core pi uninstall
kb-core devin install             # skill file + .windsurf/rules/kb_core.md (Devin CLI)
kb-core devin uninstall
kb-core antigravity install       # .agents/rules + .agents/workflows (Google Antigravity)
kb-core antigravity uninstall

kb-core extract ./docs                        # headless LLM extraction for CI (no IDE needed)
kb-core extract ./docs --backend gemini       # explicit backend: gemini, kimi, claude, openai, deepseek, ollama, bedrock, or claude-cli
kb-core extract ./docs --backend gemini --model gemini-3.1-pro-preview
kb-core extract ./docs --backend ollama       # local Ollama (set OLLAMA_BASE_URL / OLLAMA_MODEL) - no API key needed for loopback
OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_MODEL=my-model kb-core extract ./docs --backend openai   # any OpenAI-compatible server (llama.cpp, vLLM, LM Studio)
ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_MODEL=my-model kb-core extract ./docs --backend claude   # any Anthropic-compatible endpoint (LiteLLM proxy, gateways)
KB_CORE_OLLAMA_NUM_CTX=32768 kb-core extract ./docs --backend ollama   # override KV-cache window (auto-sized by default)
KB_CORE_OLLAMA_KEEP_ALIVE=0 kb-core extract ./docs --backend ollama    # unload model after each chunk (saves VRAM on small GPUs)
kb-core extract ./docs --backend bedrock      # AWS Bedrock via IAM - no API key, uses AWS credential chain
kb-core extract ./docs --backend claude-cli   # route through Claude Code CLI - no API key, uses your Claude subscription
kb-core extract ./docs --backend azure        # Azure OpenAI (set AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT)
kb-core extract ./docs --max-workers 16       # AST parallelism (also KB_CORE_MAX_WORKERS)
kb-core extract --postgres "postgresql://user:pass@host/db"   # introspect live PostgreSQL schema directly
kb-core extract ./my-workspace --cargo        # introspect Rust Cargo workspace dependencies directly
kb-core extract ./docs --token-budget 30000   # smaller semantic chunks for local/small models
kb-core extract ./docs --max-concurrency 2    # fewer parallel LLM calls (useful for local inference)
kb-core extract ./docs --api-timeout 900      # longer HTTP timeout for slow local models (default 600s)
kb-core extract ./docs --google-workspace     # export .gdoc/.gsheet/.gslides via gws before extraction
kb-core extract ./src --no-gitignore          # include git-ignored source; still honor .kb-coreignore
kb-core extract ./docs --mode deep            # richer semantic extraction via extended system prompt
kb-core extract ./docs --no-cluster           # raw extraction only, skip clustering
kb-core extract ./docs --timing               # print per-stage wall-clock timings to stderr (also works on cluster-only)
kb-core extract ./docs --force                # overwrite graph.json even if new graph has fewer nodes (use after refactors or to clear ghost duplicates)
kb-core extract ./docs --dedup-llm            # LLM tiebreaker for ambiguous entity pairs (uses same API key)
kb-core extract ./src --no-dedup              # skip entity dedup; on an incremental merge this also arms the shrink guard that refuses to drop untouched files' nodes
kb-core extract ./docs --global --as myrepo   # extract and register into the cross-project global graph
KB_CORE_MAX_OUTPUT_TOKENS=32768 kb-core extract ./docs --backend claude  # raise output cap for dense corpora

kb-core export callflow-html                       # kb-core-out/<project>-callflow.html
kb-core export callflow-html --max-sections 8      # cap generated architecture sections
kb-core export callflow-html --output docs/arch.html
kb-core export callflow-html ./some-repo/kb-core-out

kb-core global add kb-core-out/graph.json --as myrepo   # register a project graph into ~/.kb_core/global-graph.json
kb-core global remove myrepo                         # remove a project from the global graph
kb-core global list                                  # show all registered repos + node/edge counts
kb-core global path                                  # print path to the global graph file

kb-core prs                              # PR dashboard: CI, review, worktree, graph impact
kb-core prs 42                           # deep dive on PR #42
kb-core prs --triage                     # AI triage ranking (auto-detects backend from env)
kb-core prs --worktrees                  # worktree → branch → PR mapping
kb-core prs --conflicts                  # PRs sharing graph communities (merge-order risk)
kb-core prs --base main                  # filter to PRs targeting a specific base branch
kb-core prs --repo owner/repo            # run against a different GitHub repo
KB_CORE_TRIAGE_BACKEND=kimi kb-core prs --triage   # use a specific backend for triage

kb-core clone https://github.com/karpathy/nanoGPT
kb-core merge-graphs a.json b.json --out merged.json
kb-core --version                                    # print installed version
kb-core watch ./src
kb-core check-update ./src
kb-core update ./src
kb-core update ./src --no-cluster  # skip reclustering, write raw AST graph only
kb-core update ./src --force       # overwrite even if new graph has fewer nodes
kb-core cluster-only ./my-project
kb-core cluster-only ./my-project --graph path/to/graph.json  # custom graph location
kb-core cluster-only ./my-project --max-concurrency 16 --batch-size 200  # parallel community labeling (large graphs)
kb-core cluster-only ./my-project --resolution 1.5            # more, smaller communities
kb-core cluster-only ./my-project --exclude-hubs 99           # exclude p99 degree nodes from partitioning
kb-core cluster-only ./my-project --no-label                  # keep "Community N" placeholders
kb-core cluster-only ./my-project --backend=gemini            # backend for community naming
kb-core cluster-only ./my-project --backend=gemini --model gemini-2.5-pro  # specific model
kb-core label ./my-project                                    # (re)name communities with the configured backend
kb-core label ./my-project --backend=openai --model gpt-4o   # force a specific backend and model
```

> **Community names:** inside an agent (Claude Code, Gemini CLI) the agent names communities itself. When you run the bare CLI, `cluster-only` auto-names them with the configured backend (built-in or custom OpenAI-compatible provider) — pass `--no-label` to keep `Community N`, or run `kb-core label` to (re)generate names on demand.

---

## Learn more

- [How it works](docs/how-it-works.md) — the extraction pipeline, community detection, confidence scoring, benchmarks
- [ARCHITECTURE.md](ARCHITECTURE.md) — module breakdown, how to add a language
- [Optional integrations](docs/docker-mcp-sqlite.md) — Docker MCP Toolkit + SQLite
- [The Memory Layer](https://safishamsi.gumroad.com/l/qetvlo) — the book on the ideas behind kb-core, the architecture end to end

---

## kb-core Enterprise

[**kb-core Enterprise**](https://kb-core.com) is the always-on layer built on top of kb-core — it applies the same graph approach to your entire working context: meetings, files, docs, and code, updating continuously in the background.

Built for people and teams whose work lives across hundreds of conversations and documents they can never fully reconstruct.

**[Join the waitlist at kb-core.com](https://kb-core.com).** Free trial launching soon.

---

<details>
<summary>Contributing</summary>

### Development setup

The project uses [uv](https://docs.astral.sh/uv/) for dev workflow. Install it once, then:

```bash
git clone https://github.com/safishamsi/kb_core.git
cd kb-core
git checkout v8                        # active development branch

# Create the project venv and install kb-core + all extras + the dev group
# (pytest). uv installs the dev dependency group by default; pass --no-dev to
# skip it.
uv sync --all-extras
```

Verify the editable install:
```bash
uv run kb-core --version
uv run python -c "import kb_core; print(kb_core.__file__)"
```

### Running tests

```bash
uv run pytest tests/ -q                # run the full suite
uv run pytest tests/test_extract.py -q # one module
uv run pytest tests/ -q -k "python"    # filter by name
```

### CI parity checks

The authoritative CI commands live in [`.github/workflows/`](.github/workflows/).
For local CI-style verification, use Python 3.10 or 3.12 and run:

```bash
uv sync --all-extras --frozen
uv run --frozen pytest tests/ -q --tb=short
uv run --frozen python -m tools.skillgen --check
uv run --frozen python -m tools.skillgen --audit-coverage
uv run --frozen python -m tools.skillgen --schema-singleton
uv run --frozen python -m tools.skillgen --monolith-roundtrip
uv run --frozen python -m tools.skillgen --always-on-roundtrip
uv run --frozen kb-core --help
uv run --frozen kb-core install
```

Ruff is useful as an additional local check (`uv run --frozen ruff check .`),
but is not currently a blocking CI job. Pyright is also local/advisory unless it
is added to CI later. The Bandit and pip-audit CI steps currently use
`continue-on-error`, so their findings are advisory rather than blocking.

> macOS note: the test suite includes both `sample.f90` and `sample.F90` fixtures. These collide on case-insensitive HFS+ / APFS file systems. Run on Linux or in a Docker container if you need to test both Fortran variants simultaneously.

> Windows note: the native Windows test suite exercises symbolic links, long
> paths, POSIX permissions, path separators, and UTF-8 filesystem behavior.
> Enable Windows Developer Mode to allow unprivileged symbolic-link creation, or
> run the tests from an elevated shell. Enable the Windows `LongPathsEnabled`
> policy before relying on long-path tests. Restart affected shells or applications
> after changing either setting. For exact parity with the blocking GitHub Actions
> test matrix, run the suite in WSL or Linux; CI currently runs on Ubuntu with
> Python 3.10 and 3.12. Pyright is available as a local advisory check, but it is
> not currently a blocking CI job.

### Git workflow

- Active development happens on the `v8` branch.
- Commit style: `fix: <description>` / `feat: <description>` / `docs: <description>`
- Before opening a PR, run `uv run pytest tests/ -q` and confirm it passes.
- Add a fixture file to `tests/fixtures/` and tests to `tests/test_languages.py` for any new language extractor.

### What to contribute

**Worked examples** are the most useful contribution. Run `/kb-core` on a real corpus, save the output to `worked/{slug}/`, write an honest `review.md` covering what the graph got right and wrong, and open a PR.

**Extraction bugs** — open an issue with the input file, the cache entry (`kb-core-out/cache/`), and what was missed or wrong.

See [ARCHITECTURE.md](ARCHITECTURE.md) for module responsibilities and how to add a language.

</details>

---

## Community and links

<p align="center">
  <a href="https://kb-core.com"><img src="https://img.shields.io/badge/Website-kb-core.com-4c1?style=flat&logo=googlechrome&logoColor=white" alt="Website"/></a>
  <a href="https://discord.gg/598Ad9zQZ"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"/></a>
  <a href="https://x.com/kb-core"><img src="https://img.shields.io/badge/X-kb-core-000000?logo=x&logoColor=white" alt="X"/></a>
  <a href="https://www.youtube.com/@kb-corelabs"><img src="https://img.shields.io/badge/YouTube-KB Core%20Labs-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
</p>
