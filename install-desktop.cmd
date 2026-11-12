@echo off
setlocal
powershell.exe -NoLogo -NoProfile -File "%~dp0install-desktop.ps1" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo DeepPanda kurulumu basarisiz oldu. Yukaridaki hatayi inceleyin.
) else (
  echo.
  echo Kurulum basarili. DeepPanda.exe dosyasi depo kokundeki dist klasorundedir.
)
pause
exit /b %RESULT%
