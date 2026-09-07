"""
Generate parity table: shadow signals vs backtest trades on same data.
"""
import csv
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "backtest"))
import run_h1

# Load backtest trades from run_h1.py on OOS window
bars = run_h1.load_dataset("research/data/eurusd_1h.csv")
from datetime import datetime
start = datetime(2024, 1, 1)
end = datetime(2025, 5, 13, 23, 59, 59)
oos_bars = [b for b in bars if start <= b["time"] <= end]

trades = run_h1.run_backtest(oos_bars)
print(f"Backtest trades: {len(trades)}")

# Load shadow signals from DB
conn = sqlite3.connect("database/trades.db")
cursor = conn.cursor()
cursor.execute("SELECT timestamp, side, entry_price, stop_loss, z_score, session_hour FROM signal_log WHERE phase='shadow' ORDER BY timestamp")
signals = cursor.fetchall()
conn.close()
print(f"Shadow signals: {len(signals)}")

# Build lookup: backtest trades by (entry_time, side)
backtest_lookup = {}
for t in trades:
    key = (oos_bars[t.entry_idx]["time"].strftime("%Y-%m-%d %H:%M:%S"), t.side)
    backtest_lookup[key] = t

# Compare
matched = 0
shadow_only = 0
backtest_only = 0

print("\n" + "=" * 100)
print(f"{'Timestamp':<22} {'Side':<6} {'Shadow Price':<14} {'BT Price':<14} {'Match':<8} {'Z':<8}")
print("=" * 100)

shadow_keys = set()
for sig in signals:
    ts, side, price, sl, z, hr = sig
    shadow_keys.add((ts, side))
    if (ts, side) in backtest_lookup:
        bt_trade = backtest_lookup[(ts, side)]
        bt_price = bt_trade.entry_price
        price_match = abs(price - bt_price) < 0.00001
        print(f"{ts:<22} {side:<6} {price:<14.5f} {bt_price:<14.5f} {'✓' if price_match else '✗':<8} {z:<8.3f}")
        matched += 1
    else:
        print(f"{ts:<22} {side:<6} {price:<14.5f} {'---':<14} {'SHADOW ONLY':<8} {z:<8.3f}")
        shadow_only += 1

# Check for backtest trades without shadow signals
for key, t in backtest_lookup.items():
    if key not in shadow_keys:
        ts = oos_bars[t.entry_idx]["time"].strftime("%Y-%m-%d %H:%M:%S")
        bt_price = t.entry_price
        print(f"{ts:<22} {t.side:<6} {'---':<14} {bt_price:<14.5f} {'BT ONLY':<8}")
        backtest_only += 1

print("=" * 100)
print(f"\nMatched: {matched} | Shadow-only: {shadow_only} | Backtest-only: {backtest_only}")
print(f"Total signals: {len(signals)} | Total trades: {len(trades)}")

# Analysis
if matched == len(trades) and shadow_only == 0:
    print("\n✓ PERFECT PARITY: All backtest trades have matching shadow signals")
elif matched > 0:
    overlap = matched / len(trades) * 100
    print(f"\n{overlap:.1f}% overlap ({matched}/{len(trades)} trades matched)")
    if shadow_only > 0:
        print(f"  {shadow_only} shadow signals had no backtest trade (SL/maxhold filtered)")
    if backtest_only > 0:
        print(f"  {backtest_only} backtest trades had no shadow signal (requires investigation)")
