# SCRATCH - Quick Start Guide

**Get SCRATCH running in 15 minutes** (local testing) or **1 hour** (full production deployment).

---

## 🚀 Local Testing (15 Minutes)

Perfect for testing the bot locally before deploying to VPS.

### Step 1: Install Python (2 minutes)

```bash
# Check if Python 3.11+ is installed
python --version

# If not installed, download from:
# https://www.python.org/downloads/
```

### Step 2: Clone and Setup (5 minutes)

```bash
# Clone repository
git clone https://github.com/your-username/SCRATCH.git
cd SCRATCH

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r api/requirements.txt
```

### Step 3: Configure (3 minutes)

```bash
# Copy environment template
copy .env.example .env  # Windows
# cp .env.example .env  # Mac/Linux

# Edit with your credentials
notepad .env  # Windows
# nano .env   # Mac/Linux
```

Fill in:
```env
TL_USERNAME=your_tradelocker_username
TL_PASSWORD=your_tradelocker_password
TL_SERVER=https://demo.tradelocker.com
API_KEY=any-random-string-for-testing
```

### Step 4: Run (5 minutes)

**Terminal 1 - Bot:**
```bash
python scratch_bot.py
```

You should see:
```
SCRATCH Bot initialized
Connecting to TradeLocker...
Successfully connected
Bot is now LIVE - MONITORING EURUSD
```

**Terminal 2 - API (optional):**
```bash
python api/app.py
```

**Terminal 3 - Dashboard (optional):**
```bash
cd dashboard
npm install
npm run dev
# Open http://localhost:3000
```

**Test for 5-10 minutes.** If bot connects and monitors without errors, you're ready for production!

Stop with `Ctrl+C` in each terminal.

---

## 🏢 Production Deployment (1 Hour)

Deploy to Windows VPS with monitoring and auto-start.

### Prerequisites Checklist

- [ ] Windows VPS (Server 2022 or Win 10/11)
- [ ] Administrator access to VPS
- [ ] TradeLocker account (demo or live)
- [ ] GitHub account
- [ ] Vercel account (free tier)

### Part 1: VPS Setup (20 minutes)

**On your Windows VPS:**

```powershell
# 1. Install Python 3.11+
# Download from: https://www.python.org/downloads/windows/
# ✅ Check "Add Python to PATH" during installation

# 2. Install Git
# Download from: https://git-scm.com/download/win

# 3. Install NSSM (with Chocolatey)
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
choco install nssm -y

# 4. Clone SCRATCH
cd C:\
git clone https://github.com/your-username/SCRATCH.git
cd SCRATCH
```

### Part 2: Bot Installation (15 minutes)

```powershell
# 1. Configure environment
copy .env.example .env
notepad .env
# Fill in your TradeLocker credentials

# 2. Install as Windows services
.\scripts\install_services.bat
# This creates virtual environment and installs dependencies automatically

# 3. Start services
.\scripts\start_services.bat
```

Verify services are running:
```powershell
Get-Service ScratchBot, ScratchAPI
```

### Part 3: Firewall Setup (5 minutes)

```powershell
# Open port 5000 for API
.\scripts\firewall_setup.ps1 -Port 5000

# Or restrict to specific IPs (more secure)
.\scripts\firewall_setup.ps1 -Port 5000 -AllowedIPs @("your.home.ip")
```

Test from another computer:
```bash
curl http://your-vps-ip:5000/health
```

### Part 4: Dashboard Deployment (15 minutes)

**On Vercel:**

1. Go to https://vercel.com
2. Sign in with GitHub
3. Click "Add New" → "Project"
4. Import your SCRATCH repository
5. Framework: **Next.js**
6. Root Directory: **dashboard**
7. Add Environment Variables:
   - `API_URL` = `http://your-vps-ip:5000`
   - `API_KEY` = `your-api-key-from-env-file`
8. Click "Deploy"

**Done!** Your dashboard will be live at `https://your-project.vercel.app`

### Part 5: CI/CD Setup (5 minutes)

**Enable SSH on VPS:**
```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
```

**Add GitHub Secrets:**
1. Go to GitHub repository → Settings → Secrets
2. Add:
   - `VPS_IP` = Your VPS IP address
   - `VPS_USERNAME` = Administrator
   - `VPS_PASSWORD` = Your admin password

**Test:**
```bash
# Make a change and push
echo "# Test" >> README.md
git add .
git commit -m "Test CI/CD"
git push origin main
```

GitHub Actions will automatically deploy to your VPS!

---

## ✅ Verification Checklist

After deployment, verify everything works:

### Bot Status
```powershell
# Check services
Get-Service ScratchBot, ScratchAPI

# View recent logs
Get-Content C:\SCRATCH\logs\bot_stdout.log -Tail 20
```

### API Status
```bash
# From any computer
curl http://your-vps-ip:5000/health
curl http://your-vps-ip:5000/status?api_key=your-key
```

### Dashboard Status
- Open `https://your-project.vercel.app`
- Should show bot status and metrics
- Auto-refreshes every 5 seconds

---

## 🎯 What to Watch First Day

### Hour 1-2: Initial Monitoring
- [ ] Bot connects to TradeLocker
- [ ] Fetches EURUSD data
- [ ] Identifies previous candle high/low
- [ ] Dashboard shows "RUNNING" status

### First Trade:
- [ ] Bot detects breakout
- [ ] Checks spread (must be < 2 pips)
- [ ] Enters position
- [ ] Sets SL and TP correctly
- [ ] Dashboard shows open position
- [ ] Database records entry

### First Exit:
- [ ] Bot closes based on exit rule
- [ ] Records P&L and exit reason
- [ ] Dashboard updates
- [ ] Trade appears in history table

---

## 🔧 Common First-Time Issues

### "ERROR: tradelocker library not found"
```bash
pip install tradelocker
```

### "Authentication failed"
- Check username/password in `.env`
- Verify TradeLocker account is active
- Try logging into TradeLocker web manually

### "Service won't start"
```powershell
# Check Python path
nssm get ScratchBot Application

# Check error logs
Get-Content logs\bot_stderr.log -Tail 50

# Reinstall service
.\scripts\uninstall_services.bat
.\scripts\install_services.bat
```

### "Dashboard shows connection error"
- Verify API is running: `Get-Service ScratchAPI`
- Check firewall: `Get-NetFirewallRule -DisplayName "SCRATCH*"`
- Test API directly: `curl http://localhost:5000/health`
- Verify API_URL in Vercel matches VPS IP

---

## 📚 Next Steps

After successful deployment:

1. **Monitor for 24 hours** - Ensure bot handles different market conditions
2. **Review first 10 trades** - Check exit reasons and hold times
3. **Calculate real metrics** - Win rate, average P&L, max drawdown
4. **Adjust if needed** - See PRODUCTION_README.md for parameter tuning
5. **Set up alerts** (optional) - Add Discord/Telegram notifications

---

## 🆘 Getting Help

### Documentation
- **This file** - Quick start
- **README.md** - User guide and strategy
- **PRODUCTION_README.md** - Complete deployment guide
- **DEPLOYMENT_SUMMARY.md** - What's been built

### Logs Location
- Bot logs: `C:\SCRATCH\logs\bot_stdout.log`
- API logs: `C:\SCRATCH\logs\api_stdout.log`
- Error logs: `*_stderr.log` files

### Common Commands
```powershell
# View services
Get-Service Scratch*

# Restart services
Restart-Service ScratchBot, ScratchAPI

# View logs live
Get-Content logs\bot_stdout.log -Wait

# Check database
sqlite3 database\trades.db "SELECT * FROM trades ORDER BY id DESC LIMIT 5;"
```

---

## 🎉 Success Criteria

You'll know everything is working when:

✅ Both services show "Running" status
✅ Bot logs show "MONITORING EURUSD"
✅ Dashboard shows green "RUNNING" indicator
✅ API responds to `/health` endpoint
✅ First trade executes and logs correctly
✅ Dashboard updates with trade data

---

**Time to Deploy**: ~1 hour
**Time to First Trade**: Depends on market (could be minutes to hours)
**Monitoring Required**: High for first 24 hours, then daily checks

Good luck! 🚀

---

**Need more help?** See PRODUCTION_README.md for detailed troubleshooting and advanced configuration.
