param([Parameter(Mandatory = $true)][string]$PackageRoot, [switch]$Quiet)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.Windows.Forms

function Show-Error([string]$Message) {
    [System.Windows.Forms.MessageBox]::Show(
        $Message, 'DeepPanda Kurulumu',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

try {
    $packageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
    $archive = Join-Path $packageRoot 'DeepPandaPayload.zip'
    $hashFile = Join-Path $packageRoot 'DeepPandaPayload.sha256'
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf) -or
        -not (Test-Path -LiteralPath $hashFile -PathType Leaf)) {
        throw 'Kurulum paketi eksik veya gecersiz.'
    }
    $expectedHash = (Get-Content -LiteralPath $hashFile -Raw).Trim().ToLowerInvariant()
    if ($expectedHash -notmatch '^[a-f0-9]{64}$') { throw 'Paket SHA-256 manifesti gecersiz.' }
    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw 'Kurulum arsivinin SHA-256 degeri eslesmiyor.' }

    $localPrograms = Join-Path $env:LOCALAPPDATA 'Programs'
    $installRoot = [System.IO.Path]::GetFullPath((Join-Path $localPrograms 'DeepPanda'))
    $expectedRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\DeepPanda'))
    if (-not [string]::Equals($installRoot, $expectedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Kurulum hedefi guvenli beklenen dizinle eslesmiyor.'
    }
    $marker = Join-Path $installRoot 'DeepPanda.install.json'
    $progressMarker = Join-Path $installRoot '.DeepPanda.installing'
    if ((Test-Path -LiteralPath $installRoot) -and
        -not (Test-Path -LiteralPath $marker -PathType Leaf) -and
        -not (Test-Path -LiteralPath $progressMarker -PathType Leaf)) {
        throw "Hedef klasor zaten var ve DeepPanda kurulumu olarak isaretli degil; uzerine yazmiyorum: $installRoot"
    }

    $archiveHandle = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $required = [long](($archiveHandle.Entries | Measure-Object -Property Length -Sum).Sum)
    }
    finally {
        $archiveHandle.Dispose()
    }
    $root = [System.IO.Path]::GetPathRoot($installRoot).Substring(0, 1)
    $drive = Get-PSDrive -Name $root -ErrorAction Stop
    $minimumFree = $required + 1GB
    if ($drive.Free -lt $minimumFree) {
        throw ('Kurulum icin en az {0:N1} GiB bos alan gerekli; mevcut: {1:N1} GiB.' -f
            ($minimumFree / 1GB), ($drive.Free / 1GB))
    }

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    Set-Content -LiteralPath $progressMarker -Value $actualHash -Encoding ASCII
    Expand-Archive -LiteralPath $archive -DestinationPath $installRoot -Force
    foreach ($requiredPath in @(
        'desktop\app.py', 'backend\app', 'docker-compose.yml',
        'run-desktop.ps1', 'install-desktop.ps1', 'dist\DeepPanda.exe'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $installRoot $requiredPath))) {
            throw "Paket dosyasi eksik: $requiredPath"
        }
    }

    & (Join-Path $installRoot 'install-desktop.ps1')
    if ($LASTEXITCODE -ne 0) { throw "Python/Qt ortami hazirlanamadi (cikis kodu $LASTEXITCODE)." }

    $manifest = [ordered]@{
        product = 'DeepPanda'
        version = '1.0.0'
        installed_utc = [DateTime]::UtcNow.ToString('o')
        payload_sha256 = $actualHash
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8

    $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\DeepPanda'
    New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $startMenu 'DeepPanda.lnk'))
    $shortcut.TargetPath = Join-Path $installRoot 'dist\DeepPanda.exe'
    $shortcut.WorkingDirectory = $installRoot
    $shortcut.Description = 'DeepPanda Qt Kontrol Merkezi'
    $shortcut.Save()

    $uninstaller = Join-Path $installRoot 'packaging\windows\Uninstall-DeepPanda.ps1'
    $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepPanda'
    New-Item -Path $uninstallKey -Force | Out-Null
    $properties = @{
        DisplayName = 'DeepPanda'
        DisplayVersion = '1.0.0'
        Publisher = 'DeepPanda'
        InstallLocation = $installRoot
        DisplayIcon = (Join-Path $installRoot 'dist\DeepPanda.exe')
        UninstallString = ('powershell.exe -NoLogo -NoProfile -File "{0}"' -f $uninstaller)
        NoModify = 1
        NoRepair = 1
        EstimatedSize = [int][Math]::Min([Math]::Ceiling($required / 1KB), [int]::MaxValue)
    }
    foreach ($entry in $properties.GetEnumerator()) {
        $propertyType = 'String'
        if ($entry.Value -is [int]) { $propertyType = 'DWord' }
        New-ItemProperty -Path $uninstallKey -Name $entry.Key -Value $entry.Value -PropertyType (
            $propertyType
        ) -Force | Out-Null
    }
    Remove-Item -LiteralPath $progressMarker -Force

    $message = "DeepPanda kuruldu.`r`n`r`nBaslat menusu: DeepPanda`r`nKurulum konumu: $installRoot`r`n`r`nQt istemcisi yerel API'ye baglanir. Docker/API servisleri bu kurulumda otomatik baslatilmadi."
    if ($Quiet) {
        Write-Output $message
    }
    else {
        [System.Windows.Forms.MessageBox]::Show(
            $message,
            'DeepPanda Kurulumu',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }
}
catch {
    $message = "Kurulum tamamlanamadi. Hata: " + $_.Exception.Message + "`r`n`r`nKismi dosyalar, duzeltmeden sonra kurulumu tekrar denemek icin birakilmis olabilir."
    if ($Quiet) { Write-Error $message } else { Show-Error $message }
    exit 1
}
