#!/usr/bin/env python3
"""
tools/download_sector_etfs.py — Download Sector ETF daily OHLC.

Downloads: XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB, XLRE
Period: 2015-01-01 to 2025-05-13.
Source: yfinance (Yahoo Finance free tier).
"""

import csv
import hashlib
import os
import sys
import time

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "data", "equity", "sector_etfs")
OUT_DIR = os.path.abspath(OUT_DIR)

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE"]


def main():
    import yfinance as yf
    os.makedirs(OUT_DIR, exist_ok=True)

    for sym in SECTORS:
        print(f"Downloading {sym} daily...")
        try:
            df = yf.download(sym, start="2015-01-01", end="2025-05-13",
                             interval="1d", progress=False, auto_adjust=False)
            if len(df) == 0:
                print(f"  {sym}: no data")
                continue

            rows = []
            for idx, row in df.iterrows():
                rows.append({
                    "timestamp_utc": idx.strftime("%Y-%m-%d"),
                    "open": float(row[("Open", sym)]),
                    "high": float(row[("High", sym)]),
                    "low": float(row[("Low", sym)]),
                    "close": float(row[("Close", sym)]),
                    "volume": int(row[("Volume", sym)]) if row[("Volume", sym)] else 0,
                })

            out = os.path.join(OUT_DIR, f"{sym.lower()}_daily_2015_2025.csv")
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
                w.writeheader()
                w.writerows(rows)
            sha = hashlib.sha256(open(out, "rb").read()).hexdigest()[:16]
            print(f"  {sym}: {len(rows)} bars, sha={sha}, range={rows[0]['timestamp_utc']}..{rows[-1]['timestamp_utc']}")
        except Exception as e:
            print(f"  {sym}: ERROR {e}")
        time.sleep(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
