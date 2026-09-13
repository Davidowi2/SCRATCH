#!/usr/bin/env python3
"""
tools/s010_smoke_test.py — 2020 M2 smoke test (audit-only, no verdict).

Assertions:
- trades > 0 (proves B1 fix)
- exit reasons include at least two of {STOP, TARGET, HARDFLAT}
- no exceptions
- gross_pf and net PF both printed

Records NO verdict, NO ledger row, NO graveyard row.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "research", "backtest"))

from S010_banklevel_fx import load_dataset, run_backtest, compute_metrics

def main():
    data_file = "research/data/eurusd_1h_2020_smoke.csv"
    
    print("=" * 70)
    print("S-010 2020 SMOKE TEST (M2 - Audit Only)")
    print("=" * 70)
    print(f"Data file: {data_file}")
    print()
    
    # Load data
    bars = load_dataset(data_file)
    print(f"Loaded {len(bars)} bars")
    
    # Filter to 2020 (sanity check)
    bars_2020 = [b for b in bars if b["time"].year == 2020]
    print(f"2020 bars: {len(bars_2020)}")
    
    # Run backtest (no Gate 1 - this is synthetic data)
    trades = run_backtest(bars_2020)
    metrics = compute_metrics(trades)
    
    print()
    print(f"Trades: {metrics['n']}")
    print(f"Wins: {metrics['wins']}")
    print(f"Win rate: {metrics['win_rate']:.4f}")
    print(f"Net PF: {metrics['profit_factor']:.4f}")
    print(f"Gross PF: {metrics['gross_pf']:.4f}")
    print(f"Gross Expectancy: {metrics['gross_expectancy']:.4f} pips")
    print(f"Net Expectancy: {metrics['net_expectancy']:.4f} pips")
    print(f"Max Drawdown: {metrics['max_dd_pips']:.1f} pips")
    print(f"Exit breakdown: {metrics['exits']}")
    print()
    
    # Assertions
    assert metrics['n'] > 0, "SMOKE FAIL: No trades (B1 fix not working)"
    print(f"ASSERT 1: trades > 0 -> PASS (n={metrics['n']})")
    
    exit_reasons = set(metrics['exits'].keys())
    required = {"STOP", "TARGET", "HARDFLAT"}
    found = exit_reasons & required
    assert len(found) >= 2, f"SMOKE FAIL: Only found {found}, need >= 2 of {required}"
    print(f"ASSERT 2: exit reasons include {found} -> PASS")
    
    assert metrics['gross_pf'] > 0, "SMOKE FAIL: Gross PF not computed"
    print(f"ASSERT 3: gross_pf = {metrics['gross_pf']:.4f} -> PASS")
    
    print()
    print("=" * 70)
    print("SMOKE TEST PASSED - All assertions met")
    print("NO verdict recorded, NO ledger row, NO graveyard row")
    print("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nSMOKE TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nSMOKE TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
