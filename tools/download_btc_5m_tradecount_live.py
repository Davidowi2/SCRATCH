#!/usr/bin/env python3
"""
tools/download_btc_5m_tradecount_live.py — Phase 2A live-window data download.

Downloads Binance UM 5m klines for BTCUSDT perp, PRESERVING col[8] (trades),
for both the IS and OOS windows. Saves to separate files; does NOT touch
the col[8]-less file (sha db2b863b).

  IS  window: 2021-01-01 .. 2023-12-31
  OOS window: 2024-01-01 .. 2025-05-13
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

BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m"
OUT_DIR = "research/data/crypto"


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
            mal = 0
            with zf.open(zf.namelist()[0]) as f:
                for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if not row or len(row) < 9 or not row[0].isdigit():
                        if row: mal += 1
                        continue
                    ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
                    rows.append({
                        "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": float(row[1]), "high": float(row[2]),
                        "low": float(row[3]), "close": float(row[4]),
                        "volume": float(row[5]), "trades": int(row[8]),
                    })
            return rows, mal
        except Exception as e:
            if attempt == retries - 1:
                print(f"  {ym}: FAILED ({e})")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def build(start_ym, end_ym, label):
    print(f"\n[{label}] downloading {start_ym} .. {end_ym}")
    all_rows = []
    total_mal = 0
    for ym in months_for(start_ym, end_ym):
        res = download_month(ym)
        if res is None:
            print(f"  {ym}: skipped")
            continue
        rows, mal = res
        all_rows.extend(rows)
        total_mal += mal
        print(f"  {ym}: {len(rows)} bars")
        time.sleep(0.3)
    all_rows.sort(key=lambda r: r["timestamp_utc"])
    seen, clean = set(), []
    for r in all_rows:
        if r["timestamp_utc"] not in seen:
            seen.add(r["timestamp_utc"])
            clean.append(r)
    print(f"  {label}: {len(clean)} deduped bars ({total_mal} malformed skipped)")
    return clean


def save(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low",
                                          "close", "volume", "trades"])
        w.writeheader()
        w.writerows(rows)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return sha


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 72)
    print("PHASE 2A — LIVE-WINDOW DOWNLOAD (BTCUSDT 5m WITH TRADE-COUNT)")
    print("=" * 72)

    is_rows = build("2021-01", "2023-12", "IS")
    is_path = os.path.join(OUT_DIR, "btcusdt_5m_tradecount_is_2021_2023.csv")
    is_sha = save(is_rows, is_path)
    print(f"\nIS  -> {is_path}")
    print(f"  rows={len(is_rows)} range={is_rows[0]['timestamp_utc']}..{is_rows[-1]['timestamp_utc']}")
    print(f"  sha256={is_sha}")

    oos_rows = build("2024-01", "2025-05", "OOS")
    oos_path = os.path.join(OUT_DIR, "btcusdt_5m_tradecount_oos_2024_2025.csv")
    oos_sha = save(oos_rows, oos_path)
    print(f"\nOOS -> {oos_path}")
    print(f"  rows={len(oos_rows)} range={oos_rows[0]['timestamp_utc']}..{oos_rows[-1]['timestamp_utc']}")
    print(f"  sha256={oos_sha}")

    # zero-trades sanity
    for label, rows in [("IS", is_rows), ("OOS", oos_rows)]:
        zt = sum(1 for r in rows if r["trades"] == 0)
        print(f"{label} trades==0 bars: {zt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
