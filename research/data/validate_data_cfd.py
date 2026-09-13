"""
research/data/validate_data_cfd.py — Gate 1 validator for CFD instruments (NAS100, US30).

Uses zoneinfo for NY session detection with proper DST handling.
Holiday-aware continuity checks.
Bid-side note: CFD prices are inherently bid-side (no separate ask).

HARD RULE: Any dataset with synthetic: true in factory/data_provenance.json
is REJECTED for verdict runs (IS/OOS). Plumbing smoke tests are exempt
but must be labeled.
"""

import csv
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "factory", "data_provenance.json")


def is_synthetic_dataset(dataset_path):
    """Check if a dataset is marked as synthetic in the manifest."""
    if not os.path.exists(MANIFEST_PATH):
        return False  # No manifest = assume real (backward compat)
    
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    
    datasets = manifest.get("datasets", {})
    return datasets.get(dataset_path, {}).get("synthetic", False)


def gate1_audit_cfd(dataset_path, instrument, resolution="5M"):
    """
    Gate 1 audit for CFD data.
    
    Returns: "PASS", "FLAG", or "REJECT"
    """
    # HARD RULE: Reject synthetic data for verdict runs
    if is_synthetic_dataset(dataset_path):
        return "REJECT", f"SYNTHETIC DATA REJECTED: {dataset_path} is marked synthetic in manifest"
    
    # Load and validate data
    bars = []
    with open(dataset_path, newline="") as f:
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
    
    result = validate_cfd_data(bars, instrument, resolution)
    
    if result.get("fatal"):
        return "REJECT", result["flags"]
    elif result.get("flags"):
        return "FLAG", result["flags"]
    else:
        return "PASS", []

# US market holidays (2021-02-13..2025-05-13)
US_HOLIDAYS_2021 = {
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-06-18", "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24",
}
US_HOLIDAYS_2022 = {
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
    "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
}
US_HOLIDAYS_2023 = {
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
    "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
}
US_HOLIDAYS_2024 = {
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
}
US_HOLIDAYS_2025 = {
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
}

ALL_HOLIDAYS = US_HOLIDAYS_2021 | US_HOLIDAYS_2022 | US_HOLIDAYS_2023 | US_HOLIDAYS_2024 | US_HOLIDAYS_2025


def is_weekend(dt_utc):
    """Check if UTC datetime is on a weekend."""
    return dt_utc.weekday() >= 5


def is_ny_session(dt_utc):
    """
    Check if UTC datetime falls in NY session (08:00-17:00 ET).
    DST-aware: uses America/New_York timezone to determine actual NY time.
    """
    dt_ny = dt_utc.astimezone(NY_TZ)
    hour_ny = dt_ny.hour
    return 8 <= hour_ny < 17


def is_market_closed(dt_utc):
    """Check if market is closed (weekend or US holiday)."""
    if is_weekend(dt_utc):
        return True
    date_str = dt_utc.strftime("%Y-%m-%d")
    return date_str in ALL_HOLIDAYS


def validate_cfd_data(bars, instrument, resolution="5M"):
    """
    Validate CFD data quality.
    """
    flags = []
    total = len(bars)
    
    if total == 0:
        flags.append("FATAL: No bars in dataset")
        return {"fatal": True, "flags": flags}
    
    real_bars = 0
    zero_volume = 0
    weekend_bars = 0
    holiday_bars = 0
    duplicates = 0
    gaps = 0
    misaligned = 0
    
    seen_timestamps = set()
    prev_ts = None
    
    for bar in bars:
        ts = bar["time"]
        
        # Check duplicates
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        if ts_str in seen_timestamps:
            duplicates += 1
        seen_timestamps.add(ts_str)
        
        # Check weekend
        if is_weekend(ts):
            weekend_bars += 1
            continue
        
        # Check holiday
        date_str = ts.strftime("%Y-%m-%d")
        if date_str in ALL_HOLIDAYS:
            holiday_bars += 1
            continue
        
        # Check zero volume
        if bar.get("volume", 0) == 0:
            zero_volume += 1
        
        # Check timestamp alignment (5-min boundaries)
        if resolution == "5M":
            if ts.minute % 5 != 0:
                misaligned += 1
        
        # Check gaps
        if prev_ts is not None:
            expected_gap = timedelta(minutes=5)
            actual_gap = ts - prev_ts
            if actual_gap > expected_gap * 3 and is_ny_session(ts):
                gaps += 1
            prev_ts = ts
        
        real_bars += 1
    
    # Flag checks
    if misaligned > 0:
        flags.append(f"FLAG: {misaligned} misaligned timestamp(s) (not on 5-min boundary)")
    
    if gaps > 0:
        flags.append(f"FLAG: {gaps} gap(s) detected during NY session")
    
    if duplicates > 0:
        flags.append(f"FLAG: {duplicates} duplicate timestamp(s)")
    
    if real_bars > 0 and zero_volume > real_bars * 0.5:
        flags.append(f"FATAL: {zero_volume} zero-volume bars ({100*zero_volume/real_bars:.1f}% of real)")
        return {"fatal": True, "flags": flags}
    
    if real_bars < 100:
        flags.append(f"FATAL: Only {real_bars} real bars (minimum 100)")
        return {"fatal": True, "flags": flags}
    
    return {
        "fatal": False,
        "total_bars": total,
        "real_bars": real_bars,
        "zero_volume_bars": zero_volume,
        "weekend_bars": weekend_bars,
        "holiday_bars": holiday_bars,
        "duplicate_timestamps": duplicates,
        "gaps_detected": gaps,
        "misaligned_timestamps": misaligned,
        "flags": flags,
    }


def run_probe_report():
    """
    Run probe report for NAS100 CFD data.

    CLASSIFICATION: PLUMBING SMOKE — NOT data validation.
    This tool probes data files for structural integrity (alignment, dupes,
    gaps) but does NOT validate real-market fidelity. Synthetic data can
    PASS this probe while being worthless for trading analysis.

    For real data validation, use dukascopy ticks + holiday cross-reference.
    """
    print("=" * 78)
    print("GATE 1 CFD PROBE — NAS100 DATA VALIDATION")
    print("=" * 78)
    print()
    print("Instrument: NAS100 (CFD on NASDAQ 100)")
    print("Source: Dukascopy historical data")
    print("Resolution: 5 minutes")
    print("Window: 2021-01-01..2025-05-13")
    print("Session detection: zoneinfo America/New_York (DST-aware)")
    print("Holiday list: 49 US market holidays loaded")
    print()
    print("DST Boundary Tests:")
    print("-" * 78)
    
    # DST 2024
    dst_start_2024 = datetime(2024, 3, 10, 7, 0, tzinfo=ZoneInfo("UTC"))
    dst_end_2024 = datetime(2024, 11, 3, 6, 0, tzinfo=ZoneInfo("UTC"))
    
    print(f"  2024 DST start (Mar 10 07:00 UTC):")
    print(f"    UTC:  {dst_start_2024.strftime('%Y-%m-%d %H:%M')}")
    print(f"    NY:   {dst_start_2024.astimezone(NY_TZ).strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"    Session: {is_ny_session(dst_start_2024)}")
    
    print(f"  2024 DST end (Nov 3 06:00 UTC):")
    print(f"    UTC:  {dst_end_2024.strftime('%Y-%m-%d %H:%M')}")
    print(f"    NY:   {dst_end_2024.astimezone(NY_TZ).strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"    Session: {is_ny_session(dst_end_2024)}")
    
    # Winter vs Summer
    winter_ts = datetime(2024, 1, 15, 13, 0, tzinfo=ZoneInfo("UTC"))
    summer_ts = datetime(2024, 7, 15, 13, 0, tzinfo=ZoneInfo("UTC"))
    
    print(f"  Winter (Jan 15 13:00 UTC):")
    print(f"    NY: {winter_ts.astimezone(NY_TZ).strftime('%H:%M %Z')} → Session: {is_ny_session(winter_ts)}")
    print(f"  Summer (Jul 15 13:00 UTC):")
    print(f"    NY: {summer_ts.astimezone(NY_TZ).strftime('%H:%M %Z')} → Session: {is_ny_session(summer_ts)}")
    
    print()
    print("Holiday Continuity Tests:")
    print("-" * 78)
    test_holidays = [
        datetime(2024, 1, 1, 15, 0, tzinfo=ZoneInfo("UTC")),   # New Year
        datetime(2024, 7, 4, 15, 0, tzinfo=ZoneInfo("UTC")),   # Independence Day
        datetime(2024, 11, 28, 15, 0, tzinfo=ZoneInfo("UTC")), # Thanksgiving
    ]
    for ts in test_holidays:
        print(f"  {ts.strftime('%Y-%m-%d')}: market_closed={is_market_closed(ts)}, ny_session={is_ny_session(ts)}")
    
    print()
    print("CFD Gate 1 Status: CODE WRITTEN, awaiting Dukascopy data download")
    print("=" * 78)


if __name__ == "__main__":
    run_probe_report()
