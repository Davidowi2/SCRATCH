@echo off
REM SCRATCH Bot - Windows Service Installation Script
REM This script installs both the bot and API as Windows services using NSSM

echo ============================================================
echo SCRATCH Bot - Service Installation
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

REM Get the current directory (SCRATCH root)
set "SCRATCH_DIR=%~dp0.."
cd /d "%SCRATCH_DIR%"

echo Current directory: %CD%
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.11 or higher
    pause
    exit /b 1
)

echo Python found: 
python --version
echo.

REM Check if NSSM is installed
nssm --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: NSSM is not installed or not in PATH
    echo.
    echo To install NSSM:
    echo 1. With Chocolatey: choco install nssm
    echo 2. Manual: Download from https://nssm.cc/download
    echo    Extract and add to PATH
    pause
    exit /b 1
)

echo NSSM found:
nssm --version
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
    echo.
)

REM Activate virtual environment and install dependencies
echo Installing bot dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo.

echo Installing API dependencies...
pip install -r api\requirements.txt
echo.

REM Get Python path from virtual environment
set "PYTHON_PATH=%CD%\venv\Scripts\python.exe"
set "BOT_SCRIPT=%CD%\scratch_bot.py"
set "API_SCRIPT=%CD%\api\app.py"

echo Python executable: %PYTHON_PATH%
echo Bot script: %BOT_SCRIPT%
echo API script: %API_SCRIPT%
echo.

REM Install bot service
echo ============================================================
echo Installing SCRATCH Bot Service...
echo ============================================================

nssm install ScratchBot "%PYTHON_PATH%" "%BOT_SCRIPT%"
nssm set ScratchBot AppDirectory "%CD%"
nssm set ScratchBot DisplayName "SCRATCH Trading Bot"
nssm set ScratchBot Description "TradeLocker 5-minute breakout scalping bot"
nssm set ScratchBot Start SERVICE_AUTO_START

REM Configure bot service logging
nssm set ScratchBot AppStdout "%CD%\logs\bot_stdout.log"
nssm set ScratchBot AppStderr "%CD%\logs\bot_stderr.log"
nssm set ScratchBot AppRotateFiles 1
nssm set ScratchBot AppRotateOnline 1
nssm set ScratchBot AppRotateBytes 10485760

REM Configure bot service restart policy
nssm set ScratchBot AppExit Default Restart
nssm set ScratchBot AppRestartDelay 5000
nssm set ScratchBot AppThrottle 10000

echo Bot service installed successfully!
echo.

REM Install API service
echo ============================================================
echo Installing SCRATCH API Service...
echo ============================================================

nssm install ScratchAPI "%PYTHON_PATH%" "%API_SCRIPT%"
nssm set ScratchAPI AppDirectory "%CD%"
nssm set ScratchAPI DisplayName "SCRATCH Monitoring API"
nssm set ScratchAPI Description "Flask API for SCRATCH bot monitoring dashboard"
nssm set ScratchAPI Start SERVICE_AUTO_START

REM Configure API service logging
nssm set ScratchAPI AppStdout "%CD%\logs\api_stdout.log"
nssm set ScratchAPI AppStderr "%CD%\logs\api_stderr.log"
nssm set ScratchAPI AppRotateFiles 1
nssm set ScratchAPI AppRotateOnline 1
nssm set ScratchAPI AppRotateBytes 10485760

REM Configure API service restart policy
nssm set ScratchAPI AppExit Default Restart
nssm set ScratchAPI AppRestartDelay 5000
nssm set ScratchAPI AppThrottle 10000

echo API service installed successfully!
echo.

echo ============================================================
echo Installation Complete!
echo ============================================================
echo.
echo Two services have been installed:
echo 1. ScratchBot - The trading bot
echo 2. ScratchAPI - The monitoring API
echo.
echo To start the services:
echo   net start ScratchBot
echo   net start ScratchAPI
echo.
echo To stop the services:
echo   net stop ScratchBot
echo   net stop ScratchAPI
echo.
echo To check service status:
echo   nssm status ScratchBot
echo   nssm status ScratchAPI
echo.
echo IMPORTANT: Make sure you have configured the .env file
echo with your TradeLocker credentials before starting!
echo.
pause
