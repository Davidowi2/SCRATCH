@echo off
REM SCRATCH Bot - Windows Service Uninstallation Script

echo ============================================================
echo SCRATCH Bot - Service Uninstallation
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

echo Stopping and removing services...
echo.

REM Stop and remove bot service
echo Stopping ScratchBot service...
net stop ScratchBot 2>nul
echo Removing ScratchBot service...
nssm remove ScratchBot confirm
echo.

REM Stop and remove API service
echo Stopping ScratchAPI service...
net stop ScratchAPI 2>nul
echo Removing ScratchAPI service...
nssm remove ScratchAPI confirm
echo.

echo ============================================================
echo Services Uninstalled Successfully!
echo ============================================================
echo.
pause
