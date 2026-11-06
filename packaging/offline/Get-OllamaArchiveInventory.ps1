[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [Parameter(Mandatory = $true)][string]$TarPath
)

$ErrorActionPreference = "Stop"
$paths = @(
    & $TarPath -tf $ArchivePath | ForEach-Object {
        if ($_ -cmatch '^(\./)?(models/manifests/[^/]+/[^/]+/[^/]+/[^/]+)$') {
            $Matches[2]
        }
    }
)
if ($LASTEXITCODE -ne 0) {
    throw "Could not read the Ollama volume tar archive: $ArchivePath"
}
$paths | Sort-Object -CaseSensitive
