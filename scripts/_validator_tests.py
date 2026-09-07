"""
Validator test suite — synthetic datasets with known outcomes.
Each test builds a tiny CSV, runs validate_data.audit(), and checks the verdict.
All must pass → validator is frozen.

Run: python scripts/_validator_tests.py
"""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research', 'data'))
from validate_data import audit, MARKET_HOLIDAYS

PASSED = 0
FAILED = 0


def make_csv(rows, path):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['timestamp_utc', 'open', 'high', 'low', 'close', 'volume'])
        for r in rows:
            w.writerow(r)


def run_test(name, fn, expected_verdict):
    global PASSED, FAILED
    with tempfile.TemporaryDirectory() as tmpdir:
        fn(tmpdir)
        log_path = os.path.join(tmpdir, 'audit.log')
        verdict = audit(log_path, tmpdir, os.path.join(tmpdir, 'cleaned.csv'))
        if verdict == expected_verdict:
            print(f"  ✅ {name}: {verdict}")
            PASSED += 1
        else:
            print(f"  ❌ {name}: expected {expected_verdict}, got {verdict}")
            FAILED += 1


# === ORIGINAL TESTS ===

def clean_single_day(tmpdir):
    """Clean single day — should be CLEAN"""
    rows = [
        ['2024-01-02 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2024-01-02 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
        ['2024-01-02 02:00:00', '1.10040', '1.10090', '1.09990', '1.10060', '100'],
        ['2024-01-02 03:00:00', '1.10060', '1.10110', '1.10010', '1.10080', '100'],
        ['2024-01-02 04:00:00', '1.10080', '1.10130', '1.10030', '1.10100', '100'],
        ['2024-01-02 05:00:00', '1.10100', '1.10150', '1.10050', '1.10120', '100'],
        ['2024-01-02 06:00:00', '1.10120', '1.10170', '1.10070', '1.10140', '100'],
        ['2024-01-02 07:00:00', '1.10140', '1.10190', '1.10090', '1.10160', '100'],
        ['2024-01-02 08:00:00', '1.10160', '1.10210', '1.10110', '1.10180', '100'],
        ['2024-01-02 09:00:00', '1.10180', '1.10230', '1.10130', '1.10200', '100'],
        ['2024-01-02 10:00:00', '1.10200', '1.10250', '1.10150', '1.10220', '100'],
        ['2024-01-02 11:00:00', '1.10220', '1.10270', '1.10170', '1.10240', '100'],
        ['2024-01-02 12:00:00', '1.10240', '1.10290', '1.10190', '1.10260', '100'],
        ['2024-01-02 13:00:00', '1.10260', '1.10310', '1.10210', '1.10280', '100'],
        ['2024-01-02 14:00:00', '1.10280', '1.10330', '1.10230', '1.10300', '100'],
        ['2024-01-02 15:00:00', '1.10300', '1.10350', '1.10250', '1.10320', '100'],
        ['2024-01-02 16:00:00', '1.10320', '1.10370', '1.10270', '1.10340', '100'],
        ['2024-01-02 17:00:00', '1.10340', '1.10390', '1.10290', '1.10360', '100'],
        ['2024-01-02 18:00:00', '1.10360', '1.10410', '1.10310', '1.10380', '100'],
        ['2024-01-02 19:00:00', '1.10380', '1.10430', '1.10330', '1.10400', '100'],
        ['2024-01-02 20:00:00', '1.10400', '1.10450', '1.10350', '1.10420', '100'],
        ['2024-01-02 21:00:00', '1.10420', '1.10470', '1.10370', '1.10440', '100'],
        ['2024-01-02 22:00:00', '1.10440', '1.10490', '1.10390', '1.10460', '100'],
        ['2024-01-02 23:00:00', '1.10460', '1.10510', '1.10410', '1.10480', '100'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-01-02.csv'))


def ohlc_fail_day(tmpdir):
    """OHLC failure — should be FLAGGED (high < low)"""
    rows = [
        ['2024-01-02 00:00:00', '1.10000', '1.09950', '1.10050', '1.10020', '100'],
        ['2024-01-02 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-01-02.csv'))


def weekend_contam_day(tmpdir):
    """Weekend contamination — Saturday real bars → FLAGGED"""
    rows = [
        ['2024-01-06 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2024-01-06 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-01-06.csv'))


def holiday_day(tmpdir):
    """Market holiday — all flat filler → REJECT (no real bars)"""
    rows = [
        ['2024-01-01 00:00:00', '1.10000', '1.10000', '1.10000', '1.10000', '0'],
        ['2024-01-01 01:00:00', '1.10000', '1.10000', '1.10000', '1.10000', '0'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-01-01.csv'))


def multi_file_gap(tmpdir):
    """Two consecutive days with a gap → REJECT"""
    day1 = [
        ['2024-01-02 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2024-01-02 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
    ]
    day2 = [
        ['2024-01-04 10:00:00', '1.10100', '1.10150', '1.10050', '1.10120', '100'],  # Wednesday
        ['2024-01-04 11:00:00', '1.10120', '1.10170', '1.10070', '1.10140', '100'],
    ]
    make_csv(day1, os.path.join(tmpdir, '2024-01-02.csv'))
    make_csv(day2, os.path.join(tmpdir, '2024-01-04.csv'))


# === PHASE 2.1: HISTORICAL-FAILURE TESTS ===

def boundary_truncated_week_start(tmpdir):
    """
    Dataset starts 2021-01-03 (Sunday). First week is truncated.
    Should be CLEAN because the validator excludes boundary weeks
    from session coverage check.
    """
    rows = [
        ['2021-01-03 22:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2021-01-03 23:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
        ['2021-01-04 00:00:00', '1.10040', '1.10090', '1.09990', '1.10060', '100'],
        ['2021-01-04 01:00:00', '1.10060', '1.10110', '1.10010', '1.10080', '100'],
        ['2021-01-04 02:00:00', '1.10080', '1.10130', '1.10030', '1.10100', '100'],
        ['2021-01-04 03:00:00', '1.10100', '1.10150', '1.10050', '1.10120', '100'],
        ['2021-01-04 04:00:00', '1.10120', '1.10170', '1.10070', '1.10140', '100'],
        ['2021-01-04 05:00:00', '1.10140', '1.10190', '1.10090', '1.10160', '100'],
        ['2021-01-04 06:00:00', '1.10160', '1.10210', '1.10110', '1.10180', '100'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2021-01-03.csv'))


def same_day_partial_holiday_gap(tmpdir):
    """
    Christmas Day 2024: only Asian session hours have real bars.
    Gap from 06:00 to 22:00 is same-day holiday → excluded from gap check.
    Should be CLEAN.
    """
    rows = [
        ['2024-12-25 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2024-12-25 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
        ['2024-12-25 02:00:00', '1.10040', '1.10090', '1.09990', '1.10060', '100'],
        ['2024-12-25 03:00:00', '1.10060', '1.10110', '1.10010', '1.10080', '100'],
        ['2024-12-25 04:00:00', '1.10080', '1.10130', '1.10030', '1.10100', '100'],
        ['2024-12-25 05:00:00', '1.10100', '1.10150', '1.10050', '1.10120', '100'],
        ['2024-12-25 06:00:00', '1.10120', '1.10170', '1.10070', '1.10140', '100'],
        ['2024-12-25 22:00:00', '1.10140', '1.10190', '1.10090', '1.10160', '100'],
        ['2024-12-25 23:00:00', '1.10160', '1.10210', '1.10110', '1.10180', '100'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-12-25.csv'))


def same_day_non_holiday_gap(tmpdir):
    """
    Non-holiday with same-day gap (mid-day outage).
    Should be REJECT (real outage, not a holiday artifact).
    """
    rows = [
        ['2024-03-15 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2024-03-15 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
        # 10-hour gap — real outage
        ['2024-03-15 11:00:00', '1.10100', '1.10150', '1.10050', '1.10120', '100'],
        ['2024-03-15 12:00:00', '1.10120', '1.10170', '1.10070', '1.10140', '100'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-03-15.csv'))


def real_gap_non_holiday(tmpdir):
    """
    Monday → Wednesday gap (no Saturday in between, no holiday).
    Should be REJECT.
    """
    day1 = [
        ['2024-03-11 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2024-03-11 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
    ]
    day2 = [
        ['2024-03-13 10:00:00', '1.10100', '1.10150', '1.10050', '1.10120', '100'],
        ['2024-03-13 11:00:00', '1.10120', '1.10170', '1.10070', '1.10140', '100'],
    ]
    make_csv(day1, os.path.join(tmpdir, '2024-03-11.csv'))
    make_csv(day2, os.path.join(tmpdir, '2024-03-13.csv'))


print("=== VALIDATOR TEST SUITE ===\n")

# Original tests
print("Original tests:")
run_test("Clean single day", clean_single_day, "CLEAN")
run_test("OHLC integrity failure", ohlc_fail_day, "FLAGGED")
run_test("Weekend contamination", weekend_contam_day, "FLAGGED")
run_test("Market holiday (no real bars)", holiday_day, "REJECT")
run_test("Multi-file gap", multi_file_gap, "REJECT")

# Phase 2.1: Historical-failure tests
print("\nPhase 2.1: Historical-failure tests:")
run_test("Boundary-truncated week start", boundary_truncated_week_start, "CLEAN")
run_test("Same-day partial holiday gap", same_day_partial_holiday_gap, "CLEAN")
run_test("Same-day non-holiday gap", same_day_non_holiday_gap, "REJECT")
run_test("Real gap (Mon→Wed, no holiday)", real_gap_non_holiday, "REJECT")

print(f"\n=== RESULTS: {PASSED} passed, {FAILED} failed ===")
if FAILED > 0:
    sys.exit(1)
