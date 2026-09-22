#!/usr/bin/env python3
"""
tools/derive_tom_windows.py — S-017 TOM Phase 1: holdout window derivation.

NO IS test. NO kernel. NO P&L on IS data.

Grid search over (N,M) = {1,2,3} x {1,2,3}:
  N = last N days of month (turn-of-month window)
  M = first M days of next month

For each (N,M):
  - Identify all TOM windows in 2019-2020 holdout
  - Compute: price return, funding cost over hold, net return
  - Selection rule: highest mean net return on holdout
  - Abort check: if best mean net return <= 0, NON-VIABLE
"""

import csv
import os
from datetime import datetime, timedelta, timezone

HOLDOUT_START = datetime(2020, 1, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2020, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
FEE_ROUND_TRIP = 0.0010  # 0.10%
N_GRID = [1, 2, 3]
M_GRID = [1, 2, 3]

DAILY_FILE = "research/data/crypto/btcusdt_daily_2019_2025.csv"
FUNDING_FILE = "research/data/crypto/btcusdt_fundingrate_8h.csv"


def load_daily(path):
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


def load_funding(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({"time": ts, "rate": float(row["funding_rate"])})
    rows.sort(key=lambda r: r["time"])
    return rows


def get_funding_for_hold(funding, start, end):
    """Sum funding rates that apply during the hold window."""
    total = 0.0
    for f in funding:
        if start <= f["time"] < end:
            total += f["rate"]
    return total


def identify_tom_windows(daily, n, m):
    """
    Identify TOM windows: last N days of month + first M days of next.
    Returns list of (entry_date, exit_date, entry_price, exit_price).
    """
    windows = []
    dates = [d["date"] for d in daily]
    date_map = {d["date"]: d for d in daily}

    # Group by month
    months = {}
    for d in daily:
        ym = (d["date"].year, d["date"].month)
        if ym not in months:
            months[ym] = []
        months[ym].append(d)

    for ym in sorted(months.keys()):
        month_days = months[ym]
        last_n = month_days[-n:] if len(month_days) >= n else month_days

        # Next month
        if ym[1] == 12:
            next_ym = (ym[0] + 1, 1)
        else:
            next_ym = (ym[0], ym[1] + 1)

        if next_ym not in months:
            continue
        next_month_days = months[next_ym]
        first_m = next_month_days[:m] if len(next_month_days) >= m else next_month_days

        if not last_n or not first_m:
            continue

        # Entry: open of first day of TOM window (first of last N)
        entry_date = last_n[0]["date"]
        entry_price = last_n[0]["open"]

        # Exit: close of last day of TOM window (last of first M)
        exit_date = first_m[-1]["date"]
        exit_price = first_m[-1]["close"]

        # Both must be in holdout
        entry_dt = datetime.combine(entry_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        exit_dt = datetime.combine(exit_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        if entry_dt < HOLDOUT_START or exit_dt > HOLDOUT_END:
            continue

        windows.append({
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "n_days": len(last_n) + len(first_m),
        })

    return windows


def compute_window_returns(window, funding):
    """Compute price return, funding cost, net return for a window."""
    entry_price = window["entry_price"]
    exit_price = window["exit_price"]

    # Price return
    price_ret = (exit_price - entry_price) / entry_price

    # Funding cost: sum funding rates during the hold
    entry_dt = datetime.combine(window["entry_date"], datetime.min.time()).replace(tzinfo=timezone.utc)
    exit_dt = datetime.combine(window["exit_date"], datetime.min.time()).replace(tzinfo=timezone.utc)
    funding_cost = get_funding_for_hold(funding, entry_dt, exit_dt)

    # Net return
    net_ret = price_ret + funding_cost - FEE_ROUND_TRIP

    return {
        "price_ret": price_ret,
        "funding_cost": funding_cost,
        "net_ret": net_ret,
    }


def main():
    print("=" * 72)
    print("S-017 TOM Phase 1 — Holdout Window Derivation (2019-2020)")
    print("=" * 72)

    daily = load_daily(DAILY_FILE)
    funding = load_funding(FUNDING_FILE)

    # Filter to holdout
    daily_h = [d for d in daily if HOLDOUT_START <= d["time"] <= HOLDOUT_END]
    funding_h = [f for f in funding if HOLDOUT_START <= f["time"] <= HOLDOUT_END]

    print(f"Holdout daily bars: {len(daily_h)}")
    print(f"Holdout funding settlements: {len(funding_h)}")
    if daily_h:
        print(f"Range: {daily_h[0]['date']}..{daily_h[-1]['date']}")

    # Grid search
    print(f"\n{'='*72}")
    print("GRID SEARCH (N,M) = {1,2,3} x {1,2,3}")
    print(f"{'='*72}")
    print(f"{'N':>3} | {'M':>3} | {'n_win':>6} | {'mean_net%':>10} | {'win_rate':>9} | {'mean_cost%':>10}")
    print("-" * 60)

    best = None
    for n in N_GRID:
        for m in M_GRID:
            windows = identify_tom_windows(daily_h, n, m)
            if not windows:
                continue

            returns = [compute_window_returns(w, funding_h) for w in windows]
            mean_net = sum(r["net_ret"] for r in returns) / len(returns)
            win_rate = sum(1 for r in returns if r["net_ret"] > 0) / len(returns)
            mean_cost = sum(r["funding_cost"] for r in returns) / len(returns)

            viable = mean_net > 0
            if best is None or mean_net > best["mean_net"]:
                best = {"n": n, "m": m, "mean_net": mean_net, "win_rate": win_rate,
                        "n_windows": len(windows), "mean_cost": mean_cost}

            print(f"{n:>3} | {m:>3} | {len(windows):>6} | {mean_net*100:>+9.4f}% | {win_rate:>8.1%} | {mean_cost*100:>+9.6f}%")

    # Verdict
    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    if best is None:
        print("NO WINDOWS FOUND. S-017 NON-VIABLE.")
    elif best["mean_net"] <= 0:
        print(f"S-017 NON-VIABLE (abort condition met)")
        print(f"Best (N,M) = ({best['n']},{best['m']}), mean net = {best['mean_net']*100:.4f}%")
        print("IS test CANCELLED.")
    else:
        print(f"S-017 VIABLE on holdout")
        print(f"LOCKED (N,M) = ({best['n']},{best['m']})")
        print(f"Mean net return: {best['mean_net']*100:.4f}%")
        print(f"Win rate: {best['win_rate']:.1%}")
        print(f"Windows: {best['n_windows']}")
        print(f"Proceed to IS test (Phase 2).")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
