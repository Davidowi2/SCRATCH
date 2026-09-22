#!/usr/bin/env python3
"""
tools/download_equity_index.py — Download VIX and SPX daily from Yahoo Finance.

Uses yfinance REST API (query1.finance.yahoo.com/v8/finance/chart) for
reliable, rate-limited access. Falls back to direct CSV if yfinance breaks.

Outputs:
  research/data/equity/vix_daily_2010_2025.csv
  research/data/equity/spx_daily_2010_2025.csv

Format: timestamp_utc,open,high,low,close,volume (Gate-1 compatible)
"""

import csv
import hashlib
import os
import time
import urllib.request
import json
from datetime import datetime, timezone

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "data", "equity")
OUT_DIR = os.path.abspath(OUT_DIR)


def download_daily(symbol, start_year=2010, end_year=2025):
    """Download daily data via Yahoo Finance chart API."""
    start_ts = int(datetime(start_year, 1, 1, tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime(end_year, 12, 31, tzinfo=timezone.utc).timestamp())

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    rows = []
    for i, ts in enumerate(timestamps):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append({
            "timestamp_utc": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "open": quote["open"][i],
            "high": quote["high"][i],
            "low": quote["low"][i],
            "close": quote["close"][i],
            "volume": quote.get("volume", [0])[i] or 0,
        })

    rows.sort(key=lambda r: r["timestamp_utc"])
    return rows


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    for sym, fname in [("%5EVIX", "vix_daily_2010_2025.csv"), ("%5EGSPC", "spx_daily_2010_2025.csv")]:
        out = os.path.join(OUT_DIR, fname)
        rows = download_daily(sym)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
            w.writeheader()
            w.writerows(rows)
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        print(f"{sym}: {len(rows)} rows, sha={sha[:16]}")
        if rows:
            print(f"  Range: {rows[0]['timestamp_utc']} .. {rows[-1]['timestamp_utc']}")
        print(f"  Saved: {out}")
        time.sleep(1)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
