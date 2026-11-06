[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$bundleRoot = $PSScriptRoot
$projectName = "deeppanda-offline"
$composeFile = Join-Path $bundleRoot "docker-compose.offline.yml"
$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
if (-not $dockerCommand) { $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue }
if (-not $dockerCommand) { throw "Docker is not installed. Install Docker Desktop with WSL2/Linux containers, then run this installer again." }
$docker = $dockerCommand.Source

function Invoke-Docker {
    param([string[]]$Arguments)
    & $docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: docker $($Arguments -join ' ')" }
}

if (-not (Test-Path $composeFile) -or -not (Test-Path (Join-Path $bundleRoot "images.tar"))) {
    throw "This does not look like a complete DeepPanda offline bundle. Extract the entire folder first."
}
$serverPlatform = & $docker version --format "{{.Server.Os}}/{{.Server.Arch}}"
if ($LASTEXITCODE -ne 0) { throw "Docker Engine is not running. Start Docker Desktop and retry." }
if ($serverPlatform.Trim() -ne "linux/amd64") {
    throw "This bundle requires a linux/amd64 Docker Engine; detected $($serverPlatform.Trim())."
}
$composeVersionText = (& $docker compose version --short).Trim().TrimStart("v")
try { $composeVersion = [version]$composeVersionText } catch { throw "Docker Compose v2 is required." }
if ($composeVersion -lt [version]"2.20.0") { throw "Docker Compose 2.20 or newer is required; found $composeVersionText." }

$checksumsFile = Join-Path $bundleRoot "SHA256SUMS.txt"
if (-not (Test-Path $checksumsFile)) { throw "SHA256SUMS.txt is missing; the bundle is incomplete." }
foreach ($line in Get-Content -LiteralPath $checksumsFile) {
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw "Invalid checksum manifest line." }
    $expectedHash = $Matches[1]
    $relativePath = $Matches[2]
    if ([System.IO.Path]::IsPathRooted($relativePath) -or ($relativePath -split '[/\\]' -contains '..')) {
        throw "Unsafe path in checksum manifest."
    }
    $filePath = Join-Path $bundleRoot $relativePath
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) { throw "Bundle file is missing: $relativePath" }
    $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw "Checksum mismatch: $relativePath" }
}

$volumeKeys = @("ollama_data", "ai_data", "qdrant_data", "redis_data")
$existingVolumes = @(& $docker volume ls --format "{{.Name}}")
$targetVolumes = @($volumeKeys | ForEach-Object { "${projectName}_$_" })
$conflicts = @($targetVolumes | Where-Object { $existingVolumes -contains $_ })
if ($conflicts.Count -gt 0) {
    throw "Target Docker volumes already exist; refusing to overwrite: $($conflicts -join ', '). Back them up or remove them explicitly first."
}

Write-Output "Loading bundled Docker images..."
Invoke-Docker -Arguments @("load", "--input", (Join-Path $bundleRoot "images.tar"))

$bundleMount = $bundleRoot.Replace("\", "/")
foreach ($key in $volumeKeys) {
    $volumeName = "${projectName}_$key"
    $archiveName = "${key}.tar"
    $archivePath = "/bundle/volumes/$archiveName"
    Invoke-Docker -Arguments @("volume", "create", "--label", "com.deep-panda.bundle=offline", $volumeName)
    Invoke-Docker -Arguments @(
        "run", "--rm", "--network", "none", "--user", "0:0",
        "--mount", "type=volume,source=$volumeName,target=/restore",
        "--mount", "type=bind,source=$bundleMount,target=/bundle,readonly",
        "redis:7-alpine", "sh", "-c", "tar -C /restore -xf $archivePath"
    )
}

Write-Output "Starting DeepPanda without pulling or building images..."
Invoke-Docker -Arguments @(
    "compose", "-p", $projectName, "-f", $composeFile,
    "up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "300"
)

$shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "DeepPanda AI.lnk"
try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "http://127.0.0.1:8788/"
    $shortcut.Description = "Open the local DeepPanda AI application"
    $shortcut.Save()
    Write-Output "Desktop shortcut created: $shortcutPath"
} catch {
    Write-Warning "Could not create a desktop shortcut. Open http://127.0.0.1:8788/ manually."
}

Write-Output "Installation complete. DeepPanda AI: http://127.0.0.1:8788/"
Write-Output "PE Workbench: http://127.0.0.1:8788/pe-lab.html"
Write-Output "This installation is offline; images, models, and data were restored from the bundle."