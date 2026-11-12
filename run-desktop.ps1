# DeepPanda Kontrol Merkezi (Qt) - proje içindeki Python ve .venv ile çalışır.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
. (Join-Path $root 'tools\project-env.ps1')
& (Join-Path $root 'setup-python.ps1')
& $python -I -c "import importlib.util, sys; sys.exit(not all(importlib.util.find_spec(name) for name in ('PySide6', 'httpx', 'mcp', 'jsonschema')))"
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Masaüstü bağımlılıkları kuruluyor...'
    & $python -m pip install -r (Join-Path $root 'desktop\requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Masaüstü bağımlılıkları kurulamadı; uygulama başlatılmadı.' }
}
Set-Location $root
& $python -m desktop @args
