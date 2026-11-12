$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
. (Join-Path $root 'tools\project-env.ps1')
& (Join-Path $root 'setup-python.ps1') -VerifyOnly
$python = Join-Path $root '.tools\venvs\gpu-benchmark\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & (Join-Path $root '.venv\Scripts\python.exe') -I -m venv (Join-Path $root '.tools\venvs\gpu-benchmark')
    if ($LASTEXITCODE -ne 0) { throw 'GPU benchmark environment creation failed.' }
}
& $python -I -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('cupy') is None)"
if ($LASTEXITCODE -ne 0) {
    & $python -I -m pip install -r (Join-Path $root 'tools\requirements-gpu-benchmark.txt')
    if ($LASTEXITCODE -ne 0) { throw 'GPU benchmark dependencies could not be installed.' }
}
& $python -I -B (Join-Path $root 'tools\gpu-benchmark.py')
if ($LASTEXITCODE -ne 0) { throw 'GPU benchmark failed; no unlock/performance conclusion can be drawn.' }
