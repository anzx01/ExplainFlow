@echo off
chcp 65001 >nul
title ExplainFlow

echo ========================================
echo   ExplainFlow Dev Start
echo   API:    http://localhost:8000
echo   Web:    http://localhost:3000
echo   Render: http://localhost:3001
echo ========================================
echo.

for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3001 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq EF-API" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq EF-Web" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq EF-Render" /F >nul 2>&1
timeout /t 1 /nobreak >nul

start "EF-API" cmd /k "cd /d %~dp0..\services\api && uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2 /nobreak >nul
start "EF-Web" cmd /k "cd /d %~dp0..\apps\web && node_modules\.bin\next dev --turbopack"
start "EF-Render" cmd /k "set REMOTION_CHROME_HEADLESS_SHELL=C:\Users\DELL\AppData\Local\ms-playwright\chromium_headless_shell-1223\chrome-headless-shell-win64\chrome-headless-shell.exe && cd /d %~dp0..\apps\render && node server.mjs"

echo API     http://localhost:8000
echo Web     http://localhost:3000
echo Render  http://localhost:3001
echo.
pause
