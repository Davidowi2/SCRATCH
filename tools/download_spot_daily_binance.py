#!/usr/bin/env python3
"""
tools/download_spot_daily_binance.py — Download BTCUSDT SPOT daily from Binance API.

Binance monthly archive zips for spot daily are 404. Falling back to the
REST API: api.binance.com/v3/klines?symbol=BTCUSDT&interval=1d&limit=1000

Pulls in ~1500 daily bars covering 2020-2025 (for basis with perp daily).
Uses startTime/endTime pagination to get full coverage.

Output: research/data/crypto/btcusdt_spot_daily_2020_2025.csv
NOTE: This is SPOT data (the funding pipeline had only perp). SPOT daily starts ~Dec 2016 on Binance.
"""

import csv
import hashlib
import os
import time
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "data", "crypto", "btcusdt_spot_daily_2020_2025.csv")
OUT = os.path.abspath(OUT)

import requests

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    url = "https://api.binance.com/api/v3/klines"
    all_rows = []
    # Start from 2020-01-01, paginate with startTime until we pass 2025-05-13
    start_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime(2025, 5, 13, tzinfo=timezone.utc).timestamp() * 1000)

    while start_ts < end_ts:
        params = {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "limit": 1000,
            "startTime": start_ts,
            "endTime": end_ts,
        }
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f"ERROR: {r.status_code} {r.text[:200]}")
            break
        data = r.json()
        if not data:
            break
        for bar in data:
            ts = datetime.fromtimestamp(bar[0] / 1000, tz=timezone.utc)
            all_rows.append({
                "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(bar[1]),
                "high": float(bar[2]),
                "low": float(bar[3]),
                "close": float(bar[4]),
                "volume": float(bar[5]),
            })
        # Advance past last returned
        start_ts = int(data[-1][0]) + 1
        time.sleep(0.2)  # be nice

    # Sort and dedupe
    seen = set()
    unique = []
    for r in sorted(all_rows, key=lambda r: r["timestamp_utc"]):
        if r["timestamp_utc"] not in seen:
            seen.add(r["timestamp_utc"])
            unique.append(r)

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(unique)

    sha = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    print(f"Spot daily (Binance REST): {len(unique)} rows, sha={sha}")
    if unique:
        print(f"Range: {unique[0]['timestamp_utc']} .. {unique[-1]['timestamp_utc']}")
    print(f"Saved: {OUT}")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
