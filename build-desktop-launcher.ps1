$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$source = Join-Path $root 'tools\DeepPandaLauncher.cs'
$outputDir = Join-Path $root 'dist'
$output = Join-Path $outputDir 'DeepPanda.exe'
$compilerCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) { throw 'Windows .NET Framework C# compiler was not found; no executable was built.' }
if (-not (Test-Path -LiteralPath $source)) { throw "Launcher source is missing: $source" }
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
& $compiler /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll "/out:$output" $source
if ($LASTEXITCODE -ne 0) { throw "Launcher compilation failed with exit code $LASTEXITCODE." }
Write-Output "Built launcher: $output"
