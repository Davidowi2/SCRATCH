#!/usr/bin/env python3
"""
research/backtest/S029_gold_tom.py — S-029 Gold Turn-of-Month Effect.

THESIS: Gold (GLD) exhibits the same pension-flow TOM effect as SPY.
Window: (N,M) = (3,3) LOCKED from S-024. LONG only.

HOLDOUT: 2010-2013 (derivation context)
IS+OOS: 2014-2025 (full sample, one-shot confirmation)

Fees: 0.05% round-trip (GLD spread wider than SPY).

SURVIVE: excess > 0 AND mean > 0 AND WR > 52%.
KILL: excess <= 0 OR mean <= 0.
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "equity")
DATA_DIR = os.path.abspath(DATA_DIR)
GLD_PATH = os.path.join(DATA_DIR, "gld_daily_2010_2025.csv")

FEES = 0.0005  # 0.05% round-trip
N_DAYS = 3
M_DAYS = 3


def load_prices(path):
    """Load daily CSV into dict {date_str: {open,high,low,close,volume,date}}."""
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
                "volume": int(row["volume"]),
            }
    return prices


def gate1_validate(prices, sym):
    """Gate-1: validate data integrity."""
    n = len(prices)
    dates = sorted(prices.keys())
    start = dates[0]
    end = dates[-1]

    bad = sum(1 for d in prices.values() if d["close"] <= 0 or d["high"] < d["low"])

    # Check for missing dates (gaps in trading calendar)
    date_objs = [prices[d]["date"] for d in dates]
    gaps = 0
    for i in range(1, len(date_objs)):
        delta = (date_objs[i] - date_objs[i-1]).days
        if delta > 5 and delta < 10:  # weekend gap is ~3 days, longer = holiday gap
            gaps += 1

    print(f"[{sym}] Gate-1: {n} rows, range {start}..{end}, bad={bad}, gaps={gaps}")
    if bad > 0:
        print(f"  FAIL: {bad} bad rows")
        return False
    print(f"  PASS")
    return True


def find_month_end(date_str, sorted_dates):
    """Find the last trading day on or before date_str that is a month-end."""
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    # Find the last trading day of the month containing target_date
    target_month = (target_date.year, target_date.month)
    month_dates = [d for d in sorted_dates if datetime.strptime(d, "%Y-%m-%d").date().year == target_month[0]
                   and datetime.strptime(d, "%Y-%m-%d").date().month == target_month[1]]
    if not month_dates:
        return None
    return month_dates[-1]


def get_tom_window(end_date_str, sorted_dates, n=N_DAYS, m=M_DAYS):
    """
    Get the TOM window: last N trading days of the month ending at end_date_str,
    plus first M trading days of the next month.
    Returns (entry_date_str, exit_date_str, list_of_all_window_dates).
    """
    target_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    target_month = (target_date.year, target_date.month)

    # All trading days in the target month
    month_dates = [d for d in sorted_dates if datetime.strptime(d, "%Y-%m-%d").date().year == target_month[0]
                   and datetime.strptime(d, "%Y-%m-%d").date().month == target_month[1]]

    if len(month_dates) < n:
        return None, None, None

    # Last N trading days of current month
    last_n = month_dates[-n:]

    # Next month's first M trading days
    if target_month[1] == 12:
        next_month = (target_month[0] + 1, 1)
    else:
        next_month = (target_month[0], target_month[1] + 1)

    next_month_dates = [d for d in sorted_dates if datetime.strptime(d, "%Y-%m-%d").date().year == next_month[0]
                        and datetime.strptime(d, "%Y-%m-%d").date().month == next_month[1]]

    if len(next_month_dates) < m:
        return None, None, None

    first_m = next_month_dates[:m]

    entry_date = last_n[0]  # Open of first TOM day
    exit_date = first_m[-1]  # Close of last TOM day
    window_dates = last_n + first_m

    return entry_date, exit_date, window_dates


def count_trading_days(start_date, end_date, sorted_dates_set):
    """Count trading days between two date strings inclusive."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    current = start
    count = 0
    while current <= end:
        if current.strftime("%Y-%m-%d") in sorted_dates_set:
            count += 1
        current += timedelta(days=1)
    return count


def compute_tom_returns(prices, start_date, end_date, fees=FEES):
    """Compute TOM window returns for all month-end windows in the date range."""
    sorted_dates = sorted(prices.keys())
    sorted_dates_set = set(sorted_dates)

    # Find all month-end dates in range
    tom_windows = []
    for i, d in enumerate(sorted_dates):
        d_date = prices[d]["date"]
        # Check if this is a month-end (last trading day of the month)
        if i < len(sorted_dates) - 1:
            next_d = prices[sorted_dates[i + 1]]["date"]
            # If next day is a different month, this is month-end
            if next_d.month != d_date.month or next_d.year != d_date.year:
                if start_date <= d <= end_date:
                    entry, exit_d, window = get_tom_window(d, sorted_dates)
                    if entry and exit_d and window:
                        tom_windows.append({
                            "month_end": d,
                            "entry": entry,
                            "exit": exit_d,
                            "window_dates": window,
                        })

    returns = []
    for w in tom_windows:
        entry_price = prices[w["entry"]]["open"]
        exit_price = prices[w["exit"]]["close"]

        # Count actual holding days
        hold_days = count_trading_days(w["entry"], w["exit"], sorted_dates_set)

        if entry_price > 0 and exit_price > 0 and hold_days > 0:
            ret = (exit_price - entry_price) / entry_price - fees
            returns.append({
                "entry_date": w["entry"],
                "exit_date": w["exit"],
                "return": ret,
                "hold_days": hold_days,
                "month_end": w["month_end"],
            })

    return returns, tom_windows


def compute_baseline_returns(prices, start_date, end_date, window_size=6):
    """Compute mean return of ALL 6-day windows (non-overlapping from month-end)."""
    sorted_dates = sorted([d for d in prices.keys() if start_date <= d <= end_date])

    returns = []
    for i in range(len(sorted_dates) - window_size):
        entry_price = prices[sorted_dates[i]]["open"]
        exit_idx = min(i + window_size, len(sorted_dates) - 1)
        exit_price = prices[sorted_dates[exit_idx]]["close"]
        if entry_price > 0 and exit_price > 0:
            ret = (exit_price - entry_price) / entry_price
            returns.append(ret)

    return returns


def compute_stats(returns):
    """Compute return statistics."""
    if not returns:
        return {"n": 0, "mean": 0, "wr": 0, "sharpe": 0, "maxdd": 0}

    rets = [r["return"] for r in returns]
    n = len(rets)
    mean = sum(rets) / n
    std = (sum((r - mean) ** 2 for r in rets) / (n - 1)) ** 0.5 if n > 1 else 0

    wins = sum(1 for r in rets if r > 0)
    wr = wins / n

    sharpe = (mean / std) * (252 ** 0.5) if std > 0 else 0

    # MaxDD
    running = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in rets:
        running *= (1 + r)
        if running > peak:
            peak = running
        dd = (running - peak) / peak
        if dd < max_dd:
            max_dd = dd

    return {"n": n, "mean": mean * 100, "wr": wr * 100, "sharpe": sharpe, "maxdd": max_dd * 100}


def per_year_breakdown(returns):
    """Break down returns by year."""
    by_year = defaultdict(list)
    for r in returns:
        yr = r["entry_date"][:4]
        by_year[yr].append(r)

    results = {}
    for yr in sorted(by_year.keys()):
        yr_returns = [r["return"] for r in by_year[yr]]
        stats = compute_stats([{"return": r} for r in yr_returns])
        results[yr] = stats
    return results


def main():
    print("=" * 80)
    print("S-029 GOLD TOM — (3,3) Window Locked from S-024")
    print("=" * 80)

    prices = load_prices(GLD_PATH)
    if not gate1_validate(prices, "GLD"):
        return 1

    sorted_dates = sorted(prices.keys())

    # Compute TOM returns for full period 2010-2025
    tom_returns, tom_windows = compute_tom_returns(prices, "2010-01-01", "2025-05-13")

    # Baseline: ALL 6-day windows
    baseline_returns = compute_baseline_returns(prices, "2010-01-01", "2025-05-13", window_size=6)
    baseline_mean = sum(baseline_returns) / len(baseline_returns) if baseline_returns else 0

    print(f"\n{'TOML':>50}")
    print(f"n_windows: {len(tom_returns)}")
    print(f"mean TOM return: {sum(r['return'] for r in tom_returns)/len(tom_returns)*100:.4f}%")
    print(f"baseline mean (all 6-day windows): {baseline_mean*100:.4f}%")

    stats = compute_stats(tom_returns)
    excess = (stats["mean"] / 100 - baseline_mean) * 100

    print(f"\n{'STAT':>20} {'VALUE':>12}")
    print("-" * 35)
    print(f"{'n_windows':>20} {stats['n']:>12}")
    print(f"{'mean TOM return':>20} {stats['mean']:>11.4f}%")
    print(f"{'baseline return':>20} {baseline_mean*100:>11.4f}%")
    print(f"{'excess over baseline':>20} {excess:>11.4f}%")
    print(f"{'win rate':>20} {stats['wr']:>11.1f}%")
    print(f"{'sharpe':>20} {stats['sharpe']:>11.3f}")
    print(f"{'max drawdown':>20} {stats['maxdd']:>11.2f}%")

    # Per-year breakdown
    print(f"\n{'PER-YEAR BREAKDOWN':>50}")
    print(f"{'Year':>6} {'n':>4} {'Mean':>8} {'WR':>6} {'MaxDD':>8}")
    print("-" * 35)
    yr_stats = per_year_breakdown(tom_returns)
    for yr, s in sorted(yr_stats.items()):
        # Flag notable years
        flag = ""
        if yr == "2013":
            flag = " ⚠️ Gold crash"
        elif yr == "2020":
            flag = " ⚠️ COVID"
        elif yr == "2022":
            flag = " ⚠️ rate hike"
        print(f"{yr:>6} {s['n']:>4} {s['mean']:>7.2f}% {s['wr']:>5.1f}% {s['maxdd']:>7.2f}%{flag}")

    # --- VERDICT ---
    print(f"\n{'=' * 80}")
    print(f"VERDICT CRITERIA:")
    print(f"  excess > 0: {excess:.4f}% > 0? {'YES' if excess > 0 else 'NO'}")
    print(f"  mean > 0: {stats['mean']:.4f}% > 0? {'YES' if stats['mean'] > 0 else 'NO'}")
    print(f"  WR > 52%: {stats['wr']:.1f}% > 52%? {'YES' if stats['wr'] > 52 else 'NO'}")

    if excess > 0 and stats['mean'] > 0 and stats['wr'] > 52:
        verdict = "SURVIVE — Portfolio Candidate #3"
    else:
        verdict = "KILL"

    print(f"\nVERDICT: {verdict}")

    import hashlib
    import json
    payload = json.dumps({
        "experiment": "S-029",
        "window": f"({N_DAYS},{M_DAYS})",
        "mean": round(stats['mean'], 6),
        "excess": round(excess, 6),
        "wr": round(stats['wr'], 6),
        "sharpe": round(stats['sharpe'], 6),
        "maxdd": round(stats['maxdd'], 6),
        "n": stats['n'],
        "verdict": verdict,
    }, sort_keys=True)
    verdict_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    print(f"\nverdict_hash: {verdict_hash}")

    return 0 if "SURVIVE" in verdict else 1


if __name__ == "__main__":
    sys.exit(main())
