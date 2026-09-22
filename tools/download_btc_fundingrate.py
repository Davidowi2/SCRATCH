#!/usr/bin/env python3
"""
tools/download_btc_fundingrate.py — Download Binance UM BTCUSDT funding rate history.

Two sources:
  (a) data.binance.vision monthly archive zips (primary, historical)
      https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-YYYY-MM.zip
  (b) fapi.binance.com REST (supplement / recent not in archive)
      https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime=...

Funding settles on 00:00 / 00:08 / 01:00... wait — per Binance spec it's
8h grid at 00:00, 08:00, 16:00 UTC.

Output: research/data/crypto/btcusdt_fundingrate_8h.csv
Columns: timestamp_utc, funding_rate (decimal, not %), settlement_hour_utc
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
OUT_FILE = os.path.join(OUT_DIR, "btcusdt_fundingrate_8h.csv")
ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT"

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
    url = f"{ARCHIVE_BASE}/BTCUSDT-fundingRate-{ym}.zip"
    try:
        r = session.get(url, timeout=60)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        rows = []
        with zf.open(zf.namelist()[0]) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            header = next(reader)
            for row in reader:
                if not row or len(row) < 3:
                    continue
                try:
                    ts_ms = int(row[0])
                    ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                    rate = float(row[2])  # last_funding_rate
                    # Binance format: timestamp, fundingRate (decimal), symbol, etc.
                    rows.append({
                        "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "funding_rate": rate,
                        "settlement_hour_utc": ts.hour,
                    })
                except (ValueError, IndexError):
                    continue
        return rows
    except Exception as e:
        print(f"  {ym}: FAILED ({e})")
        return None


def download_rest(start_ms, end_ms, limit=1000):
    """Fetch funding rate from REST API (supplement for recent months not in archive)."""
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    rows = []
    current = start_ms
    while current < end_ms:
        try:
            r = session.get(url, params={
                "symbol": "BTCUSDT",
                "startTime": current,
                "endTime": min(current + 30 * 24 * 3600 * 1000, end_ms),
                "limit": limit
            }, timeout=30)
            if r.status_code != 200:
                print(f"  REST HTTP {r.status_code}: {r.text[:200]}")
                break
            data = r.json()
            if not data:
                break
            for item in data:
                ts = datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc)
                rate = float(item["fundingRate"])
                rows.append({
                    "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "funding_rate": rate,
                    "settlement_hour_utc": ts.hour,
                })
            if len(data) < limit:
                break
            current = data[-1]["fundingTime"] + 1
            time.sleep(0.5)
        except Exception as e:
            print(f"  REST error: {e}")
            break
    return rows


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 72)
    print("PHASE 3A — BTCUSDT FUNDING RATE DOWNLOAD")
    print("Window: 2019-09-01 → 2025-05-13 (8h settlement grid)")
    print("=" * 72)

    # --- (a) Archive download ---
    print("\n[A] data.binance.vision monthly archive (fundingRate)")
    archive_rows = []
    for ym in months_for("2020-01", "2025-05"):
        rows = download_month(ym)
        if rows is None:
            print(f"  {ym}: skipped (404)")
            continue
        archive_rows.extend(rows)
        print(f"  {ym}: {len(rows)} settlements")
        time.sleep(0.2)

    print(f"\nArchive total: {len(archive_rows)} rows")

    # --- (b) REST supplement (recent months archive might not have) ---
    print("\n[B] fapi.binance.com REST supplement")
    # Check if archive already covers 2025
    if archive_rows:
        latest_archive = max(r["timestamp_utc"] for r in archive_rows)
    else:
        latest_archive = "2019-09-01"
    print(f"  Latest archive date: {latest_archive}")

    rest_rows = []
    if latest_archive < "2025-05-13":
        # Supplement from latest archive to 2025-05-13
        supplement_start = datetime.strptime(
            max(latest_archive[:10], "2025-01-01"), "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc).timestamp() * 1000
        rest_end = datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000
        print(f"  Fetching REST from {latest_archive} to 2025-05-13...")
        rest_rows = download_rest(int(supplement_start), int(rest_end))
        print(f"  REST supplement: {len(rest_rows)} rows")
    else:
        print("  Archive already covers window — REST not needed")

    # --- Merge + dedup ---
    all_rows = archive_rows + rest_rows
    seen, unique = set(), []
    for r in all_rows:
        if r["timestamp_utc"] not in seen:
            seen.add(r["timestamp_utc"])
            unique.append(r)

    unique.sort(key=lambda r: r["timestamp_utc"])

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "funding_rate", "settlement_hour_utc"])
        w.writeheader()
        w.writerows(unique)

    sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
    print(f"\nFinal: {len(unique)} settlements")
    print(f"Range: {unique[0]['timestamp_utc']} .. {unique[-1]['timestamp_utc']}")
    print(f"SHA256: {sha}")
    print(f"Saved: {OUT_FILE}")

    # Sanity: settlement hour distribution
    hours = {}
    for r in unique:
        hours[r["settlement_hour_utc"]] = hours.get(r["settlement_hour_utc"], 0) + 1
    print(f"Settlement hours (UTC): {dict(sorted(hours.items()))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
