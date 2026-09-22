#!/usr/bin/env python3
"""
tools/download_eth_perp_daily.py — Download ETHUSDT perp daily from Binance API.

Spot daily archive zips are 404 on Binance. Using REST API fallback.
ETHUSDT spot/perpt daily from 2020-01-01..2025-05-13.

Output: research/data/crypto/ethusdt_daily_2020_2025.csv
"""

import csv
import hashlib
import os
import time
from datetime import datetime, timezone

import requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "data", "crypto", "ethusdt_daily_2020_2025.csv")
OUT = os.path.abspath(OUT)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    url = "https://api.binance.com/api/v3/klines"
    all_rows = []
    start_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime(2025, 5, 13, tzinfo=timezone.utc).timestamp() * 1000)

    while start_ts < end_ts:
        params = {
            "symbol": "ETHUSDT",
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
        start_ts = int(data[-1][0]) + 1
        time.sleep(0.2)

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
    print(f"ETH daily: {len(unique)} rows, sha={sha}")
    if unique:
        print(f"Range: {unique[0]['timestamp_utc']} .. {unique[-1]['timestamp_utc']}")
    print(f"Saved: {OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
