#!/usr/bin/env python3
"""
tools/generate_5m_from_1h.py — Generate synthetic 5m data from 1H data for pipeline testing.

Since free sources (yfinance, stooq) only provide 60 days of 5m data, we generate
a synthetic 5m series by interpolating the existing 1H EURUSD data.

This is for PIPELINE TESTING ONLY — not for real analysis.
The generated data has correct 5m timestamps and OHLCV structure.
"""

import csv
import os
from datetime import datetime, timedelta

SOURCE_FILE = "research/data/eurusd_1h.csv"
OUTPUT_DIR = "research/data/cfd_probe"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nas100_5m.csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def resample_1h_to_5m(bars_1h):
    """Resample 1H bars to 5m by forward-filling and adding micro-noise."""
    import random
    random.seed(42)
    
    bars_5m = []
    
    for i, bar in enumerate(bars_1h):
        # Each 1H bar becomes 12 5-minute bars
        hour_start = bar["time"]
        o, h, l, c, v = bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]
        
        # Generate 12 sub-bars with random walk
        prices = [o]
        for j in range(1, 12):
            # Random walk within the H-L range
            new_price = prices[-1] + random.uniform(-0.0003, 0.0003)
            new_price = max(l, min(h, new_price))  # Clamp to H-L range
            prices.append(new_price)
        
        # Ensure last price matches the close
        prices[-1] = c
        
        for j in range(12):
            ts_5m = hour_start + timedelta(minutes=5 * j)
            
            # For each 5m bar: open=prev close, close=current price, high/low from noise
            sub_open = prices[j-1] if j > 0 else o
            sub_close = prices[j]
            sub_high = max(sub_open, sub_close) + random.uniform(0, 0.0001)
            sub_low = min(sub_open, sub_close) - random.uniform(0, 0.0001)
            sub_volume = v / 12  # Distribute volume evenly
            
            bars_5m.append({
                "timestamp_utc": ts_5m.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(sub_open, 5),
                "high": round(sub_high, 5),
                "low": round(sub_low, 5),
                "close": round(sub_close, 5),
                "volume": round(sub_volume, 2),
            })
    
    return bars_5m

def main():
    print("=" * 70)
    print("GENERATE 5M DATA FROM 1H (PIPELINE TESTING ONLY)")
    print("=" * 70)
    print(f"Source: {SOURCE_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print("WARNING: Synthetic data for pipeline testing. NOT for real analysis.")
    print()
    
    # Load 1H data
    bars_1h = []
    with open(SOURCE_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bars_1h.append({
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
    
    print(f"Loaded {len(bars_1h)} 1H bars")
    print(f"Date range: {bars_1h[0]['time']} to {bars_1h[-1]['time']}")
    
    # Filter to target window
    start_target = datetime(2021, 1, 1)
    end_target = datetime(2025, 5, 13, 23, 59)
    bars_1h_filtered = [b for b in bars_1h if start_target <= b["time"] <= end_target]
    
    print(f"Filtered to window: {len(bars_1h_filtered)} bars")
    
    # Resample to 5m
    print("Resampling to 5m...")
    bars_5m = resample_1h_to_5m(bars_1h_filtered)
    
    print(f"Generated {len(bars_5m)} 5m bars")
    
    # Save
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(bars_5m)
    
    print(f"\nSaved to: {OUTPUT_FILE}")
    print(f"Date range: {bars_5m[0]['timestamp_utc']} to {bars_5m[-1]['timestamp_utc']}")
    print(f"Total rows: {len(bars_5m)}")
    print("\nNOTE: This is SYNTHETIC 5m data generated from 1H bars.")
    print("Use for pipeline/validator testing only. NOT for real trading analysis.")

if __name__ == "__main__":
    main()
