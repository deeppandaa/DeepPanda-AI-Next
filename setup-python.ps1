param([switch]$VerifyOnly)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
. (Join-Path $root 'tools\project-env.ps1')
$manifest = Get-Content -LiteralPath (Join-Path $root 'tools\python-runtime.json') -Raw | ConvertFrom-Json
$runtime = Join-Path $root ('runtimes\python-' + $manifest.version)
$basePython = Join-Path $runtime 'tools\python.exe'
$python = Join-Path $root '.venv\Scripts\python.exe'
$lock = [IO.File]::Open((Join-Path $root '_tmp\python-setup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    if (-not (Test-Path -LiteralPath $basePython)) {
        if ($VerifyOnly) { throw 'Project Python is missing. Run setup-python.ps1 first.' }
        if (Test-Path -LiteralPath $runtime) { throw "Incomplete Python runtime: $runtime. Inspect it before retrying." }
        $downloadDir = Join-Path $root '_tmp\downloads'
        New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
        $archive = Join-Path $downloadDir ('python.' + $manifest.version + '.nupkg')
        if (-not (Test-Path -LiteralPath $archive)) {
            & curl.exe --fail --location --connect-timeout 10 --max-time 120 --output $archive $manifest.url
            if ($LASTEXITCODE -ne 0) { throw 'Python download failed; no environment was changed.' }
        }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $manifest.archiveSha256) {
            throw 'Python archive checksum mismatch; refusing to extract it.'
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($archive, $runtime)
    }
    if ((Get-FileHash -LiteralPath $basePython -Algorithm SHA256).Hash -ne $manifest.executableSha256) {
        throw 'Project Python executable checksum mismatch; refusing to execute it.'
    }
    & $basePython -I -c "import sys; assert sys.version.split()[0] == '$($manifest.version)', sys.version"
    if ($LASTEXITCODE -ne 0) { throw 'Project Python version verification failed.' }
    if (-not (Test-Path -LiteralPath $python)) {
        if ($VerifyOnly) { throw 'Project .venv is missing. Run setup-python.ps1 first.' }
        & $basePython -I -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Project virtual environment creation failed.' }
    }
    $base = & $python -I -c "import sys; print(sys.base_prefix)"
    if ($LASTEXITCODE -ne 0) { throw 'Existing .venv could not start; no environment was replaced.' }
    if ($base.Trim() -ne (Split-Path -Parent $basePython)) {
        if ($VerifyOnly) { throw "Virtual environment still uses an external Python: $base" }
        $version = & $python -I -c "import sys; print(sys.version.split()[0])"
        if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne $manifest.version) {
            throw 'Existing .venv version differs from the pinned runtime; recreate it explicitly, not in place.'
        }
        $backup = Join-Path $root ('_tmp\python-base-backup-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $backup | Out-Null
        Copy-Item -LiteralPath (Join-Path $root '.venv\pyvenv.cfg'),$python,(Join-Path $root '.venv\Scripts\pythonw.exe') -Destination $backup
        try {
            & $basePython -I -m venv --upgrade (Join-Path $root '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Rebinding .venv to project Python failed.' }
            & $python -I -c "import sys; from pathlib import Path; assert Path(sys.base_prefix) == Path(sys.argv[1])" (Split-Path -Parent $basePython)
            if ($LASTEXITCODE -ne 0) { throw 'Rebound .venv failed verification.' }
        }
        catch {
            Copy-Item -LiteralPath (Join-Path $backup 'pyvenv.cfg') -Destination (Join-Path $root '.venv\pyvenv.cfg') -Force
            Copy-Item -LiteralPath (Join-Path $backup 'python.exe'),(Join-Path $backup 'pythonw.exe') -Destination (Join-Path $root '.venv\Scripts') -Force
            throw
        }
        Write-Host "Previous Python binding saved in $backup. Existing packages were retained."
    }
    & $python -I -c "import ssl, sqlite3, venv, pip; print('Project Python OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Project Python standard library/pip verification failed.' }
}
finally {
    $lock.Dispose()
}
