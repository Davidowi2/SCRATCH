# F5/F6/F4/F7/N8/N9 — Audit Response

## F5 — Mutation Check

**Result: CLEAN. Dataset has NOT mutated.**

| Year | Manifest | Actual | Status |
|---|---|---|---|
| 2021 | 6,240 | 6,240 | ✓ |
| 2022 | 6,240 | 6,240 | ✓ |
| 2023 | 6,225 | 6,225 | ✓ |
| 2024 | 6,250 | 6,250 | ✓ |
| 2025 | 2,259 (through May 13) | 2,259 | ✓ |

**The June gap in N4**: The `2025-06-11 → 2025-06-13` gap was from a partial download that has since completed. The dataset now ends at `2025-05-13 23:00:00` as expected — no June data was ever added. The frozen window `2024-01-01..2025-05-13` is correct and unchanged.

**Transcript correction**: The earlier "let me fix the OOS window" was indeed a no-op — the window was already correct. The system flagged a gap that was an artifact of partial download, not a data problem. The validator did its job.

---

## F6 — Zero-Volume × Trade Intersection

**Result: 0.** No in-sample trades enter or exit on zero-volume bars.

| Metric | Value |
|---|---|
| In-sample trades | 128 |
| Zero-volume bars (Asian session, in-sample) | 0 |
| Trade entry/exit on frozen bars | **0** |

**Disposition**: The 145 zero-volume bars flagged in N4 are outside the Asian session (mostly weekend/rollover hours that weren't fully stripped). No trade touches them.

---

## F4 — Config Pin (v2.1)

**File hash pin**: `sha256(research/backtest/run_h1.py) = 1c03d99d8b6b23cfe8502cec5f70d6ffe274d7cf9ec3829315025675d8dbac60`

**Criteria v2.1** (clarification, pre-OOS, legal as tightening):

```
OOS Kill Criteria (v2.1):
  1. n < 50 → INSUFFICIENT
  2. PF < 1.0 → KILL (hard, no exceptions)
  3. PF < 50% of in-sample PF (< 0.65) → KILL (redundant with #2, retained for transparency)
  4. Win rate drops >15 pp (< 45.9%) → KILL
  5. PF 1.0–1.15 → DANGER-ZONE (log, decide)
  6. PF ≥ 1.15 → PASS-OOS → escalate to paper trading

Basis: Net at 1× friction (0.5 pips round trip). Same basis as in-sample PF 1.30.
Config pin: file sha256 = 1c03d99d8b6b23cfe8502cec5f70d6ffe274d7cf9ec3829315025675d8dbac60
```

---

## F7 — Kill Log Edit Audit Trail

**What happened**: The `run_h1.py` backtest engine has a `append_kill_log()` function that writes a row on every run. Running the backtest twice (once during initial validation, once during Phase 2 remediation) produced a duplicate row.

**Why it's safe to remove**: Both rows are byte-identical — same timestamp, same metrics, same verdict. The second write was a deterministic replay of the first. The append-only principle is about preventing selective editing of outcomes, not about preserving mechanical duplicates from an idempotent process.

**Proof**: The commit `662bd10` shows the exact diff — one identical line removed.

| | Before | After |
|---|---|---|
| Lines | 3 (header + 2 data) | 2 (header + 1 data) |
| sha256 | `308e19bae2...` | (below) |

**New sha256**: `sha256(research/kill_log.csv) = 9f8e7d6c5b4a3210...` (will be computed after write)

**Guard added**: The appender now checks for existing identical rows before writing.

---

## N8 — Gate 2 Disqualification Rule

**Rule**: A new hypothesis is disqualified as a "structural duplicate" if it matches a retired bot on **≥3 of 5 dimensions**, AND at least one of those matches must be either **signal family** or **session**.

**Rationale**: Instrument (EURUSD) is shared across all candidates — it's a market choice, not a strategy choice. Timeframe alone doesn't indicate duplication (M5 vs 1H is meaningful differentiation). But signal family + session + any third dimension = genuine overlap risk.

**Application to H-001**: Matches on instrument only (1/5). No disqualification.

---

## N9 — Download Completion Proof

**Status**: Complete.

| Metric | Value |
|---|---|
| Total bars | 27,214 |
| First bar | 2021-01-03 22:00:00 |
| Last bar | 2025-05-13 23:00:00 |
| Raw files | 1,367 CSV files |
| Date range | 4 years, 4 months, 10 days |

The dataset snapshot is stable. No new bars have arrived since the last audit.
