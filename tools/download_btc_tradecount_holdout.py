#!/usr/bin/env python3
"""
tools/download_btc_tradecount_holdout.py — Phase 1B holdout data download.

Downloads Binance UM futures BTCUSDT 5m monthly kline zips for
2019-09 .. 2020-12 KEEPING the trade-count column (col[8]) — the column
the original downloader (tools/download_binance_btc.py) dropped.

Output: research/data/crypto/btcusdt_5m_tradecount_holdout_2019_2020.csv
Columns: timestamp_utc,open,high,low,close,volume,trades

Purpose: VEED v1.1 Phase 1B parameter derivation on the RETIRED holdout
(2019-09-01..2020-12-31). NOT for verdict runs (FLAG-4 in the spec).
"""

import csv
import hashlib
import io
import os
import sys
import time
import zipfile
from datetime import datetime, timezone

import requests

OUT_DIR = "research/data/crypto"
OUT_FILE = os.path.join(OUT_DIR, "btcusdt_5m_tradecount_holdout_2019_2020.csv")
BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m"

MONTHS = ["2019-09", "2019-10", "2019-11", "2019-12"] + \
         [f"2020-{m:02d}" for m in range(1, 13)]


def download_month(ym, retries=3):
    url = f"{BASE}/BTCUSDT-5m-{ym}.zip"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            rows = []
            malformed = 0
            with zf.open(zf.namelist()[0]) as f:
                for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if not row or len(row) < 9 or not row[0].isdigit():
                        if row:
                            malformed += 1
                        continue
                    ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
                    rows.append({
                        "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                        "trades": int(row[8]),   # col[8] = trade count
                    })
            return rows, malformed
        except Exception as e:
            if attempt == retries - 1:
                print(f"  {ym}: FAILED ({e})")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 70)
    print("PHASE 1B HOLDOUT DOWNLOAD — BTCUSDT 5m WITH TRADE COUNT (col[8])")
    print("Window: 2019-09 .. 2020-12 (16 monthly zips)")
    print("=" * 70)

    all_rows = []
    total_malformed = 0
    for ym in MONTHS:
        res = download_month(ym)
        if res is None:
            print(f"  {ym}: SKIPPED (no file)")
            continue
        rows, malformed = res
        all_rows.extend(rows)
        total_malformed += malformed
        print(f"  {ym}: {len(rows)} bars" + (f" ({malformed} malformed skipped)" if malformed else ""))
        time.sleep(0.3)

    all_rows.sort(key=lambda r: r["timestamp_utc"])
    seen, clean = set(), []
    for r in all_rows:
        if r["timestamp_utc"] not in seen:
            seen.add(r["timestamp_utc"])
            clean.append(r)

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low",
                                          "close", "volume", "trades"])
        w.writeheader()
        w.writerows(clean)

    sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
    print()
    print(f"Rows: {len(clean)} (malformed skipped: {total_malformed})")
    if clean:
        print(f"Range: {clean[0]['timestamp_utc']} .. {clean[-1]['timestamp_utc']}")
    print(f"SHA256: {sha}")
    print(f"Saved: {OUT_FILE}")

    # sanity: trades column populated?
    zero_trades = sum(1 for r in clean if r["trades"] == 0)
    sample = clean[len(clean) // 2]
    print(f"trades==0 bars: {zero_trades}; mid-sample: {sample['timestamp_utc']} "
          f"trades={sample['trades']} o={sample['open']} c={sample['close']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
