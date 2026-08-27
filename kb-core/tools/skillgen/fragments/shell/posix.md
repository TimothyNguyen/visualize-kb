```bash
# Detect the correct Python interpreter (handles uv tool, pipx, venv, system installs)
PYTHON=""
KB_CORE_BIN=$(which kb-core 2>/dev/null)
# 1. uv tool installs — most reliable on modern Mac/Linux
if [ -z "$PYTHON" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run --from kb-core python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
fi
# 2. Read shebang from kb_core binary (pipx and direct pip installs)
if [ -z "$PYTHON" ] && [ -n "$KB_CORE_BIN" ]; then
    _SHEBANG=$(head -1 "$KB_CORE_BIN" | tr -d '#!')
    case "$_SHEBANG" in
        *[!a-zA-Z0-9/_.@-]*) ;;
        *) "$_SHEBANG" -c "import kb_core" 2>/dev/null && PYTHON="$_SHEBANG" ;;
    esac
fi
# 3. Fall back to python3
if [ -z "$PYTHON" ]; then PYTHON="python3"; fi
if ! "$PYTHON" -c "import kb_core" 2>/dev/null; then
    if command -v uv >/dev/null 2>&1; then
        uv tool install --upgrade kb-core -q 2>&1 | tail -3
        _UV_PY=$(uv tool run --from kb-core python -c "import sys; print(sys.executable)" 2>/dev/null)
        if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
    else
        "$PYTHON" -m pip install kb-core -q 2>/dev/null \
          || "$PYTHON" -m pip install kb-core -q --break-system-packages 2>&1 | tail -3
    fi
fi
# Write interpreter path for all subsequent steps (persists across invocations)
mkdir -p kb-core-out
"$PYTHON" -c "import sys; open('kb-core-out/.kb_core_python', 'w', encoding='utf-8').write(sys.executable)"
# Save scan root so `kb-core update` (no args) knows where to look next time
echo "$(cd INPUT_PATH && pwd)" > kb-core-out/.kb_core_root
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent bash block, replace `python3` with `$(cat kb-core-out/.kb_core_python)` to use the correct interpreter.**
