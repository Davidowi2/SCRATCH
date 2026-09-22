# S-017 — MACRO GRAVITY LEAD: DXY → EURUSD Short

- KERNEL: S-017
- BATCH: S-017-BATCH-1 (Phase 2 IS run)
- PREREGISTERED: 2026-09-17, owner-approved (Macro Gravity Lead directive)
- INSTRUMENT/TF: EURUSD daily (target) + DXY daily (DTWEXBGS, trigger)
- DATA:
  - prices: research/data/eurusd_1h.csv (Gate-1 validated via S-015 pipeline, sha c90278f9...)
  - dxy: research/data/dxy_daily_2018_2025.csv (FRED DTWEXBGS, sha pending)

## MECHANISM

Macro gravity lead: when the US Dollar Index (DXY) spikes to an extreme
>2.0 SD above its 20-day mean, it signals a strong-dollar regime that
pressures EURUSD. Enter SHORT EURUSD the next day at open. The trade
uses the modular Trade Manager for dynamic exit.

## TRIGGER (LOCKED)

1. Compute DXY 20-day simple moving mean (SMM) and standard deviation (SD).
2. Z-score = (DXY_close - SMM_20) / SD_20.
3. SIGNAL: Z-score > 2.0 (DXY extreme strength breakout).
4. Entry: SHORT EURUSD at the open of the NEXT business day.
5. One position at a time — skip signals while in position.

## TRADE MANAGEMENT (Trade Manager v1, wired for first time)

- Stop Loss: 1.5 x ATR(14) placed at signal bar.
- Management: move stop to breakeven when unrealized >= +1R.
- Trail: after BE trigger, trail stop behind previous day's high (SHORT).
- Scale out: take 50% profit at +2R, trail remainder with prior-day-high trail.
- Max hold: 15 days (prevents runaway if trend stalls).

## FEES

- Friction: 0.5 pips per side (standard Spot FX), 1.0 pips round trip.
- PIP = 0.0001 for EURUSD.

## FILL CONVENTIONS (FACTORY-WIDE)

- R1: stop evaluated before target each bar; one bar touching both = LOSS.
- Exits processed bar-by-bar with OHLC high/low for stop/target hits.

## WINDOWS (FROZEN)

- IS:  2021-01-01 .. 2023-12-31
- OOS: 2024-01-01 .. 2025-05-13 (one-shot, gated, NOT touched until IS verdict)

## GATES

- n>=50 for verdict; PF<1.0 KILL; WR<45% KILL; PF<1.15 DANGER-ZONE;
  PF>=1.15 PASS; unrounded. OOS WR-drop > 15pp = KILL.
- Verdict gate applies to NET PF.
- Autopsy classifier (friction=0 gross): gross clears ALL gates →
  TUNING-SHORT; else MECHANISM-DEAD.
- One shot via batch ledger.

## SURVIVE CRITERION (pre-registered)

- SURVIVE: net PF >= 1.0 AND bootstrap 90% CI lower >= 1.0 AND mean net ret > 0.
- INCONCLUSIVE: net PF >= 1.0 BUT CI lower < 1.0 (small sample).
- KILL: net PF < 1.0.
- Bootstrap over IS trade sequence; note iid caveat.

## ADDENDUM — DATA NOTE

DXY (DTWEXBGS) starts 2006-01-02 from FRED. EURUSD H1 starts 2018-01-03.
Signal alignment: DXY z-score computed on DXY daily; EURUSD entry uses
the next-day open from the H1 pipeline (same as S-015 daily aggregation).
