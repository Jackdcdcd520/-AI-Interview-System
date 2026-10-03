@echo off
chcp 65001 >nul
setlocal
title InterviewSystem - Backend + Frontend (LAN mode)

set PROJECT_ROOT=%~dp0..

echo Starting backend (LAN mode) in a new window ...
start "InterviewSystem-Backend-LAN" cmd /k "%PROJECT_ROOT%\scripts\start_backend_lan.bat"

echo Waiting for backend to boot (5s) ...
timeout /t 5 /nobreak >nul

echo Starting frontend (LAN mode) in a new window ...
start "InterviewSystem-Frontend-LAN" cmd /k "%PROJECT_ROOT%\scripts\start_frontend_lan.bat"

echo Detecting LAN IP (adapter with default gateway) ...
set LAN_IP=
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1).IPv4Address.IPAddress"') do set LAN_IP=%%i

if "%LAN_IP%"=="" (
  for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | Select-Object -First 1).IPAddress"') do set LAN_IP=%%i
)

echo.
echo ============================================================
echo   InterviewSystem started in LAN mode
echo.
echo   On this PC      :
echo     Frontend : http://127.0.0.1:5173
echo     Backend  : http://127.0.0.1:8000/docs
echo.
echo   On other devices (same Wi-Fi / LAN, open in browser) :
echo     Frontend : http://%LAN_IP%:5173
echo     Backend  : http://%LAN_IP%:8000/docs
echo.
echo   TROUBLESHOOTING (if phone cannot open the page) :
echo     1. Run scripts\firewall_allow_lan.bat ONCE (click YES on UAC)
echo     2. Make sure the phone is on the SAME Wi-Fi as this PC
echo     3. Enter the address manually starting with http://
echo        (not https://)
echo     4. If ports 5173/8000 were already in use by old windows,
echo        close those windows first, then run this script again
echo ============================================================
echo Two windows were opened. Close them to stop the services.
echo.
pause
