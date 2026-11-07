# DeepPanda Kontrol Merkezi (Qt) - her şey F: sürücüsünde, proje klasöründeki .venv ile çalışır.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$temp = Join-Path $root '_tmp\temp'
New-Item -ItemType Directory -Force -Path $temp | Out-Null
$env:TEMP = $temp
$env:TMP = $temp
$env:PIP_CACHE_DIR = Join-Path $root '_tmp\pip-cache'

if (-not (Test-Path $python)) {
    Write-Host 'Sanal ortam yok; F: üzerinde oluşturuluyor...'
    py -3 -m venv (Join-Path $root '.venv')
}
& $python -c "import PySide6, httpx, mcp" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Masaüstü bağımlılıkları kuruluyor...'
    & $python -m pip install -r (Join-Path $root 'desktop\requirements.txt')
}
Set-Location $root
& $python -m desktop @args
