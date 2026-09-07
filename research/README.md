# Research Platform (roadmap v2, Phase 1.5)

Implements the validation-first pipeline from `quant-research-roadmap-v2-multi-ai-consolidated.md`.
Built incrementally: only what Hypothesis #1 (H-001) needs.

```
download_dukascopy.py ──► raw/ (per-day H1 CSV) ──► validate_data.py ──► eurusd_1h.csv (cleaned)
        (Gate 0: acquire)            │                    (Gate 1)               │
                                     │              data_audit.log               ▼
                                     │                                   run_h1.py (backtest)
                                     │                                   + kill criteria + kill_log.csv
```

## Pipeline steps

### 1. Download (run once per date range, resumable)

```bash
# From the repo root. One request per trading day (M1 file resampled to H1).
# ~35-50s/day on a throttled datacenter IP; faster from a residential IP.
python research/data/download_dukascopy.py --start 2021-01-01 --end 2025-12-31
```

- Writes `research/data/raw/EURUSD_H1/YYYY-MM-DD.csv`, one file per day.
- Resumable: existing day files are skipped. Re-run to retry failed days.
- Saturdays are skipped automatically (Dukascopy files contain filler only).
- The feed rate-limits this IP (HTTP 503); the script crawls patiently and
  logs progress to `research/data/download_progress.log`.

### 2. Validate (Gate 1 — mandatory before any backtest)

```bash
python research/data/validate_data.py --raw-dir research/data/raw/EURUSD_H1 \
                                      --dataset-out research/data/eurusd_1h.csv
```

Checks (calibrated to Dukascopy's FX week: Sun 22:00 UTC → Fri 22:00 UTC, with
zero-volume flat filler outside it):

| Check | Rule | Action |
|---|---|---|
| Gap detection | >3 consecutive missing candles, not spanning a weekend | REJECT |
| Weekend contamination | real bar Sat, or Sun before 21:00 UTC | strip + flag |
| Zero-volume candles | volume 0 during Mon 00:00–Fri 21:59 | flag as feed freeze |
| OHLC integrity | high < low, open/close outside [low, high] | reject row + flag |
| Timestamp monotonic | duplicates / out-of-order | dedupe/sort + flag |
| Session coverage | <80% of Asian-session slots (45/week, 22:00–07:00 UTC) | REJECT |

Verdict `REJECT` means the data is unfit — the backtest refuses to run
(`run_h1.py` enforces this by re-running the audit itself).

### 3. Backtest (Hypothesis #1 — pre-committed Variant A, no tuning)

```bash
python research/backtest/run_h1.py --dataset research/data/eurusd_1h.csv \
                                   --raw-dir research/data/raw/EURUSD_H1
# in-sample window:
python research/backtest/run_h1.py ... --start 2021-01-01 --end 2023-12-31 --phase insample
# out-of-sample (separate pre-committed run, only after an in-sample PASS):
python research/backtest/run_h1.py ... --start 2024-01-01 --end 2025-12-31 --phase oos
```

Strategy (frozen): fade |Z| ≥ 2 deviations of price from SMA20 on EURUSD 1H,
entries only when the bar opens 22:00–07:00 UTC, exit on reversion inside the
1 SD band, stop 1.5 × entry-SD, max hold 8 bars, 0.5 pips friction round trip.

Every run appends a row to `research/kill_log.csv` in the roadmap's
standardized format (WHY field included, process_version = v1).

## Kill criteria (pre-committed — see roadmap Gate 5)

- n < 50 in-sample → `INSUFFICIENT` (below the statistical floor)
- PF < 1.0 → `KILL`; PF > 2.0 → `SUSPICIOUS` (likely a bug/leak, debug first)
- PF 1.0–1.15 or win rate < 45% → `KILL`
- PF 1.15–1.8 → `DANGER-ZONE`: log it, stop, no tweaks, decide tomorrow
- PF 1.8–2.0 → `PASS-INSAMPLE` → next gate is a fresh OOS run

If a verdict lands in `DANGER-ZONE` or `KILL`, do **not** edit the parameters
and re-run. That is process suicide. Pre-commit any alternative, then test it
as a separate experiment.
