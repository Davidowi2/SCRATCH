# S-028b SECTOR MOMENTUM — LONG/SHORT VARIANT

**Status:** PREREGISTERED — NOT RUN YET. Awaiting S-028 long-only IS survival confirmation.

## Locked Parameters (from S-028)

| Parameter | Value |
|-----------|-------|
| **Lookback** | 126 trading days |
| **Hold** | 21 trading days |
| **Rebalance** | Monthly (month-end ranking) |
| **Leverage** | None |
| **Fees** | 0.05% round-trip per leg (0.10% total per rebalance) |
| **Borrow cost** | 0.30% annualized on short proceeds |

## Strategy Definition

- **Universe:** XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB, XLRE
- **Signal:** Rank all 10 sectors by trailing 126-day return at month-end
- **LONG** top 3 sectors (equal-weight, 33.3% each)
- **SHORT** bottom 3 sectors (equal-weight, 33.3% each)
- **Dollar-neutral:** Long notional equals short notional (50% portfolio each side)
- **Holding period:** 21 trading days from month-end entry

## Construction Rules

1. At each month-end, rank sectors by 126-day trailing return
2. Enter dollar-neutral position: long top 3, short bottom 3
3. Hold for 21 trading days
4. Rebalance monthly (close all positions, re-rank, re-enter)
5. If fewer than 3 sectors qualify (e.g., XLRE inception gap), use available universe

## Benchmarks

1. **SPY buy-and-hold** (absolute market return)
2. **S-028 long-only** (same universe, same lookback, long top-3 only)

The L/S variant should be compared against both. If L/S Sharpe ≤ S-028 Sharpe, the short side adds no value and the long-only is preferred.

## Data Requirements

- Same sector ETF daily data as S-028 (already downloaded)
- Short proceeds tracked (borrow cost applied daily)
- No leverage constraints beyond dollar-neutrality

## OOS Protocol

- If S-028 IS survives → proceed to S-028b IS (2019-2022)
- S-028b IS SURVIVE: L/S Sharpe > 0.5 AND L/S Sharpe > S-028 IS Sharpe
- OOS (2023-2025): one-shot gated after Overseer review

## Restraints

- SAME lookback (126d) as S-028 — no parameter re-optimization
- NO sector exclusion beyond data availability
- NO timing filters or macro overlays on the L/S version
- If L/S Sharpe < long-only Sharpe → KILL (short side destroys value)
