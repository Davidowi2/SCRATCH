#!/usr/bin/env python3
"""
tools/download_btc_spot_daily.py — Download BTCUSDT SPOT daily bars (2018-2020).

Spot has pre-2020 history that perp does not.
Tries monthly archive zips first, then daily archive zips for any gaps.

Output: research/data/crypto/btcusdt_spot_daily_2018_2020.csv
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
OUT_FILE = os.path.join(OUT_DIR, "btcusdt_spot_daily_2018_2020.csv")
SPOT_MONTHLY = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d"
SPOT_DAILY = "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1d"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def months_for(start_ym, end_ym):
    y, m = int(start_ym[:4]), int(start_ym[5:])
    ey, em = int(end_ym[:4]), int(end_ym[5:])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def download_monthly(ym):
    url = f"{SPOT_MONTHLY}/BTCUSDT-1d-{ym}.zip"
    try:
        r = session.get(url, timeout=60)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        rows = []
        with zf.open(zf.namelist()[0]) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                if not row or len(row) < 6 or not row[0].isdigit():
                    continue
                ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
                rows.append({
                    "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                })
        return rows
    except Exception as e:
        print(f"  {ym}: FAILED ({e})")
        return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 72)
    print("BTCUSDT SPOT DAILY DOWNLOAD (2018-01-01 .. 2020-12-31)")
    print("=" * 72)

    rows = []
    earliest_404 = None
    for ym in months_for("2018-01", "2020-12"):
        r = download_monthly(ym)
        if r is None:
            if earliest_404 is None:
                earliest_404 = ym
            print(f"  {ym}: 404")
            continue
        if earliest_404 is None:
            earliest_404 = ym
        rows.extend(r)
        print(f"  {ym}: {len(r)} days")
        time.sleep(0.2)

    print(f"\nTotal: {len(rows)} days")
    if rows:
        print(f"Earliest: {rows[0]['timestamp_utc']}")
        print(f"Latest: {rows[-1]['timestamp_utc']}")

    # Dedup + sort
    seen = set()
    unique = []
    for r in rows:
        if r['timestamp_utc'] not in seen:
            seen.add(r['timestamp_utc'])
            unique.append(r)
    unique.sort(key=lambda r: r['timestamp_utc'])

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=['timestamp_utc', 'open', 'high', 'low', 'close', 'volume'])
        w.writeheader()
        w.writerows(unique)

    sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
    print(f"\nFinal: {len(unique)} days, sha={sha}")
    print(f"Saved: {OUT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
