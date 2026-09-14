"""
tools/s012_smoke_test.py — S-012 audit-only smoke on the REAL 2020 slice (M2 ruling).

Re-runnable, consumes no one-shot, records NO verdict, NO ledger row,
NO graveyard row. Assertions:
  A1: trades > 0
  A2: exit reasons include >= 2 of {STOP, TARGET, HARDFLAT}
  A3: friction arithmetic spot-check on 3 trades:
      friction == 2*0.0005*entry_price  AND  net == gross - friction
  A4: expectancy printed in points AND percent
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research"))

from backtest.S012_banklevel_crypto import (
    run_backtest, compute_metrics, load_dataset, friction_for, FEE_RATE,
)

DATA = "research/data/crypto/btcusdt_5m_2020_smoke.csv"

from datetime import datetime
start = datetime(2020, 1, 1)
end = datetime(2020, 12, 31, 23, 59, 59)

bars = load_dataset(DATA)
bars = [b for b in bars if start <= b["time"] <= end]
print(f"Slice: 2020-01-01 .. 2020-12-31  ({len(bars)} bars)")

trades = run_backtest(bars)
metrics = compute_metrics(trades)

print(f"\nTrades: {len(trades)}")
print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.2%}  "
      f"net PF={metrics['profit_factor']:.4f}  gross PF={metrics['gross_pf']:.4f}")
print(f"  expectancy net: {metrics['expectancy_points']:+.2f} points/trade "
      f"({metrics['expectancy_pct']:+.4f}% of mean entry {metrics.get('mean_entry',0):,.2f})")
print(f"  expectancy gross: {metrics['gross_expectancy']:+.2f} points/trade")
print(f"  exits: {metrics['exits']}")

# ---- ASSERTIONS ----
ok = True

# A1
a1 = len(trades) > 0
print(f"\n[A1] trades > 0: {'PASS' if a1 else 'FAIL'} (n={len(trades)})")
ok &= a1

# A2
core = {"STOP", "TARGET", "HARDFLAT"}
present = core & set(metrics["exits"].keys())
a2 = len(present) >= 2
print(f"[A2] >=2 of {{STOP,TARGET,HARDFLAT}}: {'PASS' if a2 else 'FAIL'} (found {sorted(present)})")
ok &= a2

# A3: spot-check first, middle, last trade
import random
idxs = [0, len(trades) // 2, len(trades) - 1]
print("[A3] friction arithmetic spot-check (3 trades):")
a3 = True
for q, ti in enumerate(idxs):
    t = trades[ti]
    expected_fric = 2 * FEE_RATE * t.entry_price
    actual_fric = t.friction
    net_check = t.gross_pips - actual_fric
    fric_ok = abs(expected_fric - actual_fric) < 1e-9
    net_ok = abs(net_check - t.pips) < 1e-9
    print(f"  trade#{q+1} (idx {ti}): side={t.side} entry_price={t.entry_price:.2f}")
    print(f"    2*0.0005*entry = 2*0.0005*{t.entry_price:.2f} = {expected_fric:.6f} | stored friction = {actual_fric:.6f} -> {'OK' if fric_ok else 'MISMATCH'}")
    print(f"    gross = {t.gross_pips:.6f} | net = {t.pips:.6f} | gross - friction = {net_check:.6f} -> {'OK' if net_ok else 'MISMATCH'}")
    a3 &= fric_ok and net_ok
print(f"[A3] all 3 consistent: {'PASS' if a3 else 'FAIL'}")
ok &= a3

# A4
a4 = ("points" in str(metrics.keys()) or True) and "expectancy_points" in metrics and "expectancy_pct" in metrics
print(f"[A4] expectancy in points AND percent: {'PASS' if a4 else 'FAIL'} "
      f"(points={metrics['expectancy_points']:+.2f}, pct={metrics['expectancy_pct']:+.4f}%)")
ok &= a4

print(f"\nSMOKE OVERALL: {'ALL ASSERTIONS PASS' if ok else 'FAILURE — STOP'}")
print("NOTE: audit-only. No verdict, no ledger row, no graveyard row.")
sys.exit(0 if ok else 1)
