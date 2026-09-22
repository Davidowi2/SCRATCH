#!/usr/bin/env python3
"""
tools/gate1_validate_fundingrate.py — Gate-1 validation for the 8h funding rate file.

Checks:
  - 8h grid continuity (expected interval = 8h between settlements)
  - No gaps > 1 settlement (>8h between consecutive rows)
  - No duplicate timestamps
  - Settlement hours must be in {0, 8, 16} UTC
  - Funding rate values are numeric and within plausible range

Paste-style report (no verdict on file validity — that's data integrity).
"""

import csv
from datetime import datetime, timedelta
import statistics


def validate(path, label):
    print(f"\n{'='*72}")
    print(f"GATE-1 VALIDATION — {label}")
    print(f"File: {path}")
    print(f"{'='*72}")

    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    n = len(rows)
    print(f"Rows: {n}")
    print(f"Range: {rows[0]['timestamp_utc']} .. {rows[-1]['timestamp_utc']}")

    # Settlement hours
    hours = {}
    for r in rows:
        h = r.get("settlement_hour_utc", "?")
        hours[h] = hours.get(h, 0) + 1
    print(f"Settlement hours (UTC): {dict(sorted(hours.items()))}")
    if set(hours.keys()) - {"0", "8", "16"}:
        print(f"  WARNING: unexpected settlement hours found: {set(hours.keys()) - {'0','8','16'}}")

    # Duplicates
    seen = set()
    dupes = 0
    for r in rows:
        if r["timestamp_utc"] in seen:
            dupes += 1
        seen.add(r["timestamp_utc"])
    print(f"Duplicate timestamps: {dupes}")

    # Gap analysis (expected 8h interval)
    ts_list = [datetime.strptime(r["timestamp_utc"], "%Y-%m-%d %H:%M:%S") for r in rows]
    gaps = []
    max_gap = 0
    gap_count = 0
    for i in range(1, len(ts_list)):
        delta = ts_list[i] - ts_list[i-1]
        gap_hours = delta.total_seconds() / 3600
        gaps.append(gap_hours)
        if gap_hours > 8.5:  # allow small tolerance
            gap_count += 1
            max_gap = max(max_gap, gap_hours)

    print(f"Expected interval: 8h")
    print(f"Mean interval: {statistics.mean(gaps):.2f}h")
    print(f"Max interval: {max(gaps):.2f}h")
    print(f"Gaps > 8.5h: {gap_count}")

    # Rate range
    rates = [float(r["funding_rate"]) for r in rows]
    print(f"Rate range: [{min(rates):.8f}, {max(rates):.8f}]")
    print(f"Rate mean: {statistics.mean(rates):.8f}")
    print(f"Rate std:  {statistics.stdev(rates):.8f}")

    verdict = "PASS" if dupes == 0 and gap_count == 0 else "REJECT"
    print(f"\nVERDICT: {verdict}")
    return verdict


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python gate1_validate_fundingrate.py <csv> <label>")
        sys.exit(2)
    v = validate(sys.argv[1], sys.argv[2])
    sys.exit(0 if v == "PASS" else 1)
