@echo off
chcp 65001 >nul
setlocal
title InterviewSystem - Frontend (Vite)

REM 按需修改：如果 node/npm 不在 PATH 中，请把 Node.js 所在目录加入 PATH
set PROJECT_ROOT=%~dp0..

cd /d "%PROJECT_ROOT%\frontend"

if not exist "node_modules" (
  echo [INFO] node_modules not found, running npm install ...
  call npm install
)

echo ============================================================
echo   InterviewSystem Frontend
echo   URL : http://127.0.0.1:5173
echo ============================================================
echo.

call npm run dev

echo.
echo [Frontend stopped]
pause
