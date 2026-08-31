@echo off
REM SCRATCH Bot - Stop Services Script

echo ============================================================
echo SCRATCH Bot - Stopping Services
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

echo Stopping ScratchBot service...
net stop ScratchBot
echo.

echo Stopping ScratchAPI service...
net stop ScratchAPI
echo.

echo ============================================================
echo Services Stopped!
echo ============================================================
echo.
pause
