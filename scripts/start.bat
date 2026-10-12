@echo off
chcp 65001 >nul
title ExplainFlow

echo ========================================
echo   ExplainFlow Dev Start
echo   API:    http://localhost:8010
echo   Web:    http://localhost:3010
echo   Render: http://localhost:3002
echo   ComfyUI: http://127.0.0.1:8188
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-explainflow-processes.ps1"
timeout /t 1 /nobreak >nul

if not exist "D:\ck\ComfyUI\venv\Scripts\python.exe" (
  echo ComfyUI Python runtime not found: D:\ck\ComfyUI\venv\Scripts\python.exe
  pause
  exit /b 1
)
start "EF-ComfyUI" cmd /k "cd /d D:\ck\ComfyUI && venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --extra-model-paths-config D:\aiapp\ExplainFlow\config\comfyui\extra_model_paths.yaml"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wait-for-comfyui.ps1" -Port 8188 -TimeoutSeconds 90
if errorlevel 1 echo ComfyUI did not become ready within 90 seconds. API will still start; check the EF-ComfyUI window.

set "UV_EXE=%USERPROFILE%\AppData\Local\Programs\Python\Python311\Scripts\uv.exe"
if not exist "%UV_EXE%" set "UV_EXE=uv"
start "EF-API" /D "%~dp0..\services\api" "%UV_EXE%" run uvicorn main:app --host 127.0.0.1 --port 8010 --reload
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wait-for-api.ps1" -Port 8010 -TimeoutSeconds 45
if errorlevel 1 (
  echo API did not become ready. Check the EF-API window for the startup error.
  pause
  exit /b 1
)
start "EF-Web" cmd /k "cd /d %~dp0..\apps\web && node_modules\.bin\next dev --turbopack --port 3010"
start "EF-Render" cmd /k "cd /d %~dp0..\apps\render && set PYTHON_API_URL=http://127.0.0.1:8010 && node server.mjs"

echo API     http://localhost:8010
echo Web     http://localhost:3010
echo Render  http://localhost:3002
echo ComfyUI http://127.0.0.1:8188
echo.
pause
