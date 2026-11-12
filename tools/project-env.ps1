$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPaths = @{
    TEMP = '_tmp\temp'
    TMP = '_tmp\temp'
    TMPDIR = '_tmp\temp'
    PIP_CACHE_DIR = '_tmp\pip-cache'
    XDG_CACHE_HOME = '.tools\cache'
    HF_HOME = '.tools\cache\huggingface'
    TORCH_HOME = '.tools\cache\torch'
    CUPY_CACHE_DIR = '.tools\cache\cupy'
    CUDA_CACHE_PATH = '.tools\cache\cuda'
    PLAYWRIGHT_BROWSERS_PATH = '.tools\browsers'
}
foreach ($key in $projectPaths.Keys) {
    $target = Join-Path $projectRoot $projectPaths[$key]
    New-Item -ItemType Directory -Force -Path $target -ErrorAction Stop | Out-Null
    [Environment]::SetEnvironmentVariable($key, $target, 'Process')
}
$env:PYTHONNOUSERSITE = '1'
$pythonScripts = Join-Path $projectRoot '.venv\Scripts'
$pathEntries = @($env:PATH -split ';' | Where-Object { $_ -and $_ -ne $pythonScripts })
$env:PATH = (@($pythonScripts) + $pathEntries) -join ';'
