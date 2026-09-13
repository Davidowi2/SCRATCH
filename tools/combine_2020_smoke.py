#!/usr/bin/env python3
"""
tools/combine_2020_smoke.py — Combine 2020 smoke slice into single CSV.
"""

import csv
import os
from datetime import datetime

SOURCE_DIR = "research/data/raw/EURUSD_H1_2020_SMOKE"
TARGET_FILE = "research/data/eurusd_1h_2020_smoke.csv"

files = sorted([f for f in os.listdir(SOURCE_DIR) if f.endswith(".csv")])

all_rows = []
for fname in files:
    path = os.path.join(SOURCE_DIR, fname)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_rows.append(row)

# Sort by timestamp
all_rows.sort(key=lambda r: r["timestamp_utc"])

with open(TARGET_FILE, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
    writer.writeheader()
    writer.writerows(all_rows)

print(f"Combined {len(all_rows)} rows from {len(files)} files into {TARGET_FILE}")
