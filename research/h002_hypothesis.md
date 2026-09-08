# H-002 Hypothesis: Trend Following on EURUSD 4H, London Session

**Status:** HYPOTHESIS — criteria preregistered, no backtest yet
**Created:** 2026-09-08
**DNA vs H-001:** 4/5 dims differ (timeframe, session, signal family, holding) ✓

---

## Hypothesis

London session (12:00–17:00 UTC) trend continuation on 4H candles. When price breaks the previous day's high/low with momentum, ride the move until exhaustion (trailing stop or time-based exit).

**Why this should work:** London sees the day's first real institutional flow. A breakout of the Asian range at the open often starts a trend that lasts into New York.

---

## Pre-Committed Parameters

| Parameter | Value |
|---|---|
| Instrument | EURUSD |
| Timeframe | 4H |
| Session | London 12:00–17:00 UTC (hours 12, 13, 14, 15, 16) |
| Entry | Breakout of previous day's high (LONG) or low (SHORT) |
| Confirm | Close beyond level + volume > 20-bar avg |
| Stop | 1.5× ATR(14) from entry |
| Exit | Trailing stop at 2× ATR OR end of session (17:00) OR max 3 days |
| Size | 0.25% fixed-fractional |

---

## Kill Criteria (preregistered)

| Criterion | Threshold | Verdict |
|---|---|---|
| n < 50 trades | statistical floor | INSUFFICIENT |
| PF < 1.0 | hard kill | KILL |
| WR < 40% | kill floor | KILL |
| PF 1.0–1.15 | danger zone | DANGER-ZONE |
| PF ≥ 1.15 | pass | PASS-OOS |

---

## Pre-Registration Checklist

- [ ] Hypothesis file committed
- [ ] Parameters preregistered (above)
- [ ] Kill criteria preregistered (above)
- [ ] DNA check vs H-001 + retired bots (passed — 4/5 dims differ)
- [ ] Data availability verified (4H data downloadable)
- [ ] Validator adapted for 4H timeframe
- [ ] Engine adapted for 4H + daily breakout logic

**Backtest authorized:** ONLY after all boxes checked
