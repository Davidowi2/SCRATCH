# S-025 — Gold Time-Series Momentum

- KERNEL: S-025
- BATCH: S-025-BATCH-1
- PREREGISTERED: 2026-09-22
- INSTRUMENT/TF: GLD daily OHLC
- DATA: research/data/equity/gld_daily_2010_2025.csv (3864 bars, 2010-2025)
- SOURCE: Yahoo Finance via tools/download_gld_daily.py

## MECHANISM

Time-series momentum on Gold: if Close(t) > Close(t - Lookback), go LONG;
else go CASH. Rebalance every 20 trading days.

## POSITION

- LONG GLD if the trend is up (Close vs Close[Lookback] days ago).
- CASH (no position) if the trend is down.
- No shorting Gold (respects long-term upward drift).
- Entry: Open of next bar after signal. Exit: Close of bar 20 trading days later.
- Hold constant 20 trading days, then re-evaluate.

## SIGNAL

Entry: Open of bar t+1, where signal computed on Close(t) vs Close(t - Lookback).
Exit: Close of bar t+1+HoldDays (20 trading days).
Direction: LONG if Close(t) > Close(t - Lookback), CASH otherwise.

## FEES

- Friction: 0.05% round-trip per trade (entry + exit).
- Applied per position change.

## WINDOWS

- Holdout: 2010-01-01 .. 2015-12-31 (for lookback selection)
- IS:      2016-01-01 .. 2020-12-31
- OOS:     2021-01-01 .. 2025-05-13 (one-shot, gated, NOT touched)

## LOOKBACK GRID (LOCKED by holdout selection)

Tested: {60, 120, 250} days. Selection rule: highest Sharpe on holdout.
Abort: if best Sharpe < 0.3, report NON-VIABLE.

## SURVIVE CRITERIA (IS)

ALL THREE must pass:
1. Sharpe > 0.5
2. CAGR > 4%
3. Max DD < 20% (i.e., drawdown > -20%)

## HOLD-OUT RESULT

```
Lookback   |  n_trades |    CAGR |  Sharpe |   MaxDD |     WR
------------------------------------------------------------
      60d |        66 |  -1.84% |  -0.09  | -37.72% |  22.7%
     120d |        64 |  +2.67% |  +0.28  | -20.28% |  28.1%
     250d |        58 |  -0.64% |  -0.01  | -19.07% |  20.7%

Selected: 120d (Sharpe=0.28)
VERDICT: NON-VIABLE (Sharpe < 0.3)
```

## KILL CRITERIA

If holdout best Sharpe < 0.3 → KILL. No IS, no OOS.
Gold TSMOM is structurally non-viable: win rate ~20-28% (barely above
the 20-day hold period), and the trend-catching window is too slow
to avoid the multi-decade sideways periods that trap momentum.

## CLOSURE

Gold TSMOM hypothesis CLOSED — dead mechanism, no retest without Owner override.
