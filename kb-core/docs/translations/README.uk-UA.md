<p align="center">
  <a href="https://kb-core.com"><img src="https://raw.githubusercontent.com/safishamsi/kb_core/v4/docs/logo-text.svg" width="260" height="64" alt="KB Core"/></a>
</p>

<p align="center">
  🇺🇸 <a href="../../README.md">English</a> | 🇨🇳 <a href="README.zh-CN.md">简体中文</a> | 🇯🇵 <a href="README.ja-JP.md">日本語</a> | 🇰🇷 <a href="README.ko-KR.md">한국어</a> | 🇩🇪 <a href="README.de-DE.md">Deutsch</a> | 🇫🇷 <a href="README.fr-FR.md">Français</a> | 🇪🇸 <a href="README.es-ES.md">Español</a> | 🇮🇳 <a href="README.hi-IN.md">हिन्दी</a> | 🇧🇷 <a href="README.pt-BR.md">Português</a> | 🇷🇺 <a href="README.ru-RU.md">Русский</a> | 🇸🇦 <a href="README.ar-SA.md">العربية</a> | 🇮🇹 <a href="README.it-IT.md">Italiano</a> | 🇵🇱 <a href="README.pl-PL.md">Polski</a> | 🇳🇱 <a href="README.nl-NL.md">Nederlands</a> | 🇹🇷 <a href="README.tr-TR.md">Türkçe</a> | 🇺🇦 <a href="README.uk-UA.md">Українська</a> | 🇻🇳 <a href="README.vi-VN.md">Tiếng Việt</a> | 🇮🇩 <a href="README.id-ID.md">Bahasa Indonesia</a> | 🇸🇪 <a href="README.sv-SE.md">Svenska</a> | 🇬🇷 <a href="README.el-GR.md">Ελληνικά</a> | 🇷🇴 <a href="README.ro-RO.md">Română</a> | 🇨🇿 <a href="README.cs-CZ.md">Čeština</a> | 🇫🇮 <a href="README.fi-FI.md">Suomi</a> | 🇩🇰 <a href="README.da-DK.md">Dansk</a> | 🇳🇴 <a href="README.no-NO.md">Norsk</a> | 🇭🇺 <a href="README.hu-HU.md">Magyar</a> | 🇹🇭 <a href="README.th-TH.md">ภาษาไทย</a> | 🇺🇿 <a href="README.uz-UZ.md">Oʻzbekcha</a> | 🇹🇼 <a href="README.zh-TW.md">繁體中文</a>
</p>

<p align="center">
  <a href="https://www.ycombinator.com/companies/kb-core"><img src="https://img.shields.io/badge/Y%20Combinator-S26-F0652F?style=flat&logo=ycombinator&logoColor=white" alt="YC S26"/></a>
  <a href="https://safishamsi.gumroad.com/l/qetvlo"><img src="https://img.shields.io/badge/Book-The%20Memory%20Layer-2ea44f?style=flat&logo=gitbook&logoColor=white" alt="The Memory Layer"/></a>
  <a href="https://github.com/safishamsi/kb_core/actions/workflows/ci.yml"><img src="https://github.com/safishamsi/kb_core/actions/workflows/ci.yml/badge.svg?branch=v8" alt="CI"/></a>
  <a href="https://pypi.org/project/kb-core/"><img src="https://img.shields.io/pypi/v/kb-core" alt="PyPI"/></a>
  <a href="https://clickpy.clickhouse.com/dashboard/kb-core"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fsql-clickhouse.clickhouse.com%2F%3Fquery%3DSELECT%2520concat%2528toString%2528round%2528sum%2528count%2529%2F1000%2529%2529%2C%2520%2527k%2527%2529%2520AS%2520c%2520FROM%2520pypi.pypi_downloads%2520WHERE%2520project%253D%2527kb-core%2527%2520FORMAT%2520JSON%26user%3Ddemo&query=%24.data%5B0%5D.c&label=downloads&color=blue" alt="Downloads"/></a>
  <a href="https://github.com/sponsors/safishamsi"><img src="https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors" alt="Sponsor"/></a>
  <a href="https://www.linkedin.com/company/kb-core-labs"><img src="https://img.shields.io/badge/LinkedIn-KB Core%20Labs-0077B5?logo=linkedin" alt="LinkedIn"/></a>
  <a href="https://x.com/kb-core"><img src="https://img.shields.io/badge/X-kb-core-000000?logo=x&logoColor=white" alt="X"/></a>
</p>

<p align="center">
  <a href="https://star-history.com/#safishamsi/kb-core&Date">
    <img src="https://api.star-history.com/svg?repos=safishamsi/kb-core&type=Date" alt="Star History Chart" width="370"/>
  </a>
</p>

Введіть `/kb-core` у своєму ШІ-асистенті для кодингу, і він нанесе весь ваш проект — код, документи, PDF, зображення, відео — на граф знань, який можна запитувати замість того, щоб шукати по файлах.

Працює в Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kimi Code, Kiro, Pi та Google Antigravity.

```
/kb-core .
```

Це все. Ви отримуєте три файли:

```
kb-core-out/
├── graph.html       відкрийте в будь-якому браузері — клікайте по вузлах, фільтруйте, шукайте
├── GRAPH_REPORT.md  основне: ключові концепції, неочікувані зв’язки, запропоновані запитання
└── graph.json       повний граф — запитуйте його будь-коли без повторного перечитування ваших файлів
```

Для читабельної сторінки архітектури з діаграмами викликів Mermaid виконайте:

```bash
kb-core export callflow-html
```

---

## Вимоги

| Вимога | Мінімум | Перевірка | Встановлення |
|---|---|---|---|
| Python | 3.10+ | `python --version` | [python.org](https://www.python.org/downloads/) |
| uv *(рекомендовано)* | будь-яка | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pipx *(альтернатива)* | будь-яка | `pipx --version` | `pip install pipx` |

**Швидке встановлення на macOS (Homebrew):**
```bash
brew install python@3.12 uv
```

**Швидке встановлення на Windows:**
```powershell
winget install astral-sh.uv
```

**Ubuntu/Debian:**
```bash
sudo apt install python3.12 python3-pip pipx
# або встановити uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Встановлення

> **Офіційний пакет:** Пакет PyPI — `kb-core` (подвійна y). Інші пакети `kb-core*` на PyPI не є афілійованими. Команда CLI залишається `kb-core`.

**Крок 1 — встановити пакет:**

```bash
# Рекомендовано (uv автоматично додає kb-core до PATH):
uv tool install kb-core

# Альтернативи:
pipx install kb-core
pip install kb-core
```

**Крок 2 — зареєструвати навичку у вашому ШІ-асистенті:**

```bash
kb-core install
```

Це все. Відкрийте асистента і введіть `/kb-core .`

Щоб встановити навичку в поточний репозиторій замість профілю користувача, додайте `--project`:

```bash
kb-core install --project
kb-core install --project --platform codex
```

Встановлення на рівні проєкту записуються в поточну директорію, наприклад .claude/skills/kb_core/SKILL.md або .agents/skills/kb_core/SKILL.md, і виводять підказку git add для файлів, які можна закомітити. Команди для окремих платформ, що підтримують інсталяції на рівні проєкту, приймають той самий прапорець, наприклад kb-core claude install --project або kb-core codex install --project.

> **Примітка для PowerShell:** Використовуйте `kb-core .` замість `/kb-core .` — ведучий слеш є роздільником шляху в PowerShell.

> **`kb-core: command not found`?** Використовуйте `uv tool install kb-core` або `pipx install kb-core` — обидва автоматично додають CLI до PATH. При використанні звичайного `pip` додайте `~/.local/bin` (Linux) або `~/Library/Python/3.x/bin` (Mac) до вашого PATH, або запустіть `python -m kb_core`.

### Оберіть платформу

| Платформа | Команда встановлення |
|----------|----------------|
| Claude Code (Linux/Mac) | `kb-core install` |
| Claude Code (Windows) | `kb-core install --platform windows` |
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
| Kimi Code | `kb-core install --platform kimi` |
| Kiro IDE/CLI | `kb-core kiro install` |
| Pi coding agent | `kb-core install --platform pi` |
| Cursor | `kb-core cursor install` |
| Google Antigravity | `kb-core antigravity install` |

> Користувачам Codex: також додайте `multi_agent = true` під `[features]` у `~/.codex/config.toml`.
> Codex використовує `$kb-core` замість `/kb-core`.

### Додаткові пакети (опціонально)

Встановіть лише те, що потрібно:

| Пакет | Що додає | Встановлення |
|---|---|---|
| `pdf` | Вилучення PDF | `pip install "kb-core[pdf]"` |
| `office` | Підтримка `.docx` та `.xlsx` | `pip install "kb-core[office]"` |
| `google` | Рендеринг Google Sheets | `pip install "kb-core[google]"` |
| `video` | Транскрипція відео/аудіо (faster-whisper + yt-dlp) | `pip install "kb-core[video]"` |
| `mcp` | MCP stdio-сервер | `pip install "kb-core[mcp]"` |
| `neo4j` | Підтримка надсилання до Neo4j | `pip install "kb-core[neo4j]"` |
| `svg` | Експорт графу в SVG | `pip install "kb-core[svg]"` |
| `leiden` | Виявлення спільнот Leiden (лише Python < 3.13) | `pip install "kb-core[leiden]"` |
| `ollama` | Локальний вивід Ollama | `pip install "kb-core[ollama]"` |
| `openai` | OpenAI / OpenAI-сумісні API | `pip install "kb-core[openai]"` |
| `gemini` | Google Gemini API | `pip install "kb-core[gemini]"` |
| `bedrock` | AWS Bedrock (використовує IAM, без API-ключа) | `pip install "kb-core[bedrock]"` |
| `sql` | Вилучення SQL схем | `pip install "kb-core[sql]"` |
| `all` | Все вищезазначене | `pip install "kb-core[all]"` |

---

## Змусьте асистента завжди використовувати граф

Виконайте один раз у своєму проекті після побудови графу:

| Платформа | Команда |
|----------|---------|
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
| Kimi Code | `kb-core install --platform kimi` |
| Kiro IDE/CLI | `kb-core kiro install` |
| Pi coding agent | `kb-core pi install` |
| Google Antigravity | `kb-core antigravity install` |

Це записує невеликий конфігураційний файл, який каже асистенту звертатися до графу знань для питань про кодову базу — надаючи перевагу локалізованим запитам на кшталт `kb-core query "<питання>"` замість читання повного звіту або пошуку по сирих файлах. На платформах, що підтримують хуки з корисним навантаженням (Claude Code, Gemini CLI), хук спрацьовує автоматично перед пошуковими викликами інструментів і спрямовує асистента до графу. На інших (Codex, OpenCode, Cursor тощо) постійні файли інструкцій (`AGENTS.md`, `.cursor/rules/` тощо) забезпечують таке саме керівництво. `GRAPH_REPORT.md` все ще доступний для загального огляду архітектури.

Щоб видалити kb-core з усіх платформ одразу: `kb-core uninstall` (додайте `--purge`, щоб також видалити `kb-core-out/`). Або скористайтеся командою для конкретної платформи (напр. `kb-core claude uninstall`).

---

## Що є у звіті

- **Вузли-боги** — найбільш пов'язані концепції у вашому проекті. Через них проходить все.
- **Несподівані зв'язки** — зв'язки між речами з різних файлів або модулів. Відсортовані за ступенем несподіваності.
- **«Чому»** — рядкові коментарі (`# NOTE:`, `# WHY:`, `# HACK:`), рядки документації та обґрунтування дизайну з документів витягуються як окремі вузли, пов'язані з кодом, який вони пояснюють.
- **Запропоновані питання** — 4–5 питань, на які граф унікально здатний відповісти.
- **Теги впевненості** — кожен виведений зв'язок позначений як `EXTRACTED`, `INFERRED` або `AMBIGUOUS`. Ви завжди знаєте, що знайдено, а що виведено.

---

## Які файли підтримуються

| Тип | Розширення |
|------|-----------|
| Код (31 мова) | `.py .ts .js .jsx .tsx .mjs .go .rs .java .c .cpp .h .hpp .rb .cs .kt .scala .php .swift .lua .luau .zig .ps1 .ex .exs .m .mm .jl .vue .svelte .astro .groovy .gradle .dart .v .sv .sql .f .f90 .f95 .f03 .f08 .pas .pp .dpr .dpk .lpr .inc .dfm .lfm .lpk .sh .bash .json` |
| Документи | `.md .mdx .qmd .html .txt .rst .yaml .yml` |
| Office | `.docx .xlsx` (потрібен `pip install kb-core[office]`) |
| Google Workspace | `.gdoc .gsheet .gslides` (опціонально; потрібна автентифікація `gws` та `--google-workspace`; Sheets потребує `pip install kb-core[google]`) |
| PDF | `.pdf` |
| Зображення | `.png .jpg .webp .gif` |
| Відео / Аудіо | `.mp4 .mov .mp3 .wav` та інші (потрібен `pip install kb-core[video]`) |
| YouTube / URL | будь-який URL відео (потрібен `pip install kb-core[video]`) |

Код витягується локально без API-викликів (AST через tree-sitter). Все інше обробляється через API моделі вашого ШІ-асистента.

Файли `.gdoc`, `.gsheet` та `.gslides` з Google Drive for desktop — це ярлики-посилання, а не вміст документів. Щоб включити нативні Google Docs, Sheets та Slides у безголове витягування, встановіть та автентифікуйте [`gws` CLI](https://github.com/googleworkspace/cli), потім запустіть:

```bash
pip install "kb-core[google]"  # потрібен для рендерингу таблиць Google Sheets
gws auth login -s drive
kb-core extract ./docs --google-workspace
```

Також можна встановити `KB_CORE_GOOGLE_WORKSPACE=1`. KB Core експортує ярлики в `kb-core-out/converted/` як Markdown-сайдкари, а потім витягує ці файли.

---

## Часті команди

```bash
/kb-core .                        # побудувати граф для поточної папки
/kb-core ./docs --update          # повторно витягнути лише змінені файли
/kb-core . --cluster-only         # перезапустити кластеризацію без повторного витягування
/kb-core . --cluster-only --resolution 1.5      # більш дрібні спільноти
/kb-core . --cluster-only --exclude-hubs 99     # виключити утилітарні суперхаби з рейтингів “god-node” вузлів-богів
/kb-core . --no-viz               # пропустити HTML, лише звіт + JSON
/kb-core . --wiki                 # побудувати markdown-вікі з графу
kb-core export callflow-html      # Mermaid архітектура/flow-викликів HTML (автоматично регенерується на кожен git-коміт, якщо встановлений hook)

/kb-core query "що пов'язує auth з базою даних?"
/kb-core path "UserService" "DatabasePool"
/kb-core explain "RateLimiter"

/kb-core add https://arxiv.org/abs/1706.03762   # завантажити статтю і додати її
/kb-core add <youtube-url>                       # транскрибувати і додати відео

kb-core hook install              # автоматичне перебудування при git-коміті
kb-core merge-graphs a.json b.json              # об'єднати два графи

kb-core prs                       # дашборд PR: стан CI, статус рев’ю, мапінг worktree
kb-core prs 42                    # детальний огляд PR #42 з впливом на граф
kb-core prs --triage              # ШІ оцінює вашу чергу рев’ю (використовує будь-який налаштований бекенд)
kb-core prs --conflicts           # PR-и, що ділять спільні графові спільноти — ризик порядку злиття
```

Дивіться [повний довідник команд](#повний-довідник-команд) нижче.

---

## Ігнорування файлів

Створіть `.kb-coreignore` у кореневій директорії проекту — той самий синтаксис, що й `.gitignore`, включно з запереченням `!`:

```
# .kb-coreignore
node_modules/
dist/
*.generated.py

# індексувати лише src/, ігнорувати все інше
*
!src/
!src/**
```

---

## Налаштування для команди

`kb-core-out/` призначений для коміту в git, щоб кожен у команді починав із картою.

**Рекомендовані доповнення до `.gitignore`:**
```
kb-core-out/manifest.json    # базується на mtime, ламається після git clone
kb-core-out/cost.json        # лише локальний
# kb-core-out/cache/         # опціонально: комітьте для швидкості, пропустіть для меншого репо
```

**Робочий процес:**
1. Одна людина запускає `/kb-core .` і комітить `kb-core-out/`.
2. Усі виконують pull — їхній асистент одразу читає граф.
3. Запустіть `kb-core hook install` для автоматичного перебудування після кожного коміту (лише AST, без витрат API). Це також налаштовує git merge driver, щоб `graph.json` ніколи не залишався з маркерами конфліктів — два розробники, що комітять одночасно, отримають автоматично об'єднані графи.
4. Коли документи або статті змінюються, запустіть `/kb-core --update`, щоб оновити ці вузли.

---

## Використання графу напряму

```bash
# запит до графу з терміналу
kb-core query "покажи потік автентифікації"
kb-core query "що пов'язує DigestAuth з Response?" --graph kb-core-out/graph.json

# відкрити граф як MCP-сервер (для повторного доступу через інструменти)
python -m kb_core.serve kb-core-out/graph.json

# зареєструвати в Kimi Code:
kimi mcp add --transport stdio kb-core -- python -m kb_core.serve kb-core-out/graph.json
```

MCP-сервер надає асистенту структурований доступ: `query_graph`, `get_node`, `get_neighbors`, `shortest_path`, `list_prs`, `get_pr_impact`, `triage_prs`.

> **Примітка для WSL / Linux:** Ubuntu постачає `python3`, а не `python`. Використовуйте venv, щоб уникнути конфліктів:
> ```bash
> python3 -m venv .venv && .venv/bin/pip install "kb-core[mcp]"
> ```

---

## Змінні середовища

Потрібні лише для **headless / CI витягування** (`kb-core extract`). При запуску через навичку `/kb-core` у вашому IDE API моделі надається сесією IDE — додаткових ключів не потрібно.

| Змінна | Використання | Коли потрібна |
|---|---|---|
| `ANTHROPIC_API_KEY` | Backend Claude (Anthropic) | `--backend claude` |
| `ANTHROPIC_BASE_URL` | URL Anthropic-сумісного endpoint (LiteLLM proxy, шлюзи, ...) | `--backend claude` (типово: `https://api.anthropic.com`) |
| `ANTHROPIC_MODEL` | Назва моделі для backend Claude — для власних endpoint використовуйте назву/псевдонім моделі вашого сервера | `--backend claude` (типово: `claude-sonnet-4-6`) |
| `GEMINI_API_KEY` або `GOOGLE_API_KEY` | Backend Google Gemini | `--backend gemini` |
| `OPENAI_API_KEY` | OpenAI або OpenAI-сумісні API | `--backend openai` (локальні сервери приймають будь-яке непорожнє значення) |
| `OPENAI_BASE_URL` | URL OpenAI-сумісного сервера (llama.cpp, vLLM, LM Studio, ...) | `--backend openai` (типово: `https://api.openai.com/v1`) |
| `OPENAI_MODEL` | Назва моделі для backend OpenAI — для self-hosted серверів використовуйте назву/псевдонім моделі, яку надає ваш сервер (див. його endpoint `/v1/models`), напр. `LFM2.5-8B-A1B-UD-Q4_K_XL` для llama.cpp | `--backend openai` (типово: `gpt-4.1-mini`) |
| `DEEPSEEK_API_KEY` | Backend DeepSeek | `--backend deepseek` |
| `MOONSHOT_API_KEY` | Backend Kimi Code | `--backend kimi` |
| `OLLAMA_BASE_URL` | URL локального виводу Ollama | `--backend ollama` (типово: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Назва моделі Ollama | `--backend ollama` (типово: автовизначення) |
| `KB_CORE_OLLAMA_NUM_CTX` | Перевизначити розмір KV-кеш вікна Ollama | опціонально — автоматично за замовчуванням |
| `KB_CORE_OLLAMA_KEEP_ALIVE` | Хвилини утримання моделі Ollama завантаженою | опціонально — встановіть `0` для вивантаження після кожного шматка |
| `AWS_*` / `~/.aws/credentials` | AWS Bedrock — стандартний ланцюг облікових даних | `--backend bedrock` (без API-ключа, використовує IAM) |
| `KB_CORE_MAX_WORKERS` | Кількість потоків паралелізму AST | опціонально — також прапор `--max-workers` |
| `KB_CORE_MAX_OUTPUT_TOKENS` | Підвищити ліміт виводу для щільних корпусів | опціонально — напр. `32768` для великих файлів |
| `KB_CORE_API_TIMEOUT` | HTTP тайм-аут у секундах (типово: 600) | опціонально — також прапор `--api-timeout` |
| `KB_CORE_FORCE` | Примусове перебудування графу навіть із меншою кількістю вузлів | опціонально — також прапор `--force` |
| `KB_CORE_GOOGLE_WORKSPACE` | Автоввімкнення експорту Google Workspace | опціонально — встановіть в `1` |
| `KB_CORE_TRIAGE_BACKEND` | Backend для `kb-core prs --triage` | опціонально — автовизначення з наявних ключів |
| `KB_CORE_TRIAGE_MODEL` | Перевизначення моделі для triage | опціонально — напр. `claude-opus-4-7` |

---

## Конфіденційність

- **Файли коду** — обробляються локально через tree-sitter. Нічого не покидає ваш комп'ютер.
- **Відео / аудіо** — транскрибуються локально за допомогою faster-whisper. Нічого не покидає ваш комп'ютер.
- **Документи, PDF, зображення** — надсилаються до вашого ШІ-асистента для семантичного витягування (через навичку `/kb-core`, використовуючи модель, що запущена у вашому IDE). Безголове `kb-core extract` потребує `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude), `OPENAI_API_KEY` (OpenAI), `DEEPSEEK_API_KEY` (DeepSeek), запущеного екземпляра Ollama (`OLLAMA_BASE_URL`), AWS-облікових даних через стандартний ланцюг провайдерів (Bedrock — без API-ключа, використовує IAM) або бінарного файлу `claude` CLI (Claude Code — без API-ключа, використовує вашу підписку Claude). Прапор `--dedup-llm` використовує той самий ключ.
- Без телеметрії, без відстеження використання, без аналітики.

---

## Вирішення проблем

**`kb-core: command not found` після `pip install kb-core`**
pip встановлює скрипти в директорію bin для користувача, яка може не бути в PATH. Виправлення:
- macOS: додайте `~/Library/Python/3.x/bin` до PATH у `~/.zshrc`
- Linux: додайте `~/.local/bin` до PATH у `~/.bashrc`
- Або використовуйте `uv tool install kb-core` / `pipx install kb-core` — обидва автоматично керують PATH.

**`python -m kb_core` працює, але команда `kb-core` — ні**
PATH вашої оболонки не включає директорію скриптів Python. Використовуйте `uv` або `pipx` замість звичайного `pip`.

**`/kb-core .` викликає "path not recognized" в PowerShell**
PowerShell трактує ведучий `/` як роздільник шляху. Використовуйте `kb-core .` (без слеша) на Windows.

**Граф має менше вузлів після `--update` або перебудови**
Якщо рефакторинг видалив файли, старі вузли залишаються. Передайте `--force` (або встановіть `KB_CORE_FORCE=1`), щоб перезаписати навіть якщо перебудова має менше вузлів.

**Граф має дублікати вузлів для однієї сутності (фантомні дублікати)**
Це трапляється, коли семантичне та AST-витягування не погодилось щодо формату ID вузла. Запустіть повне повторне витягування для очищення:
```bash
kb-core extract . --force
```

**Ollama вичерпує VRAM / перевищено вікно контексту**
KV-кеш вікно автоматично розраховується, але може бути завеликим для вашого GPU. Зменшіть його:
```bash
KB_CORE_OLLAMA_NUM_CTX=8192 kb-core extract ./docs --backend ollama --token-budget 4000
```

**HTML графу занадто великий для відкриття в браузері (>5000 вузлів)**
Пропустіть генерацію HTML і використовуйте JSON напряму:
```bash
kb-core cluster-only ./my-project --no-viz
kb-core query "..."
```

**`graph.json` має маркери конфліктів після одночасного коміту двох розробників**
Запустіть `kb-core hook install` — це налаштовує git merge driver, який автоматично об'єднує `graph.json`, щоб конфліктів ніколи не виникало.

**Вилучення повертає порожні вузли/ребра для документів або PDF**
Документи та PDF потребують LLM-виклику. Перевірте, що API-ключ встановлено і backend правильний:
```bash
ANTHROPIC_API_KEY=sk-... kb-core extract ./docs --backend claude
```

**Попередження про невідповідність версій навички у вашому IDE**
Встановлена версія kb-core відрізняється від файлу навички. Оновіть:
```bash
uv tool upgrade kb-core
kb-core install  # перезаписує файл навички
```

---

## Повний довідник команд

```
/kb-core                          # запустити в поточному каталозі
/kb-core ./raw                    # запустити у конкретній папці
/kb-core ./raw --mode deep        # більш агресивне витягування зв'язків
/kb-core ./raw --update           # повторно витягнути лише змінені файли
/kb-core ./raw --directed         # зберегти напрямок ребер
/kb-core ./raw --cluster-only     # повторна кластеризація існуючого графу
/kb-core ./raw --no-viz           # пропустити HTML-візуалізацію
/kb-core ./raw --obsidian         # згенерувати сховище Obsidian
/kb-core ./raw --wiki             # побудувати markdown-вікі для обходу агентами
/kb-core ./raw --svg              # експортувати graph.svg
/kb-core ./raw --graphml          # експортувати для Gephi / yEd
/kb-core ./raw --neo4j            # згенерувати cypher.txt для Neo4j
/kb-core ./raw --neo4j-push bolt://localhost:7687
/kb-core ./raw --watch            # автосинхронізація при зміні файлів
/kb-core ./raw --mcp              # запустити MCP stdio-сервер

/kb-core add https://arxiv.org/abs/1706.03762
/kb-core add <video-url>
/kb-core add https://... --author "Name" --contributor "Name"

/kb-core query "що пов'язує attention з optimizer?"
/kb-core query "..." --dfs --budget 1500
/kb-core path "DigestAuth" "Response"
/kb-core explain "SwinTransformer"

kb-core uninstall                 # видалити з усіх платформ одразу
kb-core uninstall --purge         # також видалити kb-core-out/
kb-core uninstall --project --platform codex  # видалити лише файли проектного встановлення

kb-core hook install              # хуки post-commit + post-checkout
kb-core hook uninstall
kb-core hook status

kb-core claude install / uninstall
kb-core codex install / uninstall
kb-core opencode install
kb-core cursor install / uninstall
kb-core gemini install / uninstall
kb-core copilot install / uninstall
kb-core aider install / uninstall
kb-core claw install / uninstall
kb-core droid install / uninstall
kb-core trae install / uninstall
kb-core trae-cn install / uninstall
kb-core hermes install / uninstall
kb-core kiro install / uninstall
kb-core antigravity install / uninstall

kb-core extract ./docs                        # headless LLM-витягування для CI (без IDE)
kb-core extract ./docs --backend gemini       # явний backend: gemini, kimi, claude, openai, deepseek, ollama, bedrock або claude-cli
kb-core extract ./docs --backend gemini --model gemini-3.1-pro-preview
kb-core extract ./docs --backend ollama       # локальний Ollama (встановіть OLLAMA_BASE_URL / OLLAMA_MODEL) — без API-ключа для loopback
OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_MODEL=my-model kb-core extract ./docs --backend openai   # будь-який OpenAI-сумісний сервер (llama.cpp, vLLM, LM Studio)
ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_MODEL=my-model kb-core extract ./docs --backend claude   # будь-який Anthropic-сумісний endpoint (LiteLLM proxy, шлюзи)
KB_CORE_OLLAMA_NUM_CTX=32768 kb-core extract ./docs --backend ollama   # перевизначити KV-кеш вікно (автоматично за замовчуванням)
KB_CORE_OLLAMA_KEEP_ALIVE=0 kb-core extract ./docs --backend ollama    # вивантажити модель після кожного шматка (економить VRAM на малих GPU)
kb-core extract ./docs --backend bedrock      # AWS Bedrock через IAM — без API-ключа, використовує ланцюг облікових даних AWS
kb-core extract ./docs --backend claude-cli   # маршрутизація через Claude Code CLI — без API-ключа, використовує вашу підписку Claude
kb-core extract ./docs --max-workers 16       # паралелізм AST (також KB_CORE_MAX_WORKERS)
kb-core extract ./docs --token-budget 30000   # менші семантичні шматки для локальних/малих моделей
kb-core extract ./docs --max-concurrency 2    # менше паралельних LLM-викликів (корисно для локального виводу)
kb-core extract ./docs --api-timeout 900      # довший HTTP тайм-аут для повільних локальних моделей (типово 600с)
kb-core extract ./docs --google-workspace     # експортувати .gdoc/.gsheet/.gslides через gws перед витягуванням
kb-core extract ./docs --no-cluster           # лише сире витягування, пропустити кластеризацію
kb-core extract ./docs --force                # перезаписати graph.json навіть якщо новий граф має менше вузлів (використовуйте після рефакторингу або для очищення фантомних дублікатів)
kb-core extract ./docs --dedup-llm            # LLM-арбітр для неоднозначних пар сутностей (використовує той самий API-ключ)
kb-core extract ./docs --global --as myrepo   # витягнути і зареєструвати в крос-проектний глобальний граф
KB_CORE_MAX_OUTPUT_TOKENS=32768 kb-core extract ./docs --backend claude  # підвищити ліміт виводу для щільних корпусів

kb-core export callflow-html                       # kb-core-out/<project>-callflow.html
kb-core export callflow-html --max-sections 8      # обмежити кількість згенерованих секцій архітектури
kb-core export callflow-html --output docs/arch.html
kb-core export callflow-html ./some-repo/kb-core-out

kb-core global add kb-core-out/graph.json myrepo   # зареєструвати граф проекту в ~/.kb_core/global.json
kb-core global remove myrepo                         # видалити проект з глобального графу
kb-core global list                                  # показати всі зареєстровані репо + кількість вузлів/ребер
kb-core global path                                  # вивести шлях до файлу глобального графу

kb-core prs                              # дашборд PR: CI, рев’ю, worktree, вплив на граф
kb-core prs 42                           # детальний огляд PR #42
kb-core prs --triage                     # AI ранжування пріоритизації (автоматично визначає бекенд з середовища)
kb-core prs --worktrees                  # worktree → гілка → PR зіставлення
kb-core prs --conflicts                  # PR-и, що ділять спільні графові спільноти (ризик порядку злиття)
kb-core prs --base main                  # фільтр PR-ів за цільовою базовою гілкою
kb-core prs --repo owner/repo            # запустити для іншого GitHub-репо
KB_CORE_TRIAGE_BACKEND=kimi kb-core prs --triage   # використовувати конкретний backend для triage

kb-core clone https://github.com/karpathy/nanoGPT
kb-core merge-graphs a.json b.json --out merged.json
kb-core --version                                    # вивести встановлену версію
kb-core watch ./src
kb-core check-update ./src
kb-core update ./src
kb-core update ./src --no-cluster  # пропустити рекластеризацію, записати лише сирий AST граф
kb-core update ./src --force       # перезаписати навіть якщо новий граф має менше вузлів
kb-core cluster-only ./my-project
kb-core cluster-only ./my-project --graph path/to/graph.json  # власне розташування графу
kb-core cluster-only ./my-project --resolution 1.5            # більше, менших спільнот
kb-core cluster-only ./my-project --exclude-hubs 99           # виключити вузли p99 ступеня з розбиття
```

---

## Дізнатися більше

- [Як це працює](../how-it-works.md) — пайплайн витягування, виявлення спільнот, оцінка впевненості, бенчмарки
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — опис модулів, як додати мову
- [Опціональні інтеграції](../docker-mcp-sqlite.md) — Docker MCP Toolkit + SQLite

---

## Побудовано на kb-core — Penpax

[**Penpax**](https://kb-core.com) — це завжди активний шар поверх kb-core, він застосовує той самий графовий підхід до всього робочого життя: зустрічей, історії браузера, email-ів, файлів і коду, постійно оновлюючись у фоновому режимі.

Створений для людей, чия робота розкидана по сотнях розмов і документів, які неможливо повністю відтворити. Без хмари, повністю на пристрої.

**Безкоштовна пробна версія незабаром.** [Приєднайтесь до списку очікування →](https://kb-core.com)

---

<details>
<summary>Участь у розробці</summary>

### Налаштування розробки

Клонуйте репо і встановіть у редагованому режимі:

```bash
git clone https://github.com/safishamsi/kb_core.git
cd kb-core
git checkout v8                        # гілка активної розробки

# Створіть віртуальне середовище (потрібен Python 3.10+):
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate

# Встановіть у редагованому режимі з усіма опціональними пакетами:
pip install -e ".[all]"
```

Перевірте редаговане встановлення:
```bash
kb-core --version
python -c "import kb_core; print(kb_core.__file__)"
```

### Запуск тестів

```bash
pip install pytest
pytest tests/ -q                       # запустити весь набір тестів
pytest tests/test_extract.py -q        # один модуль
pytest tests/ -q -k "python"           # фільтрація за назвою
```

> Примітка для macOS: набір тестів включає обидва файли `sample.f90` та `sample.F90`. Вони конфліктують на файлових системах HFS+ / APFS без урахування регістру. Запускайте на Linux або в Docker-контейнері, якщо потрібно тестувати обидва варіанти Fortran одночасно.

### Робочий процес з git

- Активна розробка відбувається в гілці `v8`.
- Стиль комітів: `fix: <опис>` / `feat: <опис>` / `docs: <опис>`
- Перед відкриттям PR запустіть `pytest tests/ -q` і переконайтесь, що він проходить.
- Додайте файл-фікстуру до `tests/fixtures/` і тести до `tests/test_languages.py` для будь-якого нового екстрактора мови.

### Що варто додати

Найкорисніший внесок — це **опрацьовані приклади**. Запустіть `/kb-core` на реальному корпусі, збережіть результат у `worked/{slug}/`, напишіть чесний `review.md` про те, що граф зробив правильно і неправильно, і відкрийте PR.

**Помилки витягування** — відкрийте issue з вхідним файлом, записом кешу (`kb-core-out/cache/`) і тим, що було пропущено або неправильно.

Дивіться [ARCHITECTURE.md](../../ARCHITECTURE.md) щодо відповідальностей модулів і того, як додати мову.

</details>
