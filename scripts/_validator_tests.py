"""
Validator test suite — synthetic datasets with known outcomes.
Each test builds a tiny CSV, runs validate_data.audit(), and checks the verdict.
All must pass → validator is frozen.
"""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research', 'data'))
from validate_data import audit, MARKET_HOLIDAYS, ASIAN_HOURS

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


def clean_single_day(tmpdir):
    """Clean single day — should be CLEAN (all real bars, no gaps, no flags)"""
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
    """OHLC integrity failure — should be FLAGGED (high < low)"""
    rows = [
        ['2024-01-02 00:00:00', '1.10000', '1.09950', '1.10050', '1.10020', '100'],  # high < low
        ['2024-01-02 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-01-02.csv'))


def weekend_contam_day(tmpdir):
    """Weekend contamination — Saturday real bar should be stripped + FLAGGED"""
    rows = [
        ['2024-01-06 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],  # Saturday
        ['2024-01-06 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],  # Saturday
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-01-06.csv'))


def holiday_day(tmpdir):
    """Market holiday — all flat filler on known holiday"""
    rows = [
        ['2024-01-01 00:00:00', '1.10000', '1.10000', '1.10000', '1.10000', '0'],
        ['2024-01-01 01:00:00', '1.10000', '1.10000', '1.10000', '1.10000', '0'],
    ]
    make_csv(rows, os.path.join(tmpdir, '2024-01-01.csv'))


def multi_file_gap(tmpdir):
    """Two consecutive days with a gap — should be REJECT"""
    day1 = [
        ['2024-01-02 00:00:00', '1.10000', '1.10050', '1.09950', '1.10020', '100'],
        ['2024-01-02 01:00:00', '1.10020', '1.10070', '1.09970', '1.10040', '100'],
    ]
    day2 = [
        ['2024-01-03 10:00:00', '1.10100', '1.10150', '1.10050', '1.10120', '100'],
        ['2024-01-03 11:00:00', '1.10120', '1.10170', '1.10070', '1.10140', '100'],
    ]
    make_csv(day1, os.path.join(tmpdir, '2024-01-02.csv'))
    make_csv(day2, os.path.join(tmpdir, '2024-01-03.csv'))


print("=== VALIDATOR TEST SUENITE ===\n")

# 1. Clean single day
run_test("Clean single day (all real, no gaps)", clean_single_day, "CLEAN")

# 2. OHLC failure
run_test("OHLC integrity failure (high < low)", ohlc_fail_day, "FLAGGED")

# 3. Weekend contamination
run_test("Weekend contamination (Saturday real bars)", weekend_contam_day, "FLAGGED")

# 4. Holiday
run_test("Market holiday (all flat, known holiday)", holiday_day, "REJECT")

# 5. Multi-file gap
run_test("Multi-file data gap (>4h not explained)", multi_file_gap, "REJECT")

print(f"\n=== RESULTS: {PASSED} passed, {FAILED} failed ===")
if FAILED > 0:
    sys.exit(1)
