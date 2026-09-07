"""
P3 — First live signal check + place paper fill.
Uses frozen strategy via live_h1.py adapter, gets real-time bar from TradeLocker.
"""
import os
import sys
import logging
import hashlib
import sqlite3
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("tradelocker").setLevel(logging.WARNING)

from tradelocker import TLAPI

# === Connect to TradeLocker ===
print("=" * 70)
print("P3 — FIRST LIVE SIGNAL")
print("=" * 70)

tl = TLAPI(
    environment=os.getenv("TL_ENVIRONMENT"),
    username=os.getenv("TL_USERNAME"),
    password=os.getenv("TL_PASSWORD"),
    server=os.getenv("TL_SERVER"),
    log_level="warning",
)

acc = tl.get_account_state()
print(f"Account balance: ${acc.get('balance', 0):.2f}")

# === Get latest EURUSD 1H bar ===
eusd_id = 278

# Use lookback_period for recent data
history = tl.get_price_history(
    instrument_id=eusd_id,
    resolution="1H",
    lookback_period="1000H",  # ~41 days of H1 bars
)

print(f"\nPrice history: {history.shape[0]} bars")
print(f"Columns: {list(history.columns)}")
print(history.tail(5))

# Convert to run_h1.py bar format
closes = []
for _, row in history.iterrows():
    dt = datetime.utcfromtimestamp(row["t"] / 1000)
    closes.append({
        "time": dt,
        "open": float(row["o"]),
        "high": float(row["h"]),
        "low": float(row["l"]),
        "close": float(row["c"]),
        "volume": float(row.get("v", 0)),
    })

# === Run frozen strategy check ===
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "backtest"))
import run_h1

# Check the latest bar
latest_bar = closes[-1]
print(f"\nLatest bar: time={latest_bar['time']}, O={latest_bar['open']:.5f}, H={latest_bar['high']:.5f}, L={latest_bar['low']:.5f}, C={latest_bar['close']:.5f}")

# Check if in session
if latest_bar["time"].hour in run_h1.SESSION_HOURS:
    print(f"  Hour {latest_bar['time'].hour} is in Asian session ✓")
else:
    print(f"  Hour {latest_bar['time'].hour} is NOT in Asian session (22-07 UTC)")

# Check Z-score
if len(closes) >= run_h1.MA_PERIOD:
    window = closes[-run_h1.MA_PERIOD:]
    window_closes = [b["close"] for b in window]
    mean = sum(window_closes) / run_h1.MA_PERIOD
    sd = (sum((c - mean) ** 2 for c in window_closes) / run_h1.MA_PERIOD) ** 0.5
    latest_close = closes[-1]["close"]
    z = (latest_close - mean) / sd if sd > 0 else 0
    print(f"\n  SMA20: {mean:.5f}")
    print(f"  SD20:  {sd:.6f}")
    print(f"  Z-score: {z:.3f}")

    if z >= run_h1.Z_ENTRY:
        print(f"  >>> SHORT signal! Z={z:.2f} >= {run_h1.Z_ENTRY}")
        signal_side = "SHORT"
    elif z <= -run_h1.Z_ENTRY:
        print(f"  >>> LONG signal! Z={z:.2f} <= -{run_h1.Z_ENTRY}")
        signal_side = "LONG"
    else:
        print(f"  No entry signal (|Z| < {run_h1.Z_ENTRY})")
        signal_side = None

# === Log first heartbeat to DB ===
conn = sqlite3.connect("database/trades.db")
cursor = conn.cursor()
cursor.execute("""
    INSERT INTO signal_log (timestamp, side, entry_price, stop_loss, z_score, sd, session_hour, bars_used, phase)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    latest_bar["time"].strftime("%Y-%m-%d %H:%M:%S"),
    signal_side or "NONE",
    latest_bar["open"],
    0,
    round(z, 4),
    round(sd, 6),
    latest_bar["time"].hour,
    len(closes),
    "paper",
))
conn.commit()
conn.close()
print(f"\nLogged to signal_log (phase=paper)")
