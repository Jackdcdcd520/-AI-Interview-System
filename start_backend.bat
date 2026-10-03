@echo off
chcp 65001 >nul
setlocal
title InterviewSystem - Backend (FastAPI)

REM 按需修改：如果你的 python 不在 PATH 中，请把下面改为 python.exe 的完整路径
set PY=python

set PROJECT_ROOT=%~dp0..

cd /d "%PROJECT_ROOT%"
echo ============================================================
echo   InterviewSystem Backend
echo   Root : %PROJECT_ROOT%
echo   URL  : http://127.0.0.1:8000/docs
echo ============================================================
echo.

"%PY%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

echo.
echo [Backend stopped]
pause
