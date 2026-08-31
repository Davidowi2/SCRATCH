@echo off
REM SCRATCH Bot - Start Services Script

echo ============================================================
echo SCRATCH Bot - Starting Services
echo ============================================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo Starting ScratchBot service...
net start ScratchBot
echo.

echo Starting ScratchAPI service...
net start ScratchAPI
echo.

echo ============================================================
echo Services Started!
echo ============================================================
echo.
echo Check status:
echo   nssm status ScratchBot
echo   nssm status ScratchAPI
echo.
echo View logs in the logs/ directory
echo.
pause
