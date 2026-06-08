@echo off
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install-desktop-shortcut.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
exit /b 0
