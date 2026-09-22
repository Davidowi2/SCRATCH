# S-021 — Volatility Risk Premium Harvest (VIX - SPX)

- KERNEL: S-021
- BATCH: S-021-BATCH-1 (Phase 5)
- PREREGISTERED: 2026-09-22
- INSTRUMENT/TF: VIX daily (implied vol) + SPX daily (realized vol proxy)
- DATA:
  - VIX: research/data/equity/vix_daily_2010_2025.csv (4007 bars, 2010-2025)
  - SPX: research/data/equity/spx_daily_2010_2025.csv (3864 bars, 2010-2025)
- SOURCE: yfinance (query1.finance.yahoo.com), verified coverage

## MECHANISM

Persistent short-volatility position: collect the volatility risk premium.
VIX (implied vol) systematically exceeds realized volatility (SPX daily
moves). The daily return model:

  daily_return = (VIX_{t-1}/100)/sqrt(252) - abs(SPX_return_t)

This collects the daily implied-volatility premium and pays the daily
absolute realized move. The position is ALWAYS-ON baseline — no timing
filters in the initial test. Pure VRP first.

## PNL MODEL (LOCKED)

Per day t:
  gross_VRP[t] = (VIX[t-1]/100) / sqrt(252)     # implied vol premium collected
  realized_cost[t] = abs(SPX_return[t])          # absolute realized move paid
  gross_return[t] = gross_VRP[t] - realized_cost[t]
  fees[t] = 0.05% per day                         # vol product carry cost
  net[t] = gross_return[t] - fees[t]

THREE-DECOMPOSITION per period (daily):
  (1) gross_VRP = implied vol premium collected (VIX/sqrt(252))
  (2) minus_fees = gross_return minus realized_cost minus daily_fees
  (3) net = gross_return - fees

## FEES

- Friction: 0.05% per day (vol products are cheap, nonzero carry).
- This is a daily position cost, not a per-trade cost.

## WINDOWS (FROZEN)

- IS:  2015-01-01 .. 2020-12-31
- OOS: 2021-01-01 .. 2025-05-13 (one-shot, gated, NOT touched until IS verdict)

## KILL CRITERIA (pre-registered)

ALL THREE must pass to survive:
1. net Sharpe > 0
2. max drawdown < 25%
3. worst-day loss > -8%

Note: VRP is judged on TAIL RISK, not just PF. A profitable-but-blowup
strategy is KILL.

## CLOSURE RULE

If killed, VRP-harvest-on-SPX is CLOSED. No timing-filter rescue without
Owner override. The pure persistent VRP must stand or fall on its own.

## ADDITIONAL REPORTING

- Cumulative return curve (daily).
- Net Sharpe (annualized, risk-free = 0).
- Max drawdown.
- Worst-day loss (single worst daily return).
- Return skewness.
- Return kurtosis.
- % days profitable.
- FLAG March-2020 and Feb-2018 drawdowns explicitly in output.

## NOTES

- SPX_return computed as (close_t - close_{t-1}) / close_{t-1}.
- VIX is a volatility index (not directly investable); this is a proxy
  model for the economic return of a delta-hedged short-vol position.
- The sqrt(252) annualization converts VIX (annualized vol) to daily.
