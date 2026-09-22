#!/usr/bin/env python3
"""
tests/test_trade_manager.py — Unit tests for trade_manager.py exit engine.

Tests:
- BE trigger fires at +1R exactly
- Trail ratchets correctly (never moves stop backward)
- Scale-out splits 50/50 at +1.5R
- Stop-hit before BE = full loss at initial stop
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research"))
from execution.trade_manager import manage_trade


def test_be_trigger_at_1r():
    """BE trigger should fire when unrealized P&L reaches +1R."""
    bars = [
        {"time": "0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"time": "1", "open": 100, "high": 105, "low": 100, "close": 105},
        {"time": "2", "open": 105, "high": 110, "low": 105, "close": 110},  # +1R → BE
        {"time": "3", "open": 110, "high": 115, "low": 108, "close": 115},  # +1.5R → scale
        {"time": "4", "open": 115, "high": 120, "low": 113, "close": 120},  # +2R target
    ]
    fills = manage_trade(bars, 0, "LONG", 100.0, 90.0, max_hold=72)
    # Should have scale-out at 1.5R (BE triggered, then scaled)
    scale_fills = [f for f in fills if f.reason == "SCALE_OUT_1.5R"]
    assert len(scale_fills) == 1, f"Expected 1 scale-out, got {scale_fills}"
    assert scale_fills[0].fraction == 0.5
    print(f"  PASS: BE trigger at 1R → {fills}")


def test_trail_ratchet_never_backward():
    """Trailing stop should never move backward."""
    bars = [
        {"time": "0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"time": "1", "open": 100, "high": 105, "low": 100, "close": 105},
        {"time": "2", "open": 105, "high": 110, "low": 105, "close": 110},  # BE trigger
        {"time": "3", "open": 110, "high": 115, "low": 106, "close": 112},  # trail to prev low (106)
        {"time": "4", "open": 112, "high": 113, "low": 108, "close": 110},  # trail to 108
        {"time": "5", "open": 110, "high": 110, "low": 105, "close": 107},  # no trail back (107 < 108)
        {"time": "6", "open": 107, "high": 107, "low": 95, "close": 95},   # stop hit at 108
    ]
    fills = manage_trade(bars, 0, "LONG", 100.0, 90.0, max_hold=72)
    assert len(fills) >= 1, f"Expected fills, got {fills}"
    assert fills[-1].reason == "STOP", f"Expected STOP, got {fills[-1].reason}"
    print(f"  PASS: Trail ratchet → {fills}")


def test_scale_out_50_50():
    """Scale-out should split 50/50 at +1.5R."""
    bars = [
        {"time": "0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"time": "1", "open": 100, "high": 105, "low": 100, "close": 105},
        {"time": "2", "open": 105, "high": 110, "low": 105, "close": 110},  # +1R → BE
        {"time": "3", "open": 110, "high": 115, "low": 110, "close": 115},  # +1.5R → scale out
        {"time": "4", "open": 115, "high": 120, "low": 113, "close": 120},  # remainder → target
    ]
    fills = manage_trade(bars, 0, "LONG", 100.0, 90.0, max_hold=72)
    scale_fills = [f for f in fills if f.reason == "SCALE_OUT_1.5R"]
    assert len(scale_fills) == 1, f"Expected 1 scale-out, got {scale_fills}"
    assert scale_fills[0].fraction == 0.5, f"Expected 0.5 fraction, got {scale_fills[0].fraction}"
    print(f"  PASS: Scale-out 50/50 at 1.5R → {fills}")


def test_stop_hit_before_be():
    """Stop hit before BE trigger = full loss at initial stop."""
    bars = [
        {"time": "0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"time": "1", "open": 100, "high": 102, "low": 95, "close": 95},  # low=95 > 90, no stop
        {"time": "2", "open": 95, "high": 95, "low": 85, "close": 85},   # low=85 < 90 → STOP
    ]
    fills = manage_trade(bars, 0, "LONG", 100.0, 90.0, max_hold=72)
    assert len(fills) == 1, f"Expected 1 fill, got {fills}"
    assert fills[0].reason == "STOP", f"Expected STOP, got {fills[0].reason}"
    assert fills[0].fraction == 1.0, f"Expected full fraction, got {fills[0].fraction}"
    print(f"  PASS: Stop hit before BE = full loss → {fills}")


def test_be_trigger_exact_1r():
    """BE should trigger at exactly +1R (unrealized == risk)."""
    bars = [
        {"time": "0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"time": "1", "open": 100, "high": 110, "low": 100, "close": 110},  # +1R exactly → BE
        {"time": "2", "open": 110, "high": 115, "low": 105, "close": 115},  # +1.5R → scale
        {"time": "3", "open": 115, "high": 120, "low": 113, "close": 120},  # +2R → target
    ]
    fills = manage_trade(bars, 0, "LONG", 100.0, 90.0, max_hold=72)
    # BE at +1R means the position survives to scale-out (not stopped out)
    scale_fills = [f for f in fills if f.reason == "SCALE_OUT_1.5R"]
    assert len(scale_fills) == 1, f"BE should trigger → scale-out at 1.5R, got {fills}"
    print(f"  PASS: BE at exactly +1R → {fills}")


def test_short_be_trigger():
    """SHORT version: BE trigger at -1R."""
    bars = [
        {"time": "0", "open": 100, "high": 100, "low": 100, "close": 100},
        {"time": "1", "open": 100, "high": 100, "low": 90, "close": 90},   # unrealized = 10 = 1R
        {"time": "2", "open": 90, "high": 95, "low": 80, "close": 80},
    ]
    fills = manage_trade(bars, 0, "SHORT", 100.0, 110.0, max_hold=72)
    # Should scale-out at 1.5R (SHORT)
    scale_fills = [f for f in fills if f.reason == "SCALE_OUT_1.5R"]
    assert len(scale_fills) == 1, f"Expected scale-out, got {fills}"
    print(f"  PASS: SHORT BE trigger → {fills}")


if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("TRADE MANAGER UNIT TESTS")
    print("=" * 60)
    passed = 0
    tests = [
        test_be_trigger_at_1r,
        test_trail_ratchet_never_backward,
        test_scale_out_50_50,
        test_stop_hit_before_be,
        test_be_trigger_exact_1r,
        test_short_be_trigger,
    ]
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {t.__name__} — {e}")
    print("-" * 60)
    print(f"Results: {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
