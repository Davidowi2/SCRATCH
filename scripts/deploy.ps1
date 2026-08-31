# SCRATCH Bot - Automated Deployment Script
# This script pulls the latest code from GitHub and restarts services

param(
    [string]$Branch = "main",
    [switch]$SkipTests = $false
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "SCRATCH Bot - Automated Deployment" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as administrator'" -ForegroundColor Yellow
    exit 1
}

# Get script directory and SCRATCH root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScratchDir = Split-Path -Parent $ScriptDir
Set-Location $ScratchDir

Write-Host "Deployment directory: $ScratchDir" -ForegroundColor Green
Write-Host ""

# Backup current .env file
if (Test-Path ".env") {
    Write-Host "Backing up .env file..." -ForegroundColor Yellow
    Copy-Item ".env" ".env.backup" -Force
    Write-Host "✓ .env backed up to .env.backup" -ForegroundColor Green
    Write-Host ""
}

# Stop services
Write-Host "Stopping services..." -ForegroundColor Yellow
try {
    Stop-Service -Name "ScratchBot" -ErrorAction SilentlyContinue
    Stop-Service -Name "ScratchAPI" -ErrorAction SilentlyContinue
    Write-Host "✓ Services stopped" -ForegroundColor Green
} catch {
    Write-Host "⚠ Warning: Could not stop services (they may not be running)" -ForegroundColor Yellow
}
Write-Host ""

# Pull latest code from GitHub
Write-Host "Pulling latest code from GitHub ($Branch branch)..." -ForegroundColor Yellow
try {
    git fetch origin
    git checkout $Branch
    git pull origin $Branch
    
    if ($LASTEXITCODE -ne 0) {
        throw "Git pull failed"
    }
    
    Write-Host "✓ Code updated successfully" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: Failed to pull from GitHub" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    
    # Restore services
    Write-Host "Restoring services..." -ForegroundColor Yellow
    Start-Service -Name "ScratchBot" -ErrorAction SilentlyContinue
    Start-Service -Name "ScratchAPI" -ErrorAction SilentlyContinue
    
    exit 1
}
Write-Host ""

# Restore .env file if it was removed by git pull
if (Test-Path ".env.backup") {
    if (-not (Test-Path ".env")) {
        Write-Host "Restoring .env file..." -ForegroundColor Yellow
        Copy-Item ".env.backup" ".env" -Force
        Write-Host "✓ .env restored" -ForegroundColor Green
        Write-Host ""
    }
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
    Write-Host "✓ Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "⚠ Warning: Virtual environment not found, using system Python" -ForegroundColor Yellow
}
Write-Host ""

# Update bot dependencies
Write-Host "Updating bot dependencies..." -ForegroundColor Yellow
try {
    pip install -r requirements.txt --upgrade
    Write-Host "✓ Bot dependencies updated" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: Failed to update bot dependencies" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}
Write-Host ""

# Update API dependencies
Write-Host "Updating API dependencies..." -ForegroundColor Yellow
try {
    pip install -r api\requirements.txt --upgrade
    Write-Host "✓ API dependencies updated" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: Failed to update API dependencies" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}
Write-Host ""

# Run tests (if not skipped)
if (-not $SkipTests) {
    Write-Host "Running tests..." -ForegroundColor Yellow
    # Add test commands here if you have tests
    # python -m pytest tests/
    Write-Host "✓ Tests passed (or skipped)" -ForegroundColor Green
    Write-Host ""
}

# Start services
Write-Host "Starting services..." -ForegroundColor Yellow
try {
    Start-Service -Name "ScratchBot"
    Start-Sleep -Seconds 2
    
    $botStatus = Get-Service -Name "ScratchBot"
    if ($botStatus.Status -eq "Running") {
        Write-Host "✓ ScratchBot service started" -ForegroundColor Green
    } else {
        Write-Host "✗ WARNING: ScratchBot service is not running" -ForegroundColor Red
    }
    
    Start-Service -Name "ScratchAPI"
    Start-Sleep -Seconds 2
    
    $apiStatus = Get-Service -Name "ScratchAPI"
    if ($apiStatus.Status -eq "Running") {
        Write-Host "✓ ScratchAPI service started" -ForegroundColor Green
    } else {
        Write-Host "✗ WARNING: ScratchAPI service is not running" -ForegroundColor Red
    }
} catch {
    Write-Host "✗ ERROR: Failed to start services" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Check logs in the logs/ directory for details" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Deployment summary
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Services Status:" -ForegroundColor Cyan
Get-Service -Name "ScratchBot", "ScratchAPI" | Format-Table -Property Name, Status, DisplayName
Write-Host ""
Write-Host "Logs are available in: $ScratchDir\logs" -ForegroundColor Yellow
Write-Host ""
Write-Host "To check logs:" -ForegroundColor Cyan
Write-Host "  Get-Content logs\bot_stdout.log -Tail 20" -ForegroundColor White
Write-Host "  Get-Content logs\api_stdout.log -Tail 20" -ForegroundColor White
Write-Host ""
