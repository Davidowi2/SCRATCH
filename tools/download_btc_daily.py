#!/usr/bin/env python3
"""
tools/download_btc_daily.py — Download BTCUSDT daily price data.

Two sources:
  (a) data.binance.vision monthly kline zips (primary, historical)
      https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-YYYY-MM.zip
  (b) fapi.binance.com REST (supplement for recent months)
      https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1d&startTime=...

Output: research/data/crypto/btcusdt_daily_2019_2025.csv
Columns: timestamp_utc,open,high,low,close,volume
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
OUT_FILE = os.path.join(OUT_DIR, "btcusdt_daily_2019_2025.csv")
ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d"

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


def download_month(ym):
    url = f"{ARCHIVE_BASE}/BTCUSDT-1d-{ym}.zip"
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


def download_rest(start_ms, end_ms):
    url = "https://fapi.binance.com/fapi/v1/klines"
    rows = []
    current = start_ms
    while current < end_ms:
        try:
            r = session.get(url, params={
                "symbol": "BTCUSDT",
                "interval": "1d",
                "startTime": current,
                "limit": 1500
            }, timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break
            for item in data:
                ts = datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc)
                rows.append({
                    "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                })
            if len(data) < 1500:
                break
            current = data[-1][0] + 86400000
            time.sleep(0.5)
        except Exception as e:
            print(f"  REST error: {e}")
            break
    return rows


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 72)
    print("BTCUSDT DAILY DATA DOWNLOAD (2019-01-01 .. 2025-05-13)")
    print("=" * 72)

    archive_rows = []
    earliest_404 = None
    for ym in months_for("2019-01", "2025-05"):
        rows = download_month(ym)
        if rows is None:
            if earliest_404 is None:
                earliest_404 = ym
            print(f"  {ym}: skipped (404)")
            continue
        if earliest_404 is None:
            earliest_404 = ym
        archive_rows.extend(rows)
        print(f"  {ym}: {len(rows)} days")
        time.sleep(0.2)

    print(f"\nArchive total: {len(archive_rows)} rows")
    if archive_rows:
        print(f"  Earliest: {archive_rows[0]['timestamp_utc']}")
        print(f"  Latest: {archive_rows[-1]['timestamp_utc']}")

    rest_rows = []
    if archive_rows and archive_rows[-1]['timestamp_utc'][:10] < "2025-05-13":
        latest = datetime.strptime(archive_rows[-1]['timestamp_utc'], "%Y-%m-%d %H:%M:%S")
        rest_start = int(latest.timestamp() * 1000) + 86400000
        rest_end = int(datetime(2025, 5, 13, tzinfo=timezone.utc).timestamp() * 1000)
        rest_rows = download_rest(rest_start, rest_end)
        print(f"  REST supplement: {len(rest_rows)} rows")

    all_rows = archive_rows + rest_rows
    all_rows.sort(key=lambda r: r['timestamp_utc'])

    # Dedup
    seen = set()
    unique = []
    for r in all_rows:
        if r['timestamp_utc'] not in seen:
            seen.add(r['timestamp_utc'])
            unique.append(r)

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=['timestamp_utc', 'open', 'high', 'low', 'close', 'volume'])
        w.writeheader()
        w.writerows(unique)

    sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
    print(f"\nFinal: {len(unique)} days")
    if unique:
        print(f"Range: {unique[0]['timestamp_utc']}..{unique[-1]['timestamp_utc']}")
    print(f"SHA256: {sha}")
    print(f"Saved: {OUT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
