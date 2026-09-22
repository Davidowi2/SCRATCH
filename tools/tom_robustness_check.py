#!/usr/bin/env python3
"""
tools/tom_robustness_check.py — S-017 Phase 1.6: robustness checks.

Checks regime robustness (2018 bear year) + selection-bias (excess vs
baseline per window length). NO IS. NO OOS. NO kernel.
"""

import csv
import os
from datetime import datetime, timezone

HOLDOUT_START = datetime(2018, 1, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2020, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
N_GRID = [1, 2, 3]
M_GRID = [1, 2, 3]

SPOT_FILE = "research/data/crypto/btcusdt_spot_daily_2018_2020.csv"


def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({
                "time": ts,
                "date": ts.date(),
                "year": ts.year,
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
            "year": entry_date.year,
        })

    return windows


def identify_all_windows(daily, window_len):
    """All contiguous same-length windows (baseline)."""
    windows = []
    for i in range(len(daily) - window_len + 1):
        windows.append({
            "entry_price": daily[i]["open"],
            "exit_price": daily[i + window_len - 1]["close"],
            "year": daily[i]["year"],
        })
    return windows


def ret(w):
    return (w["exit_price"] - w["entry_price"]) / w["entry_price"]


def main():
    print("=" * 72)
    print("S-017 Phase 1.6 — Robustness Checks (Last Pre-IS Gate)")
    print("=" * 72)

    rows = load_csv(SPOT_FILE)
    daily = filter_holdout(rows)
    print(f"Holdout bars: {len(daily)} | Range: {daily[0]['date']}..{daily[-1]['date']}")

    # Part 1: Per-year breakdown for (3,3)
    print(f"\n{'='*72}")
    print("PART 1 — PER-YEAR BREAKDOWN FOR (N,M) = (3,3)")
    print(f"{'='*72}")
    print(f"{'Year':>4} | {'n_tom':>5} | {'tom_mean%':>10} | {'tom_wr':>6} | {'baseline_mean%':>14} | {'excess%':>8}")
    print("-" * 65)

    tom_windows = identify_tom_windows(daily, 3, 3)
    all_windows = identify_all_windows(daily, 6)

    for yr in [2018, 2019, 2020]:
        tom_yr = [w for w in tom_windows if w["year"] == yr]
        base_yr = [w for w in all_windows if w["year"] == yr]

        tom_mean = sum(ret(w) for w in tom_yr) / len(tom_yr) if tom_yr else 0
        tom_wr = sum(1 for w in tom_yr if w["exit_price"] > w["entry_price"]) / len(tom_yr) if tom_yr else 0
        base_mean = sum(ret(w) for w in base_yr) / len(base_yr) if base_yr else 0

        print(f"{yr:>4} | {len(tom_yr):>5} | {tom_mean*100:>+9.4f}% | {tom_wr:>5.1%} | {base_mean*100:>+13.4f}% | {(tom_mean-base_mean)*100:>+7.4f}%")

    # Overall
    tom_all = [ret(w) for w in tom_windows]
    base_all = [ret(w) for w in all_windows]
    print(f"\n{'ALL':>4} | {len(tom_windows):>5} | {sum(tom_all)/len(tom_all)*100:>+9.4f}% | {sum(1 for w in tom_windows if w['exit_price']>w['entry_price'])/len(tom_windows):>5.1%} | {sum(base_all)/len(base_all)*100:>+13.4f}% | {(sum(tom_all)/len(tom_all)-sum(base_all)/len(base_all))*100:>+7.4f}%")

    # Part 2: Excess for all nine windows
    print(f"\n{'='*72}")
    print("PART 2 — EXCESS (TOM - baseline) FOR ALL 9 (N,M) COMBOS")
    print(f"{'='*72}")
    print(f"{'N':>3} | {'M':>3} | {'n':>4} | {'tom_mean%':>10} | {'L=N+M':>6} | {'base_mean%':>11} | {'excess%':>9}")
    print("-" * 60)

    results = []
    for n in N_GRID:
        for m in M_GRID:
            windows = identify_tom_windows(daily, n, m)
            if not windows:
                continue
            L = n + m
            tom_mean = sum(ret(w) for w in windows) / len(windows)
            all_w = identify_all_windows(daily, L)
            base_mean = sum(ret(w) for w in all_w) / len(all_w) if all_w else 0
            excess = tom_mean - base_mean
            results.append((n, m, len(windows), tom_mean, L, base_mean, excess))
            print(f"{n:>3} | {m:>3} | {len(windows):>4} | {tom_mean*100:>+9.4f}% | {L:>6} | {base_mean*100:>+10.4f}% | {excess*100:>+8.4f}%")

    best_excess = max(results, key=lambda x: x[6])
    selected = (3, 3)
    selected_result = next(r for r in results if r[0] == 3 and r[1] == 3)
    print(f"\nSelected (3,3) excess: {selected_result[6]*100:+.4f}%")
    print(f"Highest excess: ({best_excess[0]},{best_excess[1]}) = {best_excess[6]*100:+.4f}%")

    # Part 3: Verdict
    print(f"\n{'='*72}")
    print("PART 3 — VIABILITY VERDICT")
    print(f"{'='*72}")

    tom_2018 = [w for w in tom_windows if w["year"] == 2018]
    tom_2018_mean = sum(ret(w) for w in tom_2018) / len(tom_2018) if tom_2018 else 0

    bull_only = tom_2018_mean > 0
    excess_winner = selected_result[6] == best_excess[6] or best_excess[6] <= selected_result[6] * 1.5

    print(f"2018 bear year TOM mean: {tom_2018_mean*100:+.4f}% — {'POSITIVE (bull-beta ruled out)' if bull_only else 'NEGATIVE (regime-dependent)'}")
    print(f"Selected (3,3) excess vs highest: {selected_result[6]*100:+.4f}% vs {best_excess[6]*100:+.4f}%")

    if not bull_only:
        verdict = "NON-VIABLE (artifact: regime-dependent — only positive in bull years)"
        reason = "TOM effect negative in 2018 bear market → bull-beta, not calendar anomaly"
    elif best_excess[6] > selected_result[6] * 1.5 and (best_excess[0], best_excess[1]) != (3, 3):
        verdict = "NON-VIABLE AS (3,3) — recommend ({},{})".format(best_excess[0], best_excess[1])
        reason = f"Window ({best_excess[0]},{best_excess[1]}) has materially higher excess ({best_excess[6]*100:.4f}% vs {selected_result[6]*100:.4f}%)"
    else:
        verdict = "VIABLE"
        reason = "Positive in bear year 2018 AND (3,3) has competitive excess"

    print(f"\nVERDICT: {verdict}")
    print(f"REASON: {reason}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
