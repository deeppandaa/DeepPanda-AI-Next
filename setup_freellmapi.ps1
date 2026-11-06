$ErrorActionPreference = 'Stop'

$envPath = Join-Path $PSScriptRoot '.freellmapi.env'
$lines = @()

if (Test-Path $envPath) {
    $lines = @(Get-Content $envPath)
    $keyLine = $lines | Where-Object { $_ -match '^ENCRYPTION_KEY=' } | Select-Object -First 1
    if ($keyLine) {
        $key = $keyLine.Substring('ENCRYPTION_KEY='.Length)
        if ($key -notmatch '^[0-9a-fA-F]{64}$') {
            throw 'ENCRYPTION_KEY in .freellmapi.env must be 64 hexadecimal characters. The file was not changed.'
        }
        Write-Output 'FreeLLMAPI encryption key is already configured; keeping it unchanged.'
        exit 0
    }
}

$bytes = New-Object byte[] 32
$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $random.GetBytes($bytes)
} finally {
    $random.Dispose()
}
$key = -join ($bytes | ForEach-Object { $_.ToString('x2') })
$bytes = $null
$lines += "ENCRYPTION_KEY=$key"
[System.IO.File]::WriteAllText(
    $envPath,
    (($lines -join "`n") + "`n"),
    [System.Text.UTF8Encoding]::new($false)
)
$key = $null
Write-Output 'Generated the local FreeLLMAPI encryption key in the gitignored .freellmapi.env file.'