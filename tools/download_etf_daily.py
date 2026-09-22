#!/usr/bin/env python3
"""
tools/download_etf_daily.py — Download IWM and QQQ daily from Yahoo Finance.

Output: research/data/equity/iwm_daily_2010_2025.csv, qqq_daily_2010_2025.csv
"""

import csv
import hashlib
import os
import time
import urllib.request
import json
import sys
from datetime import datetime, timezone

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "data", "equity")
OUT_DIR = os.path.abspath(OUT_DIR)


def download_daily(symbol_url):
    start_ts = int(datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_url}"
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
        if quote.get("close", [None])[i] is None:
            continue
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
    for sym_url, fname in [("%5EIWM", "iwm_daily_2010_2025.csv"), ("%5EQQQ", "qqq_daily_2010_2025.csv")]:
        out = os.path.join(OUT_DIR, fname)
        rows = download_daily(sym_url)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
            w.writeheader()
            w.writerows(rows)
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        label = fname.replace("_daily_2010_2025", "").upper().replace("_", "")
        print(f"{label}: {len(rows)} rows, sha={sha[:16]}")
        if rows:
            print(f"  Range: {rows[0]['timestamp_utc']} .. {rows[-1]['timestamp_utc']}")
        print(f"  Saved: {out}")
        time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
