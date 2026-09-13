#!/usr/bin/env python3
"""
tools/download_dukascopy_nas100.py — Download real NAS100 data from Dukascopy public feed.

Dukascopy public HTTP feed (no API key):
URL pattern: https://data-feed.dukascopy.com/datafeed/{PAIR}/{YYYY}/{MM}/{DD}/h_ticks.bi5
Each file = 1 hour of tick data (LZMA compressed, 20 bytes per tick)
Tick format: timestamp_ms(4) + bid(4) + ask(4) + bid_vol(4) + ask_vol(4)

Aggregates ticks to 5m bars on :05 boundaries.
"""

import os
import sys
import struct
import lzma
import requests
import time
import csv
from datetime import datetime, timedelta

DUKASCOPY_URL = "https://data-feed.dukascopy.com/datafeed"
PAIR = "NAS100USD"
OUTPUT_FILE = "research/data/cfd_probe/nas100_5m_REAL.csv"
START = datetime(2021, 1, 4)  # First trading day
END = datetime(2025, 5, 13)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

def download_hour(pair, dt):
    """Download one hour of tick data."""
    url = f"{DUKASCOPY_URL}/{pair}/{dt.strftime('%Y/%m/%d')}/{dt.hour}h_ticks.bi5"
    try:
        r = session.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 0:
            # Decompress LZMA
            data = lzma.decompress(r.content)
            return data
    except Exception as e:
        pass
    return None

def parse_ticks(data, base_dt):
    """Parse binary tick data into list of dicts."""
    ticks = []
    for i in range(0, len(data), 20):
        if i + 20 > len(data):
            break
        ts_ms, bid, ask, bid_vol, ask_vol = struct.unpack(">Iffff", data[i:i+20])
        ts = base_dt + timedelta(milliseconds=ts_ms)
        ticks.append({
            "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2,
            "bid_vol": bid_vol,
            "ask_vol": ask_vol,
        })
    return ticks

def aggregate_to_5m(ticks):
    """Aggregate ticks to 5-minute bars on :05 boundaries."""
    if not ticks:
        return []
    
    bars = {}
    for tick in ticks:
        ts = datetime.strptime(tick["timestamp_utc"][:19], "%Y-%m-%d %H:%M:%S")
        # Floor to 5-min boundary
        minute = (ts.minute // 5) * 5
        bar_ts = ts.replace(minute=minute, second=0, microsecond=0)
        bar_key = bar_ts.strftime("%Y-%m-%d %H:%M:%S")
        
        if bar_key not in bars:
            bars[bar_key] = {
                "timestamp_utc": bar_key,
                "open": tick["mid"],
                "high": tick["mid"],
                "low": tick["mid"],
                "close": tick["mid"],
                "volume": 0,
                "tick_count": 0,
            }
        
        bar = bars[bar_key]
        bar["high"] = max(bar["high"], tick["mid"])
        bar["low"] = min(bar["low"], tick["mid"])
        bar["close"] = tick["mid"]
        bar["volume"] += tick["bid_vol"] + tick["ask_vol"]
        bar["tick_count"] += 1
    
    return list(bars.values())

def main():
    print("=" * 70)
    print("DUKASCOPY NAS100 REAL DATA DOWNLOAD")
    print("=" * 70)
    print(f"Pair: {PAIR}")
    print(f"Range: {START.date()} to {END.date()}")
    print()
    
    all_ticks = []
    current = START
    hours_attempted = 0
    hours_success = 0
    ticks_downloaded = 0
    
    # Download hour by hour (skip weekends)
    while current < END:
        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(hours=1)
            continue
        
        # Download
        hours_attempted += 1
        data = download_hour(PAIR, current)
        
        if data:
            ticks = parse_ticks(data, current)
            all_ticks.extend(ticks)
            hours_success += 1
            ticks_downloaded += len(ticks)
        
        current += timedelta(hours=1)
        
        # Progress every 100 hours
        if hours_attempted % 100 == 0:
            print(f"  {current.date()} {current.hour}:00 — {hours_success}/{hours_attempted} hours, {ticks_downloaded} ticks")
        
        # Rate limit
        time.sleep(0.05)
    
    print(f"\nDownload complete:")
    print(f"  Hours attempted: {hours_attempted}")
    print(f"  Hours success: {hours_success}")
    print(f"  Total ticks: {len(all_ticks)}")
    
    if not all_ticks:
        print("No ticks downloaded!")
        return False
    
    # Aggregate to 5m
    print("\nAggregating to 5m bars...")
    bars = aggregate_to_5m(all_ticks)
    bars.sort(key=lambda b: b["timestamp_utc"])
    
    print(f"Generated {len(bars)} 5m bars")
    print(f"Date range: {bars[0]['timestamp_utc']} to {bars[-1]['timestamp_utc']}")
    
    # Save
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for bar in bars:
            writer.writerow({
                "timestamp_utc": bar["timestamp_utc"],
                "open": round(bar["open"], 5),
                "high": round(bar["high"], 5),
                "low": round(bar["low"], 5),
                "close": round(bar["close"], 5),
                "volume": round(bar["volume"], 2),
            })
    
    print(f"\nSaved to: {OUTPUT_FILE}")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
