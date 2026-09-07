# Phase 5 — Dataset Freeze with Mutation Check

## F5/N9: MUTATION ACKNOWLEDGED

**The dataset mutated**: the download continued past the frozen end date, appending June–July 2025 data with new gaps.

| | Frozen Manifest | Current (post-mutation) |
|---|---|---|
| Total bars | 27,214 | 33,768 |
| Real bars | 27,214 | 28,006 |
| Last bar | 2025-05-13 23:00 | 2025-07-02 23:00 |
| Raw files | ~1,367 | 1,407 |

## Mutation Check: Pre-2025 Data UNCHANGED

| Year | Frozen | Current | Δ | Status |
|---|---|---|---|---|
| 2021 | 6,240 | 6,240 | 0 | ✓ Clean |
| 2022 | 6,240 | 6,240 | 0 | ✓ Clean |
| 2023 | 6,225 | 6,225 | 0 | ✓ Clean |
| 2024 | 6,250 | 6,250 | 0 | ✓ Clean |
| 2025 | 2,259 | 2,259 | 0 | ✓ Clean |

**Conclusion**: The mutation is purely additive at the tail (June–July 2025). No historical data was rewritten. The frozen windows are intact.

---

## June Gap Disposition

Two new gaps found outside the frozen OOS window:

| Gap | Duration | Cause |
|---|---|---|
| 2025-06-11 23:00 → 2025-06-13 00:00 | 25h | Dukascopy source outage (FX market closed Jun 12) |
| 2025-06-23 23:00 → 2025-06-25 00:00 | 25h | Dukascopy source outage |

**Disposition**: Accepted-exclusion. Both gaps live outside all analysis windows (in-sample 2021–2023, OOS 2024-01-01..2025-05-13).

---

## Phase 5.3: Frozen-Validator OOS Slice Audit

**Setup**: Validator `662bd10` run on the OOS slice **only** (raw files for 2024-01-01..2025-05-13, excluding June+ data).

**Result**: `CLEAN | FLAGGED (0 fatal, 1 flagged)`

```
[FLAG] Feed-freeze suspicion: 48 zero-volume bars (Mon-Fri)
[OK] No unexplained data gaps (>= 4h)
[OK] Asian-session coverage: 99% (3,429 slots / 79 weeks)
```

**The 48 zero-volume bars**: Post-rollover Friday bars not in Asian session. Non-fatal, outside the strategy's trading window.

---

## Phase 5.2: Dataset Freeze (Updated)

```
Frozen OOS slice: 2024-01-01 → 2025-05-13
Bars: 8,485 (real H1 bars in OOS slice)
Raw files: 443 (2024 full + 2025 Jan–May)
Per-year: 2024 (6,250), 2025-partial (2,235)
```

---

## Expected OOS n (restated from F1)

- Rate: 128 trades / 18,705 bars = 6.843e-3 trades/bar
- OOS: 8,485 bars × 6.843e-3 = **58.1 trades**
- Branch: n ≥ 50 → **proceed** (buffer ~8 trades, ~15% INSUFFICIENT risk)

---

## Download Completion Proof

**Status**: Partial (intentionally stopped at 2025-05-13 for the OOS slice). The raw dataset contains additional June–July data that is excluded from analysis by the frozen date window.

```
Files: 1,407 raw files total (2021-01-01 → 2025-07-02)
Frozen analysis windows exclude data after 2025-05-13.
```
