# FRMR BTC Perps — Closure Artifact

- ARTIFACT: FRMR_BTC_PERPS_CLOSURE.md
- STATUS: CLOSED on BTC perps (pending S-016 valid test)
- DATE: 2026-09-22
- AUTHOR: Hermes executor (Factory)
- AUTHORITY: Overseer

## THESIS (the original idea)

"Extreme-funding carry + crowded-positioning reversion is profitable after fees, on BTC perps."

When the funding rate is extreme-positive, the perp is crowded long. Shorting at that moment captures the funding credit (the longs pay you to hold the short) AND benefits from mean-reversion in the basis. Net of fees, the carry should be positive.

## LINEAGE

### S-014 (Model A) — MECHANISM-DEAD, but NOT a valid test

- **Design:** Entry at first 5m bar AFTER settlement boundary. Exit 8h later at next settlement. Funding credit = F_T (the realized rate at the EXIT settlement).
- **Result:** Short arm n=202, net PF=0.9668, KILL/MECHANISM-DEAD.
- **BUG (not a feature):** S-014 entered AFTER the funding snapshot at T. It captured F_{T+8h} (the NEXT settlement's rate), NOT F_T (the rate at the entry settlement). The thesis is about capturing the funding PAYMENT — which is determined by the rate AT the moment you enter (F_T), not 8h later.
- **Why it matters:** F_T and F_{T+8h} are different realizations. S-014 was structurally unable to capture the carry the thesis is about. Its death proves nothing about the thesis.
- **Verdict:** S-014 is INVALID as a test of the FRMR thesis. It was a timing bug, not a reframing. The thesis remains untested.

### S-016 (Model B) — the FIRST valid test

- **Design:** Signal on F_{T-8h} (previous settlement's rate, known at entry). Entry at the bar FOLLOWING settlement T. Funding credit = F_T (realized at exit 8h later, which IS the rate determined at entry T).
- **Why valid:** The signal F_{T-8h} is lookahead-free (known before entry). The credit F_T is the actual payment received. The test is structurally correct.

## CLOSURE CONDITION

If S-016 dies (net PF < 1.0 on the IS window), the FRMR thesis is **CLOSED on BTC perps, full stop**:

- No entry-timing variants (Model C)
- No "maybe it works on ETH" port
- No backdoor retest of the same core idea (e.g., different threshold, different horizon, same signal family)
- No relaxation of the thesis to "extreme carry" without the mean-reversion component

Future work on this specific thesis requires **Owner override + genuinely new evidence** (e.g., a structural change in the funding mechanism, a new data source showing the carry was mispriced, or a different instrument where the fee structure is fundamentally different).

## TECHNICAL NOTES

- Funding credit on Binance UM: 0.01% per 8h settlement (paid by longs to shorts when F > 0).
- Round-trip taker fee: 0.10% (0.05% per leg).
- Required carry margin: > 0.10% per trade (to break even on fees).
- 2020 holdout used for threshold derivation (IS 2021-2023 reserved for test).

## CHAIN OF CUSTODY

```
S-014 (Model A) → MECHANISM-DEAD (invalid test, timing bug)
    ↓
S-016 (Model B) → FIRST VALID TEST (lookahead-free signal)
    ↓
    ├─ PASS → thesis validated, proceed to OOS
    └─ KILL → THESIS CLOSED (closure condition met)
```

## ADDENDUM — WHY THIS DOCUMENT EXISTS

The Factory does not re-test dead ideas. But it also does not kill ideas based on buggy tests. S-014 was a bug. This artifact records that fact so the Overseer can distinguish between "the idea was tested and died" (closed, no retest) and "the idea was never properly tested" (open, valid to test once more with correct design).

S-016 is the one-shot test. If it dies, the idea dies with it. No appeals, no variants, no ports.
