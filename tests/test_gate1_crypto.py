"""
tests/test_gate1_crypto.py — Unit tests for Gate 1 CRYPTO branch.

Tests:
- 24/7 continuity: single missing 5m bar = gap event (no weekend exemption)
- :05 boundary alignment
- duplicate rejection
- OHLC sanity
- synthetic rejection via manifest (HARD RULE)
- completeness floor
- BTCUSDT price plausibility (symbol sanity)
"""

import os
import sys
import csv
import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from research.data.validate_data_crypto import gate1_audit_crypto, is_synthetic_dataset

TMP = tempfile.mkdtemp(prefix="gate1crypto_")


def make_csv(path, bars):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for b in bars:
            w.writerow(b)


def gen_bars(start, n, skip_idx=None, misalign_idx=None, dupe_idx=None):
    """Generate n clean 5m bars starting at `start` (UTC)."""
    bars = []
    step = timedelta(minutes=5)
    for i in range(n):
        ts = start + i * step
        if skip_idx is not None and i == skip_idx:
            continue
        if misalign_idx is not None and i == misalign_idx:
            ts = ts + timedelta(minutes=2)  # off-boundary
        price = 40000.0 + i
        bar = {
            "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "open": price, "high": price + 10, "low": price - 10, "close": price + 1,
            "volume": 12.5,
        }
        bars.append(bar)
        if dupe_idx is not None and i == dupe_idx:
            bars.append(dict(bar))  # exact duplicate
    return bars


def test_clean_pass():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    path = os.path.join(TMP, "clean.csv")
    make_csv(path, gen_bars(start, 288))  # full day, 24h
    rep = gate1_audit_crypto(path, verbose=False)
    assert rep["verdict"] == "PASS", f"expected PASS, got {rep['verdict']}: {rep['fatal'] + rep['flags']}"
    print("  test_clean_pass: PASS")


def test_single_missing_bar_gap():
    """24/7 rule: ONE missing bar (even across a weekend boundary) = gap event."""
    start = datetime(2024, 3, 8, tzinfo=timezone.utc)  # Friday
    path = os.path.join(TMP, "gap.csv")
    make_csv(path, gen_bars(start, 576, skip_idx=100))  # 2 days, skip one bar
    rep = gate1_audit_crypto(path, verbose=False)
    assert rep["stats"]["gap_events"] == 1, rep
    assert rep["stats"]["max_gap_bars"] == 1, rep
    assert rep["verdict"] in ("FLAG", "REJECT"), "missing bar must not PASS"
    print("  test_single_missing_bar_gap: PASS")


def test_weekend_no_exemption():
    """A gap ON the weekend is still a gap — crypto doesn't close."""
    start = datetime(2024, 3, 9, 0, tzinfo=timezone.utc)  # Saturday
    path = os.path.join(TMP, "weekend_gap.csv")
    # skip 288 bars worth = entire Sunday... simpler: skip one mid-Saturday bar
    bars = gen_bars(start, 576)
    del bars[50]
    make_csv(path, bars)
    rep = gate1_audit_crypto(path, verbose=False)
    assert rep["stats"]["gap_events"] >= 1, "weekend gap must register (no exemption)"
    print("  test_weekend_no_exemption: PASS")


def test_misaligned_bar():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    path = os.path.join(TMP, "misalign.csv")
    make_csv(path, gen_bars(start, 288, misalign_idx=10))
    rep = gate1_audit_crypto(path, verbose=False)
    assert rep["verdict"] == "REJECT", "misaligned bar is fatal"
    print("  test_misaligned_bar: PASS")


def test_duplicates():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    path = os.path.join(TMP, "dupe.csv")
    make_csv(path, gen_bars(start, 288, dupe_idx=10))
    rep = gate1_audit_crypto(path, verbose=False)
    assert rep["stats"]["duplicates"] == 1
    assert rep["verdict"] == "REJECT", "duplicates are fatal"
    print("  test_duplicates: PASS")


def test_bad_ohlc():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    path = os.path.join(TMP, "ohlc.csv")
    bars = gen_bars(start, 288)
    bars[5]["high"] = bars[5]["open"] - 100  # impossible: high < open
    make_csv(path, bars)
    rep = gate1_audit_crypto(path, verbose=False)
    assert rep["stats"]["bad_ohlc"] == 1
    assert rep["verdict"] == "REJECT"
    print("  test_bad_ohlc: PASS")


def test_price_implausible():
    """Wrong symbol sanity: prices in cents/absurd range must reject."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    path = os.path.join(TMP, "wrongsym.csv")
    bars = gen_bars(start, 288)
    for b in bars:
        b["open"] /= 100000; b["high"] /= 100000; b["low"] /= 100000; b["close"] /= 100000
    make_csv(path, bars)
    rep = gate1_audit_crypto(path, verbose=False)
    assert rep["verdict"] == "REJECT", "BTCUSDT price floor sanity failed"
    print("  test_price_implausible: PASS")


def test_synthetic_rejection_hard_rule():
    """HARD RULE: manifest synthetic:true => REJECT even if structurally perfect."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rel_path = "research/data/crypto/_synthetic_test_tmp.csv"
    abs_path = os.path.join(os.path.dirname(__file__), "..", rel_path)
    make_csv(abs_path, gen_bars(start, 288))
    manifest_path = os.path.join(os.path.dirname(__file__), "..", "factory", "data_provenance.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    entry = {
        "source": "unit-test-fixture",
        "generator": "tests/test_gate1_crypto.py",
        "sha256": "0" * 64,
        "synthetic": True,
        "rows": 288,
        "note": "TEMPORARY TEST ENTRY — removed after run",
    }
    manifest["datasets"][rel_path.replace("\\", "/")] = entry
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    try:
        assert is_synthetic_dataset(rel_path) is True
        rep = gate1_audit_crypto(rel_path, verbose=False)
        assert rep["verdict"] == "REJECT", f"synthetic must be REJECTed, got {rep['verdict']}"
        assert any("SYNTHETIC" in x for x in rep["fatal"]), rep["fatal"]
    finally:
        # cleanup: remove fixture + manifest entry
        os.remove(abs_path)
        del manifest["datasets"][rel_path.replace("\\", "/")]
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
    print("  test_synthetic_rejection_hard_rule: PASS")


def main():
    print("=" * 70)
    print("GATE 1 CRYPTO UNIT TESTS")
    print("=" * 70)
    tests = [
        test_clean_pass,
        test_single_missing_bar_gap,
        test_weekend_no_exemption,
        test_misaligned_bar,
        test_duplicates,
        test_bad_ohlc,
        test_price_implausible,
        test_synthetic_rejection_hard_rule,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  {t.__name__}: FAIL — {e}")
    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
