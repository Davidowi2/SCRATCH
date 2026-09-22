# S-015 — Overnight Gap Fade (EURUSD)

- KERNEL: S-015
- BATCH: GAP-1 (Phase 3C)
- PREREGISTERED: 2026-09-22, owner-approved (Phase 3C directive)
- INSTRUMENT/TF: EURUSD daily (aggregated from H1)
- DATA: research/data/eurusd_1h.csv (Gate-1 validated, sha c90278f9...)
- MECHANISM: Fade the overnight gap. When price gaps down at the daily open
  (open < previous close), enter LONG at the daily open, targeting a reversion
  to the previous close. Hypothesis: intraday gaps partially fill within the
  session, especially in FX where liquidity resets create transient dislocations.
- MIRROR of H-01 lineage: Uses the same H1 Dukascopy data pipeline that
  H-001 (EURUSD mean reversion) used. If S-015 works, H-001 paper lane gets
  a fresh validation path.

## MATH (LOCKED)

1. GAP DEFINITION:
   - Gap = daily_open − previous_close
   - LONG trigger: gap < 0 (price gapped DOWN)
   - SHORT trigger: gap > 0 (price gapped UP)
   - Both directions tested — the thesis is symmetric gap fill.

2. DAILY AGGREGATION:
   - Daily bar = [00:00 UTC, 23:59 UTC] for each calendar day
   - Daily open = first H1 bar's open
   - Daily close = last H1 bar's close
   - Daily high = max of all H1 highs
   - Daily low = min of all H1 lows
   - Only days with complete 24 bars are used (incomplete days skipped).

3. ATR(14) on daily bars:
   - True range = max(high − low, |high − prev_close|, |low − prev_close|)
   - ATR(14) = mean of last 14 true ranges
   - EMA Wilder smoothing NOT used (simple mean, consistent with S-001 lineage).

4. ENTRY: Daily open (the open of the first H1 bar of the day).

5. STOP:
   - LONG: entry − 1.0 × ATR(14)
   - SHORT: entry + 1.0 × ATR(14)

6. TARGET: Previous close (the close of the prior daily bar).
   - LONG: target = previous close
   - SHORT: target = previous close

7. MAX HOLD: 1 day (exit at end of session if stop/target not hit).
   - End of session = last H1 bar of the day.

8. ONE POSITION at a time.

9. FRICTION: 0.5 pips (consistent with EURUSD lineage).

## FILL CONVENTIONS (FACTORY-WIDE)

- R1: stop evaluated before target every bar; one bar touching both =
  LOSS (stop takes priority).

## WINDOWS (FROZEN — NEVER SHRINK, NEVER EXTEND)

- IS:  2021-01-01 .. 2023-12-31
- OOS: 2024-01-01 .. 2025-05-13 (one-shot, gated, NOT touched)

## GATES

- Frozen kill criteria v2.1 (n>=50; PF<1.0 KILL; WR<45% KILL; PF<1.15 DANGER;
  PF>=1.15 PASS; unrounded) + OOS WR-drop > 15pp = KILL.
- Verdict gate applies to NET PF.
- Autopsy classifier (friction=0 gross): gross clears ALL gates
  (PF>=1.15, WR>=45%, Exp>0) → TUNING-SHORT; else MECHANISM-DEAD.
- One shot per window via batch ledger.

## ADDENDUM — DATA NOTE

The H1 data starts 2021-01-03 (not 2021-01-01). The first complete daily
day is 2021-01-04. The IS window is effectively 2021-01-04..2023-12-31.
