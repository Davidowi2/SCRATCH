# Changelog

All notable changes to SCRATCH will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-31

### Added
- Initial release of SCRATCH trading bot
- 5-minute breakout strategy on EURUSD
- TradeLocker API integration
- SQLite database for trade logging
- Flask REST API with 7 endpoints
- Next.js real-time monitoring dashboard
- Windows service support via NSSM
- Automated deployment via GitHub Actions
- PowerShell deployment scripts
- Firewall configuration script
- Comprehensive documentation (15,000+ words)
- Gap handling for candle opens outside range
- Stalling exit rule (5 seconds, <2 pips)
- Maximum hold time (15 seconds)
- Spread validation (<2 pips)
- Single position enforcement
- Auto-retry on connection loss
- Rotating log files
- Bot heartbeat tracking
- Performance metrics calculation
- API key authentication
- CORS support for dashboard

### Security
- Environment variable for credentials
- API key authentication on endpoints
- Windows Firewall configuration
- Optional IP whitelisting
- No hardcoded credentials

### Documentation
- README.md - User guide and strategy overview
- PRODUCTION_README.md - Complete VPS deployment guide
- QUICKSTART.md - 15-minute / 1-hour setup guide
- DEPLOYMENT_SUMMARY.md - Delivery summary
- DELIVERY_PACKAGE.md - Complete package overview
- CONTRIBUTING.md - Contribution guidelines
- LICENSE - MIT License with trading disclaimer
- CHANGELOG.md - This file

### Known Issues
- Dashboard uses HTTP (not HTTPS) for VPS connection
- SQLite not suitable for multiple concurrent writers (not an issue for single bot)
- No built-in notification system (logs only)
- Windows-specific deployment (Linux scripts not included)

### Coming Soon
- Multiple instrument support
- Discord/Telegram notifications
- Advanced analytics dashboard
- Backtesting framework
- Paper trading mode

---

## Version History

**[1.0.0] - 2026-08-31** - Initial release

---

## Upgrade Notes

This is the initial release. No upgrade path needed.

---

## Support

For issues, questions, or feature requests:
- GitHub Issues: https://github.com/Davidowi2/SCRATCH/issues
- Discussions: https://github.com/Davidowi2/SCRATCH/discussions
- Documentation: See README.md and PRODUCTION_README.md
