# Contributing to SCRATCH

Thank you for your interest in contributing to SCRATCH! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful and constructive in all interactions. This is a trading bot used by real people with real money - bugs can have serious consequences.

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use the bug report template
3. Include detailed reproduction steps
4. Provide relevant logs
5. Specify your environment (OS, Python version, etc.)

### Suggesting Features

1. Check if the feature has already been requested
2. Use the feature request template
3. Explain the use case clearly
4. Consider backward compatibility

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly on demo account
5. Update documentation
6. Commit with clear messages
7. Push to your fork
8. Open a Pull Request

## Development Guidelines

### Code Style

- Follow PEP 8 for Python code
- Use type hints for all functions
- Add docstrings to all classes and methods
- Keep functions focused and small
- Use meaningful variable names

### Testing

- Test all changes on demo account first
- Verify database operations
- Test API endpoints
- Check dashboard updates
- Monitor logs for errors

### Documentation

- Update README.md if behavior changes
- Update PRODUCTION_README.md for deployment changes
- Add inline comments for complex logic
- Update API documentation for new endpoints

### Commit Messages

Use clear, descriptive commit messages:
- `feat: Add support for multiple instruments`
- `fix: Correct stalling exit calculation`
- `docs: Update deployment guide`
- `refactor: Simplify entry logic`
- `test: Add database integration tests`

## Areas for Contribution

### High Priority
- Additional exit strategies
- Multi-instrument support
- Enhanced error recovery
- Performance optimization
- More comprehensive testing

### Medium Priority
- Additional notification channels (Discord, Telegram)
- Advanced analytics
- Backtesting framework
- Paper trading mode
- Web-based configuration

### Documentation
- Video tutorials
- More examples
- Troubleshooting guides
- Translation to other languages

## Testing Requirements

### Before Submitting PR

1. **Unit Tests**: If adding new features, include tests
2. **Integration Tests**: Test with TradeLocker API (demo)
3. **Manual Testing**: Run for at least 1 hour on demo
4. **Documentation**: Update relevant docs
5. **Changelog**: Add entry to CHANGELOG.md

### Test Checklist

- [ ] Bot connects to TradeLocker
- [ ] Candle detection works
- [ ] Entry logic triggers correctly
- [ ] Exit rules work as expected
- [ ] Database logging functions
- [ ] API endpoints respond
- [ ] Dashboard displays correctly
- [ ] Services install/start/stop
- [ ] No new errors in logs

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/SCRATCH.git
cd SCRATCH

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
pip install -r api/requirements.txt

# Install development dependencies
pip install pytest black flake8 mypy

# Configure environment
copy .env.example .env
# Edit .env with demo credentials

# Run bot
python scratch_bot.py
```

## Project Structure

```
SCRATCH/
├── scratch_bot.py          # Main bot - core trading logic
├── database/               # Database layer
│   └── db_manager.py      # Database operations
├── api/                   # Monitoring API
│   └── app.py            # Flask endpoints
├── dashboard/            # Next.js dashboard
├── scripts/              # Deployment scripts
├── .github/              # GitHub templates
└── docs/                 # Documentation
```

## Questions?

- **General Questions**: Open a discussion on GitHub
- **Bug Reports**: Use the bug report template
- **Feature Requests**: Use the feature request template
- **Security Issues**: Email directly (do not open public issue)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to SCRATCH! 🚀
