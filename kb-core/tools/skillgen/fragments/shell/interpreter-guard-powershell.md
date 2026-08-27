```powershell
if (-not (Test-Path kb-core-out\.kb_core_python)) {
    $KB_CORE_PYTHON = $null
    $kb-coreCmd = Get-Command kb-core -ErrorAction SilentlyContinue
    if ($kb-coreCmd) {
        # The interpreter that owns the kb-core entry point sits next to it
        # (<env>\Scripts\python.exe for uv tool, pipx, and venv installs).
        $py = Join-Path (Split-Path $kb-coreCmd.Source) "python.exe"
        if (Test-Path $py) { $KB_CORE_PYTHON = $py }
    }
    if (-not $KB_CORE_PYTHON) { $KB_CORE_PYTHON = "python" }
    New-Item -ItemType Directory -Force -Path kb-core-out | Out-Null
    & $KB_CORE_PYTHON -c "import sys; open('kb-core-out/.kb_core_python', 'w', encoding='utf-8').write(sys.executable)"
}
```
