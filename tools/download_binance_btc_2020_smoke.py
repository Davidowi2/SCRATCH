#!/usr/bin/env python3
"""
tools/download_binance_btc_2020_smoke.py — REAL 2020 slice for S-012 audit-only smoke (M2).

OUTSIDE the frozen windows (IS 2021-2023 / OOS 2024-2025). Consumes no
one-shot, records no verdict. Kept in a SEPARATE file so the frozen-window
dataset's manifest sha256 (db2b863b...) stays immutable.

Source: data.binance.vision UM monthly kline zips (public, no key).
Binance UM BTCUSDT 5m begins 2019-09-08, so 2020 is REAL data.
"""

import os
import io
import csv
import time
import zipfile
import hashlib
import requests
from datetime import datetime, timezone

OUT_FILE = "research/data/crypto/btcusdt_5m_2020_smoke.csv"
BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m"
MONTHS = [f"2020-{m:02d}" for m in range(1, 13)]


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
            with zf.open(zf.namelist()[0]) as f:
                for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if not row or len(row) < 6 or not row[0].isdigit():
                        continue
                    ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
                    rows.append({
                        "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": float(row[1]), "high": float(row[2]),
                        "low": float(row[3]), "close": float(row[4]),
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
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    print("=" * 70)
    print("S-012 SMOKE DATA — REAL 2020 BTCUSDT PERP 5m (M2, audit-only)")
    print("=" * 70)

    all_rows = []
    for ym in MONTHS:
        rows = download_month(ym)
        if rows is None:
            print(f"  {ym}: skipped")
            continue
        all_rows.extend(rows)
        print(f"  {ym}: {len(rows)} bars")
        time.sleep(0.3)

    all_rows.sort(key=lambda r: r["timestamp_utc"])
    seen, clean = set(), []
    for r in all_rows:
        if r["timestamp_utc"] not in seen:
            seen.add(r["timestamp_utc"])
            clean.append(r)

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(clean)

    sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
    print(f"\nRows: {len(clean)}")
    if clean:
        print(f"Range: {clean[0]['timestamp_utc']} .. {clean[-1]['timestamp_utc']}")
    print(f"SHA256: {sha}")
    print(f"Saved: {OUT_FILE}")

    # Expected bar count for 2020 (leap year): 366*288
    expected = 366 * 288
    print(f"Expected 24/7 bars in 2020: {expected}  actual: {len(clean)}  "
          f"completeness: {len(clean)/expected:.6f}")


if __name__ == "__main__":
    main()
