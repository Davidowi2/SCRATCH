#!/usr/bin/env python3
"""
tools/fundingrate_distribution_report.py — Phase 3A funding rate distribution report.

Data report only. NO backtest. NO kernel. NO threshold selection.

Reports:
  - Full percentile table (1st, 5th, 10th, 25th, 50th, 75th, 90th, 95th, 99th)
  - Event counts at absolute thresholds |F| >= x for IS window 2021-2023
  - Long-side (F <= -x) and short-side (F >= +x) counts separately
  - Total settlements in IS window
"""

import csv
from datetime import datetime
import statistics


def load_funding(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "rate": float(row["funding_rate"]),
            })
    rows.sort(key=lambda r: r["time"])
    return rows


def percentile(values, p):
    """Linear-interpolation percentile."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    if n == 1:
        return s[0]
    pos = (n - 1) * p / 100.0
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def main():
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "research/data/crypto/btcusdt_fundingrate_8h.csv"
    
    all_rows = load_funding(path)
    print("=" * 72)
    print("PHASE 3A — BTCUSDT FUNDING RATE DISTRIBUTION REPORT")
    print(f"File: {path}")
    print(f"Total settlements: {len(all_rows)}")
    print(f"Range: {all_rows[0]['time']} .. {all_rows[-1]['time']}")
    print("=" * 72)

    # IS window: 2021-01-01 .. 2023-12-31
    is_start = datetime(2021, 1, 1)
    is_end = datetime(2023, 12, 31, 23, 59, 59)
    is_rows = [r for r in all_rows if is_start <= r["time"] <= is_end]
    is_rates = [r["rate"] for r in is_rows]

    print(f"\nIS window: {is_start.date()} .. {is_end.date()}")
    print(f"IS settlements: {len(is_rates)}")

    # --- Percentile table ---
    print("\n" + "=" * 72)
    print("PERCENTILE TABLE (IS window)")
    print("=" * 72)
    pcts = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    print(f"{'Percentile':>12} | {'Rate (decimal)':>16} | {'Rate (%)':>12}")
    print("-" * 48)
    for p in pcts:
        val = percentile(is_rates, p)
        print(f"{'P' + str(p):>12} | {val:>16.8f} | {val*100:>12.6f}%")

    # --- Threshold event counts ---
    print("\n" + "=" * 72)
    print("THRESHOLD EVENT COUNTS (IS window)")
    print("=" * 72)
    thresholds = [0.0003, 0.0005, 0.00075, 0.0010, 0.0015]  # 0.03% etc
    print(f"{'Threshold':>12} | {'|F| >= x':>10} | {'Long (F<=-x)':>14} | {'Short (F>=+x)':>14}")
    print("-" * 60)
    for t in thresholds:
        abs_count = sum(1 for r in is_rates if abs(r) >= t)
        long_count = sum(1 for r in is_rates if r <= -t)
        short_count = sum(1 for r in is_rates if r >= t)
        print(f"{t*100:>11.4f}% | {abs_count:>10} | {long_count:>14} | {short_count:>14}")

    # --- Additional stats ---
    print("\n" + "=" * 72)
    print("SUMMARY STATS (IS window)")
    print("=" * 72)
    pos_rates = [r for r in is_rates if r > 0]
    neg_rates = [r for r in is_rates if r < 0]
    zero_rates = [r for r in is_rates if r == 0]
    print(f"Positive rates: {len(pos_rates)} ({100*len(pos_rates)/len(is_rates):.1f}%)")
    print(f"Negative rates: {len(neg_rates)} ({100*len(neg_rates)/len(is_rates):.1f}%)")
    print(f"Zero rates:     {len(zero_rates)} ({100*len(zero_rates)/len(is_rates):.1f}%)")
    print(f"Mean:   {statistics.mean(is_rates):.8f}  ({statistics.mean(is_rates)*100:.6f}%)")
    print(f"Stdev:  {statistics.stdev(is_rates):.8f}")
    print(f"Min:    {min(is_rates):.8f}  ({min(is_rates)*100:.6f}%)")
    print(f"Max:    {max(is_rates):.8f}  ({max(is_rates)*100:.6f}%)")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
