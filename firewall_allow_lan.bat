@echo off
chcp 65001 >nul
setlocal
title InterviewSystem - Firewall Allow (one-time)

REM ---- self elevate to administrator ----
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privilege, please click YES in the UAC popup ...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo Adding firewall rules ...

netsh advfirewall firewall delete rule name="InterviewSystem-Frontend-5173" >nul 2>&1
netsh advfirewall firewall add rule name="InterviewSystem-Frontend-5173" dir=in action=allow protocol=TCP localport=5173

netsh advfirewall firewall delete rule name="InterviewSystem-Backend-8000" >nul 2>&1
netsh advfirewall firewall add rule name="InterviewSystem-Backend-8000" dir=in action=allow protocol=TCP localport=8000

echo.
echo ============================================================
echo   Done. Inbound TCP 5173 and 8000 are now allowed.
echo   You only need to run this ONCE.
echo ============================================================
pause
