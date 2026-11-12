param([switch]$StartServices, [switch]$VerifyOnly)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$requiredPaths = @(
    'desktop\app.py',
    'desktop\requirements.txt',
    'backend\app',
    'tools\python-runtime.json',
    'tools\project-env.ps1',
    'setup-python.ps1',
    'run-desktop.ps1',
    'build-desktop-launcher.ps1',
    'tools\DeepPandaLauncher.cs'
)

foreach ($relativePath in $requiredPaths) {
    $path = Join-Path $root $relativePath
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Kurulum yapisi eksik: $relativePath bulunamadi. Tum DeepPanda kaynak klasorlerini ayni kok dizinde tutun."
    }
}

. (Join-Path $root 'tools\project-env.ps1')

Write-Host 'DeepPanda proje yapisi dogrulandi.'
if ($VerifyOnly -and $StartServices) {
    throw '-VerifyOnly ile Docker servislerini baslatamazsiniz.'
}
if ($VerifyOnly) {
    & (Join-Path $root 'setup-python.ps1') -VerifyOnly
    if ($LASTEXITCODE -ne 0) { throw "Python ortami dogrulanamadi (cikis kodu $LASTEXITCODE)." }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    $probe = "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(name) for name in ('PySide6','httpx','mcp','jsonschema')) else 1)"
    & $python -c $probe
    if ($LASTEXITCODE -ne 0) { throw 'Masaustu bagimliliklari eksik. Kurulum icin install-desktop.cmd calistirin.' }
    $launcher = Join-Path $root 'dist\DeepPanda.exe'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw 'dist\DeepPanda.exe yok. Kurulum icin install-desktop.cmd calistirin.'
    }
    Write-Host "Python, Qt bagimliliklari ve launcher dogrulandi: $launcher"
    return
}

Write-Host 'SHA-256 ile sabitlenmis proje Python ortami hazirlaniyor...'
& (Join-Path $root 'setup-python.ps1')
if ($LASTEXITCODE -ne 0) { throw "Python ortami hazirlanamadi (cikis kodu $LASTEXITCODE)." }

$python = Join-Path $root '.venv\Scripts\python.exe'
$requirements = Join-Path $root 'desktop\requirements.txt'
$probe = "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(name) for name in ('PySide6','httpx','mcp','jsonschema')) else 1)"
& $python -c $probe
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Qt ve masaustu bagimliliklari proje .venv ortaminda kuruluyor...'
    & $python -m pip install --disable-pip-version-check --no-input -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "Masaustu bagimliliklari kurulurken pip $LASTEXITCODE koduyla sonlandi." }
}

Push-Location $root
try {
    & $python -c 'import desktop.app'
    if ($LASTEXITCODE -ne 0) { throw "Qt uygulama modulu yuklenemedi (cikis kodu $LASTEXITCODE)." }
}
finally {
    Pop-Location
}

$launcher = Join-Path $root 'dist\DeepPanda.exe'
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    Write-Host 'Qt launcher EXE olusturuluyor...'
    & (Join-Path $root 'build-desktop-launcher.ps1')
    if ($LASTEXITCODE -ne 0) { throw "Launcher olusturulamadi (cikis kodu $LASTEXITCODE)." }
}
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'Launcher derleme sonrasi beklenen dist\DeepPanda.exe dosyasi bulunamadi.'
}

if ($StartServices) {
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI bulunamadi. Docker Desktop kurup baslatin; sonra -StartServices ile tekrar deneyin.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root '.freellmapi.env') -PathType Leaf)) {
        throw '.freellmapi.env yok. Gizli ayarlari ornek dosyalarla otomatik olusturmadim; mevcut kurulum degerlerinizi ayarlayin.'
    }
    & docker.exe info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Engine calismiyor. Docker Desktop acildiktan sonra tekrar deneyin.' }
    Push-Location $root
    try {
        & docker.exe compose config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose yapilandirmasi gecersiz; servisler baslatilmadi.' }
        Write-Host 'Yerel API ve Docker servisleri hazirlaniyor; image indirme/build islemleri baslayabilir...'
        & docker.exe compose up -d --build --wait
        if ($LASTEXITCODE -ne 0) { throw "Docker servisleri hazir degil (cikis kodu $LASTEXITCODE)." }
    }
    finally {
        Pop-Location
    }
}

Write-Host ''
Write-Host 'DeepPanda Qt kurulumu tamamlandi.'
Write-Host "Baslatici: $launcher"
if (-not $StartServices) {
    Write-Host 'Qt istemcisi yerel API bekler. Docker servislerini de hazirlamak icin: .\install-desktop.ps1 -StartServices'
}
