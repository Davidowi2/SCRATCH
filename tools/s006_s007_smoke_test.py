"""
tools/s006_s007_smoke_test.py — B-004 official smoke (M2) for S-006 + S-007
on the 2020 slice. Audit-only: NO verdict, NO ledger row, NO graveyard row.

Assertions:
  A1: trades > 0 (both kernels)
  A2: exit reasons subset of {STOP, TARGET, MAXHOLD, EOD}
  A3: MATCH-CHECK (the peek control, Directive V):
        S-006 n == 155
        S-007 n == 82 AND exits == {STOP:53, TARGET:25, MAXHOLD:3, EOD:1}
      EXACT match or HALT with divergence report.
  A4: no exceptions (any raise aborts the script)

Determinism re-verified: same peek conditions — full-file bars, no window
filter beyond "the file is the slice".
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "research"))

from backtest.S006_ema_trendfilter import (
    load_dataset as load6, run_backtest as run6, compute_metrics as met6,
)
from backtest.S007_regression_stoch import (
    load_dataset as load7, run_backtest as run7, compute_metrics as met7,
)

SLICE = os.path.join(ROOT, "research", "data", "eurusd_1h_2020_smoke.csv")
ALLOWED = {"STOP", "TARGET", "MAXHOLD", "EOD"}

print("=" * 70)
print("B-004 OFFICIAL SMOKE (M2) — 2020 SLICE — AUDIT-ONLY, NO VERDICT")
print("=" * 70)

ok = True

for label, load, run, met in (("S-006", load6, run6, met6), ("S-007", load7, run7, met7)):
    print(f"\n--- {label} ---")
    bars = load(SLICE)
    print(f"bars loaded: {len(bars)}")
    trades = run(bars)
    m = met(trades)
    print(f"trades={m['n']}  WR={m['win_rate']:.2%}  netPF={m['profit_factor']:.4f}  "
          f"grossPF={m['gross_pf']:.4f}  netExp={m['expectancy_pips']:+.2f}p  grossExp={m['gross_expectancy']:+.2f}p")
    print(f"exits: {m['exits']}")

    a1 = m["n"] > 0
    print(f"[A1] trades>0: {'PASS' if a1 else 'FAIL'} (n={m['n']})")
    ok &= a1

    bad = set(m["exits"]) - ALLOWED
    a2 = not bad
    print(f"[A2] exits within {sorted(ALLOWED)}: {'PASS' if a2 else 'FAIL' + str(bad)}")
    ok &= a2

# MATCH-CHECK (A3): re-run under identical conditions and compare exactly.
print("\n--- A3 MATCH-CHECK (peek control) ---")
bars = load6(SLICE)
m6 = met6(run6(bars))
s6_ok = (m6["n"] == 155)
print(f"S-006 n: expected 155, got {m6['n']} -> {'MATCH' if s6_ok else 'DIVERGENCE'}")

bars = load7(SLICE)
m7 = met7(run7(bars))
expected7 = {"STOP": 53, "TARGET": 25, "MAXHOLD": 3, "EOD": 1}
s7_n_ok = (m7["n"] == 82)
s7_x_ok = (m7["exits"] == expected7)
print(f"S-007 n: expected 82, got {m7['n']} -> {'MATCH' if s7_n_ok else 'DIVERGENCE'}")
print(f"S-007 exits: expected {expected7}, got {m7['exits']} -> {'MATCH' if s7_x_ok else 'DIVERGENCE'}")

a3 = s6_ok and s7_n_ok and s7_x_ok
print(f"[A3] match-check: {'PASS' if a3 else 'HALT — DIVERGENCE, report to Overseer'}")
ok &= a3

print(f"\nSMOKE OVERALL: {'ALL ASSERTIONS PASS' if ok else 'FAILURE — HALT'}")
print("Audit-only. No verdict, no ledger row, no graveyard row.")
sys.exit(0 if ok else 1)
