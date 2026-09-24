# Open Thesis: Momentum Mechanism Regime Dependence

**Status:** OPEN — requires NEW preregistration for any future test.

## The Question

Does equity momentum / trend-following work across all market regimes?

### Evidence So Far

| Experiment | Period | Regime | Result |
|------------|--------|--------|--------|
| S-028 Holdout | 2015-2018 | Low-rate, low-volatility | Sharpe 2.25 (SURVIVE) |
| S-028 IS | 2019-2022 | Rate rising, commodity supercycle | Sharpe 4.033 (SURVIVE) |
| S-028 OOS | 2023-2025 | Mega-cap tech concentration, Fed pivot | Sharpe -0.122 (KILL) |
| S-029 Seg 1 | 2010-2018 | Global growth | excess +0.076% (survives) |
| S-029 Seg 2 | 2019-2022 | Pandemic + recovery | excess +0.060% (survives) |
| S-029 Seg 3 | 2023-2025 | Tech dominance | excess -0.004% (fails) |

### Pattern

Momentum/trend strategies performed well in **2010-2022** (diversified economy, rising rates, commodity cycles, post-GFC normalization). They **degraded** in **2023-2025** where:
- Mega-cap tech (AAPL, MSFT, NVDA, GOOG) dominated S&P 500 returns (≈50% of gains in 2024-2025)
- Sector rotation flattened as capital concentrated in "the magnificent 7"
- Equal-weight sector rotation missed the concentrated rally
- The "momentum" was stock-level, not sector-level

## Rules for Future Momentum Tests

Any future momentum experiment MUST:

1. **Be a NEW preregistered hypothesis** (new S-XXX number, new factory/preregistrations file).
2. **Adaptations must be rule-based and derived on holdout only** — the 2015-2018 window.
   - Examples: regime filters, concentration-adjusted weighting, hybrid single-stock + sector approach.
3. **No discretionary post-OOS rescue filters** — if S-028 OOS failed, the failure stands; new hypotheses must be independent.
4. **No parameter tweaking after seeing IS/OOS failure** — the 126d/Top-3 combination is locked for S-028.
5. **Include a macro regime classifier** — any new momentum test must explicitly define which regime(s) it targets and how regime is measured at signal time (no lookahead).
6. **Report both absolute and risk-adjusted metrics** — CAGR alone is insufficient when SPY delivers +20% CAGR in certain regimes.

## Open Sub-Hypotheses

- H1: Sector momentum fails when SPY concentration (top-10 weight) exceeds 30%. Test: add concentration filter.
- H2: Single-stock momentum (top-5 S&P 500 stocks by 126d return) survives the 2023-2025 regime. Test: S-033b.
- H3: Volatility targeting (scale exposure inversely to realized vol) restores Sharpe in concentrated regimes. Test: S-031 Variant E (pulse test).

## Status

OPEN — no code, no backtest. Awaiting a new preregistration that explicitly defines the regime-dependency adaptation as a rule, not a post-hoc fix.
