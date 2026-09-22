# S-014 — FRMR (Funding Rate Mean Reversion) Kernel (BTCUSDT 5m)

- KERNEL: S-014
- BATCH: FRMR-1 (Phase 3B)
- PREREGISTERED: 2026-09-22, owner-approved (Phase 3B directive)
- INSTRUMENT/TF: BTCUSDT USD-M PERPETUAL, 5m bars with 8h funding settlements
- DATA:
  - funding: research/data/crypto/btcusdt_fundingrate_8h.csv (sha a6e42ffb...)
  - prices: research/data/crypto/btcusdt_5m_tradecount_is_2021_2023.csv (sha 63b02ddd...)
- MEAN-REVERT the funding rate. When F is high positive, perp is expensive → SHORT
  (collect funding credit). When F is deep negative, perp is cheap → LONG.
  Hypothesis: funding rate predicts SHORT-TERM mean reversion in the basis,
  and the funding credit provides a tailwind.

## THRESHOLDS (FROZEN — Overseer pre-reg, Phase 3A distribution report)

```
SHORT trigger: F >= +0.05%  (0.0005 decimal)
LONG  trigger: F <= -0.05%  (-0.0005 decimal)
```

Pre-registration justification (Overseer, Phase 3A):
"The 0.05% threshold lands at P95 of the IS distribution (P95=0.058%),
yielding ~207 events over 3 years (~5.8/month). This is extreme enough to
represent a genuine basis dislocation but frequent enough for statistical
validation. The threshold is principled (P95) and pre-committed BEFORE seeing
any P&L, avoiding selection bias."

## MATH (LOCKED)

1. TRIGGER: funding rate F at settlement boundary (00/08/16 UTC) crosses threshold.
2. DIRECTION:
   - SHORT when F >= +0.05%
   - LONG  when F <= -0.05%
3. ENTRY: open of the FIRST 5m bar AFTER the settlement timestamp.
   (If settlement is at 00:00 UTC, entry at 00:05 UTC bar open.)
4. HOLD: EXACTLY one funding interval (8h). Exit at the NEXT settlement's open.
   FIXED HORIZON — no early exit. No management. Naked-entry baseline.
5. EXIT: open of the 5m bar at the next settlement boundary.
6. ONE POSITION at a time. Skip signals while a position is open.
7. PnL DECOMPOSITION (three series reported per trade):
   - price_only: (exit_price - entry_price)  [or mirrored for SHORT]
   - price_plus_funding: price_only + funding_credit
   - net: price_plus_funding - fees
8. FUNDING MODEL:
   - Funding credit = F * entry_price * notional (applied at exit boundary)
   - SHORT + positive F → CREDIT (receive funding)
   - LONG + negative F → CREDIT (receive funding)
   - SHORT + negative F → DEBIT (pay funding)
   - LONG + positive F → DEBIT (pay funding)
9. FEES: 0.05% taker per leg (0.10% round-trip). Applied to entry + exit notional.
10. PRE-FLAG: Long arm expected INSUFFICIENT (n~5 in IS). Only short arm is
    the primary test.

## WINDOWS (FROZEN)

- IS:  2021-01-01 .. 2023-12-31
- OOS: 2024-01-01 .. 2025-05-13 (one-shot, gated, NOT touched)

## GATES

- Frozen kill criteria v2.1 (n>=50; PF<1.0 KILL; WR<45% KILL; PF<1.15 DANGER;
  PF>=1.15 PASS; unrounded) + OOS WR-drop > 15pp = KILL.
- Verdict gate applies to NET PF.
- Autopsy classifier (friction=0 gross = price_plus_funding): gross clears ALL
  gates → TUNING-SHORT else MECHANISM-DEAD.
- One shot per window via batch ledger.

## ADDENDUM — INSUFFICIENT ARM POLICY

Long arm (F <= -0.05%) expected n~5 in IS. If long arm has n<50, it is reported
separately but does NOT contribute to the verdict. The short arm (n~202) is the
primary test. If the short arm passes, the long arm can be re-examined in Phase
4 with a relaxed window or a lower threshold (not in frozen IS/OOS).
