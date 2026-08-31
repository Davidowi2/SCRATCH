# SCRATCH Bot - Windows Firewall Configuration Script
# This script configures Windows Firewall rules for the API

param(
    [int]$Port = 5000,
    [string[]]$AllowedIPs = @()  # Empty = allow all, or specify IPs like @("1.2.3.4", "5.6.7.8")
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "SCRATCH Bot - Firewall Configuration" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "Configuring firewall for API on port $Port..." -ForegroundColor Yellow
Write-Host ""

# Remove existing rule if it exists
$existingRule = Get-NetFirewallRule -DisplayName "SCRATCH Monitoring API" -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "Removing existing firewall rule..." -ForegroundColor Yellow
    Remove-NetFirewallRule -DisplayName "SCRATCH Monitoring API"
    Write-Host "✓ Existing rule removed" -ForegroundColor Green
    Write-Host ""
}

# Create new firewall rule
try {
    if ($AllowedIPs.Count -gt 0) {
        # Create rule with IP restriction
        Write-Host "Creating firewall rule with IP restrictions..." -ForegroundColor Yellow
        Write-Host "Allowed IPs: $($AllowedIPs -join ', ')" -ForegroundColor Cyan
        
        New-NetFirewallRule `
            -DisplayName "SCRATCH Monitoring API" `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $Port `
            -Action Allow `
            -RemoteAddress $AllowedIPs `
            -Profile Any `
            -Description "Allow SCRATCH Bot API access from specific IPs"
    } else {
        # Create rule without IP restriction (allow all)
        Write-Host "Creating firewall rule (allowing all IPs)..." -ForegroundColor Yellow
        Write-Host "⚠ WARNING: This will allow access from ANY IP address!" -ForegroundColor Red
        
        New-NetFirewallRule `
            -DisplayName "SCRATCH Monitoring API" `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $Port `
            -Action Allow `
            -Profile Any `
            -Description "Allow SCRATCH Bot API access"
    }
    
    Write-Host "✓ Firewall rule created successfully" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: Failed to create firewall rule" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Firewall Configuration Complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Current firewall rules:" -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName "SCRATCH Monitoring API" | Format-Table -Property DisplayName, Enabled, Direction, Action
Write-Host ""
Write-Host "Port $Port is now open for the SCRATCH API" -ForegroundColor Green

if ($AllowedIPs.Count -eq 0) {
    Write-Host ""
    Write-Host "SECURITY RECOMMENDATION:" -ForegroundColor Yellow
    Write-Host "Consider restricting access to specific IPs for better security:" -ForegroundColor Yellow
    Write-Host "  .\firewall_setup.ps1 -Port $Port -AllowedIPs @('your.home.ip', 'vercel.ip')" -ForegroundColor White
}

Write-Host ""
