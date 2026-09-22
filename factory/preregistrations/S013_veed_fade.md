# S-013 — VEED Fade Kernel (BTCUSDT 5m)

- KERNEL: S-013
- BATCH: VEED-1 (queued behind Phase 2B)
- PREREGISTERED: 2026-09-21, owner-approved (Phase 2B directive)
- INSTRUMENT/TF: BTCUSDT USD-M PERPETUAL, 5-minute bars (Binance UM klines)
- DATA: research/data/crypto/btcusdt_5m_tradecount_is_2021_2023.csv —
  Gate-1 validated, trade-count column col[8] present, sha 63b02ddd...
- SIGNAL SOURCE: VEED v1.1 detector (sha ff9b696c…) — emits event stream
  with direction label (sell-side / buy-side)
- SESSION FILTER: none (crypto 24/7)
- MECHANISM: Fade extreme-event conviction. When the market has just made
  a violent move (VEED event = trade-count outlier + conviction close),
  enter against the move at the next bar. Hypothesis: the burst exhausts
  and price reverts toward the event bar's mid-range within the hold window.

## MATH (LOCKED)

1. SIGNAL: a VEED v1.1 event (X=1%, Y=25%, N=4032, two-sided) fires at bar t.
2. DIRECTION:
   - Sell-side event (closepos ≤ 0.25) → LONG (fade the dump).
   - Buy-side event (closepos ≥ 0.75) → SHORT (fade the rally).
3. ENTRY: open of bar t+1 (the bar following the event bar).
4. STOP: event bar's extreme.
   - LONG  → stop = low(event bar)
   - SHORT → stop = high(event bar)
5. TARGET: 1.5R where R = |entry − stop| (fixed-R target).
6. ENTRY GUARD (R3): if entry bar's open gaps through the planned stop
   (risk ≤ 0), signal is discarded entirely. No trade, no deferral.
   - LONG:  entry_open ≤ stop → discard
   - SHORT: entry_open ≥ stop → discard
7. MAX HOLD: 72 bars (12 hours). If neither stop nor target is hit, exit
   at the close of bar t+72.
8. FRICTION:
   - Binance UM taker fee: 0.04% per leg (0.08% round-trip)
   - Funding: 0.01% per 8h settlement, applied to notional exposure at
     each settlement crossing while position is open
   - Friction is applied at exit (realized), not at entry
9. ONE POSITION at a time. One trade per signal event.

## FILL CONVENTIONS (FACTORY-WIDE)

- R1: stop evaluated before target every bar; one bar touching both =
  LOSS (stop takes priority); max-hold exit at close.

## WINDOWS (FROZEN — NEVER SHRINK, NEVER EXTEND)

- IS:  2021-01-01 .. 2023-12-31
- OOS: 2024-01-01 .. 2025-05-13 (one-shot, gated, NOT touched in Phase 2B)

## GATES

- Frozen kill criteria v2.1 (n>=50; PF<1.0 KILL; WR<45% KILL; PF<1.15 DANGER;
  PF>=1.15 PASS; unrounded) + OOS WR-drop > 15pp = KILL.
- Autopsy classifier (friction=0 gross): gross clears ALL gates (PF>=1.15,
  WR>=45%, Exp>0) → TUNING-SHORT; else MECHANISM-DEAD.
- One shot per window via batch ledger.

## ADDENDUM — RULING 1 (2026-09-21)

- VEED derivation denominator corrected from BARS_PER_DAY=288 to n_holdout_days
  (= 366 for the 2020 holdout). X=1% stays locked. Corrected bars/day = 3.28.
- Re-logged in the derivation event (no re-derivation of X/Y needed).

## ADDENDUM — RULING 2 (2026-09-21)

- Zero-trade bars (45 IS, 18 OOS) are legitimate brief-downtime events,
  NOT data corruption. Detector §1 guard trades(t)==0 → skip handles them.
  Zero-trade timestamps are logged in the Gate-1 probe report.
