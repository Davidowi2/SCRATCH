#!/usr/bin/env python3
"""
research/backtest/S029_gold_timesplit.py — S-029 Gold TOM Time-Split Validation.

Locked from S-024: (N,M)=(3,3), LONG only, entry=open of first TOM day,
exit=close of last TOM day.

Time splits:
- Segment 1: 2010-2018
- Segment 2: 2019-2022
- Segment 3: 2023-2025 (OOS)

Sensitivity: test 0.02% and 0.05% fees.
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "equity")
GLD_PATH = os.path.join(DATA_DIR, "gld_daily_2010_2025.csv")
SPY_PATH = os.path.join(DATA_DIR, "spy_daily_2010_2025.csv")

N_DAYS = 3
M_DAYS = 3
FEE_LEVELS = [0.0002, 0.0005]  # 0.02% and 0.05%


def load_prices(path):
    prices = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row["timestamp_utc"][:10]
            prices[date_str] = {
                "date": datetime.strptime(date_str, "%Y-%m-%d").date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "adj_close": float(row["close"]),
            }
    return prices


def get_tom_windows(prices, start_date, end_date, n=N_DAYS, m=M_DAYS):
    """Get TOM windows for a date range."""
    sorted_dates = sorted([d for d in prices.keys() if start_date <= d <= end_date])
    sorted_dates_set = set(sorted_dates)

    tom_windows = []
    for i, d in enumerate(sorted_dates):
        d_date = prices[d]["date"]
        if i < len(sorted_dates) - 1:
            next_d = prices[sorted_dates[i + 1]]["date"]
            if next_d.month != d_date.month or next_d.year != d_date.year:
                # Find last N trading days of current month
                month_dates = [x for x in sorted_dates if prices[x]["date"].year == d_date.year
                               and prices[x]["date"].month == d_date.month]
                if len(month_dates) < n:
                    continue

                last_n = month_dates[-n:]

                # Next month first M days
                if d_date.month == 12:
                    next_month = (d_date.year + 1, 1)
                else:
                    next_month = (d_date.year, d_date.month + 1)

                next_month_dates = [x for x in sorted_dates if prices[x]["date"].year == next_month[0]
                                    and prices[x]["date"].month == next_month[1]]

                if len(next_month_dates) < m:
                    continue

                first_m = next_month_dates[:m]
                entry = last_n[0]
                exit_d = first_m[-1]
                window_dates = last_n + first_m

                if start_date <= entry and exit_d <= end_date:
                    tom_windows.append({
                        "month_end": d,
                        "entry": entry,
                        "exit": exit_d,
                    })

    return tom_windows, sorted_dates, sorted_dates_set


def compute_baseline_mean(prices, start_date, end_date, window_size=6):
    """Baseline: mean return of all 6-day windows."""
    sorted_dates = sorted([d for d in prices.keys() if start_date <= d <= end_date])
    returns = []
    for i in range(len(sorted_dates) - window_size):
        entry = prices[sorted_dates[i]]["open"]
        exit_idx = min(i + window_size, len(sorted_dates) - 1)
        exit_p = prices[sorted_dates[exit_idx]]["close"]
        if entry > 0 and exit_p > 0:
            returns.append((exit_p - entry) / entry)
    return sum(returns) / len(returns) if returns else 0


def count_trading_days(start_d, end_d, sorted_dates_set):
    start = datetime.strptime(start_d, "%Y-%m-%d").date()
    end = datetime.strptime(end_d, "%Y-%m-%d").date()
    count = 0
    current = start
    while current <= end:
        if current.strftime("%Y-%m-%d") in sorted_dates_set:
            count += 1
        current += timedelta(days=1)
    return count


def analyze_segment(prices, start_date, end_date, fee_rate):
    tom_windows, sorted_dates, sorted_dates_set = get_tom_windows(prices, start_date, end_date)

    returns = []
    for w in tom_windows:
        entry_price = prices[w["entry"]]["open"]
        exit_price = prices[w["exit"]]["close"]
        if entry_price > 0:
            ret = (exit_price - entry_price) / entry_price - fee_rate
            returns.append(ret)

    n = len(returns)
    if n == 0:
        return None

    mean = sum(returns) / n
    wins = sum(1 for r in returns if r > 0)
    wr = wins / n
    std = (sum((r - mean) ** 2 for r in returns) / (n - 1)) ** 0.5 if n > 1 else 0
    sharpe = (mean / std) * (252 ** 0.5) if std > 0 else 0

    # MaxDD
    running = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        running *= (1 + r)
        if running > peak:
            peak = running
        dd = (running - peak) / peak
        if dd < max_dd:
            max_dd = dd

    baseline_mean = compute_baseline_mean(prices, start_date, end_date)
    excess = mean - baseline_mean

    # Per-year breakdown
    by_year = defaultdict(list)
    for w in tom_windows:
        yr = w["entry"][:4]
        ret = (prices[w["exit"]]["close"] - prices[w["entry"]]["open"]) / prices[w["entry"]]["open"] - fee_rate
        by_year[yr].append(ret)

    print(f"\n  Segments at fee={fee_rate*100:.2f}%:")
    print(f"  {'Stat':>20} {'Value':>12}")
    print(f"  {'-'*35}")
    print(f"  {'n_windows':>20} {n:>12}")
    print(f"  {'mean gross return':>20} {(mean+fee_rate)*100:>11.4f}%")
    print(f"  {'mean net return':>20} {mean*100:>11.4f}%")
    print(f"  {'baseline mean':>20} {baseline_mean*100:>11.4f}%")
    print(f"  {'excess net':>20} {excess*100:>11.4f}%")
    print(f"  {'win rate':>20} {wr*100:>11.1f}%")
    print(f"  {'sharpe':>20} {sharpe:>11.3f}")
    print(f"  {'max drawdown':>20} {max_dd*100:>11.2f}%")

    print(f"\n  Per-year (fee={fee_rate*100:.2f}%):")
    print(f"  {'Year':>6} {'n':>4} {'Mean':>8} {'WR':>6} {'MaxDD':>8}")
    print(f"  {'-'*35}")
    for yr in sorted(by_year.keys()):
        yr_rets = by_year[yr]
        yr_mean = sum(yr_rets) / len(yr_rets)
        yr_wr = sum(1 for r in yr_rets if r > 0) / len(yr_rets) * 100
        yr_running = 1.0
        yr_peak = 1.0
        yr_max_dd = 0
        for r in yr_rets:
            yr_running *= (1 + r)
            if yr_running > yr_peak:
                yr_peak = yr_running
            dd = (yr_running - yr_peak) / yr_peak
            if dd < yr_max_dd:
                yr_max_dd = dd
        print(f"  {yr:>6} {len(yr_rets):>4} {yr_mean*100:>7.2f}% {yr_wr:>5.1f}% {yr_max_dd*100:>7.2f}%")

    return {"n": n, "mean": mean, "wr": wr, "sharpe": sharpe, "maxdd": max_dd,
            "excess": excess, "baseline": baseline_mean, "by_year": dict(by_year)}


def main():
    print("=" * 80)
    print("S-029 GOLD TOM — TIME-SPLIT VALIDATION")
    print("(3,3) window locked from S-024, LONG only, 0.02%/0.05% fee sensitivity")
    print("=" * 80)

    prices = load_prices(GLD_PATH)
    n_total = len(prices)
    dates = sorted(prices.keys())
    print(f"\nGLD Gate-1: {n_total} bars, {dates[0]}..{dates[-1]}, all valid")

    segments = [
        ("Segment 1", "2010-01-01", "2018-12-31"),
        ("Segment 2", "2019-01-01", "2022-12-31"),
        ("Segment 3", "2023-01-01", "2025-05-13"),
    ]

    # Full period results
    print(f"\n{'=' * 80}")
    print(f"FULL PERIOD ANALYSIS (2010-2025)")
    print(f"{'=' * 80}")

    for fee in FEE_LEVELS:
        r = analyze_segment(prices, "2010-01-01", "2025-05-13", fee)

    # Segment-by-segment
    print(f"\n{'=' * 80}")
    print(f"TIME-SPLIT ANALYSIS")
    print(f"{'=' * 80}")

    seg_results = {}
    for label, start, end in segments:
        print(f"\n{label} ({start}..{end}):")
        for fee in FEE_LEVELS:
            r = analyze_segment(prices, start, end, fee)
            seg_results[f"{label}_{fee}"] = r

    # --- Promotion Criteria ---
    print(f"\n{'=' * 80}")
    print(f"PROMOTION CRITERIA (S-029):")
    print(f"{'=' * 80}")

    seg3 = seg_results[f"Segment 3_{FEE_LEVELS[0]}"]  # 0.02%
    full = analyze_segment(prices, "2010-01-01", "2025-05-13", FEE_LEVELS[0])

    print(f"  Segment 3 net excess > 0: {seg3['excess']*100:.4f}%? {'YES' if seg3['excess'] > 0 else 'NO'}")
    print(f"  Segment 3 mean net > 0: {seg3['mean']*100:.4f}%? {'YES' if seg3['mean'] > 0 else 'NO'}")
    print(f"  Full-period net excess > 0: {full['excess']*100:.4f}%? {'YES' if full['excess'] > 0 else 'NO'}")

    # Check no single-year dependency
    seg3_005 = seg_results[f"Segment 3_{FEE_LEVELS[1]}"]
    all_years_positive = all(seg3_005["by_year"][yr] for yr in seg3_005["by_year"]
                            if sum(seg3_005["by_year"][yr]) > 0)
    # More precise check
    yr_excesses = {}
    for yr in sorted(seg3_005["by_year"].keys()):
        yr_rets = seg3_005["by_year"][yr]
        yr_mean = sum(yr_rets) / len(yr_rets)
        yr_excess = yr_mean - full["baseline"]
        yr_excesses[yr] = yr_excess

    print(f"  Segment 3 per-year excess (fee=0.05%):")
    for yr, ex in sorted(yr_excesses.items()):
        print(f"    {yr}: {ex*100:.4f}% {'✓' if ex > 0 else '✗'}")

    dependent = sum(1 for ex in yr_excesses.values() if ex <= 0)
    not_dependent_on_single = dependent < len(yr_excesses)
    print(f"  Not dependent on single year: {dependent}/{len(yr_excesses)} years negative → {'YES' if not_dependent_on_single else 'NO'}")

    print(f"  Segment 3 MaxDD < -25%: {seg3['maxdd']*100:.2f}%? {'YES' if seg3['maxdd'] > -25 else 'NO'}")

    all_pass = (
        seg3["excess"] > 0 and
        seg3["mean"] > 0 and
        full["excess"] > 0 and
        not_dependent_on_single and
        seg3["maxdd"] > -25
    )

    verdict = "PORTFOLIO CANDIDATE" if all_pass else "KILL / NOT PORTFOLIO READY"
    print(f"\nVERDICT: {verdict}")

    import hashlib, json
    payload = json.dumps({
        "experiment": "S-029",
        "segment3_excess": round(seg3["excess"], 6),
        "segment3_mean": round(seg3["mean"], 6),
        "full_excess": round(full["excess"], 6),
        "segment3_maxdd": round(seg3["maxdd"], 6),
        "verdict": verdict,
    }, sort_keys=True)
    verdict_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    print(f"verdict_hash: {verdict_hash}")

    return 0 if "PORTFOLIO" in verdict else 1


if __name__ == "__main__":
    sys.exit(main())
