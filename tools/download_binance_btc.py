#!/usr/bin/env python3
"""
tools/download_binance_btc.py — Download BTCUSDT PERPETUAL 5m klines from Binance public archive.

Source (a): data.binance.vision monthly zips (no API key, public):
  https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-YYYY-MM.zip

Window: 2021-01-01 .. 2025-05-13 (monthly files through 2025-05; May truncated at bar).
Output: research/data/crypto/btcusdt_5m.csv
CSV columns: timestamp_utc, open, high, low, close, volume

Real data: synthetic:false provenance entry written separately.
"""

import os
import io
import csv
import time
import zipfile
import hashlib
import requests
from datetime import datetime, timezone

OUT_DIR = "research/data/crypto"
OUT_FILE = os.path.join(OUT_DIR, "btcusdt_5m.csv")
BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m"

MONTHS = []
for year in range(2021, 2026):
    for month in range(1, 13):
        dt = datetime(year, month, 1, tzinfo=timezone.utc)
        if dt < datetime(2021, 1, 1, tzinfo=timezone.utc):
            continue
        if dt > datetime(2025, 5, 1, tzinfo=timezone.utc):
            continue
        MONTHS.append(f"{year}-{month:02d}")

CUTOFF = "2025-05-13"


def download_month(ym, retries=3):
    url = f"{BASE}/BTCUSDT-5m-{ym}.zip"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 404:
                return None  # month does not exist (future)
            r.raise_for_status()
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            name = zf.namelist()[0]
            rows = []
            with zf.open(name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8")
                for row in csv.reader(text):
                    if not row or len(row) < 6:
                        continue
                    # Futures kline CSVs have no header; first field may be header-like
                    if not row[0].isdigit():
                        continue
                    ts_ms = int(row[0])
                    ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
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
            if attempt == retries - 1:
                print(f"  {ym}: FAILED ({e})")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 70)
    print("BINANCE UM FUTURES BTCUSDT 5m DOWNLOAD (data.binance.vision)")
    print("=" * 70)

    all_rows = []
    for ym in MONTHS:
        rows = download_month(ym)
        if rows is None:
            print(f"  {ym}: skipped")
            continue
        all_rows.extend(rows)
        print(f"  {ym}: {len(rows)} bars")
        time.sleep(0.3)  # politeness

    # Truncate at cutoff day end
    all_rows = [r for r in all_rows if r["timestamp_utc"][:10] <= CUTOFF]
    all_rows.sort(key=lambda r: r["timestamp_utc"])

    # Dedupe on timestamp (keep first)
    seen = set()
    clean = []
    for r in all_rows:
        if r["timestamp_utc"] not in seen:
            seen.add(r["timestamp_utc"])
            clean.append(r)

    with open(OUT_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(clean)

    sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
    print()
    print(f"Rows: {len(clean)}")
    if clean:
        print(f"Range: {clean[0]['timestamp_utc']} .. {clean[-1]['timestamp_utc']}")
    print(f"SHA256: {sha}")
    print(f"Saved: {OUT_FILE}")


if __name__ == "__main__":
    main()
