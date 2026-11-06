[CmdletBinding()]
param([switch]$DeleteData)

$ErrorActionPreference = "Stop"
$projectName = "deeppanda-offline"
$composeFile = Join-Path $PSScriptRoot "docker-compose.offline.yml"
$dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
if (-not $dockerCommand) { $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue }
if (-not $dockerCommand) { throw "Docker CLI was not found." }
$docker = $dockerCommand.Source

& $docker compose -p $projectName -f $composeFile down
if ($LASTEXITCODE -ne 0) { throw "Could not stop the DeepPanda Compose project." }

if ($DeleteData) {
    $confirmation = Read-Host "This permanently deletes Ollama models and all DeepPanda data. Type DELETE to continue"
    if ($confirmation -cne "DELETE") { throw "Data deletion cancelled. Containers are stopped; volumes were kept." }
    $volumes = @(
        "${projectName}_ollama_data",
        "${projectName}_ai_data",
        "${projectName}_qdrant_data",
        "${projectName}_redis_data"
    )
    & $docker volume rm @volumes
    if ($LASTEXITCODE -ne 0) { throw "One or more Docker volumes could not be removed." }
    Write-Output "Containers and data volumes removed."
} else {
    Write-Output "Containers removed; all models and data volumes were preserved."
}