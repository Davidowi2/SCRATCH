# Phase 1 Results

## 1.1 Data Manifest

**Full dataset:**
- First bar: 2021-01-03 22:00:00
- Last bar:  2025-05-13 23:00:00
- Total bars: 27,214

**OOS slice (2024-01-01 → last actual bar):**
- First bar: 2024-01-01 22:00:00
- Last bar:  2025-05-13 23:00:00
- Total bars: 8,509

**Year breakdown (full):**
| Year | Bars |
|---|---|
| 2021 | 6,240 |
| 2022 | 6,240 |
| 2023 | 6,225 |
| 2024 | 6,250 |
| 2025 | 2,259 |

## 1.2 Clock Reconciliation

`date` output: Mon, Sep 7, 2026 7:22:25 PM. Kill log row dated `2026-09-07`. **Clock is correct.** No correction needed.

## 1.3 Frozen OOS Window

```
2024-01-01 .. 2025-05-13
```

Commit: 13edc7d7a89a08b63fbc5ea6df6084f7f553c088

## 1.4 Expected OOS n

In-sample: 18,705 bars, 128 trades, rate = 42.67 trades/year.

OOS: 8,509 bars = 2.33 years (2024 full + 2025 Jan-May)
Expected OOS trades: **~99 trades**

**Branch decision: expected n ≥ 50 → proceed to Phase 6 when ready.**

## 1.5 Branch Ruling

Extend OOS forward as new bars accrue (clean — defined before any OOS result).
