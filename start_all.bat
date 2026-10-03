@echo off
chcp 65001 >nul
setlocal
title InterviewSystem - Backend + Frontend

set PROJECT_ROOT=%~dp0..

echo Starting backend in a new window ...
start "InterviewSystem-Backend" cmd /k "%PROJECT_ROOT%\scripts\start_backend.bat"

echo Waiting for backend to boot (5s) ...
timeout /t 5 /nobreak >nul

echo Starting frontend in a new window ...
start "InterviewSystem-Frontend" cmd /k "%PROJECT_ROOT%\scripts\start_frontend.bat"

echo.
echo ============================================================
echo   Backend  : http://127.0.0.1:8000/docs
echo   Frontend : http://127.0.0.1:5173
echo ============================================================
echo Two windows were opened. Close them to stop the services.
echo.
pause
