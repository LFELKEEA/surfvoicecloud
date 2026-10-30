@echo off
rem Started by SurfCore: NO pause here (hidden window would hang forever).
setlocal
cd /d "%~dp0"

powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue; if($c){exit 0}else{exit 1}"
if not errorlevel 1 exit /b 0

if not exist logs mkdir logs
start "" /b "%~dp0.venv\Scripts\pythonw.exe" -m voxd --config config.toml >> "%~dp0logs\voxd.out.log" 2>&1
exit /b 0
