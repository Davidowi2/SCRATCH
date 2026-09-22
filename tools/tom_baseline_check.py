#!/usr/bin/env python3
"""
tools/tom_baseline_check.py — S-017 Phase 1.5: extended holdout + baseline check.

Distinguishes genuine TOM calendar effects from drift/beta.
NO IS test. NO kernel. NO P&L on IS data.
"""

import csv
import os
from datetime import datetime, timezone

HOLDOUT_START = datetime(2018, 1, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2020, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
N_GRID = [1, 2, 3]
M_GRID = [1, 2, 3]

SPOT_FILE = "research/data/crypto/btcusdt_spot_daily_2018_2020.csv"
PERP_FILE = "research/data/crypto/btcusdt_daily_2019_2025.csv"


def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({
                "time": ts,
                "date": ts.date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    rows.sort(key=lambda r: r["time"])
    return rows


def filter_holdout(rows):
    return [r for r in rows if HOLDOUT_START <= r["time"] <= HOLDOUT_END]


def identify_tom_windows(daily, n, m):
    months = {}
    for d in daily:
        ym = (d["date"].year, d["date"].month)
        if ym not in months:
            months[ym] = []
        months[ym].append(d)

    windows = []
    for ym in sorted(months.keys()):
        month_days = months[ym]
        last_n = month_days[-n:] if len(month_days) >= n else month_days

        if ym[1] == 12:
            next_ym = (ym[0] + 1, 1)
        else:
            next_ym = (ym[0], ym[1] + 1)

        if next_ym not in months:
            continue
        next_days = months[next_ym]
        first_m = next_days[:m] if len(next_days) >= m else next_days

        if not last_n or not first_m:
            continue

        entry_date = last_n[0]["date"]
        exit_date = first_m[-1]["date"]
        entry_dt = datetime.combine(entry_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        exit_dt = datetime.combine(exit_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        if entry_dt < HOLDOUT_START or exit_dt > HOLDOUT_END:
            continue

        windows.append({
            "entry_price": last_n[0]["open"],
            "exit_price": first_m[-1]["close"],
            "n_days": len(last_n) + len(first_m),
        })

    return windows


def identify_all_windows(daily, window_len):
    """All contiguous windows of length window_len."""
    windows = []
    for i in range(len(daily) - window_len + 1):
        entry = daily[i]["open"]
        exit = daily[i + window_len - 1]["close"]
        windows.append({"entry_price": entry, "exit_price": exit})
    return windows


def mean_return(windows):
    if not windows:
        return 0.0
    rets = [(w["exit_price"] - w["entry_price"]) / w["entry_price"] for w in windows]
    return sum(rets) / len(rets)


def win_rate(windows):
    if not windows:
        return 0.0
    wins = sum(1 for w in windows if w["exit_price"] > w["entry_price"])
    return wins / len(windows)


def main():
    print("=" * 72)
    print("S-017 Phase 1.5 — Extended Holdout + Baseline Check")
    print("2018-2020 (spot + perp where available)")
    print("=" * 72)

    spot = load_csv(SPOT_FILE)
    spot_h = filter_holdout(spot)
    print(f"Spot holdout bars: {len(spot_h)}")
    if spot_h:
        print(f"  Range: {spot_h[0]['date']}..{spot_h[-1]['date']}")

    perp = load_csv(PERP_FILE)
    perp_h = filter_holdout(perp)
    print(f"Perp holdout bars: {len(perp_h)}")

    # Use spot for the baseline check (longer history, no funding)
    daily = spot_h

    # Grid search on extended holdout
    print(f"\n{'='*72}")
    print("EXTENDED GRID SEARCH (2018-2020)")
    print(f"{'='*72}")
    print(f"{'N':>3} | {'M':>3} | {'n_win':>6} | {'mean_ret%':>10} | {'win_rate':>9} | {'n_days':>6}")
    print("-" * 55)

    best = None
    for n in N_GRID:
        for m in M_GRID:
            windows = identify_tom_windows(daily, n, m)
            if not windows:
                continue
            mr = mean_return(windows)
            wr = win_rate(windows)
            n_days = windows[0]["n_days"] if windows else 0

            if best is None or mr > best["mean_ret"]:
                best = {"n": n, "m": m, "mean_ret": mr, "win_rate": wr, "n_windows": len(windows), "n_days": n_days}

            print(f"{n:>3} | {m:>3} | {len(windows):>6} | {mr*100:>+9.4f}% | {wr:>8.1%} | {n_days:>6}")

    # Baseline: all windows of same length
    print(f"\n{'='*72}")
    print("BASELINE CHECK")
    print(f"{'='*72}")

    if best:
        window_len = best["n_days"]
        all_windows = identify_all_windows(daily, window_len)
        baseline_mean = mean_return(all_windows)
        baseline_wr = win_rate(all_windows)

        print(f"Selected (N,M) = ({best['n']},{best['m']}), window_len = {window_len} days")
        print(f"  TOM windows:     n={best['n_windows']}, mean={best['mean_ret']*100:+.4f}%, WR={best['win_rate']:.1%}")
        print(f"  Baseline windows: n={len(all_windows)}, mean={baseline_mean*100:+.4f}%, WR={baseline_wr:.1%}")
        print(f"  DIFFERENCE:      {(best['mean_ret'] - baseline_mean)*100:+.4f}%")

        # Verdict
        meaningful_excess = (best["mean_ret"] - baseline_mean) > 0.005  # >0.5% excess
        clear_winner = best["mean_ret"] > 0

        if clear_winner and meaningful_excess:
            verdict = "VIABLE"
            reason = "TOM mean meaningfully exceeds baseline → genuine calendar effect"
        elif clear_winner:
            verdict = "NON-VIABLE (artifact: regime/beta)"
            reason = "TOM mean ≈ baseline → effect is drift, not calendar anomaly"
        else:
            verdict = "NON-VIABLE"
            reason = "No positive TOM effect"

        print(f"\n{'='*72}")
        print("VERDICT")
        print(f"{'='*72}")
        print(f"{verdict}: {reason}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
