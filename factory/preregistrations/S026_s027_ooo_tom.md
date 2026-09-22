# S-026/S-027 — Out-of-Asset TOM Expansion

- KERNEL: S-026 (IWM), S-027 (QQQ)
- BATCH: S-026-BATCH-1
- PREREGISTERED: 2026-09-22
- INSTRUMENT/TF: IWM daily, QQQ daily (plus SPY for baseline comparison)
- DATA:
  - IWM: research/data/equity/iwm_daily_2010_2025.csv (3864 bars, sha=b3e58cee)
  - QQQ: research/data/equity/qqq_daily_2010_2025.csv (3864 bars, sha=583fbb90)
  - SPY: research/data/equity/spy_daily_2010_2025.csv (3864 bars, sha=9b9d1f6e)
- SOURCE: Yahoo Finance via tools/download_etf_daily.py

## MECHANISM

The LOCKED (N,M) = (3,3) TOM window [from S-024 SPY holdout] applied to
IWM (Russell 2000) and QQQ (Nasdaq 100). This is inherently out-of-asset —
the SPY-derived parameter is tested on different underlying instruments.

Entry: Open of first TOM window day (last 3 of month + first 3 of next).
Exit: Close of last TOM window day.
Fees: 0.02% round-trip (highly liquid ETFs).

## WINDOW (LOCKED)

(N, M) = (3, 3), L = 6 days. No optimization. No parameter selection.

## BASELINE

For each asset: mean return of ALL 6-day windows over the full 2010-2025 period.
Excess = TOM mean - baseline mean.

## VERDICT CRITERIA

- Excess > 0 → PORTFOLIO CANDIDATE (pension flow exists here)
- Excess ≤ 0 → KILL (no pension flow on this asset)

## RESULTS (Full 2010-2025)

```
Asset    | n_windows | TOM_mean% | baseline% | excess%  | WinRt | MaxDD  | Viable
---------------------------------------------------------------------------
SPY      |    184    |  +0.380%  |  +0.255%  | +0.1252% | 57.1% | -0.15% | ✓
IWM      |    184    |  +0.237%  |  +0.190%  | +0.0467% | 51.1% | -0.24% | ✓
QQQ      |    184    |  +0.483%  |  +0.368%  | +0.1153% | 59.8% | -0.18% | ✓
```

All three assets show positive excess → all 3 are PORTFOLIO CANDIDATES.

The pension-flow anomaly is NOT SPY-specific — it generalizes to IWM (small-cap)
and QQQ (tech large-cap). The excess is smaller for IWM (+0.047%) vs SPY/QQQ
(+0.125% / +0.115%), but still positive. This makes economic sense: small-cap
stocks have weaker institutional pension flow concentration than large/mid-cap.

## CLOSURE

S-026 (IWM) and S-027 (QQQ) both SURVIVE. The TOM window is a generalizable
calendar anomaly across US equity ETFs.
