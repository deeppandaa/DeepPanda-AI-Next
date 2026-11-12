$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
. (Join-Path $root 'tools\project-env.ps1')
$runtime = Get-Content (Join-Path $root 'tools\package.json') -Raw | ConvertFrom-Json
$nodeRoot = Join-Path $root ('.tools\runtime\node-v' + $runtime.deeppanda.nodeVersion + '-win-x64')
$node = Join-Path $nodeRoot 'node.exe'
if (-not (Test-Path -LiteralPath $node)) { throw 'Once setup-tools.ps1 ile proje Node ortamini kurun.' }
if ((Get-FileHash -LiteralPath $node -Algorithm SHA256).Hash.ToLowerInvariant() -ne $runtime.deeppanda.nodeExecutableSha256) {
    throw 'Proje Node SHA-256 dogrulamasi basarisiz; Cline kurulumu durduruldu.'
}
$target = Join-Path $root '.tools\cline'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'tools\cline\package.json'), (Join-Path $root 'tools\cline\package-lock.json') -Destination $target
& $node (Join-Path $nodeRoot 'node_modules\npm\bin\npm-cli.js') ci --prefix $target --ignore-scripts --no-audit --fund=false --registry https://registry.npmjs.org --cache (Join-Path $root '_tmp\npm-cache')
if ($LASTEXITCODE -ne 0) { throw 'Cline kurulumu basarisiz; mevcut hesaba dokunulmadi.' }
$actual = & (Join-Path $target 'node_modules\@cline\cli-windows-x64\bin\cline.exe') --version
if ($LASTEXITCODE -ne 0 -or $actual.Trim() -ne '3.0.74') { throw 'Cline surum/calisma kontrolu basarisiz.' }
Write-Host ('Cline ' + $actual.Trim() + ' proje icinde hazir. Hesap girisi Qt sohbetindeki Cline dugmesinden yapilir.')
