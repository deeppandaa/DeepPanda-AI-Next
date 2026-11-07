[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path ([Environment]::GetFolderPath("Desktop")) "DeepPanda-Offline-Portable"),
    [switch]$PauseServices,
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeMain = Join-Path $repositoryRoot "docker-compose.yml"
$composeLocal = Join-Path $repositoryRoot "docker-compose.local-services.yml"
$offlineCompose = Join-Path $PSScriptRoot "docker-compose.offline.yml"
$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
if (-not $dockerCommand) { $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue }
if (-not $dockerCommand) { throw "Docker CLI is required. Install Docker Desktop with Linux containers first." }
$docker = $dockerCommand.Source

function Invoke-Docker {
    param([string[]]$Arguments)
    & $docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: docker $($Arguments -join ' ')" }
}

$images = @(
    "deeppanda-ai-next-api:latest",
    "deeppanda-ai-next-web:latest",
    "ollama/ollama:latest",
    "qdrant/qdrant:latest",
    "redis:7-alpine"
)
$volumes = @(
    @{ Source = "deeppanda-ai-next_ollama_data"; Archive = "ollama_data.tar" },
    @{ Source = "deeppanda-ai-next_ai_data"; Archive = "ai_data.tar" },
    @{ Source = "deeppanda-ai-next_qdrant_data"; Archive = "qdrant_data.tar" },
    @{ Source = "deeppanda-ai-next_redis_data"; Archive = "redis_data.tar" }
)

if (-not (Test-Path $composeMain) -or -not (Test-Path $composeLocal) -or -not (Test-Path $offlineCompose)) {
    throw "Compose configuration is incomplete. Run this script from the AI-Next packaging folder."
}
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
$missingVolumeArchives = @($volumes | Where-Object { -not (Test-Path (Join-Path $outputFullPath "volumes\$($_.Archive)")) })
if (Test-Path $outputFullPath) {
    if (-not $Resume) { throw "Output path already exists; choose a new empty path or use -Resume for a partial bundle: $outputFullPath" }
    if (-not (Test-Path (Join-Path $outputFullPath "images.tar")) -or -not (Test-Path (Join-Path $outputFullPath "workspace"))) {
        throw "Resume requires an existing images.tar and staged workspace: $outputFullPath"
    }
} elseif ($Resume) {
    throw "-Resume requires an existing partial bundle folder: $outputFullPath"
}
$driveName = [System.IO.Path]::GetPathRoot($outputFullPath).Substring(0, 1)
$outputDrive = Get-PSDrive -Name $driveName
$minimumFreeBytes = 70GB
if ($outputDrive.Free -lt $minimumFreeBytes) {
    throw "At least 70 GB free space is required on drive ${driveName}:; found $([math]::Round($outputDrive.Free / 1GB, 1)) GB."
}

$platforms = & $docker image inspect --format "{{.Os}}/{{.Architecture}}" @images
if ($LASTEXITCODE -ne 0) { throw "Build all five bundle images before packaging." }
$uniquePlatforms = @($platforms | Sort-Object -Unique)
if ($uniquePlatforms.Count -ne 1 -or $uniquePlatforms[0] -ne "linux/amd64") {
    throw "The offline Windows bundle expects linux/amd64 images; found: $($uniquePlatforms -join ', ')"
}

$existingVolumes = @(& $docker volume ls --format "{{.Name}}")
foreach ($volume in $volumes) {
    if ($existingVolumes -notcontains $volume.Source) {
        throw "Required source volume is missing: $($volume.Source)"
    }
}
$runningServices = @(& $docker compose -f $composeMain -f $composeLocal ps --services --status running)
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the current Compose services." }
if ($runningServices.Count -gt 0 -and $missingVolumeArchives.Count -gt 0 -and -not $PauseServices) {
    throw "Services are running. Re-run with -PauseServices to take a consistent snapshot; they will be restarted automatically."
}

New-Item -ItemType Directory -Path $outputFullPath -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $outputFullPath "volumes") -Force | Out-Null
if (-not $Resume) {
    New-Item -ItemType Directory -Path (Join-Path $outputFullPath "workspace\backend") | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $outputFullPath "workspace\frontend") | Out-Null
    Copy-Item $offlineCompose (Join-Path $outputFullPath "docker-compose.offline.yml")
    Copy-Item (Join-Path $PSScriptRoot "Install-OfflineBundle.ps1") $outputFullPath
    Copy-Item (Join-Path $PSScriptRoot "Remove-OfflineBundle.ps1") $outputFullPath
    Copy-Item (Join-Path $PSScriptRoot "README-OFFLINE.md") $outputFullPath
    Copy-Item (Join-Path $repositoryRoot "backend\app") (Join-Path $outputFullPath "workspace\backend") -Recurse
    Copy-Item (Join-Path $repositoryRoot "backend\tests") (Join-Path $outputFullPath "workspace\backend") -Recurse
    Copy-Item (Join-Path $repositoryRoot "backend\requirements.txt") (Join-Path $outputFullPath "workspace\backend")
    Copy-Item (Join-Path $repositoryRoot "backend\Dockerfile") (Join-Path $outputFullPath "workspace\backend")
    Copy-Item (Join-Path $repositoryRoot "frontend\*") (Join-Path $outputFullPath "workspace\frontend") -Recurse
    Write-Output "Workspace and offline Compose staged."

    Write-Output "Saving local Docker images..."
    Invoke-Docker -Arguments (@("save", "--output", (Join-Path $outputFullPath "images.tar")) + $images)
    Write-Output "Image archive complete."
} else {
    Write-Output "Resuming from existing images.tar and workspace."
    Copy-Item $offlineCompose (Join-Path $outputFullPath "docker-compose.offline.yml") -Force
    Copy-Item (Join-Path $PSScriptRoot "Install-OfflineBundle.ps1") $outputFullPath -Force
    Copy-Item (Join-Path $PSScriptRoot "Remove-OfflineBundle.ps1") $outputFullPath -Force
    Copy-Item (Join-Path $PSScriptRoot "README-OFFLINE.md") $outputFullPath -Force
}

Get-ChildItem (Join-Path $outputFullPath "workspace") -Directory -Filter "__pycache__" -Recurse |
    Remove-Item -Recurse -Force
Get-ChildItem (Join-Path $outputFullPath "workspace") -File -Filter "*.pyc" -Recurse |
    Remove-Item -Force

$servicesStopped = $false
try {
    if ($runningServices.Count -gt 0 -and $missingVolumeArchives.Count -gt 0) {
        $servicesStopped = $true
        Invoke-Docker -Arguments (@("compose", "-f", $composeMain, "-f", $composeLocal, "stop") + $runningServices)
    }

    $bundleMount = $outputFullPath.Replace("\", "/")
    foreach ($volume in $volumes) {
        Write-Output "Archiving Docker volume $($volume.Source)..."
        $archivePath = Join-Path $outputFullPath "volumes\$($volume.Archive)"
        if ($Resume -and (Test-Path $archivePath)) {
            Write-Output "Reusing existing snapshot: $($volume.Archive)"
            continue
        }
        Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
        $archiveInContainer = "/backup/volumes/$($volume.Archive)"
        $tarCommand = "tar -C /source -cf $archiveInContainer ."
        Invoke-Docker -Arguments @(
            "run", "--rm", "--network", "none", "--user", "0:0",
            "--mount", "type=volume,source=$($volume.Source),target=/source,readonly",
            "--mount", "type=bind,source=$bundleMount,target=/backup",
            "redis:7-alpine", "sh", "-c", $tarCommand
        )
        if (-not (Test-Path $archivePath)) { throw "Volume snapshot was not created: $archivePath" }
        Write-Output "Volume archive complete: $($volume.Archive)"
    }
}
finally {
    if ($servicesStopped) {
        Invoke-Docker -Arguments (@("compose", "-f", $composeMain, "-f", $composeLocal, "start") + $runningServices)
    }
}

$bundleManifest = @{
    created_utc = [DateTime]::UtcNow.ToString("o")
    platform = "linux/amd64"
    project = "deeppanda-offline"
    images = $images
    models = @("qwen2.5-coder:7b", "llama3.1:8b", "gemma:7b", "codellama:7b", "nomic-embed-text:latest")
    volumes = $volumes | ForEach-Object { @{ archive = "volumes/$($_.Archive)"; compose_key = $_.Archive.Replace("_data.tar", "_data") } }
} | ConvertTo-Json -Depth 6
Set-Content -Path (Join-Path $outputFullPath "bundle-manifest.json") -Value $bundleManifest -Encoding UTF8

$checksumFile = Join-Path $outputFullPath "SHA256SUMS.txt"
$checksumLines = foreach ($file in Get-ChildItem $outputFullPath -File -Recurse | Where-Object { $_.FullName -ne $checksumFile }) {
    $relative = $file.FullName.Substring($outputFullPath.Length + 1).Replace("\", "/")
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relative"
}
Set-Content -Path $checksumFile -Value $checksumLines -Encoding ASCII

$bundleSize = (Get-ChildItem $outputFullPath -File -Recurse | Measure-Object -Property Length -Sum).Sum
Write-Output "Offline bundle created: $outputFullPath"
Write-Output "Bundle size: $([math]::Round($bundleSize / 1GB, 1)) GB"
Write-Output "Copy this folder to the target Windows PC and run Install-OfflineBundle.ps1."