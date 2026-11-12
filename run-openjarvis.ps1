$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$jarvis = Join-Path $root '.tools\venvs\openjarvis\Scripts\jarvis.exe'
if (-not (Test-Path -LiteralPath $jarvis -PathType Leaf)) {
    throw 'OpenJarvis is not installed. Use Python 3.10-3.13 to create .tools\venvs\openjarvis, then install tools\requirements-openjarvis.txt.'
}

$changes = @{
    OPENJARVIS_HOME = Join-Path $root '.tools\openjarvis-state'
    OPENJARVIS_CONFIG = Join-Path $root 'tools\openjarvis-local.toml'
    PYTHONNOUSERSITE = '1'
}
$previous = @{}
$credentialNames = @(Get-ChildItem Env: | Where-Object {
    $_.Name -match '(?i)(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)'
} | Select-Object -ExpandProperty Name)
$names = @($changes.Keys) + $credentialNames
foreach ($name in $names) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    foreach ($name in $credentialNames) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    foreach ($name in $changes.Keys) {
        [Environment]::SetEnvironmentVariable($name, $changes[$name], 'Process')
    }
    & $jarvis --quiet serve
    if ($LASTEXITCODE -ne 0) { throw "OpenJarvis exited with code $LASTEXITCODE." }
}
finally {
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
