# S-028 SECTOR MOMENTUM — CLOSURE

**Experiment:** S-028 (Sector Momentum — Long/Short NOT run)
**Preregistration:** `factory/preregistrations/S028b_sector_ls.md`
**IS Result:** SURVIVE (126d, Top-3, Sharpe 4.033, n=48, 2019-2022)
**OOS Result:** KILL

## Status
S-028 long-only top-3 equal-weight 126d sector momentum is **CLOSED** as implemented.

## OOS Failure (2023-01-01..2025-05-13)

| Metric | S-028 OOS | SPY Benchmark | Excess |
|--------|-----------|---------------|--------|
| n_rebalances | 21 | — | — |
| CAGR | **-3.84%** | **+20.13%** | **-23.97%** |
| Sharpe | **-0.122** | — | — |
| MaxDD | -16.49% | — | — |
| Win Rate | 52.4% | — | — |

### Per-Year
| Year | n | Mean Gross | Mean Net | WR | CAGR |
|------|---|------------|----------|-----|------|
| 2023 | 6 | -0.11% | -0.16% | 50.0% | -1.64% |
| 2024 | 12 | +1.02% | +0.97% | 66.7% | +11.63% |
| 2025 | 3 | -5.20% | -5.25% | 0.0% | -14.95% |

### Root Cause Classification: STATIC IMPLEMENTATION / REGIME DEPENDENCE

The OOS period (2023-2025) represents a different market regime:
1. **2023:** Broad market flat, sectors rotated → strategy lost money (-1.64%)
2. **2024:** Tech rally dominated → strategy gained (+11.63%) but underperformed SPY (+20.13%)
3. **2025 YTD:** Sector rotation away from tech → strategy lost (-14.95%)

The 126d lookback + equal-weight top-3 was calibrated on 2019-2022 (post-GFC, pre-AI boom) where sector rotation was the dominant pattern. The 2020-2022 period had rising interest rates and commodity supercycles that favored rotation, while 2023-2025 has been dominated by mega-cap tech concentration.

### Top Holdings (OOS, 21 rebalances)
| Sector | Frequency | % of rebalances |
|--------|-----------|-----------------|
| XLF | 16 | 76.2% |
| XLK | 11 | 52.4% |
| XLY | 10 | 47.6% |
| XLI | 9 | 42.9% |
| XLU | 8 | 38.1% |
| XLRE | 4 | 19.0% |
| XLE | 3 | 14.3% |

## Closure Actions

1. **Do NOT resurrect S-028** with same parameters (126d, Top-3, long-only).
2. **Do NOT run S-028b** (long/short) as a rescue variant.
3. **Broader mechanism** "equity momentum may be regime-dependent" remains OPEN under `factory/open_theses/momentum_mechanism_open.md`.
4. Any future momentum test must be a **NEW preregistered hypothesis** with rule-based adaptations derived on holdout only.

## Verdict History
- Holdout (2015-2018): Selected 126d/Top-3 (Sharpe 2.25)
- IS (2019-2022): SURVIVE (Sharpe 4.033, CAGR 15.90% > SPY 11.19%)
- OOS (2023-2025): KILL (CAGR -3.84% vs SPY +20.13%)

**verdict_hash:** dc888811d1c5736d

**Commit:** 7e0ee9c (OOS audit), pushed.
