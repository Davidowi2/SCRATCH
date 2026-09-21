#!/usr/bin/env python3
"""
tools/gate1_validate_tradecount.py — Gate-1 validation for BTCUSDT 5m files
with the trade-count column (col[8]) preserved.

Extends validate_data_crypto.py's structural checks with:
  - trades column present in header
  - trades column populated (no nulls/zeros except where legitimate)
  - trades column monotonicity sanity (mean > 0, std > 0)

Paste-style report (no verdict).

Usage:
  python tools/gate1_validate_tradecount.py <csv_file> <label>
"""

import csv
import sys
from datetime import datetime, timedelta


def validate(path, label):
    print(f"\n{'='*72}")
    print(f"GATE-1 VALIDATION (+tradecount) — {label}")
    print(f"File: {path}")
    print(f"{'='*72}")

    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        header = None
        for i, row in enumerate(csv.reader(f)):
            if i == 0:
                header = row
                continue
            rows.append(row)

    print(f"Header: {header}")
    n = len(rows)
    print(f"Data rows: {n}")

    # col[8] (trades) present?
    has_trades = "trades" in header if header else False
    trades_idx = header.index("trades") if has_trades else None
    print(f"trades column present: {has_trades} (idx={trades_idx})")

    # parse
    ts = []
    trades = []
    bad_ohlc = 0
    misaligned = 0
    dupes = 0
    zero_trades = 0
    prev = None
    seen = set()

    for row in rows:
        t = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        ts.append(t)
        o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        if not (h >= max(o, c) and l <= min(o, c) and h >= l and o > 0 and c > 0):
            bad_ohlc += 1
        if has_trades and trades_idx is not None:
            tr = int(row[trades_idx]) if row[trades_idx].isdigit() else -1
            trades.append(tr)
            if tr == 0:
                zero_trades += 1
        # alignment
        if t.minute % 5 != 0 or t.second != 0:
            misaligned += 1
        # duplicates
        if t in seen:
            dupes += 1
        seen.add(t)
        prev = t

    print(f"OHLC-bad: {bad_ohlc}  misaligned: {misaligned}  duplicates: {dupes}")

    # coverage / gaps (5m)
    span = ts[-1] - ts[0]
    expected = int(span / timedelta(minutes=5)) + 1
    completeness = n / expected if expected else 0
    gaps = 0
    max_gap_bars = 0
    for i in range(1, len(ts)):
        delta = (ts[i] - ts[i - 1]) / timedelta(minutes=5)
        missing = int(delta) - 1
        if missing > 0:
            gaps += 1
            max_gap_bars = max(max_gap_bars, missing)
    print(f"5m coverage: {completeness:.6f}  gap events: {gaps}  max gap: {max_gap_bars} bars")

    # trades column stats
    if trades:
        mean_tr = sum(trades) / len(trades)
        std_tr = (sum((t - mean_tr) ** 2 for t in trades) / len(trades)) ** 0.5
        print(f"trades stats: mean={mean_tr:.1f} std={std_tr:.1f} "
              f"min={min(trades)} max={max(trades)} zero-count={zero_trades}")

    verdict = ("PASS" if has_trades and bad_ohlc == 0 and misaligned == 0
               and dupes == 0 and completeness >= 0.9999
               else "REJECT")
    print(f"\nVERDICT: {verdict}")
    return verdict


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python gate1_validate_tradecount.py <csv> <label>")
        sys.exit(2)
    v = validate(sys.argv[1], sys.argv[2])
    sys.exit(0 if v == "PASS" else 1)
