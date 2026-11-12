$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms

$installRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
$expectedRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\DeepPanda'))
$marker = Join-Path $installRoot 'DeepPanda.install.json'
if (-not [string]::Equals($installRoot, $expectedRoot, [StringComparison]::OrdinalIgnoreCase) -or
    -not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    [System.Windows.Forms.MessageBox]::Show(
        'Beklenen DeepPanda kurulum dizini veya isaret dosyasi yok; kaldirma islemi durduruldu.',
        'DeepPanda Kaldir',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 2
}

$answer = [System.Windows.Forms.MessageBox]::Show(
    "DeepPanda uygulamasi ve kurulum klasorundeki yerel ayarlar/projeler kaldirilacak:`r`n$installRoot`r`n`r`nDocker named volume'larina dokunulmayacak. Devam edilsin mi?",
    'DeepPanda Kaldir',
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Warning,
    [System.Windows.Forms.MessageBoxDefaultButton]::Button2
)
if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { exit 0 }

$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepPanda'
if (Test-Path -LiteralPath $uninstallKey) {
    Remove-Item -LiteralPath $uninstallKey -Recurse -Force
}
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\DeepPanda'
if (Test-Path -LiteralPath $startMenu) {
    Remove-Item -LiteralPath $startMenu -Recurse -Force
}

$quotedRoot = $installRoot.Replace("'", "''")
$cleanupScript = Join-Path $env:TEMP ('DeepPanda-uninstall-' + [Guid]::NewGuid().ToString('N') + '.ps1')
@"
Start-Sleep -Seconds 5
Remove-Item -LiteralPath '$quotedRoot' -Recurse -Force
Remove-Item -LiteralPath `$PSCommandPath -Force
"@ | Set-Content -LiteralPath $cleanupScript -Encoding UTF8
$powershell = Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
Start-Process -FilePath $powershell -ArgumentList @('-NoLogo', '-NoProfile', '-File', "`"$cleanupScript`"") -WindowStyle Hidden
[System.Windows.Forms.MessageBox]::Show(
    'DeepPanda kaldirma islemi baslatildi. Docker named volume ve verileri etkilenmedi.',
    'DeepPanda Kaldir',
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
