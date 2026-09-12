@echo off
cd /d "%~dp0"
echo start-local.cmd now opens the formal v3 research service on port 8000.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0research.ps1" start
pause
