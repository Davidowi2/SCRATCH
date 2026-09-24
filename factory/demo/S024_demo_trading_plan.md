# S-024 DEMO TRADING PLAN

**Status:** LOCKED — daily rules frozen. Intraday attribution (S024_intraday_attribution.py) is EXPLORATORY ONLY.

**Commit:** `41e7939` (sha256: 5a3c9f1b2e4d7a8c...)
**Git HEAD:** `41e7939f...`

## Locked Rules

| Parameter | Value |
|-----------|-------|
| **Assets** | 50% SPY, 50% QQQ of strategy capital |
| **Window** | Last 3 trading days of month + first 3 trading days of next month |
| **Entry** | Market open on first TOM day (last trading day of month before the 3-day window) |
| **Exit** | Market close on last TOM day (3rd trading day of next month) |
| **Frequency** | Once per month |
| **Leverage** | None |
| **Fees/Slippage** | Logged as actuals at execution |

## Demo Protocol

1. **Capital:** Demo account (TradeLocker paper or equivalent).
2. **Execution:** Trade both SPY and QQQ per locked rules. Log entry/exit prices, actual fees, slippage.
3. **Review gate:** After 6 TOM windows (6 months), compare live-vs-backtest performance.
4. **Kill/review criteria:**
   - If live execution repeatedly deviates from rules → fix process, not parameters.
   - If 12-window live PnL is materially worse than backtest → pause and investigate.
   - Do NOT tune parameters after live losses without Owner override.

## Rationale

The intraday attribution (n=20 SPY, n=21 QQQ) suggested possible timing improvements (12:00 entry, 14:00 exit) but sample size is insufficient to lock execution times. The locked plan uses simple open-to-close entry/exit to eliminate timing bias. Intraday optimization is deferred pending either:
- A paid 10-year hourly data feed (Polygon/Tiingo), OR
- Owner approval to proceed with the exploratory timing after more windows are collected.

## S-024 Historical Performance (IS+OOS Combined)

| Metric | Value |
|--------|-------|
| n_windows | ~118 (59 IS + ~59 OOS) |
| Mean net return | +0.305% (OOS), +0.447% (IS) |
| Excess over baseline | +0.062% (OOS), +0.150% (IS) |
| Win rate | ~55.8% |
| Sharpe | 0.59 (combined) |
| Max DD | -14.68% (OOS) |

## Appendix: Intraday Attribution Findings (EXPLORATORY)

Entry timing tests (n=20-21, 2024-2026):
- 09:30 open: SPY +0.288% WR 65%, QQQ +0.185% WR 57%
- 12:00 lunch: SPY +0.416% WR 60%, QQQ +0.438% WR 62%
- 14:00 afternoon: SPY +0.434% WR 55%, QQQ +0.456% WR 62%

Exit timing tests:
- 11:00: SPY +0.254% WR 55%, QQQ +0.175% WR 43%
- 14:00: SPY +0.389% WR 55%, QQQ +0.274% WR 52%
- 15:30 close: SPY +0.356% WR 60%, QQQ +0.262% WR 57%

**Recommendation deferred** — insufficient sample size for execution timing lock.
