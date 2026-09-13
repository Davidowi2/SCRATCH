"""
tools/download_nas100.py — Download 5-minute OHLCV data for NAS100/NQ/QQQ.

Tries multiple sources in order:
1. yfinance with chunking (handles 60-day intraday limit)
2. stooq (free, no API key needed)
3. alpha_vantage (if API key available)

Saves clean CSV to research/data/cfd_probe/nas100_5m.csv
"""

import os
import sys
import time
from datetime import datetime, timedelta
import csv
import subprocess

OUTPUT_DIR = "research/data/cfd_probe"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nas100_5m.csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

START_DATE = "2021-01-01"
END_DATE = "2025-05-13"

def try_yfinance_chunked():
    """Download via yfinance in chunks to handle 60-day intraday limit."""
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not installed, trying install...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
        import yfinance as yf
    
    # Try NQ futures first (most reliable for futures data)
    # Then QQQ ETF (tracks NASDAQ-100)
    tickers = ["NQ=F", "QQQ", "^NDX"]
    
    for ticker in tickers:
        print(f"\nTrying {ticker}...")
        all_rows = []
        
        # Download in 60-day chunks (yfinance intraday limit)
        current = datetime.strptime(START_DATE, "%Y-%m-%d")
        end = datetime.strptime(END_DATE, "%Y-%m-%d")
        chunk_size = timedelta(days=55)  # Stay under 60-day limit
        
        while current < end:
            chunk_end = min(current + chunk_size, end)
            try:
                df = yf.download(
                    ticker,
                    start=current.strftime("%Y-%m-%d"),
                    end=chunk_end.strftime("%Y-%m-%d"),
                    interval="5m",
                    progress=False,
                    threads=True,
                )
                if df is not None and len(df) > 0:
                    for idx, row in df.iterrows():
                        all_rows.append({
                            "timestamp_utc": idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, "strftime") else str(idx)[:19],
                            "open": float(row.get("Open", row.get("open", 0))),
                            "high": float(row.get("High", row.get("high", 0))),
                            "low": float(row.get("Low", row.get("low", 0))),
                            "close": float(row.get("Close", row.get("close", 0))),
                            "volume": float(row.get("Volume", row.get("volume", 0))),
                        })
                    print(f"  {current.date()} to {chunk_end.date()}: {len(df)} rows")
                else:
                    print(f"  {current.date()} to {chunk_end.date()}: No data")
                time.sleep(0.5)  # Rate limit
            except Exception as e:
                print(f"  {current.date()} to {chunk_end.date()}: Error - {e}")
            
            current = chunk_end
        
        if all_rows:
            print(f"\n{ticker}: Downloaded {len(all_rows)} total rows")
            return all_rows, ticker
    
    return None, None

def try_stooq():
    """Download via stooq (free, no API key)."""
    try:
        import pandas as pd
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas"])
        import pandas as pd
    
    # Stooq provides free CSV downloads
    # NASDAQ-100 index: ^NDX
    # QQQ ETF: QQQ.US
    
    symbols = [
        ("^ndx", "NASDAQ-100 Index"),
        ("qqq.us", "QQQ ETF"),
        ("nq.f", "NAS100 Futures"),
    ]
    
    for symbol, name in symbols:
        print(f"\nTrying stooq: {symbol} ({name})...")
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=5m&d1={START_DATE.replace('-','')}&d2={END_DATE.replace('-','')}"
        
        try:
            df = pd.read_csv(url)
            if df is not None and len(df) > 0:
                all_rows = []
                for _, row in df.iterrows():
                    all_rows.append({
                        "timestamp_utc": f"{row['Date']} {row['Time']}",
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0)),
                    })
                print(f"  {name}: Downloaded {len(all_rows)} rows")
                return all_rows, symbol
        except Exception as e:
            print(f"  {name}: Error - {e}")
    
    return None, None

def save_csv(rows, source):
    """Save rows to output CSV."""
    # Sort by timestamp
    rows.sort(key=lambda r: r["timestamp_utc"])
    
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\nSaved {len(rows)} rows to {OUTPUT_FILE}")
    print(f"Source: {source}")
    print(f"Date range: {rows[0]['timestamp_utc']} to {rows[-1]['timestamp_utc']}")
    return True

def main():
    print("=" * 70)
    print("NAS100 5-MINUTE DATA DOWNLOAD")
    print("=" * 70)
    print(f"Target: {START_DATE} to {END_DATE}")
    print(f"Output: {OUTPUT_FILE}")
    print()
    
    # Try yfinance first
    rows, source = try_yfinance_chunked()
    if rows:
        save_csv(rows, source)
        return True
    
    # Try stooq
    rows, source = try_stooq()
    if rows:
        save_csv(rows, source)
        return True
    
    print("\nAll sources failed. Manual download required.")
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
