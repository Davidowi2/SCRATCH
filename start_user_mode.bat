@echo off
title SCRATCH Bot Runner (Non-Admin User Mode)
echo ============================================================
echo Starting SCRATCH Bot and Monitoring API (User Mode)
echo ============================================================
echo.

cd /d "%~dp0"

if not exist ".env" (
    echo [ERROR] .env file not found! Copying from .env.example...
    copy .env.example .env
    echo Please configure your .env file first!
    pause
    exit /b 1
)

echo Starting Monitoring API in background...
start "SCRATCH Monitoring API" cmd /k "venv\Scripts\python.exe api\app.py"

timeout /t 2 >nul

echo Starting Trading Bot...
start "SCRATCH Trading Bot" cmd /k "venv\Scripts\python.exe scratch_bot.py"

echo.
echo ============================================================
echo Both services are now running in their own windows!
echo - API is running on http://127.0.0.1:5000
echo - To expose to Vercel without admin, run: npx localtunnel --port 5000
echo ============================================================
echo.
pause
