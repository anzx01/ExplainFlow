@echo off
chcp 65001 >nul
title ExplainFlow

echo ========================================
echo   ExplainFlow Dev Start
echo   API:    http://localhost:8010
echo   Web:    http://localhost:3010
echo   Render: http://localhost:3002
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-explainflow-processes.ps1"
timeout /t 1 /nobreak >nul

start "EF-API" cmd /k "cd /d %~dp0..\services\api && uv run uvicorn main:app --host :: --port 8010 --reload"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wait-for-api.ps1" -Port 8010 -TimeoutSeconds 45
if errorlevel 1 (
  echo API did not become ready. Check the EF-API window for the startup error.
  pause
  exit /b 1
)
start "EF-Web" cmd /k "cd /d %~dp0..\apps\web && node_modules\.bin\next dev --turbopack --port 3010"
start "EF-Render" cmd /k "cd /d %~dp0..\apps\render && node server.mjs"

echo API     http://localhost:8010
echo Web     http://localhost:3010
echo Render  http://localhost:3002
echo.
pause
