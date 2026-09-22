# S-019 — Cash & Carry Funding Arbitrage (BTCUSDT)

- KERNEL: S-019
- BATCH: S-019-BATCH-1 (Phase 4)
- PREREGISTERED: 2026-09-17, owner-approved (Structural Harvesting directive)
- INSTRUMENT/TF: BTCUSDT perpetual (funding + price) + BTCUSDT spot (daily proxy)
- DATA:
  - funding: research/data/crypto/btcusdt_fundingrate_8h.csv (Gate-1 validated, sha b863792d...)
  - perp daily: research/data/crypto/btcusdt_daily_2019_2025.csv (Gate-1 validated, sha 767c1e0e...)
  - spot 5m: research/data/crypto/btcusdt_5m.csv (sha db2b863b...) — for basis

## MECHANISM

Delta-neutral carry harvesting: hold LONG SPOT BTC + SHORT PERP BTC (notional
matched), collecting the periodic funding flow. When the perp trades at a
premium to spot (contango), the short perp receives funding from longs — net
positive carry if the premium exceeds costs. This is a structural arbitrage,
NOT a directional bet — direction is hedged out by the delta-neutral position.

Position is always-on, rebalanced daily. No price prediction.

## POSITION (LOCKED)

1. LONG 1 BTC spot + SHORT 1 BTC perp (delta-neutral, notional-matched).
2. Rebalance daily: re-establish position at next day's open.
3. Hold through the 8h funding settlements (3 per day at 00/08/16 UTC).
4. One position at a time — no compounding, fixed notional.

## PNL MODEL (LOCKED)

Per day:
  gross_funding = sum(funding_rate over 3 settlements that day) * notional
                  (long pays negative, short receives; we SHORT perp so
                   we receive the rate as payment)
  basis_entry = (perp_price - spot_price) at entry (cost if perp>spot)
  basis_exit = (perp_price - spot_price) at exit
  basis_cost = |basis_entry| + |basis_exit| (friction cost of the spread)
  fees = 2 * 0.05% * notional (entry) + 2 * 0.05% * notional (exit)
       = 0.20% * notional total (4 legs: spot buy + perp sell + spot sell + perp buy)
  net_carry = gross_funding - basis_cost - fees

THREE-DECOMPOSITION per period (daily):
  (1) gross_funding — sum of realized funding received
  (2) minus_fees — all fees + basis cost
  (3) net — net carry that period

## FEES

- Friction: 0.05% taker/leg on 4 legs (2 entry + 2 exit) = 0.20% total.
- Basis: modeled from perp_daily price - spot_daily price (daily proxy).
  If spot 5m unavailable, this is the spot_daily price. FLAG if mismatch >1%.

## WINDOWS (FROZEN)

- IS:  2021-01-01 .. 2023-12-31
- OOS: 2024-01-01 .. 2025-05-13 (one-shot, gated, NOT touched until IS verdict)

## KILL CRITERIA (pre-registered)

1. Net carry curve is negative (cumulative net falls over time).
2. Net Sharpe < 0 (annualized).
3. Max drawdown from negative-funding stretches > 5% of peak equity.
If ANY of (1, 2, 3) → KILL. Dead = closed, no retest without Owner override.

## ADDITIONAL REPORTING

- Cumulative net carry curve (daily).
- Total net return over the period.
- Net Sharpe (annualized, risk-free = 0).
- Max drawdown from peak.
- % of 8h periods with negative funding (cost periods).
- Total fees paid.
- Basis cost estimate (total).

## ADDENDUM — BASIS NOTE

Spot BTC is available via daily aggregation or 5m. The btcusdt_daily_2019_2025.csv
file is actually the PERP daily (from Binance futures klines). For true basis,
we need BOTH perp and spot. The basis = perp - spot. If perp daily is used as
a proxy for spot (when perp≈spot), FLAG: basis assumed near-zero, cost underestimated.
The 5m file (btcusdt_5m.csv) is perp 5m. True spot 5m is NOT available — we use
the perp daily as the "spot" proxy and document this as a FLAGGED assumption.
