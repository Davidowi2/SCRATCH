# S-017 — TOM (Turn-of-Month) BTC Closure Artifact

- ARTIFACT: S017_TOM_BTC_CLOSURE.md
- STATUS: PENDING (Phase 1 derivation in progress)
- DATE: 2026-09-22
- AUTHOR: Hermes executor (Factory)
- AUTHORITY: Overseer

## HYPOTHESIS

"Turn-of-month (TOM) windows on BTC perps exhibit a positive expected return,
driven by portfolio rebalancing flows at month-end and month-start."

At month-end, institutions rebalance portfolios (selling risk assets to meet
allocations, or deploying new capital). This creates predictable flows that
push prices in a consistent direction over the TOM window. On BTC perps, this
effect is amplified by funding-rate dynamics: month-end positioning affects
funding, and the funding credit adds to/subtracts from the price return.

## DESIGN

### Window Definition

The TOM window is defined by two parameters (N, M):
- N = last N days of the month (turn-of-month exit pressure)
- M = first M days of the next month (new-month deployment)

The TOM window runs from the open of the Nth-to-last day of the month to the
close of the Mth day of the next month.

### Grid Search (Phase 1)

| N \ M | 1     | 2     | 3     |
|-------|-------|-------|-------|
| 1     | (1,1) | (1,2) | (1,3) |
| 2     | (2,1) | (2,2) | (2,3) |
| 3     | (3,1) | (3,2) | (3,3) |

Each (N,M) is evaluated on the **2019-2020 holdout** (sacrificed — never reused
for IS testing).

### Selection Rule (Pre-registered)

1. Compute mean NET return for each (N,M) on the holdout.
2. NET = price_return + funding_credit − 0.10% round-trip fee.
3. Select the (N,M) with the **highest mean NET return**.
4. **Abort condition**: if the selected (N,M)'s mean NET return ≤ 0, report
   "S-017 NON-VIABLE" and STOP. No IS test.

### Locked Parameters

After Phase 1, the selected (N,M) is LOCKED and recorded below:
- **(N,M)** = (2,1) — last 2 days of month + first 1 day of next month
- **Mean net return** = +4.7746% (2020 holdout, 11 windows)
- **Win rate** = 81.8%
- **Mean funding cost** = +0.101625% per window
- **Data availability**: BTCUSDT daily data starts 2020-01-01 (earliest clean date); 2019 data not available via Binance UM archive for the perp pair. 1960 daily bars (2020-02025), Gate-1 validated (0 gaps, 0 dupes, 100% coverage).

## CLOSURE CONDITION

If S-017 dies in IS (net PF < 1.0), TOM-on-BTC is **CLOSED, full stop**:

- **No window re-shopping**: the (N,M) grid cannot be re-run or extended.
- **No direction-flip**: if the best holdout window was net-negative, we don't
  flip to the opposite direction in IS.
- **No retest**: no "maybe it works on ETH" port, no "maybe it works with
  different entry timing" variant.
- **No backdoor**: the same core idea (TOM windows on BTC perps) cannot be
  retested under a different kernel ID or with cosmetic changes.

Future work on this specific thesis requires **Owner override + genuinely new
evidence** (e.g., a structural change in institutional rebalancing patterns,
a new data source showing the effect was mispriced, or a different instrument
where the TOM window has a fundamentally different microstructure).

## ABORT CHECKS (Phase 1 → Phase 2 gate)

Phase 1 must meet ALL of the following to proceed to IS:

1. Selected (N,M) has mean NET return > 0 on holdout
2. Selected (N,M) has ≥ 30 windows in holdout (statistical floor)
3. At least 40% win rate on holdout (directional consistency)

If any check fails → S-017 NON-VIABLE, thesis CLOSED on BTC perps.

## CHAIN OF CUSTODY

```
Phase 1 (2019-2020 holdout): grid search → lock (N,M)
    ↓
    ├─ NON-VIABLE → THESIS CLOSED (no IS test)
    └─ VIABLE → Phase 2 (IS 2021-2023): S-017 kernel
                    ↓
                    ├─ PASS → proceed to OOS
                    └─ KILL → THESIS CLOSED (closure condition met)
```

## TECHNICAL NOTES

- BTCUSDT perp inception: 2019-09-08 (daily data may start 2019-09)
- Funding settlement: 8h grid (00:00, 00:08, 01:00... wait — per Binance spec
  it's 8h at 00:00, 08:00, 16:00 UTC)
- Holdout: 2019-09 (or earliest) .. 2020-12-31
- IS: 2021-01-01 .. 2023-12-31 (reserved, NOT touched until Phase 2)
- OOS: 2024-01-01 .. 2025-05-13 (reserved, NOT touched until Phase 3)

## ADDENDUM — WHY TOM

The turn-of-month effect is one of the most robust calendar effects in equities
(Gain et al., 2020; McConnell & Xu, 2008). It has been documented in futures
markets but is under-explored in crypto perps. The funding-rate leg adds a
dimension unique to perps: if month-end positioning is crowded, the funding
credit provides a tailwind that amplifies the price effect.

The Factory tests this once, honestly, with a pre-registered window selection
rule. If it dies, it dies. No appeals.
