"""
Extract in-sample trade log + run cost sensitivity analysis.
Run from SCRATCH dir: python scripts/_remediation_b2_b3_b4.py
"""
import csv
import sys
import os

# research/ must be on path so 'data' and 'backtest' are importable packages
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research', 'backtest'))

from data.validate_data import audit as gate1_audit
from run_h1 import load_dataset, run_backtest, Trade, MA_PERIOD, Z_ENTRY, Z_EXIT, MAX_HOLD_BARS, SL_SD_MULT, FRICTION_PIPS, PIP, SESSION_HOURS


def max_drawdown(trades):
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        equity += t.pips
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


# Load cleaned dataset
bars = load_dataset('research/data/eurusd_1h.csv')

# ---------------- B4: Window definition (FROZEN) ----------------
INSAMPLE_START = '2021-01-01'
INSAMPLE_END = '2023-12-31'
OOS_START = '2024-01-01'
OOS_END = '2025-12-31'

print(f"FROZEN WINDOWS:")
print(f"  In-sample: {INSAMPLE_START}..{INSAMPLE_END}")
print(f"  OOS:       {OOS_START}..{OOS_END}")

# Split
insample_bars = [b for b in bars if b['time'].year <= 2023]
print(f"\nIn-sample: {len(insample_bars)} bars ({insample_bars[0]['time'].strftime('%Y-%m-%d %H:%M')}..{insample_bars[-1]['time'].strftime('%Y-%m-%d %H:%M')}")

# ---------------- B3: Cost sensitivity analysis ----------------
# Current friction model: 0.5 pips round trip
# Let's compute what happens at 0x, 1x, 2x, 3x the friction

friction_scenarios = {
    '0x_friction_0.0': 0.0,
    '1x_friction_0.5': 0.5,
    '2x_friction_1.0': 1.0,
    '3x_friction_1.5': 1.5,
}

print(f"\n{'Scenario':<20} {'Friction':>8} {'n':>4} {'WR':>6} {'PF':>6} {'Exp':>8} {'MaxDD':>8}")
print("-" * 62)

for name, friction in friction_scenarios.items():
    trades = run_backtest(insample_bars, friction_override=friction)
    wins = [t for t in trades if t.pips > 0]
    gross_profit = sum(t.pips for t in wins)
    gross_loss = -sum(t.pips for t in trades if t.pips <= 0)
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    wr = len(wins)/len(trades)
    exp = sum(t.pips for t in trades)/len(trades)
    max_dd = max_drawdown(trades)
    print(f"{name:<20} {friction:>5.1f}   {len(trades):>4} {wr:>5.1%} {pf:>5.2f} {exp:>+7.2f} {max_dd:>7.1f}")

# Export trade log at current friction (0.5 pips)
trades = run_backtest(insample_bars, friction_override=0.5)
with open('research/trade_log_insample.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['idx','entry_time','exit_time','side','entry_price','exit_price','pips_gross','pips_net','exit_reason','bars_held'])
    for i, t in enumerate(trades, 1):
        gross_pips = ((t.exit_price - t.entry_price) if t.side == 'LONG' else (t.entry_price - t.exit_price)) / PIP
        w.writerow([
            i,
            insample_bars[t.entry_idx]['time'].strftime('%Y-%m-%d %H:%M'),
            insample_bars[t.exit_idx]['time'].strftime('%Y-%m-%d %H:%M'),
            t.side,
            f'{t.entry_price:.5f}',
            f'{t.exit_price:.5f}',
            f'{gross_pips:.1f}',
            f'{t.pips:.1f}',
            t.exit_reason,
            t.bars_held
        ])

print(f"\nTrade log exported: research/trade_log_insample.csv ({len(trades)} trades)")
