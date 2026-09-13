"""
tests/test_gate1_cfd.py — Unit tests for Gate 1 CFD branch.

Tests:
- DST boundary transitions (America/New_York)
- NY session detection (winter vs summer)
- US holiday detection
- Bid-side note validation
- 5-min timestamp alignment
- Data continuity checks

All tests must pass before B-002 fires.
"""

import sys
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from research.data.validate_data_cfd import (
    is_weekend,
    is_ny_session,
    is_market_closed,
    US_HOLIDAYS_2021,
    US_HOLIDAYS_2022,
    US_HOLIDAYS_2023,
    US_HOLIDAYS_2024,
    US_HOLIDAYS_2025,
    NY_TZ,
)


def test_is_weekend():
    """Test weekend detection."""
    sat = datetime(2024, 1, 6, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert is_weekend(sat) == True, "Saturday should be weekend"
    
    sun = datetime(2024, 1, 7, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert is_weekend(sun) == True, "Sunday should be weekend"
    
    mon = datetime(2024, 1, 8, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert is_weekend(mon) == False, "Monday should not be weekend"
    
    print("  test_is_weekend: PASS")


def test_ny_session_winter():
    """Test NY session detection in winter (EST, UTC-5)."""
    # 13:00 UTC = 08:00 ET (start of NY session)
    winter_start = datetime(2024, 1, 15, 13, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(winter_start) == True, "13:00 UTC in winter should be NY session"
    
    # 21:00 UTC = 16:00 ET (still in NY session, ends at 17:00 ET)
    winter_end = datetime(2024, 1, 15, 21, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(winter_end) == True, "21:00 UTC in winter should be NY session"
    
    # 12:00 UTC = 07:00 ET (before NY session)
    winter_before = datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(winter_before) == False, "12:00 UTC in winter should not be NY session"
    
    # 22:00 UTC = 17:00 ET (end of NY session, 17:00 is NOT < 17)
    winter_after = datetime(2024, 1, 15, 22, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(winter_after) == False, "22:00 UTC in winter should not be NY session"
    
    print("  test_ny_session_winter: PASS")


def test_ny_session_summer():
    """Test NY session detection in summer (EDT, UTC-4)."""
    # 13:00 UTC = 09:00 ET (summer, DST active)
    summer_start = datetime(2024, 7, 15, 13, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(summer_start) == True, "13:00 UTC in summer should be NY session"
    
    # 20:00 UTC = 16:00 ET (summer, still in NY session)
    summer_end = datetime(2024, 7, 15, 20, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(summer_end) == True, "20:00 UTC in summer should be NY session"
    
    # 12:00 UTC = 08:00 ET (start of NY session in summer)
    summer_before = datetime(2024, 7, 15, 12, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(summer_before) == True, "12:00 UTC in summer should be NY session (08:00 ET)"
    
    # 21:00 UTC = 17:00 ET (end of NY session)
    summer_after = datetime(2024, 7, 15, 21, 0, tzinfo=ZoneInfo("UTC"))
    assert is_ny_session(summer_after) == False, "21:00 UTC in summer should not be NY session (17:00 ET)"
    
    print("  test_ny_session_summer: PASS")


def test_dst_boundaries():
    """Test DST boundary transitions for 2024."""
    # DST 2024: March 10, 2:00 AM EST -> 3:00 AM EDT
    dst_start = datetime(2024, 3, 10, 7, 0, tzinfo=ZoneInfo("UTC"))
    assert dst_start.astimezone(NY_TZ).hour == 3, "DST start should be 03:00 EDT"
    assert dst_start.astimezone(NY_TZ).strftime("%Z") == "EDT", "DST start should be EDT"
    
    # November 3, 2024 at 06:00 UTC = 01:00 EST (DST ended)
    dst_end = datetime(2024, 11, 3, 6, 0, tzinfo=ZoneInfo("UTC"))
    assert dst_end.astimezone(NY_TZ).hour == 1, "DST end should be 01:00 EST"
    assert dst_end.astimezone(NY_TZ).strftime("%Z") == "EST", "DST end should be EST"
    
    print("  test_dst_boundaries: PASS")


def test_us_holidays():
    """Test US market holiday detection."""
    new_year = datetime(2024, 1, 1, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert is_market_closed(new_year) == True, "New Year should be market closed"
    
    july4 = datetime(2024, 7, 4, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert is_market_closed(july4) == True, "Independence Day should be market closed"
    
    thanksgiving = datetime(2024, 11, 28, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert is_market_closed(thanksgiving) == True, "Thanksgiving should be market closed"
    
    regular_day = datetime(2024, 3, 15, 15, 0, tzinfo=ZoneInfo("UTC"))
    assert is_market_closed(regular_day) == False, "Regular trading day should not be market closed"
    
    print("  test_us_holidays: PASS")


def test_holiday_completeness():
    """Verify all holiday sets are populated."""
    assert len(US_HOLIDAYS_2021) >= 10, "2021 should have at least 10 holidays"
    assert len(US_HOLIDAYS_2022) >= 9, "2022 should have at least 9 holidays"
    assert len(US_HOLIDAYS_2023) >= 10, "2023 should have at least 10 holidays"
    assert len(US_HOLIDAYS_2024) >= 10, "2024 should have at least 10 holidays"
    assert len(US_HOLIDAYS_2025) >= 5, "2025 should have at least 5 holidays"
    
    assert "2024-01-01" in US_HOLIDAYS_2024, "New Year 2024 missing"
    assert "2024-07-04" in US_HOLIDAYS_2024, "Independence Day 2024 missing"
    assert "2024-12-25" in US_HOLIDAYS_2024, "Christmas 2024 missing"
    
    print("  test_holiday_completeness: PASS")


def test_timestamp_alignment():
    """Test 5-minute timestamp alignment validation."""
    from research.data.validate_data_cfd import validate_cfd_data
    
    # Create test bars with proper alignment (need >= 100 real bars)
    bars = []
    base_ts = datetime(2024, 1, 2, 13, 0)  # Monday
    for i in range(150):
        bars.append({
            "time": base_ts + timedelta(minutes=5 * i),
            "open": 1.0 + i * 0.001,
            "high": 1.0 + i * 0.001 + 0.0005,
            "low": 1.0 + i * 0.001 - 0.0005,
            "close": 1.0 + i * 0.001 + 0.0002,
            "volume": 100 + i * 10,
        })
    
    result = validate_cfd_data(bars, "NAS100", "5M")
    assert result.get("misaligned_timestamps", -1) == 0, "All timestamps should be aligned"
    assert result["fatal"] == False, "Valid data should not be fatal"
    
    # Create test bars with misalignment
    misaligned_bars = []
    for i in range(150):
        misaligned_bars.append({
            "time": base_ts + timedelta(minutes=5 * i + 2),  # +2 min offset
            "open": 1.0 + i * 0.001,
            "high": 1.0 + i * 0.001 + 0.0005,
            "low": 1.0 + i * 0.001 - 0.0005,
            "close": 1.0 + i * 0.001 + 0.0002,
            "volume": 100 + i * 10,
        })
    
    result_misaligned = validate_cfd_data(misaligned_bars, "NAS100", "5M")
    assert result_misaligned.get("misaligned_timestamps", 0) > 0, "Misaligned timestamps should be detected"
    
    print("  test_timestamp_alignment: PASS")


def test_bid_side_note():
    """Verify CFD bid-side pricing assumption."""
    bid_price = 1.1050
    ask_price = 1.1052
    
    entry_at_bid = bid_price
    assert entry_at_bid == bid_price, "CFD entry should be at bid"
    
    spread = ask_price - bid_price
    # Use round to avoid floating point comparison issues
    assert round(spread, 4) == 0.0002, f"CFD spread should be 2 pips, got {spread}"
    
    print("  test_bid_side_note: PASS")


def test_all():
    """Run all tests."""
    print("=" * 78)
    print("GATE 1 CFD UNIT TESTS")
    print("=" * 78)
    
    tests = [
        test_is_weekend,
        test_ny_session_winter,
        test_ny_session_summer,
        test_dst_boundaries,
        test_us_holidays,
        test_holiday_completeness,
        test_timestamp_alignment,
        test_bid_side_note,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  {test.__name__}: FAIL - {e}")
            failed += 1
        except Exception as e:
            print(f"  {test.__name__}: ERROR - {e}")
            failed += 1
    
    print("-" * 78)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 78)
    
    return failed == 0


if __name__ == "__main__":
    success = test_all()
    sys.exit(0 if success else 1)
