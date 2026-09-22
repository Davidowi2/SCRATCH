#!/usr/bin/env python3
"""
tools/download_dxy_daily.py — Download DXY (US Dollar Index) daily data.

Sources: FRED DTWEXBGS (Broad Dollar Index G+S).
FRED API: https://api.stlouisfed.org/fred/series/observations
No API key needed for basic access.

Output: research/data/dxy_daily_2018_2025.csv
"""

import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "data")
OUT_DIR = os.path.abspath(OUT_DIR)
OUT_FILE = os.path.join(OUT_DIR, "dxy_daily_2018_2025.csv")
FRED_SERIES = "DTWEXBGS"


def main():
    import requests

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Downloading DXY ({FRED_SERIES}) from FRED...")

    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={FRED_SERIES}&observation_start=2018-01-01&observation_end=2025-05-13&frequency=d&file_type=json"

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    try:
        r = session.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"FRED download failed: {e}")
        print("Trying alternate approach (FRED CSV export)...")

        # Try CSV export format
        csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={FRED_SERIES}&png_size=640x480&bgcolor=%23e1e9f0&chart_type=line&date=2018-01-01&early_date=2010-01-01&end_date=2025-05-13&graph_bgcolor=%23ffffff&height=450&mode=fred&recolorbar=undefined&txtcolor=%23444444&thues=10&transparency=0&width=1168"
        try:
            r2 = session.get(csv_url, timeout=60)
            r2.raise_for_status()
            lines = r2.text.strip().split("\n")
            rows = []
            # FRED CSV format: header row with column names, then data
            # Check if it has the series_id column
            header = lines[0].strip().split(",")
            series_idx = None
            for i, h in enumerate(header):
                if FRED_SERIES in h:
                    series_idx = i
                    break

            for line in lines[1:]:
                parts = line.strip().split(",")
                if len(parts) > 1 and series_idx is not None:
                    date_str = parts[0]
                    val = parts[series_idx]
                    if val and val != ".":
                        ts = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                        rows.append({"timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"), "dxy": float(val)})

            if rows:
                rows.sort(key=lambda r: r["timestamp_utc"])
                with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["timestamp_utc", "dxy"])
                    w.writeheader()
                    w.writerows(rows)

                sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
                print(f"\nSuccess via CSV export: {len(rows)} rows, sha={sha}")
                print(f"Range: {rows[0]['timestamp_utc']} .. {rows[-1]['timestamp_utc']}")
                print(f"Saved: {OUT_FILE}")
                return 0
            else:
                print("CSV export yielded no data")
        except Exception as e2:
            print(f"CSV export also failed: {e2}")

    obs = data["observations"]
    rows = []
    skipped = 0

    for o in obs:
        date_str = o["date"]
        val = o["value"]
        if val == ".":
            skipped += 1
            continue
        ts = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        rows.append({"timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"), "dxy": float(val)})

    print(f"Downloaded {len(rows)} rows (skipped {skipped} nulls)")
    if rows:
        print(f"Range: {rows[0]['timestamp_utc']} .. {rows[-1]['timestamp_utc']}")

    rows.sort(key=lambda r: r["timestamp_utc"])

    with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "dxy"])
        w.writeheader()
        w.writerows(rows)

    sha = hashlib.sha256(open(OUT_FILE, "rb").read()).hexdigest()
    print(f"\nFinal: {len(rows)} rows, sha={sha}")
    print(f"Saved: {OUT_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
