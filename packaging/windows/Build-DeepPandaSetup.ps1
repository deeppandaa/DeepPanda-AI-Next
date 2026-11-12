$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outputDir = Join-Path $root 'dist'
$launcher = Join-Path $outputDir 'DeepPanda.exe'
$compilerCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) { throw 'Windows .NET Framework C# compiler not found; setup was not built.' }

$requiredFiles = @(
    'desktop\app.py', 'desktop\requirements.txt', 'backend\app\main.py',
    'backend\Dockerfile', 'frontend\Dockerfile', 'docker-compose.yml',
    'docker-compose.local-services.yml', 'tools\python-runtime.json',
    'runtimes\python-3.12.10\tools\python.exe', 'run-desktop.ps1',
    'setup-python.ps1', 'install-desktop.ps1', 'build-desktop-launcher.ps1',
    'tools\DeepPandaLauncher.cs'
)
foreach ($relative in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relative))) {
        throw "Required project file is missing: $relative"
    }
}

& (Join-Path $root 'build-desktop-launcher.ps1')
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'The Qt launcher could not be built; setup was not packaged.'
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$stage = Join-Path $root ('_tmp\windows-setup-' + [Guid]::NewGuid().ToString('N'))
$payloadRoot = Join-Path $stage 'payload'
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

function Copy-Tree([string]$Source, [string]$Destination, [string[]]$ExcludedDirectories = @(), [string[]]$ExcludedFiles = @()) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $arguments = @($Source, $Destination, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    if ($ExcludedDirectories.Count -gt 0) { $arguments += @('/XD') + $ExcludedDirectories }
    if ($ExcludedFiles.Count -gt 0) { $arguments += @('/XF') + $ExcludedFiles }
    & robocopy.exe @arguments | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Could not stage files from $Source (robocopy $LASTEXITCODE)." }
}

function Copy-RootFile([string]$Relative) {
    $source = Join-Path $root $Relative
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        $destination = Join-Path $payloadRoot $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

try {
    Copy-Tree (Join-Path $root 'backend') (Join-Path $payloadRoot 'backend') @('tests', '__pycache__', '.pytest_cache') @('*.pyc')
    Copy-Tree (Join-Path $root 'desktop') (Join-Path $payloadRoot 'desktop') @('tests', '__pycache__', '.pytest_cache') @('*.pyc', 'settings.ini')
    Copy-Tree (Join-Path $root 'frontend') (Join-Path $payloadRoot 'frontend') @('node_modules', 'dist', '__pycache__') @('*.pyc')
    Copy-Tree (Join-Path $root 'tools') (Join-Path $payloadRoot 'tools') @('__pycache__', '.pytest_cache') @('*.pyc', '.npmrc')
    Copy-Tree (Join-Path $root 'runtimes\python-3.12.10') (Join-Path $payloadRoot 'runtimes\python-3.12.10')
    Copy-Tree $PSScriptRoot (Join-Path $payloadRoot 'packaging\windows') @('__pycache__') @('*.pyc', 'Build-DeepPandaSetup.ps1', 'DeepPandaSetup.cs')

    foreach ($relative in @(
        'run-desktop.ps1', 'setup-python.ps1', 'install-desktop.ps1',
        'build-desktop-launcher.ps1', 'setup_freellmapi.ps1', 'README.md',
        'requirements-local-ai.txt'
    )) { Copy-RootFile $relative }
    foreach ($file in Get-ChildItem -LiteralPath $root -File -Filter 'docker-compose*.yml') {
        Copy-RootFile $file.Name
    }
    foreach ($relative in @('.env.example', '.ai-next-cloud.env.example')) { Copy-RootFile $relative }
    New-Item -ItemType Directory -Force -Path `
        (Join-Path $payloadRoot 'data'), (Join-Path $payloadRoot 'models'),
        (Join-Path $payloadRoot 'projects'), (Join-Path $payloadRoot '.tools'),
        (Join-Path $payloadRoot 'dist') | Out-Null
    Copy-Item -LiteralPath $launcher -Destination (Join-Path $payloadRoot 'dist\DeepPanda.exe')

    $forbidden = [System.Collections.Generic.List[string]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $payloadRoot -File -Recurse -Force) {
        if (($file.Name -match '(^\.env|\.env$|settings\.ini$|^mcp-servers\.json$)') -and
            $file.Name -notmatch '\.example$') {
            $forbidden.Add($file.FullName)
        }
    }
    foreach ($directory in @((Join-Path $payloadRoot 'data'), (Join-Path $payloadRoot 'projects'))) {
        foreach ($file in Get-ChildItem -LiteralPath $directory -File -Recurse -Force) {
            $forbidden.Add($file.FullName)
        }
    }
    if ($forbidden.Count -gt 0) { throw "Private configuration or user data would enter the setup payload: $($forbidden -join ', ')" }

    $archive = Join-Path $stage 'DeepPandaPayload.zip'
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $payloadRoot, $archive, [System.IO.Compression.CompressionLevel]::Fastest, $false
    )
    $payloadHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $stage 'DeepPandaPayload.sha256') -Value $payloadHash -NoNewline -Encoding ASCII
    $bootstrap = Join-Path $stage 'Install-DeepPanda.ps1'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install-DeepPanda.ps1') -Destination $bootstrap

    $output = Join-Path $outputDir 'DeepPanda-Setup.exe'
    $source = Join-Path $PSScriptRoot 'DeepPandaSetup.cs'
    $compilerArgs = @(
        '/nologo', '/target:winexe', '/optimize+',
        '/reference:System.Windows.Forms.dll',
        '/reference:System.IO.Compression.dll',
        '/reference:System.IO.Compression.FileSystem.dll',
        "/resource:$archive,DeepPandaSetup.DeepPandaPayload.zip",
        "/resource:$(Join-Path $stage 'DeepPandaPayload.sha256'),DeepPandaSetup.DeepPandaPayload.sha256",
        "/resource:$bootstrap,DeepPandaSetup.Install-DeepPanda.ps1",
        "/out:$output",
        $source
    )
    & $compiler @compilerArgs
    if ($LASTEXITCODE -ne 0) { throw "Setup compiler failed with exit code $LASTEXITCODE." }
    Get-FileHash -LiteralPath $output -Algorithm SHA256 |
        ForEach-Object { "$($_.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($output))" } |
        Set-Content -LiteralPath (Join-Path $outputDir 'DeepPanda-Setup.sha256') -Encoding ASCII

    [pscustomobject]@{
        Setup = $output
        SetupBytes = (Get-Item -LiteralPath $output).Length
        PayloadBytes = (Get-Item -LiteralPath $archive).Length
        PayloadSha256 = $payloadHash
        SetupSha256 = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash
    }
}
finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
