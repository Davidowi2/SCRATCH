# S-017 — Turn-of-Month Anomaly (BTCUSDT Perp)

- KERNEL: S-017
- BATCH: S-017-BATCH-1 (Phase 2 IS run)
- PREREGISTERED: 2026-09-22, owner-approved (FRMR closure artifact + Phase 1.5 lock)
- INSTRUMENT/TF: BTCUSDT perpetual daily (8h funding grid aligned)
- DATA: research/data/crypto/btcusdt_daily_2019_2025.csv (Gate-1 validated, sha 767c1e0e...) +
  research/data/crypto/btcusdt_fundingrate_8h.csv (sha b863792d...)

## MECHANISM

Turn-of-Month (TOM) calendar effect: institutional rebalancing flows at
month-end create a systematic price drift in the last few days of the month
and first few days of the next month. This is a pure LONG positioning:

Entry: open of the first day of the window.
Exit: close of the last day of the window.
One position per month boundary, ~6 day hold.

## WINDOW (LOCKED — NOT RE-SELECTED)

(N,M) = (3,3): last 3 days of month + first 3 days of next month.
Locked via Phase 1.5 holdout derivation (highest excess across all 9 combos,
positive in 2018 bear year).

## ENTRY/EXIT (LOCKED)

1. Window = last N_DAYS of month + first M_DAYS of next month (N=M=3).
2. Entry: open price of first window day.
3. Exit: close price of last window day.
4. Direction: LONG only (per prereg — TOM is a long-only effect).
5. One position per month boundary (no overlapping positions).
6. Hold exactly 6 calendar days (entry bar to exit bar inclusive).

## FUNDING MODEL

LONG pays funding when rate positive, receives when negative.
funding_credit = -sum(funding_rates_during_hold) * entry_price
(approximate: sum of 8h settlement rates that fall within the window)

## RAILS

- Fees: 0.05% taker each side (0.10% round trip).
- No slippage model (daily bars).
- No position sizing variation (1 contract/unit throughout).

## WINDOWS (FROZEN — NEVER SHRINK, NEVER EXTEND)

- IS:  2021-01-01 .. 2023-12-31
- OOS: 2024-01-01 .. 2025-05-13 (one-shot, gated, NOT touched)

## SURVIVE CRITERION (pre-registered)

- n >= 50
- net PF >= 1.0
- bootstrap 90% CI lower bound on mean return >= 1.0
- mean net return > 0

VERDICT:
- SURVIVE: all survive criteria pass
- INCONCLUSIVE: PF >= 1.0 but CI lower < 1.0 (small sample, no verdict)
- KILL: PF < 1.0 or mean <= 0

## GATES

- Frozen kill criteria v2.1 (n>=50; PF<1.0 KILL; WR<45% KILL; PF<1.15 DANGER;
  PF>=1.15 PASS; unrounded) + OOS WR-drop > 15pp = KILL.
- Verdict gate applies to NET PF.
- Autopsy classifier (friction=0 gross): gross clears ALL gates
  (PF>=1.15, WR>=45%, Exp>0) -> TUNING-SHORT; else MECHANISM-DEAD.
- One shot per window via batch ledger.

## ADDENDUM — DATA NOTE

BTCUSDT perp daily data starts 2019-01-01. Funding rate 8h grid
settles at 00:00/08:00/16:00 UTC. IS window 2021-01-01..2023-12-31 yields
35 month-boundary windows.
