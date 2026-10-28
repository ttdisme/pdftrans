@echo off

chcp 65001 >nul

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File ".\创建桌面快捷方式.ps1"

if errorlevel 1 (

  echo.

  echo Create failed. Or manually: right click PDFTrans.exe - Send to - Desktop shortcut

)

echo.

pause

