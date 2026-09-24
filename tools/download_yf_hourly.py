#!/usr/bin/env python3
"""
tools/download_yf_hourly.py — Download SPY + QQQ 1H data via yfinance.

yfinance/Yahoo Finance provides 1H data for ~730 days (2 years).
We download as much history as Yahoo provides and document the gap.

Output: research/data/equity/hourly/spy_hourly_yf.csv, qqq_hourly_yf.csv
"""

import csv
import hashlib
import os
import sys
import time
from datetime import datetime, timezone

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "data", "equity", "hourly")
OUT_DIR = os.path.abspath(OUT_DIR)


def main():
    import yfinance as yf
    os.makedirs(OUT_DIR, exist_ok=True)

    for sym in ["SPY", "QQQ"]:
        print(f"Downloading {sym} 1H via yfinance (2y max)...")
        df = yf.download(sym, period="2y", interval="60m", progress=False, auto_adjust=False)
        if len(df) == 0:
            print(f"  {sym}: no data")
            continue

        rows = []
        for idx, row in df.iterrows():
            dt_str = idx.strftime("%Y-%m-%d %H:%M:%S")
            rows.append({
                "timestamp_utc": dt_str,
                "open": float(row["Open"].iloc[0]) if hasattr(row["Open"], "iloc") else float(row["Open"]),
                "high": float(row["High"].iloc[0]) if hasattr(row["High"], "iloc") else float(row["High"]),
                "low": float(row["Low"].iloc[0]) if hasattr(row["Low"], "iloc") else float(row["Low"]),
                "close": float(row["Close"].iloc[0]) if hasattr(row["Close"], "iloc") else float(row["Close"]),
                "volume": int(row["Volume"].iloc[0]) if hasattr(row["Volume"], "iloc") else int(row["Volume"]) if row["Volume"] else 0,
            })

        out = os.path.join(OUT_DIR, f"{sym.lower()}_hourly_yf.csv")
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
            w.writeheader()
            w.writerows(rows)
        sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
        print(f"  {sym}: {len(rows)} bars, sha={sha[:16]}")
        print(f"  Range: {rows[0]['timestamp_utc']} .. {rows[-1]['timestamp_utc']}")
        print(f"  Saved: {out}")
        time.sleep(2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
