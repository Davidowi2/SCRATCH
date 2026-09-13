#!/usr/bin/env python3
"""
tools/download_nas100_chunked.py — Download NAS100/QQQ 5-min data in 60-day chunks.

Downloads from yfinance in chunks to work around the 60-day intraday limit.
Saves clean CSV to research/data/cfd_probe/nas100_5m.csv
"""

import os
import sys
import time
import subprocess
import csv
from datetime import datetime, timedelta

OUTPUT_DIR = "research/data/cfd_probe"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nas100_5m.csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Target window
START_YEAR = 2021
START_MONTH = 1
END_YEAR = 2025
END_MONTH = 5

def download_chunk(ticker, start_date, end_date):
    """Download a single chunk via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
        import yfinance as yf
    
    df = yf.download(
        ticker,
        start=start_date,
        end=end_date,
        interval="5m",
        progress=False,
        threads=True,
    )
    return df

def main():
    print("=" * 70)
    print("NAS100 5-MINUTE DATA DOWNLOAD (CHUNKED)")
    print("=" * 70)
    
    import yfinance as yf
    
    ticker = "QQQ"
    all_rows = []
    
    # Calculate chunks
    chunk_start = datetime(START_YEAR, START_MONTH, 1)
    chunk_size = timedelta(days=55)  # Stay under 60-day limit
    
    total_chunks = 0
    while chunk_start.year < END_YEAR or (chunk_start.year == END_YEAR and chunk_start.month <= END_MONTH):
        chunk_end = chunk_start + chunk_size
        if chunk_end.year > END_YEAR or (chunk_end.year == END_YEAR and chunk_end.month > END_MONTH):
            chunk_end = datetime(END_YEAR, END_MONTH, 13)
        
        start_str = chunk_start.strftime("%Y-%m-%d")
        end_str = chunk_end.strftime("%Y-%m-%d")
        
        print(f"  Chunk: {start_str} to {end_str}...", end=" ", flush=True)
        
        try:
            df = download_chunk(ticker, start_str, end_str)
            if df is not None and len(df) > 0:
                for idx, row in df.iterrows():
                    # Convert datetime to UTC string
                    if hasattr(idx, "strftime"):
                        ts_str = idx.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        ts_str = str(idx)[:19]
                    
                    all_rows.append({
                        "timestamp_utc": ts_str,
                        "open": float(row.get("Open", row.get("open", 0))),
                        "high": float(row.get("High", row.get("high", 0))),
                        "low": float(row.get("Low", row.get("low", 0))),
                        "close": float(row.get("Close", row.get("close", 0))),
                        "volume": float(row.get("Volume", row.get("volume", 0))),
                    })
                print(f"{len(df)} rows")
            else:
                print("No data")
        except Exception as e:
            print(f"Error: {e}")
        
        chunk_start = chunk_end
        time.sleep(1)  # Rate limit
    
    if not all_rows:
        print("\nNo data downloaded!")
        return False
    
    # Sort by timestamp
    all_rows.sort(key=lambda r: r["timestamp_utc"])
    
    # Save
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(all_rows)
    
    print(f"\nDownloaded {len(all_rows)} total rows")
    print(f"Date range: {all_rows[0]['timestamp_utc']} to {all_rows[-1]['timestamp_utc']}")
    print(f"Saved to: {OUTPUT_FILE}")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
