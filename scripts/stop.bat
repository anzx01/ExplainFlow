@echo off
chcp 65001 >nul
taskkill /FI "WINDOWTITLE eq EF-API" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq EF-Web" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq EF-Render" /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3001 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
echo Stopped.
