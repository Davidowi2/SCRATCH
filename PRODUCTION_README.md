# SCRATCH Production Deployment Guide

Complete guide for deploying SCRATCH trading bot to a Windows VPS with monitoring, auto-start, and CI/CD.

---

## 📋 Table of Contents

1. [System Requirements](#system-requirements)
2. [Windows VPS Setup](#windows-vps-setup)
3. [Bot Installation](#bot-installation)
4. [API Installation](#api-installation)
5. [Dashboard Deployment](#dashboard-deployment)
6. [Windows Services Setup](#windows-services-setup)
7. [Firewall Configuration](#firewall-configuration)
8. [CI/CD Setup](#cicd-setup)
9. [Monitoring & Maintenance](#monitoring--maintenance)
10. [Troubleshooting](#troubleshooting)

---

## System Requirements

### Windows VPS
- **OS**: Windows Server 2022 or Windows 10/11
- **CPU**: 2+ cores recommended
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 20GB minimum
- **Network**: Stable internet connection with low latency

### Software
- **Python**: 3.11 or higher
- **Git**: Latest version
- **NSSM**: Non-Sucking Service Manager
- **PowerShell**: 5.1 or higher (included in Windows)

### Accounts
- **TradeLocker**: Demo or live account with API access
- **GitHub**: For code repository and CI/CD
- **Vercel**: For dashboard hosting (free tier works)

---

## Windows VPS Setup

### Step 1: Initial Windows Configuration

1. **Enable Remote Desktop** (if not already enabled):
   - Open System Properties → Remote tab
   - Enable "Allow remote connections to this computer"

2. **Install Windows Updates**:
   ```powershell
   # Open PowerShell as Administrator
   Install-Module PSWindowsUpdate -Force
   Get-WindowsUpdate
   Install-WindowsUpdate -AcceptAll -AutoReboot
   ```

3. **Configure Windows Defender** (optional):
   - Add exclusions for Python and SCRATCH directory to improve performance

### Step 2: Install Python

1. **Download Python 3.11+**:
   - Visit: https://www.python.org/downloads/windows/
   - Download "Windows installer (64-bit)"

2. **Install Python**:
   - ✅ Check "Add Python to PATH"
   - Choose "Install Now"

3. **Verify installation**:
   ```powershell
   python --version
   pip --version
   ```

### Step 3: Install Git

1. **Download Git**:
   - Visit: https://git-scm.com/download/win
   - Download the 64-bit installer

2. **Install Git**:
   - Use default settings
   - Choose "Git from the command line and also from 3rd-party software"

3. **Verify installation**:
   ```powershell
   git --version
   ```

### Step 4: Install NSSM (Service Manager)

**Option A: Using Chocolatey** (recommended):
```powershell
# Install Chocolatey first (if not installed)
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install NSSM
choco install nssm -y
```

**Option B: Manual Installation**:
1. Download from: https://nssm.cc/download
2. Extract to `C:\nssm`
3. Add to PATH:
   ```powershell
   $env:Path += ";C:\nssm\win64"
   [Environment]::SetEnvironmentVariable("Path", $env:Path, [EnvironmentVariableTarget]::Machine)
   ```

4. **Verify installation**:
   ```powershell
   nssm --version
   ```

---

## Bot Installation

### Step 1: Clone Repository

```powershell
# Navigate to C:\ drive
cd C:\

# Clone your SCRATCH repository
git clone https://github.com/your-username/SCRATCH.git
cd SCRATCH
```

### Step 2: Create Virtual Environment

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# If you get execution policy error, run:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Step 3: Install Dependencies

```powershell
# Install bot dependencies
pip install -r requirements.txt

# Install API dependencies
pip install -r api\requirements.txt
```

### Step 4: Configure Environment Variables

1. **Copy example file**:
   ```powershell
   copy .env.example .env
   ```

2. **Edit `.env` file**:
   ```powershell
   notepad .env
   ```

3. **Fill in your credentials**:
   ```env
   TL_USERNAME=your_tradelocker_username
   TL_PASSWORD=your_tradelocker_password
   TL_SERVER=https://demo.tradelocker.com
   
   API_PORT=5000
   API_KEY=generate-a-strong-random-key-here
   ```

4. **Generate a strong API key**:
   ```powershell
   # Generate random API key
   -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
   ```

### Step 5: Test Bot Manually

```powershell
# Test the bot (Ctrl+C to stop)
python scratch_bot.py
```

If the bot connects successfully and starts monitoring, you're ready to proceed!

---

## API Installation

The API is already in the `api/` folder. No additional installation needed.

### Test API Manually

```powershell
# From SCRATCH root directory
python api\app.py
```

Open browser to `http://localhost:5000` - you should see API info.

---

## Windows Services Setup

### Step 1: Install Services

```powershell
# Navigate to SCRATCH directory
cd C:\SCRATCH

# Run installation script as Administrator
.\scripts\install_services.bat
```

This script will:
- ✅ Create virtual environment
- ✅ Install all dependencies
- ✅ Register two Windows services:
  - **ScratchBot**: The trading bot
  - **ScratchAPI**: The monitoring API
- ✅ Configure auto-start on boot
- ✅ Configure automatic restart on crash

### Step 2: Verify Services

```powershell
# Check service status
nssm status ScratchBot
nssm status ScratchAPI

# Or use Windows services manager
services.msc
```

### Step 3: Start Services

```powershell
# Option A: Using batch script
.\scripts\start_services.bat

# Option B: Using PowerShell
Start-Service ScratchBot
Start-Service ScratchAPI

# Option C: Using net command
net start ScratchBot
net start ScratchAPI
```

### Step 4: Check Logs

```powershell
# View bot logs
Get-Content logs\bot_stdout.log -Tail 20

# View API logs
Get-Content logs\api_stdout.log -Tail 20

# Follow logs in real-time
Get-Content logs\bot_stdout.log -Wait
```

---

## Firewall Configuration

### Step 1: Open API Port

```powershell
# Open port 5000 for all IPs (less secure)
.\scripts\firewall_setup.ps1 -Port 5000

# Or restrict to specific IPs (more secure)
.\scripts\firewall_setup.ps1 -Port 5000 -AllowedIPs @("your.home.ip", "76.76.21.21")
```

### Step 2: Get Vercel IP Ranges

Vercel uses dynamic IPs. For production, consider:

**Option A: Allow all IPs and use API key authentication** (recommended)
- API key in headers provides security
- Firewall allows any IP

**Option B: Use Vercel's IP ranges**
- Check: https://vercel.com/docs/security/security-checklist#ip-addresses
- Update firewall script with their ranges

### Step 3: Test Firewall

From another computer:
```bash
curl http://your-vps-ip:5000/health
```

Should return: `{"status": "healthy", ...}`

---

## Dashboard Deployment

### Step 1: Prepare Dashboard for Vercel

The dashboard is already configured in `dashboard/` folder.

### Step 2: Push to GitHub

```powershell
# From SCRATCH root
git add .
git commit -m "Initial SCRATCH deployment"
git push origin main
```

### Step 3: Deploy to Vercel

1. **Go to Vercel**: https://vercel.com
2. **Import Project**:
   - Click "Add New" → "Project"
   - Import your GitHub repository
   - Select `dashboard` as root directory
3. **Configure Environment Variables**:
   - Click "Environment Variables"
   - Add:
     - `API_URL` = `http://your-vps-ip:5000`
     - `API_KEY` = `your-api-key-from-env-file`
4. **Deploy**:
   - Click "Deploy"
   - Wait for build to complete
   - Get your dashboard URL: `https://your-project.vercel.app`

### Step 4: Test Dashboard

1. Open your Vercel URL
2. You should see:
   - Bot status (running/stopped)
   - Current position (if any)
   - Performance metrics
   - Recent trades

Dashboard auto-refreshes every 5 seconds!

---

## CI/CD Setup

### Step 1: Enable SSH on Windows VPS

```powershell
# Install OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Start SSH service
Start-Service sshd

# Set to start automatically
Set-Service -Name sshd -StartupType 'Automatic'

# Configure firewall for SSH
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

### Step 2: Configure GitHub Secrets

1. **Go to GitHub Repository**:
   - Settings → Secrets and variables → Actions
   - Click "New repository secret"

2. **Add these secrets**:
   - `VPS_IP`: Your VPS IP address (e.g., `123.45.67.89`)
   - `VPS_USERNAME`: Administrator username
   - `VPS_PASSWORD`: Administrator password

### Step 3: Test Deployment

```powershell
# Make a small change to trigger CI/CD
echo "# Test change" >> README.md
git add README.md
git commit -m "Test CI/CD"
git push origin main
```

GitHub Actions will:
1. Detect the push to `main`
2. Connect to your VPS via SSH
3. Run `deploy.ps1` script
4. Pull latest code
5. Update dependencies
6. Restart services

Check the Actions tab on GitHub to see progress!

---

## Monitoring & Maintenance

### Daily Checks

1. **Check Bot Status** (via dashboard):
   - Is bot running?
   - Any open positions?
   - Win rate trending?

2. **Check Logs**:
   ```powershell
   # Last 50 lines of bot log
   Get-Content C:\SCRATCH\logs\bot_stdout.log -Tail 50
   
   # Check for errors
   Get-Content C:\SCRATCH\logs\bot_stderr.log -Tail 50
   ```

3. **Check Services**:
   ```powershell
   Get-Service ScratchBot, ScratchAPI | Format-Table -Property Name, Status, StartType
   ```

### Weekly Maintenance

1. **Review Performance**:
   - Export trade data from database
   - Analyze win rate by time of day
   - Check which exit reasons are most common

2. **Check Disk Space**:
   ```powershell
   Get-PSDrive C | Select-Object Used, Free
   ```

3. **Rotate Logs** (if needed):
   ```powershell
   # Archive old logs
   Compress-Archive -Path C:\SCRATCH\logs\*.log -DestinationPath C:\SCRATCH\logs\archive_$(Get-Date -Format 'yyyy-MM-dd').zip
   ```

### Monthly Tasks

1. **Update Dependencies**:
   ```powershell
   cd C:\SCRATCH
   .\venv\Scripts\Activate.ps1
   pip list --outdated
   pip install --upgrade tradelocker python-dotenv Flask flask-cors
   ```

2. **Windows Updates**:
   - Check for Windows updates
   - Schedule restart during non-trading hours

3. **Backup Database**:
   ```powershell
   copy C:\SCRATCH\database\trades.db C:\SCRATCH\backups\trades_$(Get-Date -Format 'yyyy-MM-dd').db
   ```

---

## Troubleshooting

### Bot Won't Start

**Symptom**: Service shows "Running" but no trades happening

**Checks**:
1. Check logs:
   ```powershell
   Get-Content logs\bot_stderr.log -Tail 50
   ```

2. Verify credentials:
   ```powershell
   notepad .env
   ```

3. Test connection manually:
   ```powershell
   python scratch_bot.py
   ```

**Common Issues**:
- ❌ Wrong TradeLocker credentials
- ❌ VPS time is wrong (affects candle detection)
- ❌ Firewall blocking TradeLocker API
- ❌ Internet connection lost

---

### API Not Responding

**Symptom**: Dashboard shows connection error

**Checks**:
1. Is API service running?
   ```powershell
   Get-Service ScratchAPI
   ```

2. Can you reach it locally?
   ```powershell
   curl http://localhost:5000/health
   ```

3. Is firewall blocking?
   ```powershell
   Get-NetFirewallRule -DisplayName "SCRATCH Monitoring API"
   ```

**Solutions**:
- Restart API: `Restart-Service ScratchAPI`
- Check API logs: `Get-Content logs\api_stderr.log -Tail 50`
- Verify port is open: `netstat -an | findstr :5000`

---

### Dashboard Shows Stale Data

**Symptom**: Dashboard not updating

**Checks**:
1. Open browser console (F12) - any errors?
2. Is API responding?
   ```bash
   curl http://your-vps-ip:5000/status?api_key=your-key
   ```

3. Is bot updating heartbeat?
   ```sql
   sqlite3 database\trades.db "SELECT last_heartbeat FROM bot_status;"
   ```

**Solutions**:
- Verify API_URL in Vercel environment variables
- Check API_KEY matches between Vercel and VPS
- Restart browser / clear cache

---

### Services Keep Crashing

**Symptom**: Services start but stop after a few seconds

**Checks**:
1. Check stderr logs:
   ```powershell
   Get-Content logs\bot_stderr.log -Tail 100
   Get-Content logs\api_stderr.log -Tail 100
   ```

2. Check Python path in service:
   ```powershell
   nssm get ScratchBot Application
   nssm get ScratchBot AppDirectory
   ```

3. Test manually:
   ```powershell
   cd C:\SCRATCH
   .\venv\Scripts\Activate.ps1
   python scratch_bot.py
   ```

**Common Fixes**:
- Missing dependencies: `pip install -r requirements.txt`
- Wrong Python path in NSSM: Reinstall services
- Database locked: Stop both services, delete `trades.db-journal`, restart

---

### High CPU Usage

**Symptom**: Bot using 100% CPU

**Possible Causes**:
- Infinite loop in price monitoring
- TradeLocker API returning errors rapidly

**Solutions**:
1. Check logs for repeated errors
2. Increase `position_check_interval` in `scratch_bot.py`:
   ```python
   self.position_check_interval = 1.0  # Increase from 0.5 to 1.0
   ```

3. Add rate limiting in API calls

---

## Security Best Practices

### 1. API Key Security
- ✅ Use strong random API keys (32+ characters)
- ✅ Never commit `.env` file to GitHub
- ✅ Rotate API keys monthly
- ✅ Use different keys for demo and live

### 2. Firewall Configuration
- ✅ Restrict API access to known IPs only
- ✅ Use API key authentication
- ✅ Disable RDP if not needed
- ✅ Enable Windows Firewall

### 3. TradeLocker Credentials
- ✅ Use strong passwords
- ✅ Enable 2FA on TradeLocker account
- ✅ Start with demo account
- ✅ Monitor for unauthorized access

### 4. VPS Security
- ✅ Keep Windows updated
- ✅ Use strong admin password
- ✅ Disable unused services
- ✅ Enable Windows Defender
- ✅ Regular backups

---

## Project Structure on VPS

```
C:\SCRATCH\
│
├── bot/
│   └── (legacy structure - not used in flat structure)
│
├── api/
│   ├── app.py                  # Flask monitoring API
│   └── requirements.txt
│
├── database/
│   ├── db_manager.py          # Database operations
│   └── trades.db              # SQLite database (created automatically)
│
├── dashboard/
│   ├── src/
│   │   └── app/
│   │       ├── page.tsx       # Main dashboard component
│   │       └── ...
│   ├── package.json
│   └── README.md
│
├── logs/
│   ├── bot_stdout.log         # Bot output log
│   ├── bot_stderr.log         # Bot error log
│   ├── api_stdout.log         # API output log
│   ├── api_stderr.log         # API error log
│   └── scratch_bot.log        # Bot application log
│
├── scripts/
│   ├── install_services.bat   # Install Windows services
│   ├── uninstall_services.bat # Remove Windows services
│   ├── start_services.bat     # Start services
│   ├── stop_services.bat      # Stop services
│   ├── deploy.ps1             # Automated deployment
│   └── firewall_setup.ps1     # Firewall configuration
│
├── venv/                      # Python virtual environment
│
├── .env                       # Credentials (DO NOT COMMIT!)
├── .env.example              # Template for .env
├── scratch_bot.py            # Main bot script
├── requirements.txt          # Bot dependencies
├── README.md                 # User documentation
└── PRODUCTION_README.md      # This file
```

---

## Quick Reference Commands

### Service Management
```powershell
# Start services
.\scripts\start_services.bat
Start-Service ScratchBot, ScratchAPI

# Stop services
.\scripts\stop_services.bat
Stop-Service ScratchBot, ScratchAPI

# Restart services
Restart-Service ScratchBot, ScratchAPI

# Check status
Get-Service ScratchBot, ScratchAPI
nssm status ScratchBot
```

### Log Viewing
```powershell
# View bot logs
Get-Content logs\bot_stdout.log -Tail 50 -Wait

# View API logs
Get-Content logs\api_stdout.log -Tail 50 -Wait

# View errors only
Get-Content logs\bot_stderr.log -Tail 50
```

### Deployment
```powershell
# Manual deployment
.\scripts\deploy.ps1

# With specific branch
.\scripts\deploy.ps1 -Branch develop

# Skip tests
.\scripts\deploy.ps1 -SkipTests
```

### Database Queries
```powershell
# Connect to database
sqlite3 database\trades.db

# View recent trades
SELECT * FROM trades ORDER BY entry_time DESC LIMIT 10;

# Calculate win rate
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN pips > 0 THEN 1 ELSE 0 END) as wins,
    (SUM(CASE WHEN pips > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) as win_rate
FROM trades WHERE status = 'closed';

# Exit
.quit
```

---

## Support & Resources

### Documentation
- [TradeLocker API Docs](https://tradelocker.com/developers)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [NSSM Documentation](https://nssm.cc/usage)

### Monitoring
- **Dashboard**: https://your-project.vercel.app
- **API Health**: http://your-vps-ip:5000/health
- **Windows Services**: `services.msc`

### Logs Location
- Bot logs: `C:\SCRATCH\logs\`
- Windows Event Viewer: `eventvwr.msc`

---

## Changelog

### Version 1.0.0 (Initial Release)
- ✅ TradeLocker integration with 5-minute breakout strategy
- ✅ SQLite database for trade logging
- ✅ Flask API for monitoring
- ✅ Next.js dashboard with real-time updates
- ✅ Windows services with NSSM
- ✅ Automated deployment via GitHub Actions
- ✅ Firewall configuration scripts
- ✅ Comprehensive error handling and logging

---

**Remember**: Always test on demo account first! Start with small position sizes and monitor closely.

Good luck with SCRATCH! 🚀📈
