```bash
if [ ! -f kb-core-out/.kb_core_python ]; then
    KB_CORE_BIN=$(which kb-core 2>/dev/null)
    if [ -n "$KB_CORE_BIN" ]; then
        PYTHON=$(head -1 "$KB_CORE_BIN" | tr -d '#!')
        case "$PYTHON" in *[!a-zA-Z0-9/_.@-]*) PYTHON="python3" ;; esac
    else
        PYTHON="python3"
    fi
    mkdir -p kb-core-out
    "$PYTHON" -c "import sys; open('kb-core-out/.kb_core_python', 'w', encoding='utf-8').write(sys.executable)"
fi
```
