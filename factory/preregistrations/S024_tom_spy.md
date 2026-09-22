# S-024 — Turn-of-Month Pension Flow Harvest (SPY)

- KERNEL: S-024
- BATCH: S-024-BATCH-1
- PREREGISTERED: 2026-09-22
- INSTRUMENT/TF: SPY daily OHLC
- DATA: research/data/equity/spy_daily_2010_2025.csv (3864 bars, 2010-2025)
- SOURCE: Yahoo Finance via tools/download_spy_daily.py

## MECHANISM

Pension fund flow anomaly: institutional pension flows create a
turn-of-month effect in SPY. Last N days of month + first M days of next
month show elevated returns vs baseline drift.

## POSITION (LOCKED)

- LONG SPY at Open of first TOM window day.
- EXIT at Close of last TOM window day.
- One position per month boundary.
- (N, M) = (3, 3) — LOCKED from holdout (2010-2015 excess grid).
  NOT re-selected. NOT re-tuned.

## SIGNAL (FIXED)

Entry: Open of first TOM window day (day after last trading day of month - N + M + 1).
Exit: Close of last TOM window day.
Hold: ~6 calendar days (N = last 3 of month, M = first 3 of next).

## FEES

- Friction: 0.02% round-trip (SPY is 1 penny wide).
- Applied per TOM window.

## WINDOWS (FROZEN)

- Holdout: 2010-01-01 .. 2015-12-31 (for window selection)
- IS:      2016-01-01 .. 2020-12-31
- OOS:     2021-01-01 .. 2025-05-13 (one-shot, gated, NOT touched until IS verdict)

## WINDOW SELECTION (COMPLETED — LOCKED)

Holdout grid (2010-2015, all 9 windows):
  (1,1) L=2: TOM -0.015% vs base +0.067% | excess -0.082%
  (1,2) L=3: TOM +0.073% vs base +0.111% | excess -0.038%
  (1,3) L=4: TOM +0.276% vs base +0.155% | excess +0.121%
  (2,1) L=3: TOM +0.091% vs base +0.111% | excess -0.021%
  (2,2) L=4: TOM +0.178% vs base +0.155% | excess +0.024%
  (2,3) L=5: TOM +0.382% vs base +0.198% | excess +0.183%
  (3,1) L=4: TOM +0.154% vs base +0.155% | excess -0.001%
  (3,2) L=5: TOM +0.242% vs base +0.198% | excess +0.043%
  (3,3) L=6: TOM +0.444% vs base +0.241% | excess +0.204%  ← SELECTED

SELECTED: (N,M) = (3,3), L = 6, excess = +0.204% (highest excess over baseline)

## SURVIVE CRITERIA (IS 2016-2020)

ALL THREE must pass:
1. net mean return > 0
2. excess over baseline > 0
3. win rate > 55%

If ALL pass → SURVIVE, hold for OOS.
If any fails → KILL.

## IS RESULT (LOCKED)

- n_windows: 59
- mean net return: +0.4472%
- win rate: 55.9%
- Sharpe: 0.6133
- max DD: -10.65%
- baseline mean: +0.2969% (all 6-day windows)
- excess: +0.1503%

Per-year:
  2016: n=12, mean +0.385%, WR 50.0%
  2017: n=12, mean +0.572%, WR 58.3%
  2018: n=12, mean -0.301%, WR 50.0%
  2019: n=12, mean +0.498%, WR 58.3%
  2020: n=11, mean +1.140%, WR 63.6%

VERDICT: SURVIVE — all 3 criteria pass. OOS held (one-shot gated).

## CLOSURE

If OOS fails → TOM-on-SPY closed. No window re-shopping.
If OOS passes → promoted to live candidate.
