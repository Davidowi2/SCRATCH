#!/usr/bin/env python3
"""
tools/make_2020_smoke_slice.py — Create 2020 audit smoke slice from 2021 data.

M2 ruling: 2020 slice outside frozen windows for audit-only smoke test.
We don't have 2020 Dukascopy data downloaded, so we create a synthetic
2020 slice by shifting 2021 timestamps back one year. This proves the
kernel logic works; it records NO verdict, NO ledger row, NO graveyard row.
"""

import csv
import os
from datetime import datetime

SOURCE_DIR = "research/data/raw/EURUSD_H1"
TARGET_DIR = "research/data/raw/EURUSD_H1_2020_SMOKE"
os.makedirs(TARGET_DIR, exist_ok=True)

# 2021 files -> shift back 1 year
files_2021 = sorted([f for f in os.listdir(SOURCE_DIR) if f.startswith("2021") and f.endswith(".csv")])

print(f"Creating 2020 smoke slice from {len(files_2021)} 2021 files...")

for fname in files_2021:
    source_path = os.path.join(SOURCE_DIR, fname)
    target_fname = fname.replace("2021", "2020")
    target_path = os.path.join(TARGET_DIR, target_fname)
    
    rows = []
    with open(source_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S")
            ts_2020 = ts.replace(year=2020)
            row["timestamp_utc"] = ts_2020.strftime("%Y-%m-%d %H:%M:%S")
            rows.append(row)
    
    with open(target_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

print(f"Created {len(files_2021)} smoke files in {TARGET_DIR}")
print("2020 smoke slice ready for audit-only test.")
