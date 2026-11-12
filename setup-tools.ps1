param([switch]$VerifyOnly)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Get-Content (Join-Path $root 'tools\package.json') -Raw | ConvertFrom-Json
$version = $manifest.deeppanda.nodeVersion
$state = Join-Path $root '.tools'
$runtime = Join-Path $state ('runtime\node-v' + $version + '-win-x64')
$node = Join-Path $runtime 'node.exe'
$settings = @{
    TEMP = (Join-Path $state 'temp')
    TMP = (Join-Path $state 'temp')
    HOME = (Join-Path $state 'home')
    USERPROFILE = (Join-Path $state 'home')
    APPDATA = (Join-Path $state 'home\AppData\Roaming')
    LOCALAPPDATA = (Join-Path $state 'home\AppData\Local')
    NPM_CONFIG_CACHE = (Join-Path $state 'npm-cache')
    NPM_CONFIG_USERCONFIG = (Join-Path $root 'tools\.npmrc')
    NPM_CONFIG_GLOBALCONFIG = (Join-Path $state 'npm-globalrc')
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
    PUPPETEER_SKIP_DOWNLOAD = 'true'
    PATH = ($runtime + ';' + $env:PATH)
}
$previous = @{}
$lock = $null
foreach ($key in $settings.Keys) {
    $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
}

function Invoke-NodeBounded([string[]]$Arguments, [string]$Label, [int]$Seconds) {
    $stdout = Join-Path $state ('logs\' + $Label + '.stdout.log')
    $stderr = Join-Path $state ('logs\' + $Label + '.stderr.log')
    $quoted = @($Arguments | ForEach-Object { '"' + $_ + '"' })
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $node
    $start.Arguments = $quoted -join ' '
    $start.WorkingDirectory = $root
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    if (-not $process.Start()) { throw "$Label could not start." }
    $output = $process.StandardOutput.ReadToEndAsync()
    $errors = $process.StandardError.ReadToEndAsync()
    try {
        if (-not $process.WaitForExit($Seconds * 1000)) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
            throw "$Label timed out after $Seconds seconds; process stopped."
        }
        $process.WaitForExit()
        [IO.File]::WriteAllText($stdout, $output.GetAwaiter().GetResult())
        [IO.File]::WriteAllText($stderr, $errors.GetAwaiter().GetResult())
        Get-Content -LiteralPath $stdout,$stderr -Tail 60
        if ($process.ExitCode -ne 0) { throw "$Label failed with exit code $($process.ExitCode). See .tools\logs." }
    }
    finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        $process.Dispose()
    }
}

function Write-SetupFailure([string]$Message) {
    $report = @{
        checked_at = [DateTime]::UtcNow.ToString('o')
        scope = 'local MCP setup'
        installation_valid = $false
        results = @(@{ name = 'setup'; ok = $false; error = $Message })
    } | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText((Join-Path $state 'mcp-verification.json'), $report)
}

try {
    New-Item -ItemType Directory -Force -Path (Join-Path $state 'logs'),$env:TEMP,$env:HOME,$env:APPDATA,$env:LOCALAPPDATA | Out-Null
    $lock = [IO.File]::Open((Join-Path $state 'setup.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    Write-SetupFailure 'Setup is running or did not finish.'
    $hostConfig = Join-Path $state 'mcp-servers.json'
    if (Test-Path -LiteralPath $hostConfig) { Remove-Item -LiteralPath $hostConfig }
    if (-not (Test-Path -LiteralPath $node)) {
        if ($VerifyOnly) { throw 'Portable Node is not installed. Run setup-tools.ps1 without -VerifyOnly first.' }
        $archive = Join-Path $env:TEMP ('node-v' + $version + '-win-x64.zip')
        $url = 'https://nodejs.org/dist/v' + $version + '/node-v' + $version + '-win-x64.zip'
        & curl.exe --fail --location --connect-timeout 5 --max-time 120 --output $archive $url
        if ($LASTEXITCODE -ne 0) { throw "Node download failed (curl $LASTEXITCODE); nothing was installed." }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $manifest.deeppanda.nodeArchiveSha256) {
            throw 'Node archive checksum mismatch; refusing to extract it.'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $state 'runtime') -Force
    }
    if ((Get-FileHash -LiteralPath $node -Algorithm SHA256).Hash -ne $manifest.deeppanda.nodeExecutableSha256) {
        throw 'Portable Node checksum mismatch; refusing to execute it.'
    }
    if (-not $VerifyOnly) {
        Write-Host 'Installing pinned MCP packages on the project drive (no install scripts or browser downloads)...'
        Invoke-NodeBounded -Arguments @(
            (Join-Path $runtime 'node_modules\npm\bin\npm-cli.js'), 'install',
            '--prefix', (Join-Path $root 'tools'), '--ignore-scripts', '--no-audit', '--no-fund', '--engine-strict'
        ) -Label 'npm-install' -Seconds 900
    }
    Invoke-NodeBounded -Arguments @((Join-Path $root 'tools\verify-mcp.mjs')) -Label 'verify-mcp' -Seconds 180
    Invoke-NodeBounded -Arguments @((Join-Path $root 'tools\local-mcp.mjs')) -Label 'configure-mcp' -Seconds 30
    Write-Host 'Local MCP package, configuration and stdio discovery checks passed. Browser/native engines still need task-specific checks.'
}
catch {
    if ($null -ne $lock) {
        Write-SetupFailure $_.Exception.Message
        if (Test-Path -LiteralPath $hostConfig) { Remove-Item -LiteralPath $hostConfig }
    }
    throw
}
finally {
    if ($null -ne $lock) { $lock.Dispose() }
    foreach ($key in $settings.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
    }
}
