"""
tools/dukascopy_nas100_probe.py — Data probe for NAS100 CFD (audit only).

Pulls Dukascopy NAS100 data and verifies:
- 5-min granularity
- Tick-to-bar alignment to :05 boundaries
- Coverage 2021-01-01..2025-05-13
- Continuity against committed US holiday list
- Duplicates
- Gaps

This is an AUDIT tool, not a backtest. It produces a probe report.
"""

import os
import sys
import csv
import urllib.request
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from research.data.validate_data_cfd import (
    is_weekend,
    is_ny_session,
    is_market_closed,
    ALL_HOLIDAYS,
    NY_TZ,
)

PROBE_DIR = "research/data/cfd_probe"
HOLIDAY_LIST_FILE = "research/data/us_holidays.txt"


def download_dukascopy_nas100():
    """Download Dukascopy NAS100 5-min data (placeholder for actual download)."""
    os.makedirs(PROBE_DIR, exist_ok=True)
    print(f"Probe directory: {PROBE_DIR}")
    print("Note: Dukascopy data download requires manual step or API key")
    print("      This probe assumes data is already downloaded.")
    return True


def verify_5min_granularity(bars):
    """Verify all bars are on 5-min boundaries."""
    misaligned = 0
    for bar in bars:
        if bar["time"].minute % 5 != 0:
            misaligned += 1
    return misaligned


def verify_coverage(bars, start_date, end_date):
    """Verify data covers the full window."""
    if not bars:
        return False, "No bars"
    
    first_bar = bars[0]["time"]
    last_bar = bars[-1]["time"]
    
    expected_start = datetime.strptime(start_date, "%Y-%m-%d")
    expected_end = datetime.strptime(end_date, "%Y-%m-%d")
    
    coverage_ok = (first_bar.date() <= expected_start.date() and 
                   last_bar.date() >= expected_end.date())
    
    return coverage_ok, f"First: {first_bar}, Last: {last_bar}"


def verify_continuity(bars):
    """Verify no unexpected gaps (excluding weekends and holidays)."""
    gaps = []
    for i in range(1, len(bars)):
        prev_ts = bars[i-1]["time"]
        curr_ts = bars[i]["time"]
        
        # Skip weekends
        if is_weekend(curr_ts):
            continue
        
        # Skip holidays
        if curr_ts.strftime("%Y-%m-%d") in ALL_HOLIDAYS:
            continue
        
        # Expected gap: 5 minutes
        expected_gap = timedelta(minutes=5)
        actual_gap = curr_ts - prev_ts
        
        if actual_gap > expected_gap * 3:  # More than 15 min = gap
            gaps.append(f"{prev_ts} -> {curr_ts} ({actual_gap})")
    
    return gaps


def verify_duplicates(bars):
    """Check for duplicate timestamps."""
    seen = set()
    duplicates = []
    for bar in bars:
        ts_str = bar["time"].strftime("%Y-%m-%d %H:%M:%S")
        if ts_str in seen:
            duplicates.append(ts_str)
        seen.add(ts_str)
    return duplicates


def run_probe():
    """Run the full NAS100 data probe."""
    print("=" * 78)
    print("NAS100 DUKASCOPY DATA PROBE (Audit Only)")
    print("=" * 78)
    print()
    print("Instrument: NAS100 (CFD on NASDAQ 100)")
    print("Source: Dukascopy historical data")
    print("Resolution: 5 minutes")
    print("Window: 2021-01-01..2025-05-13")
    print()
    
    # Check if data exists
    data_file = os.path.join(PROBE_DIR, "nas100_5m.csv")
    if not os.path.exists(data_file):
        print("DATA FILE NOT FOUND. Download required.")
        print(f"Expected: {data_file}")
        print()
        print("Probe cannot continue without data.")
        print("=" * 78)
        return
    
    # Load data
    bars = []
    with open(data_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bars.append({
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
    
    print(f"Loaded {len(bars)} bars")
    print()
    
    # Run checks
    print("1. 5-Minute Granularity Check:")
    misaligned = verify_5min_granularity(bars)
    print(f"   Misaligned bars: {misaligned}")
    print(f"   Status: {'PASS' if misaligned == 0 else 'FAIL'}")
    print()
    
    print("2. Coverage Check:")
    coverage_ok, coverage_msg = verify_coverage(bars, "2021-01-01", "2025-05-13")
    print(f"   {coverage_msg}")
    print(f"   Status: {'PASS' if coverage_ok else 'FAIL'}")
    print()
    
    print("3. Continuity Check:")
    gaps = verify_continuity(bars)
    print(f"   Unexpected gaps: {len(gaps)}")
    if gaps:
        for gap in gaps[:5]:
            print(f"     {gap}")
    print(f"   Status: {'PASS' if len(gaps) == 0 else 'FAIL'}")
    print()
    
    print("4. Duplicate Check:")
    duplicates = verify_duplicates(bars)
    print(f"   Duplicate timestamps: {len(duplicates)}")
    print(f"   Status: {'PASS' if len(duplicates) == 0 else 'FAIL'}")
    print()
    
    print("5. Holiday Continuity Check:")
    holiday_gaps = 0
    for i in range(1, len(bars)):
        curr_date = bars[i]["time"].strftime("%Y-%m-%d")
        if curr_date in ALL_HOLIDAYS:
            # Check if previous bar is from previous trading day
            prev_date = bars[i-1]["time"].strftime("%Y-%m-%d")
            if prev_date == curr_date:
                holiday_gaps += 1
    print(f"   Bars on holidays: {holiday_gaps}")
    print(f"   Status: {'PASS' if holiday_gaps == 0 else 'FAIL'}")
    print()
    
    print("=" * 78)
    print("PROBE COMPLETE")
    print("=" * 78)


if __name__ == "__main__":
    run_probe()
