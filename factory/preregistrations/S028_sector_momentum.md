# S-028 SECTOR MOMENTUM

**Status:** IS COMPLETE — SURVIVE (proceed to OOS, one-shot gated)

**Locked Parameters:**
- Lookback: 126 trading days
- Top-K: 3 (long top 3 sector ETFs equal-weight)
- Hold: 21 trading days
- Fees: 0.05% round-trip
- Leverage: None
- Assets: XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB, XLRE

## Holdout Grid (2015-2018)

| Lookback | Top-K | CAGR | Sharpe | MaxDD | Excess | n |
|----------|-------|------|--------|-------|--------|---|
| 21d | 1 | -3.12% | -0.71 | -20.73% | -3.12% | 42 |
| 21d | 2 | 0.08% | 0.31 | -19.31% | 0.08% | 42 |
| 21d | 3 | 0.10% | 0.34 | -19.65% | 0.10% | 42 |
| 63d | 1 | 1.19% | 0.72 | -18.71% | 1.19% | 42 |
| 63d | 2 | 3.26% | 1.40 | -16.08% | 3.26% | 42 |
| 63d | 3 | 2.97% | 1.33 | -16.18% | 2.97% | 42 |
| 126d | 1 | 3.45% | 1.59 | -19.33% | 3.45% | 42 |
| 126d | 2 | 2.28% | 1.18 | -19.50% | 2.28% | 42 |
| **126d** | **3** | **5.09%** | **2.25** | **-17.66%** | **5.09%** | **42** |

**Selection rule applied:** Highest Sharpe subject to CAGR > SPY AND MaxDD > -45%.
126d/Top-K=3 wins (Sharpe=2.25, both constraints satisfied).

## IS Results (2019-2022)

| Metric | Value |
|--------|-------|
| n_trades | 48 |
| CAGR | 15.90% |
| Sharpe | 4.033 |
| MaxDD | -15.55% |
| Win Rate | 66.7% |
| Excess vs SPY | +4.71% (SPY CAGR: 11.19%) |
| Final portfolio | 1.8043x |

### Per-Year Breakdown

| Year | Mean | WR | CAGR | MaxDD |
|------|------|-----|------|-------|
| 2019 | 0.56% | 66.7% | — | -6.93% |
| 2020 | 2.23% | 66.7% | — | -15.13% |
| 2021 | 1.36% | 66.7% | — | -8.33% |
| 2022 | 1.38% | 66.7% | — | -12.24% |

### Drawdown Periods
- 2020-02 → 2020-03: -15.55% (COVID crash — survived with modest DD)
- 2022-05 → 2022-06: -8.96%
- 2021-12 → 2022-01: -8.33%

## Survive Criteria (IS)

| Criterion | Required | Actual | Pass? |
|-----------|----------|--------|-------|
| net CAGR > SPY CAGR | 15.90% > 11.19% | ✓ | YES |
| Sharpe > 0.5 | 4.033 > 0.5 | ✓ | YES |
| positive excess vs SPY | +4.71% | ✓ | YES |
| MaxDD acceptable | < -40% | -15.55% | YES |

## Verdict: SURVIVE — proceed to OOS (one-shot gated)

### Data Limitations
- XLRE inception gap: starts 2015-10-08 (2412 bars vs 2605 for other ETFs)
- 126-day lookback means first valid signal is 2015-05-26 (May 2015)
- Yahoo Finance data quality: all Gate-1 passes

### Notes
- The 126-day lookback (6 months) makes sense for pension/seasonal flows
- Top-K=3 means 30% portfolio concentration per holding (equal-weight)
- Turnover: 72x annualized (monthly rebalancing + 21-day holds)
- 2020 COVID drawdown (-15.55%) is the worst, comparable to SPY's -15% drop

verdict_hash: 65c019912318b53d
