"""Rebuild cleaned dataset from full raw directory (all years 2021-2025)."""
import csv
import os
import sys
from datetime import datetime
from collections import Counter

RAW_DIR = "research/data/raw/EURUSD_H1"
OUTPUT = "research/data/eurusd_1h.csv"

# Load all raw files
all_bars = []
files = sorted(f for f in os.listdir(RAW_DIR) if f.endswith(".csv"))
print(f"Loading {len(files)} files...")

for fname in files:
    path = os.path.join(RAW_DIR, fname)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                bar = {
                    "time": row["timestamp_utc"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            except (ValueError, KeyError):
                continue
            if bar["high"] < bar["low"]:
                continue
            if not (bar["low"] <= bar["open"] <= bar["high"] and bar["low"] <= bar["close"] <= bar["high"]):
                continue
            all_bars.append(bar)

print(f"Total bars loaded: {len(all_bars)}")

# Strip weekend contamination
contaminated = []
kept = []
for b in all_bars:
    dt = datetime.strptime(b["time"], "%Y-%m-%d %H:%M:%S")
    weekday = dt.weekday()
    hour = dt.hour
    if weekday == 5 or (weekday == 6 and hour < 21):
        contaminated.append(b)
    else:
        kept.append(b)

# Strip flat filler
real_bars = [b for b in kept if b["volume"] > 0]
print(f"Contaminated: {len(contaminated)}, Flat filler: {len(kept) - len(real_bars)}, Real bars: {len(real_bars)}")

# Write cleaned dataset
with open(OUTPUT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
    for b in real_bars:
        writer.writerow([b["time"], b["open"], b["high"], b["low"], b["close"], b["volume"]])

print(f"Written: {OUTPUT} ({len(real_bars)} bars)")

# Per-year counts
years = Counter()
for b in real_bars:
    years[b["time"][:4]] += 1
print("Per-year:", dict(sorted(years.items())))
