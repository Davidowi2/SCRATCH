<div align="center">

# 🤖 SCRATCH

### **Automated TradeLocker Scalping Bot**

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows-blue.svg)](https://www.microsoft.com/windows)
[![TradeLocker](https://img.shields.io/badge/broker-TradeLocker-green.svg)](https://tradelocker.com)
[![Status](https://img.shields.io/badge/status-production%20ready-brightgreen.svg)]()

**Production-ready 5-minute breakout scalping bot for EURUSD**

[Features](#-features) •
[Quick Start](#-quick-start) •
[Documentation](#-documentation) •
[Demo](#-live-demo) •
[Contributing](#-contributing)

</div>

---

## ⚡ Features

- 🎯 **5-Minute Breakout Strategy** - Trades EURUSD with precise entry/exit rules
- 📊 **Real-Time Dashboard** - Monitor performance via web interface
- 🗄️ **Database Logging** - Complete trade history and analytics
- 🔄 **Auto-Restart** - Windows services with crash recovery
- 🚀 **CI/CD Pipeline** - Automated deployment via GitHub Actions
- 🛡️ **Risk Management** - 5-pip SL, 10-pip TP, spread validation
- 📈 **Performance Tracking** - Win rate, P&L, exit reason analytics
- 🔐 **Secure** - API key auth, firewall configuration, environment variables

---

## 🎯 Quick Links

- **[Quick Start Guide](QUICKSTART.md)** - Deploy in 15 minutes (local) or 1 hour (production)
- **[Production Deployment](PRODUCTION_README.md)** - Complete VPS setup guide  
- **[Strategy Documentation](#-strategy-overview)** - How the bot trades
- **[API Reference](#-monitoring-api)** - REST endpoint documentation
- **[Contributing Guidelines](CONTRIBUTING.md)** - How to contribute
- **[Changelog](CHANGELOG.md)** - Version history

---

## 🎯 Strategy Overview

SCRATCH implements a precise breakout scalping strategy:

- **Instrument**: EURUSD only
- **Timeframe**: 5-minute candles
- **Position Size**: 0.06 lots (fixed)
- **Max Positions**: 1 at a time

### Entry Rules

1. **BUY Signal**: Price breaks **above** the previous 5-minute candle's high
2. **SELL Signal**: Price breaks **below** the previous 5-minute candle's low
3. **Gap Handling**: If a new candle opens outside the previous range, the bot waits for price to return inside the range before taking the next breakout

### Exit Rules (Priority Order)

The bot exits trades based on these conditions, checked in priority order:

1. **Stop-Loss**: 5 pips loss (highest priority)
2. **Take-Profit**: 10 pips profit
3. **Stalling Exit**: If after 5 seconds the trade has less than 2 pips profit, close immediately
4. **Maximum Hold Time**: Close after 15 seconds regardless of profit/loss

### Risk Management

- **Spread Check**: Only enters trades when spread < 2 pips
- **Single Position**: Never opens a new trade while one is active
- **Automatic SL/TP**: Set on every trade
- **Real-time Monitoring**: Checks exit conditions every 0.5 seconds

---

## 📋 Requirements

- Python 3.8 or higher
- TradeLocker account (demo or live)
- API credentials from TradeLocker

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    SCRATCH Trading System                │
└─────────────────────────────────────────────────────────┘

┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Trading Bot  │◄────►│   Database   │◄────►│  Monitoring  │
│ (Python)     │      │   (SQLite)   │      │  API (Flask) │
└──────┬───────┘      └──────────────┘      └──────┬───────┘
       │                                             │
       │ TradeLocker API                             │ REST API
       │                                             │
       ▼                                             ▼
┌──────────────┐                            ┌──────────────┐
│ TradeLocker  │                            │  Dashboard   │
│   Platform   │                            │  (Next.js)   │
└──────────────┘                            └──────────────┘
                                                   │
                                                   │ Vercel
                                                   ▼
                                            ┌──────────────┐
                                            │    Users     │
                                            └──────────────┘
```

## 🚀 Installation

### Quick Start (Local Testing)

### Step 1: Clone Repository

```bash
git clone https://github.com/your-username/SCRATCH.git
cd SCRATCH
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `tradelocker` - TradeLocker API library
- `python-dotenv` - Environment variable management

### Step 3: Configure Environment Variables

1. Copy the example environment file:

```bash
copy .env.example .env
```

2. Edit `.env` with your TradeLocker credentials:

```env
TL_USERNAME=your_username_here
TL_PASSWORD=your_password_here
TL_SERVER=https://demo.tradelocker.com
```

**⚠️ IMPORTANT**: 
- Never commit your `.env` file to version control
- Start with demo environment: `https://demo.tradelocker.com`
- For live trading, change to: `https://live.tradelocker.com`

---

## ▶️ Usage

### Running the Bot

```bash
python scratch_bot.py
```

### Stopping the Bot

Press `Ctrl+C` to stop gracefully. The bot will:
- Close any open positions
- Log the shutdown
- Exit cleanly

---

## 📊 Logging

The bot creates detailed logs in two places:

1. **Console Output**: Real-time status updates
2. **Log File**: `scratch_bot.log` - complete history

### Log Levels

- **INFO**: Normal operations (candle updates, entries, exits)
- **WARNING**: Unusual conditions (wide spreads, gaps detected)
- **ERROR**: Failed operations (connection issues, order failures)

### Trade Log Example

```
2026-08-31 10:05:23 - INFO - NEW CANDLE DETECTED at 2026-08-31 10:05:00
2026-08-31 10:05:23 - INFO - Reference set - High: 1.11234, Low: 1.11189
2026-08-31 10:06:45 - INFO - Breakout UP detected: 1.11236 > 1.11234
2026-08-31 10:06:45 - INFO - ENTERING BUY at 1.11236
2026-08-31 10:06:45 - INFO - BUY ORDER PLACED: Entry=1.11236, SL=1.11186, TP=1.11336
2026-08-31 10:06:55 - INFO - ============================================================
2026-08-31 10:06:55 - INFO - POSITION CLOSED - TAKE-PROFIT HIT
2026-08-31 10:06:55 - INFO - Type: BUY
2026-08-31 10:06:55 - INFO - Entry: 1.11236
2026-08-31 10:06:55 - INFO - Exit: 1.11336
2026-08-31 10:06:55 - INFO - Profit/Loss: 10.00 pips
2026-08-31 10:06:55 - INFO - Hold Time: 10.23 seconds
2026-08-31 10:06:55 - INFO - ============================================================
```

---

## 🔧 Configuration

### Bot Parameters

You can modify these in `scratch_bot.py` (in the `__init__` method):

```python
# Position sizing
self.position_size = 0.06  # Lot size per trade

# Risk management
self.stop_loss_pips = 5     # Stop-loss in pips
self.take_profit_pips = 10  # Take-profit in pips
self.max_spread_pips = 2.0  # Maximum acceptable spread

# Exit rules
self.stalling_time_seconds = 5           # Time before stalling check
self.stalling_min_profit_pips = 2.0      # Minimum profit to avoid stalling exit
self.max_hold_time_seconds = 15          # Maximum time to hold any position

# Monitoring
self.position_check_interval = 0.5  # How often to check exit conditions (seconds)
```

⚠️ **Warning**: Changing these parameters can significantly affect profitability and risk. Test thoroughly on demo before modifying.

---

## 🛡️ Safety Features

### Built-in Protections

1. **Connection Resilience**: Retries up to 3 times on connection failure
2. **API Rate Limiting**: 0.1-second delay between API calls
3. **Error Recovery**: Automatically resets state after errors
4. **Consecutive Error Limit**: Stops after 3 consecutive errors
5. **Spread Protection**: Skips trades when spread is too wide
6. **Position Verification**: Always checks if position is already open

### Manual Override

You can manually close positions through the TradeLocker interface. The bot will:
- Detect the manual close
- Reset its state
- Wait for the next valid setup

---

## 📈 Performance Monitoring

### What to Track

Monitor these metrics to evaluate performance:

1. **Win Rate**: Percentage of profitable trades
2. **Average Win/Loss**: Average pips per winning/losing trade
3. **Average Hold Time**: How long trades are held
4. **Exit Reason Distribution**: Which exit rules trigger most often
5. **Spread Rejections**: How often trades are skipped due to spread

### Review Your Logs

Use the log file to analyze:

```bash
# Count total trades
findstr "POSITION CLOSED" scratch_bot.log

# Count take-profit hits
findstr "TAKE-PROFIT HIT" scratch_bot.log

# Count stop-loss hits
findstr "STOP-LOSS HIT" scratch_bot.log
```

---

## ⚠️ Important Warnings

### Before Running on Live Account

1. **Test on Demo First**: Run for at least 1-2 weeks on demo
2. **Monitor Performance**: Ensure the strategy works in current market conditions
3. **Understand the Risks**: Automated trading can lose money rapidly
4. **Check Capital**: Ensure you can afford the position size (0.06 lots)
5. **Verify Credentials**: Double-check your `.env` file is configured correctly

### Known Limitations

- **Single Instrument**: Only trades EURUSD
- **Market Hours**: Trades 24/5 (no time filtering)
- **Internet Required**: Needs stable internet connection
- **API Dependency**: Relies on TradeLocker API availability
- **Slippage**: Market orders may execute at different prices than expected

### Risk Disclosure

**TRADING INVOLVES RISK. YOU CAN LOSE MONEY.**

- This bot is provided as-is with no guarantees
- Past performance does not indicate future results
- Always use proper risk management
- Never trade with money you cannot afford to lose
- Start with demo account and small position sizes

---

## 🐛 Troubleshooting

### Bot Won't Connect

**Error**: "Missing required environment variables"

**Solution**: 
- Ensure `.env` file exists in the SCRATCH directory
- Check that all three variables are set: `TL_USERNAME`, `TL_PASSWORD`, `TL_SERVER`

---

**Error**: "All connection attempts failed"

**Solution**:
- Verify your TradeLocker credentials are correct
- Check your internet connection
- Confirm the server URL is correct
- Try logging into TradeLocker web interface manually

---

### No Trades Being Placed

**Possible Causes**:

1. **Wide Spread**: Check logs for "Spread too wide" warnings
2. **No Breakouts**: Market may be ranging without clear breakouts
3. **Position Already Open**: Bot only allows 1 position at a time
4. **Gap Condition**: Bot may be waiting for price to return inside range

**Solution**: Monitor the logs to see what the bot is detecting

---

### Orders Failing

**Error**: "Failed to place BUY/SELL order"

**Solution**:
- Check your account balance is sufficient
- Verify the instrument is available for trading
- Check if market is open (Forex trades 24/5, closed on weekends)
- Look for API error messages in logs

---

### Position Not Closing

**Issue**: Position stays open longer than expected

**Solution**:
- Check if SL/TP were set correctly (see logs)
- Verify exit conditions in logs
- Manually close via TradeLocker if needed
- Bot will detect manual close and reset

---

## 📁 Project Structure

```
SCRATCH/
├── scratch_bot.py       # Main bot implementation
├── requirements.txt     # Python dependencies
├── .env.example         # Template for environment variables
├── .env                 # Your credentials (create this, never commit)
├── .gitignore          # Git ignore rules
├── README.md           # This file
└── scratch_bot.log     # Log file (created when bot runs)
```

---

## 🔄 Updating the Bot

To update dependencies:

```bash
pip install --upgrade -r requirements.txt
```

To update the TradeLocker library specifically:

```bash
pip install --upgrade tradelocker
```

---

## 📞 Support

### TradeLocker API Documentation

- [TradeLocker Developer Docs](https://tradelocker.com/developers)
- [TradeLocker Support](https://tradelocker.com/support)

### Python Library

- [tradelocker PyPI](https://pypi.org/project/tradelocker/)

---

## 📝 License

This bot is provided for educational and personal use. Use at your own risk.

---

## 🎉 Quick Start Checklist

- [ ] Python 3.8+ installed
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with valid credentials
- [ ] Tested connection on demo account
- [ ] Reviewed strategy and risk parameters
- [ ] Logs are being written correctly
- [ ] Ready to monitor first trades

---

## 💡 Tips for Success

1. **Start Small**: Use demo account first, then start with minimum position sizes
2. **Monitor Regularly**: Check logs daily to understand bot behavior
3. **Market Conditions**: Strategy performs differently in trending vs ranging markets
4. **Spread Matters**: Higher spreads reduce profitability significantly
5. **Time of Day**: Volatility and spreads vary by trading session
6. **Keep it Running**: Bot needs to run continuously to catch setups
7. **Backup Logs**: Save log files periodically for performance analysis

---

## 📊 Monitoring Dashboard

SCRATCH includes a real-time web dashboard built with Next.js:

**Features:**
- 🟢 Live bot status indicator
- 📈 Current open position details
- 💰 Performance metrics (win rate, P&L)
- 📋 Recent trades table
- ⚡ Auto-refresh every 5 seconds

**Deploy to Vercel:**
```bash
cd dashboard
npm install
npm run build

# Or deploy directly to Vercel
vercel deploy
```

See `dashboard/README.md` for detailed instructions.

---

## 🔌 Monitoring API

The Flask API provides endpoints for monitoring:

| Endpoint | Description |
|----------|-------------|
| `/health` | Health check |
| `/status` | Bot status and metrics |
| `/position` | Current open position |
| `/trades` | Recent closed trades |
| `/trades/last` | Last closed trade |
| `/metrics` | Performance metrics |
| `/account` | Account balance info |

**Authentication**: API key required (set in `.env`)

**Example**:
```bash
curl http://localhost:5000/status?api_key=your-key
```

---

## 🪟 Windows Production Deployment

For production deployment on Windows VPS, see **[PRODUCTION_README.md](PRODUCTION_README.md)**

**Quick production setup:**
```powershell
# 1. Install services
.\scripts\install_services.bat

# 2. Configure firewall
.\scripts\firewall_setup.ps1 -Port 5000

# 3. Start services
.\scripts\start_services.bat
```

**Features:**
- ✅ Auto-start on boot (Windows services)
- ✅ Auto-restart on crash
- ✅ Automated deployment (GitHub Actions)
- ✅ Comprehensive logging
- ✅ Database persistence
- ✅ Remote monitoring via dashboard

---

## 📁 Project Structure

```
SCRATCH/
├── scratch_bot.py           # Main trading bot
├── requirements.txt         # Bot dependencies
│
├── database/
│   ├── db_manager.py       # Database operations
│   └── trades.db           # SQLite database (auto-created)
│
├── api/
│   ├── app.py              # Flask monitoring API
│   └── requirements.txt    # API dependencies
│
├── dashboard/              # Next.js monitoring dashboard
│   ├── src/app/
│   │   └── page.tsx       # Main dashboard
│   └── package.json
│
├── scripts/                # Deployment & service scripts
│   ├── install_services.bat
│   ├── deploy.ps1
│   └── firewall_setup.ps1
│
├── logs/                   # Log files (auto-created)
│
├── .env                    # Configuration (create from .env.example)
├── README.md              # This file
└── PRODUCTION_README.md   # Production deployment guide
```

---

## 🔐 Security Features

- **API Key Authentication**: Protect monitoring endpoints
- **Environment Variables**: No hardcoded credentials
- **Firewall Configuration**: Restrict access by IP
- **Service Isolation**: Bot and API run as separate services
- **Comprehensive Logging**: Audit trail for all actions

---

## 📈 Performance Tracking

SCRATCH automatically tracks:
- Total trades and win rate
- Average profit/loss per trade
- Exit reason distribution (SL, TP, Stalling, MaxHold)
- Average hold time
- Account balance snapshots

**View metrics**:
- Dashboard: Real-time via web interface
- API: `/metrics` endpoint
- Database: Direct SQLite queries

---

## 🔄 CI/CD Pipeline

Automated deployment via GitHub Actions:

1. Push code to `main` branch
2. GitHub Actions triggers
3. Connects to VPS via SSH
4. Runs deployment script
5. Updates code and restarts services

**Setup**: See [PRODUCTION_README.md](PRODUCTION_README.md#cicd-setup)

---

## 🛠️ Development

### Running Locally

**Terminal 1 - Bot:**
```bash
python scratch_bot.py
```

**Terminal 2 - API:**
```bash
python api/app.py
```

**Terminal 3 - Dashboard:**
```bash
cd dashboard
npm run dev
```

Open `http://localhost:3000` for dashboard.

### Database Schema

**Trades Table:**
```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    entry_time TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_time TEXT,
    exit_price REAL,
    side TEXT,  -- 'BUY' or 'SELL'
    pips REAL,
    profit_usd REAL,
    exit_reason TEXT,
    status TEXT,  -- 'open' or 'closed'
    position_size REAL,
    stop_loss REAL,
    take_profit REAL,
    hold_time_seconds REAL
);
```

**Query examples** in `PRODUCTION_README.md`.

---

## 📞 Support

### Documentation
- **User Guide**: This file
- **Production Deployment**: [PRODUCTION_README.md](PRODUCTION_README.md)
- **Dashboard Setup**: [dashboard/README.md](dashboard/README.md)
- **TradeLocker API**: https://tradelocker.com/developers

### Common Issues
See [Troubleshooting](PRODUCTION_README.md#troubleshooting) section in production guide.

---

## 📝 Version History

### v1.0.0 (Current)
- ✅ Complete trading bot with 5-minute breakout strategy
- ✅ SQLite database integration
- ✅ Flask monitoring API
- ✅ Next.js real-time dashboard
- ✅ Windows service support
- ✅ Automated CI/CD deployment
- ✅ Comprehensive logging and error handling

---

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Ways to Contribute
- 🐛 Report bugs via [Issues](https://github.com/Davidowi2/SCRATCH/issues)
- 💡 Suggest features via [Discussions](https://github.com/Davidowi2/SCRATCH/discussions)
- 🔧 Submit Pull Requests
- 📖 Improve documentation
- ⭐ Star the repository if you find it useful!

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Trading Disclaimer

**TRADING INVOLVES SUBSTANTIAL RISK OF LOSS**

This software is provided for educational and informational purposes only. Past performance is not indicative of future results. 

**By using this software, you acknowledge that:**
- You are solely responsible for your trading decisions
- The authors assume no liability for any losses
- You understand algorithmic trading risks
- You will test thoroughly on demo accounts first
- You will consult with qualified financial advisors

**Always trade responsibly and within your risk tolerance.**

---

## 🎓 Resources

### Documentation
- [Quick Start Guide](QUICKSTART.md)
- [Production Deployment](PRODUCTION_README.md)
- [Deployment Summary](DEPLOYMENT_SUMMARY.md)
- [Complete Package Overview](DELIVERY_PACKAGE.md)

### External Links
- [TradeLocker API Docs](https://tradelocker.com/developers)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Next.js Documentation](https://nextjs.org/docs)

---

## 📊 Stats

![Lines of Code](https://img.shields.io/badge/lines%20of%20code-3500%2B-blue)
![Documentation](https://img.shields.io/badge/documentation-15k%2B%20words-green)
![Files](https://img.shields.io/badge/files-30%2B-orange)

---

## 🌟 Show Your Support

If you find SCRATCH useful, please:
- ⭐ Star this repository
- 🔀 Fork it for your own use
- 📢 Share with other traders
- 💬 Join the [Discussions](https://github.com/Davidowi2/SCRATCH/discussions)

---

<div align="center">

**Built with ❤️ by [David Owi](https://github.com/Davidowi2) | Powered by Kiro AI**

**Version 1.0.0** | **Released August 2026**

*Remember: The best trader is a disciplined trader. Let SCRATCH execute your strategy with precision while you focus on risk management and performance analysis.*

</div>
