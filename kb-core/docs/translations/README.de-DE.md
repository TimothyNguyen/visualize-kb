<p align="center">
  <img src="https://raw.githubusercontent.com/safishamsi/kb_core/v4/docs/logo-text.svg" width="260" height="64" alt="KB Core"/>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a>
</p>

<p align="center">
  <a href="https://github.com/safishamsi/kb_core/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/kb_core/actions/workflows/ci.yml/badge.svg?branch=v4" alt="CI"/></a>
  <a href="https://pypi.org/project/kb-core/"><img src="https://img.shields.io/pypi/v/kb-core" alt="PyPI"/></a>
  <a href="https://pepy.tech/project/kb-core"><img src="https://static.pepy.tech/badge/kb-core" alt="Downloads"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://www.linkedin.com/company/kb-core-labs"><img src="https://img.shields.io/badge/LinkedIn-KB Core%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
</p>

**Eine KI-Coding-Assistent-Skill.** Tippe `/kb-core` in Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro oder Google Antigravity — es liest deine Dateien, baut einen Wissensgraphen und gibt dir Struktur zurück, die du vorher nicht sehen konntest. Verstehe eine Codebasis schneller. Finde das „Warum" hinter Architekturentscheidungen.

Vollständig multimodal. Leg Code, PDFs, Markdown, Screenshots, Diagramme, Whiteboard-Fotos, Bilder in anderen Sprachen oder Video- und Audiodateien ab — kb-core extrahiert Konzepte und Beziehungen aus allem und verbindet sie in einem einzigen Graphen. Videos werden lokal mit Whisper transkribiert, angetrieben durch einen domänenspezifischen Prompt aus deinem Korpus. 25 Programmiersprachen werden über tree-sitter AST unterstützt (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart).

> Andrej Karpathy führt einen `/raw`-Ordner, in dem er Papers, Tweets, Screenshots und Notizen ablegt. kb-core ist die Antwort auf dieses Problem — 71,5-fach weniger Tokens pro Abfrage gegenüber dem Lesen der Rohdateien, persistent über Sitzungen hinweg, ehrlich darüber, was gefunden vs. erschlossen wurde.

```
/kb-core .                        # funktioniert mit jedem Ordner — Codebase, Notizen, Papers, alles
```

```
kb-core-out/
├── graph.html       interaktiver Graph — im Browser öffnen, Knoten anklicken, suchen, filtern
├── GRAPH_REPORT.md  Gott-Knoten, überraschende Verbindungen, vorgeschlagene Fragen
├── graph.json       persistenter Graph — Wochen später abfragen, ohne neu zu lesen
└── cache/           SHA256-Cache — erneute Ausführungen verarbeiten nur geänderte Dateien
```

Füge eine `.kb-coreignore`-Datei hinzu, um Ordner auszuschließen:

```
# .kb-coreignore
vendor/
node_modules/
dist/
*.generated.py
```

Gleiche Syntax wie `.gitignore`. Du kannst eine einzelne `.kb-coreignore` im Repo-Stammverzeichnis behalten — Muster funktionieren korrekt, auch wenn kb-core auf einem Unterordner ausgeführt wird.

## So funktioniert es

kb-core läuft in drei Durchgängen. Zuerst extrahiert ein deterministischer AST-Durchgang Strukturen aus Code-Dateien (Klassen, Funktionen, Importe, Aufrufgraphen, Docstrings, Begründungskommentare) — ohne LLM. Zweitens werden Video- und Audiodateien lokal mit faster-whisper transkribiert, angetrieben durch einen domänenspezifischen Prompt aus Korpus-Gott-Knoten — Transkripte werden gecacht, sodass erneute Ausführungen sofort sind. Drittens laufen Claude-Subagenten parallel über Dokumente, Papers, Bilder und Transkripte, um Konzepte, Beziehungen und Designbegründungen zu extrahieren. Die Ergebnisse werden in einem NetworkX-Graphen zusammengeführt, mit Leiden-Community-Erkennung geclustert und als interaktives HTML, abfragbares JSON und ein Klartext-Audit-Report exportiert.

**Clustering basiert auf Graph-Topologie — keine Embeddings.** Leiden findet Communities durch Kantendichte. Die semantischen Ähnlichkeitskanten, die Claude extrahiert (`semantically_similar_to`, markiert als INFERRED), sind bereits im Graphen, sodass sie die Community-Erkennung direkt beeinflussen. Die Graphstruktur ist das Ähnlichkeitssignal — kein separater Embedding-Schritt oder Vektordatenbank nötig.

Jede Beziehung ist markiert als `EXTRACTED` (direkt in der Quelle gefunden), `INFERRED` (begründete Schlussfolgerung mit Konfidenzwert) oder `AMBIGUOUS` (zur Überprüfung markiert). Du weißt immer, was gefunden vs. erschlossen wurde.

## Installation

**Voraussetzungen:** Python 3.10+ und eines von: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes oder [Google Antigravity](https://antigravity.google)

```bash
# Empfohlen — funktioniert auf Mac und Linux ohne PATH-Einrichtung
uv tool install kb-core && kb-core install
# oder mit pipx
pipx install kb-core && kb-core install
# oder einfaches pip
pip install kb-core && kb-core install
```

> **Offizielles Paket:** Das PyPI-Paket heißt `kb-core` (installieren mit `pip install kb-core`). Andere Pakete mit Namen `kb-core*` auf PyPI sind nicht mit diesem Projekt verbunden. Das einzige offizielle Repository ist [safishamsi/kb-core](https://github.com/safishamsi/kb-core). CLI und Skill-Befehl heißen weiterhin `kb-core`.

> **`kb-core: command not found`?** Verwende `uv tool install kb-core` (empfohlen) oder `pipx install kb-core` — beide platzieren die CLI an einem verwalteten Ort, der automatisch im PATH ist. Mit einfachem `pip` musst du möglicherweise `~/.local/bin` (Linux) oder `~/Library/Python/3.x/bin` (Mac) zum PATH hinzufügen, oder `python -m kb_core` verwenden.

### Plattformunterstützung

| Plattform | Installationsbefehl |
|-----------|---------------------|
| Claude Code (Linux/Mac) | `kb-core install` |
| Claude Code (Windows) | `kb-core install` (automatisch erkannt) oder `kb-core install --platform windows` |
| Codex | `kb-core install --platform codex` |
| OpenCode | `kb-core install --platform opencode` |
| GitHub Copilot CLI | `kb-core install --platform copilot` |
| VS Code Copilot Chat | `kb-core vscode install` |
| Aider | `kb-core install --platform aider` |
| OpenClaw | `kb-core install --platform claw` |
| Factory Droid | `kb-core install --platform droid` |
| Trae | `kb-core install --platform trae` |
| Trae CN | `kb-core install --platform trae-cn` |
| Gemini CLI | `kb-core install --platform gemini` |
| Hermes | `kb-core install --platform hermes` |
| Kiro IDE/CLI | `kb-core kiro install` |
| Cursor | `kb-core cursor install` |
| Google Antigravity | `kb-core antigravity install` |

Dann öffne deinen KI-Coding-Assistenten und tippe:

```
/kb-core .
```

Hinweis: Codex verwendet `$` statt `/` für Skill-Aufrufe, also tippe `$kb-core .`.

### Assistenten immer den Graphen nutzen lassen (empfohlen)

Nach dem Erstellen eines Graphen, führe dies einmal in deinem Projekt aus:

| Plattform | Befehl |
|-----------|--------|
| Claude Code | `kb-core claude install` |
| Codex | `kb-core codex install` |
| OpenCode | `kb-core opencode install` |
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
| Kiro IDE/CLI | `kb-core kiro install` |
| Google Antigravity | `kb-core antigravity install` |

## Verwendung

```
/kb-core                          # aktuelles Verzeichnis verarbeiten
/kb-core ./raw                    # spezifischen Ordner verarbeiten
/kb-core ./raw --mode deep        # aggressivere INFERRED-Kanten-Extraktion
/kb-core ./raw --update           # nur geänderte Dateien neu extrahieren
/kb-core ./raw --directed         # gerichteten Graphen erstellen
/kb-core ./raw --cluster-only     # Clustering auf bestehendem Graphen neu ausführen
/kb-core ./raw --no-viz           # kein HTML, nur Report + JSON
/kb-core ./raw --obsidian         # Obsidian-Vault generieren (opt-in)

/kb-core add https://arxiv.org/abs/1706.03762   # Paper abrufen, speichern, Graphen aktualisieren
/kb-core add <video-url>                         # Audio herunterladen, transkribieren, hinzufügen
/kb-core query "was verbindet Attention mit dem Optimizer?"
/kb-core path "DigestAuth" "Response"
/kb-core explain "SwinTransformer"

kb-core hook install              # Git-Hooks installieren
kb-core update ./src              # Code-Dateien neu extrahieren, kein LLM benötigt
kb-core watch ./src               # Graphen bei Änderungen automatisch aktualisieren
```

## Was du bekommst

**Gott-Knoten** — Konzepte mit dem höchsten Grad (durch die alles fließt)

**Überraschende Verbindungen** — nach Composite-Score eingestuft. Code-Paper-Kanten werden höher bewertet. Jedes Ergebnis enthält ein Klartext-Warum.

**Vorgeschlagene Fragen** — 4-5 Fragen, die der Graph einzigartig gut beantworten kann

**Das „Warum"** — Docstrings, Inline-Kommentare (`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`), und Designbegründungen aus Dokumenten werden als `rationale_for`-Knoten extrahiert.

**Konfidenzwerte** — jede INFERRED-Kante hat einen `confidence_score` (0,0-1,0).

**Token-Benchmark** — wird automatisch nach jeder Ausführung gedruckt. Auf einem gemischten Korpus: **71,5-fach** weniger Tokens pro Abfrage gegenüber Rohdateien.

**Auto-Sync** (`--watch`) — läuft im Hintergrund und aktualisiert den Graphen bei Codeänderungen automatisch.

**Git-Hooks** (`kb-core hook install`) — installiert Post-Commit- und Post-Checkout-Hooks.

## Datenschutz

kb-core sendet Dateiinhalte an die Modell-API deines KI-Assistenten für semantische Extraktion von Dokumenten, Papers und Bildern. Code-Dateien werden lokal via tree-sitter AST verarbeitet — kein Dateiinhalt verlässt dein Gerät für Code. Video- und Audiodateien werden lokal mit faster-whisper transkribiert. Keine Telemetrie, keine Nutzungsverfolgung.

## Tech-Stack

NetworkX + Leiden (graspologic) + tree-sitter + vis.js. Semantische Extraktion via Claude, GPT-4 oder welches Modell deine Plattform verwendet. Video-Transkription via faster-whisper + yt-dlp (optional).

## Auf kb-core aufgebaut — Penpax

[**Penpax**](https://safishamsi.github.io/penpax.ai) ist die Enterprise-Schicht über kb_core. Wo kb-core einen Ordner mit Dateien in einen Wissensgraphen verwandelt, wendet Penpax denselben Graphen auf dein gesamtes Arbeitsleben an — kontinuierlich.

**Kostenlose Testversion startet bald.** [Auf die Warteliste setzen →](https://safishamsi.github.io/penpax.ai)

## Star-Verlauf

[![Star History Chart](https://api.star-history.com/svg?repos=safishamsi/kb-core&type=Date)](https://star-history.com/#safishamsi/kb-core&Date)
