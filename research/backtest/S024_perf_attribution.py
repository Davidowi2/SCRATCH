#!/usr/bin/env python3
"""
research/backtest/S024_perf_attribution.py — S-024 Perfection Phase 1: Day-by-day attribution.

For the locked (3,3) TOM window, decompose into 6 individual days and test
sub-window variants to find the optimal trimmed window.

Per HERMES DIRECTIVE S-024/S-026 PERFECTION PHASE 1.
"""

import csv
import hashlib
import math
import os
import sys
from datetime import datetime, timezone, date, timedelta
import statistics

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from research.backtest.S024_tom_spy import load_daily, IS_START, IS_END

N = 3
M = 3
L = N + M
FEE = 0.0002

# Full period for this analysis
FULL_START = date(2010, 1, 1)
FULL_END = date(2025, 5, 13)

# Sub-window candidates (as (start_offset, end_offset) relative to TOM boundary)
SUB_WINDOWS = {
    "(-3,+1)": (-3, 1),   # capture peak, exit before fade
    "(-1,+1)": (-1, 1),   # tight around boundary
    "(-3,+3)": (-3, 3),   # current baseline
    "(-2,+2)": (-2, 2),
}


def get_tom_days(data, start, end):
    """Get TOM window days (last N of month + first M of next)."""
    filtered = [r for r in data if start <= r["date"] <= end]
    filtered.sort(key=lambda r: r["date"])

    by_month = {}
    for r in filtered:
        mkey = (r["date"].year, r["date"].month)
        if mkey not in by_month:
            by_month[mkey] = []
        by_month[mkey].append(r)

    months = sorted(by_month.keys())
    toms = []
    for i in range(len(months) - 1):
        curr_month = months[i]
        next_month = months[i + 1]
        curr_days = sorted(by_month[curr_month], key=lambda r: r["date"])
        next_days = sorted(by_month[next_month], key=lambda r: r["date"])

        # Last N days of current month + first M days of next month
        tom_days = curr_days[-N:] + next_days[:M]
        if len(tom_days) == L:
            toms.append(tom_days)
    return toms


def day_attribution(tom_windows):
    """Decompose each TOM window into 6 individual days and compute stats."""
    # tom_windows: list of lists of bars (each bar has 'open', 'close')
    # Day positions: -3, -2, -1 (last 3 of month), +1, +2, +3 (first 3 of next)
    day_names = ["Day -3", "Day -2", "Day -1", "Day +1", "Day +2", "Day +3"]
    day_returns = {name: [] for name in day_names}
    window_returns = []

    for tom in tom_windows:
        w_ret = 0.0
        for idx, day_name in enumerate(day_names):
            bar = tom[idx]
            day_ret = (bar["close"] - bar["open"]) / bar["open"]
            day_returns[day_name].append(day_ret)
            w_ret += day_ret
        # Subtract fees for full window
        w_ret -= FEE
        window_returns.append(w_ret)

    return day_returns, window_returns


def compute_all_windows_returns(data, start, end):
    """Compute returns of ALL 6-day windows (for baseline)."""
    filtered = [r for r in data if start <= r["date"] <= end]
    rets = []
    for i in range(len(filtered) - L):
        entry = filtered[i]["open"]
        exit_p = filtered[i + L - 1]["close"]
        ret = (exit_p - entry) / entry - FEE
        rets.append(ret)
    return rets


def compute_subwindow_ret(tom_windows, start_offset, end_offset):
    """Compute returns for a sub-window of TOM.
    start_offset: -3 means start at Day -3 (last 3rd of month)
    end_offset: +3 means end at Day +3 (first 3rd of next month)
    """
    day_names = ["Day -3", "Day -2", "Day -1", "Day +1", "Day +2", "Day +3"]
    start_idx = start_offset + N - 1  # -3 -> 0, -2 -> 1, -1 -> 2
    end_idx = end_offset + N - 1  # +1 -> 3, +2 -> 4, +3 -> 5

    rets = []
    for tom in tom_windows:
        entry = tom[start_idx]["open"]
        exit_p = tom[end_idx]["close"]
        ret = (exit_p - entry) / entry - FEE
        rets.append(ret)
    return rets


def main():
    assets = {
        "SPY": "research/data/equity/spy_daily_2010_2025.csv",
        "QQQ": "research/data/equity/qqq_daily_2010_2025.csv",
    }

    for asset_name in ["SPY", "QQQ"]:
        path = os.path.join(PROJECT_DIR, assets[asset_name])
        data = load_daily(path)
        print(f"\n{'='*80}")
        print(f"S-024 PERFECTION PHASE 1: DAY ATTRIBUTION — {asset_name}")
        print(f"{'='*80}")
        print(f"Data: {len(data)} bars, {data[0]['date']} .. {data[-1]['date']}")

        toms = get_tom_days(data, FULL_START, FULL_END)
        print(f"TOM windows: {len(toms)}")

        # Day attribution
        day_rets, window_rets = day_attribution(toms)

        # Baseline
        baseline_rets = compute_all_windows_returns(data, FULL_START, FULL_END)
        baseline_mean = statistics.mean(baseline_rets) if baseline_rets else 0

        print(f"\n{'='*80}")
        print("DAY-BY-DAY ATTRIBUTION")
        print(f"{'='*80}")
        day_names = ["Day -3", "Day -2", "Day -1", "Day +1", "Day +2", "Day +3"]
        print(f"{'Day':<10} | {'Mean%':>8} | {'WR':>6} | {'Contrib%':>9} | {'Cum%':>9}")
        print("-" * 55)

        cum = 0.0
        day_contributions = {}
        for name in day_names:
            rets = day_rets[name]
            mean_ret = statistics.mean(rets)
            wr = sum(1 for r in rets if r > 0) / len(rets) * 100
            cum += mean_ret
            pct_of_window = mean_ret / (statistics.mean(window_rets) + FEE) * 100 if window_rets else 0
            print(f"{name:<10} | {mean_ret*100:>+7.4f}% | {wr:>5.1f}% | {pct_of_window:>+8.2f}% | {cum*100:+8.4f}%")
            day_contributions[name] = {"mean": mean_ret, "wr": wr, "cum": cum}

        total_window_mean = statistics.mean(window_rets)
        print(f"\n  Total window mean: {total_window_mean*100:.4f}%")
        print(f"  Baseline (all 6-day windows): {baseline_mean*100:.4f}%")
        print(f"  Excess: {(total_window_mean - baseline_mean)*100:.4f}%")

        # Identify positive vs negative days
        print(f"\n  Positive days: {[n for n in day_names if day_contributions[n]['mean'] > 0]}")
        print(f"  Negative days: {[n for n in day_names if day_contributions[n]['mean'] <= 0]}")

        # Sub-window analysis
        print(f"\n{'='*80}")
        print("SUB-WINDOW TESTS")
        print(f"{'='*80}")
        print(f"{'Window':<12} | {'n':>4} | {'Mean%':>8} | {'Excess%':>8} | {'WR':>6} | {'Excess/day':>11}")
        print("-" * 65)

        best_excess_per_day = -999
        best_label = None

        for label, (s_off, e_off) in SUB_WINDOWS.items():
            sub_rets = compute_subwindow_ret(toms, s_off, e_off)
            sub_mean = statistics.mean(sub_rets) if sub_rets else 0
            sub_excess = sub_mean - baseline_mean
            sub_wr = sum(1 for r in sub_rets if r > 0) / len(sub_rets) * 100 if sub_rets else 0
            hold_days = (e_off - s_off) + 1 if s_off < 0 else (e_off - s_off + 1) - N + 1
            # Actually count days in window
            start_idx = s_off + N - 1
            end_idx = e_off + N - 1
            hold_days = end_idx - start_idx + 1
            excess_per_day = sub_excess / hold_days if hold_days > 0 else 0
            print(f"{label:<12} | {len(sub_rets):>4} | {sub_mean*100:>+7.4f}% | {sub_excess*100:>+7.4f}% | {sub_wr:>5.1f}% | {excess_per_day*100:>+10.4f}%")

            if excess_per_day > best_excess_per_day:
                best_excess_per_day = excess_per_day
                best_label = label

        print(f"\n  Best excess-per-day: {best_label} ({best_excess_per_day*100:.4f}%/day)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
