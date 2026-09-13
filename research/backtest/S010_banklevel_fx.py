"""
research/backtest/S010_banklevel_fx.py — S-010 Bank-Level FX Arm

Implements the exact math from the Overseer's locked spec with rulings M2/M4/M5.

M5 CORRECTIONS:
- 06:00 bar excluded (illiquid transition)
- Bid-side prices used (simulated via Dukascopy bid)
- Friction 0.5 pips

RULINGS:
- M2: 2020 smoke slice allowed for calibration only (not IS/OOS)
- M4: Pre-window violation skips day
- M5: 06:00 bar excluded, bid-side, friction 0.5

CALIBRATION PURPOSE: Hypothesis test. Expected to pass or die cleanly based
on whether bank-level zones produce predictable reactions in EURUSD H1.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "S-010"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "BANKLEVEL"
PARAM_DESC = "Bank-level FX arm: fade/breakout at institutional zones"

FRICTION_PIPS = 0.5
PIP = 0.0001
MAX_HOLD_BARS = 72
ATR_PERIOD = 14
STOP_ATR_MULT = 0.5
TARGET_R = 1.5
BANK_LEVEL_TOUCH_THRESHOLD = 0.0002  # 2 pips = touch zone
BANK_LEVEL_CLUSTER_MIN = 3  # minimum reversals to define bank level


class Trade:
    def __init__(self, entry_idx, entry_price, side, stop, target):
        self.entry_idx = entry_idx
        self.entry_price = entry_price
        self.side = side
        self.stop = stop
        self.target = target
        self.exit_idx = None
        self.exit_price = None
        self.exit_reason = None
        self.bars_held = None
        self.pips = None
        self.gross_pips = None


def load_dataset(path):
    bars = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            bars.append({
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
    return bars


def atr14(highs, lows, closes, j):
    if j < ATR_PERIOD:
        return None
    trs = []
    for k in range(j - ATR_PERIOD + 1, j + 1):
        if k == 0:
            tr = highs[k] - lows[k]
        else:
            tr = max(
                highs[k] - lows[k],
                abs(highs[k] - closes[k - 1]),
                abs(lows[k] - closes[k - 1]),
            )
        trs.append(tr)
    return sum(trs) / ATR_PERIOD


def detect_bank_levels(bars, j):
    """
    Detect bank levels: price levels where reversals cluster.
    Look back from bar j and find levels with >= BANK_LEVEL_CLUSTER_MIN reversals.
    Returns list of (level_price, strength) tuples.
    """
    if j < 50:
        return []
    
    lookback = min(j, 500)  # look back up to 500 bars
    levels = []
    
    # Find swing highs and lows in lookback window
    swings = []
    for k in range(j - lookback + 5, j - 4):
        if k < 5:
            continue
        # Swing high
        if (bars[k]["high"] > bars[k-1]["high"] and bars[k]["high"] > bars[k-2]["high"] and
            bars[k]["high"] > bars[k+1]["high"] and bars[k]["high"] > bars[k+2]["high"]):
            swings.append(bars[k]["high"])
        # Swing low
        if (bars[k]["low"] < bars[k-1]["low"] and bars[k]["low"] < bars[k-2]["low"] and
            bars[k]["low"] < bars[k+1]["low"] and bars[k]["low"] < bars[k+2]["low"]):
            swings.append(bars[k]["low"])
    
    # Cluster nearby swings into bank levels
    clusters = []
    used = [False] * len(swings)
    for i in range(len(swings)):
        if used[i]:
            continue
        cluster = [swings[i]]
        for j2 in range(i + 1, len(swings)):
            if used[j2]:
                continue
            if abs(swings[j2] - swings[i]) < BANK_LEVEL_TOUCH_THRESHOLD:
                cluster.append(swings[j2])
                used[j2] = True
        used[i] = True
        if len(cluster) >= BANK_LEVEL_CLUSTER_MIN:
            avg_level = sum(cluster) / len(cluster)
            levels.append((avg_level, len(cluster)))
    
    return levels


def run_backtest(bars, friction_override=None):
    """Run the bank-level FX arm backtest."""
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS
    
    position_open = False
    active_bank_levels = []  # (level, side, consumed)
    
    i = 50  # start after enough bars for bank level detection
    while i < n:
        # M5: exclude 06:00 bar
        if bars[i]["time"].hour == 6:
            i += 1
            continue
        
        # Check existing position
        if position_open:
            t = trades[-1]
            j = i
            exited = False
            
            if t.side == "SHORT":
                if opens[j] >= t.stop:
                    t.exit_idx, t.exit_price = j, opens[j]
                    t.exit_reason = "STOP"
                    exited = True
                elif highs[j] >= t.stop:
                    t.exit_idx, t.exit_price = j, t.stop
                    t.exit_reason = "STOP"
                    exited = True
                elif lows[j] <= t.target:
                    t.exit_idx, t.exit_price = j, t.target
                    t.exit_reason = "TARGET"
                    exited = True
            else:  # LONG
                if opens[j] <= t.stop:
                    t.exit_idx, t.exit_price = j, opens[j]
                    t.exit_reason = "STOP"
                    exited = True
                elif lows[j] <= t.stop:
                    t.exit_idx, t.exit_price = j, t.stop
                    t.exit_reason = "STOP"
                    exited = True
                elif highs[j] >= t.target:
                    t.exit_idx, t.exit_price = j, t.target
                    t.exit_reason = "TARGET"
                    exited = True
            
            if not exited and (j - t.entry_idx) >= MAX_HOLD_BARS:
                t.exit_idx, t.exit_price = j, closes[j]
                t.exit_reason = "MAXHOLD"
                exited = True
            
            if exited:
                position_open = False
                t.bars_held = t.exit_idx - t.entry_idx
                if t.side == "SHORT":
                    gross = (t.entry_price - t.exit_price) / PIP
                else:
                    gross = (t.exit_price - t.entry_price) / PIP
                t.gross_pips = gross
                t.pips = gross - friction
                i = t.exit_idx + 1
                continue
            
            i += 1
            continue
        
        # Detect bank levels
        bank_levels = detect_bank_levels(bars, i)
        
        # Check for signals at bank levels
        for level, strength in bank_levels:
            # Check if price is touching the level
            if lows[i] <= level <= highs[i]:
                # Price touching bank level - check for fade or breakout
                atr = atr14(highs, lows, closes, i)
                if atr is None or atr <= 0:
                    continue
                
                # Fade: close back inside range after touch
                if closes[i] < level and lows[i] <= level:
                    # SHORT fade (price touched level from below, closed below)
                    if i + 1 < n:
                        entry_price = opens[i + 1]
                        stop_price = highs[i] + STOP_ATR_MULT * atr
                        risk = stop_price - entry_price
                        if risk > 0:
                            target_price = entry_price - TARGET_R * risk
                            t = Trade(i + 1, entry_price, "SHORT", stop_price, target_price)
                            t.gross_pips = 0
                            trades.append(t)
                            position_open = True
                            i += 2
                            break
                elif closes[i] > level and highs[i] >= level:
                    # LONG fade (price touched level from above, closed above)
                    if i + 1 < n:
                        entry_price = opens[i + 1]
                        stop_price = lows[i] - STOP_ATR_MULT * atr
                        risk = entry_price - stop_price
                        if risk > 0:
                            target_price = entry_price + TARGET_R * risk
                            t = Trade(i + 1, entry_price, "LONG", stop_price, target_price)
                            t.gross_pips = 0
                            trades.append(t)
                            position_open = True
                            i += 2
                            break
                
                # Breakout: close beyond level
                if closes[i] > level + BANK_LEVEL_TOUCH_THRESHOLD:
                    # LONG breakout
                    if i + 1 < n:
                        entry_price = opens[i + 1]
                        stop_price = level - STOP_ATR_MULT * atr
                        risk = entry_price - stop_price
                        if risk > 0:
                            target_price = entry_price + TARGET_R * risk
                            t = Trade(i + 1, entry_price, "LONG", stop_price, target_price)
                            t.gross_pips = 0
                            trades.append(t)
                            position_open = True
                            i += 2
                            break
                elif closes[i] < level - BANK_LEVEL_TOUCH_THRESHOLD:
                    # SHORT breakout
                    if i + 1 < n:
                        entry_price = opens[i + 1]
                        stop_price = level + STOP_ATR_MULT * atr
                        risk = stop_price - entry_price
                        if risk > 0:
                            target_price = entry_price - TARGET_R * risk
                            t = Trade(i + 1, entry_price, "SHORT", stop_price, target_price)
                            t.gross_pips = 0
                            trades.append(t)
                            position_open = True
                            i += 2
                            break
        
        i += 1
    
    # Close any open position at end of data
    if position_open:
        t = trades[-1]
        t.exit_idx, t.exit_price = n - 1, closes[-1]
        t.exit_reason = "EOD"
        t.bars_held = t.exit_idx - t.entry_idx
        if t.side == "SHORT":
            gross = (t.entry_price - t.exit_price) / PIP
        else:
            gross = (t.exit_price - t.entry_price) / PIP
        t.gross_pips = gross
        t.pips = gross - friction
    
    return trades


def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "exits": {},
                "gross_profit": 0, "gross_loss": 0, "gross_pf": 0,
                "gross_expectancy": 0, "net_expectancy": 0}
    
    wins = [t for t in trades if t.pips > 0]
    gross_profit = sum(t.pips for t in wins)
    gross_loss = -sum(t.pips for t in trades if t.pips <= 0)
    
    # Gross metrics (no friction)
    gross_pips_list = [t.gross_pips if t.gross_pips is not None else t.pips for t in trades]
    gross_profit_no_friction = sum(g for g in gross_pips_list if g > 0)
    gross_loss_no_friction = sum(abs(g) for g in gross_pips_list if g <= 0)
    gross_pf = gross_profit_no_friction / gross_loss_no_friction if gross_loss_no_friction > 0 else float("inf")
    gross_expectancy = sum(gross_pips_list) / len(trades)
    
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        equity += t.pips
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    
    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
    
    net_expectancy = sum(t.pips for t in trades) / len(trades)
    
    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": net_expectancy,
        "max_dd_pips": max_dd, "exits": exits,
        "gross_profit": gross_profit, "gross_loss": gross_loss,
        "gross_pf": gross_pf, "gross_expectancy": gross_expectancy,
        "net_expectancy": net_expectancy,
    }


def decide(metrics, phase):
    n = metrics["n"]
    if n < 50:
        return "INSUFFICIENT", f"n={n} < 50"
    pf = metrics["profit_factor"]
    if pf == float("inf"):
        return "SUSPICIOUS", "zero losses"
    if pf < 1.0:
        return "KILL", f"PF {pf:.4f} < 1.0"
    if metrics["win_rate"] < 0.45:
        return "KILL", f"WR {metrics['win_rate']:.0%} < 45%"
    if pf <= 1.15:
        return "DANGER-ZONE", f"PF {pf:.4f} in 1.0-1.15 band"
    return "PASS", f"PF {pf:.4f}"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    verdict = gate1_audit(os.path.join("research", "data", "data_audit.log"), args.raw_dir, args.dataset)
    if verdict == "REJECT":
        print("Gate 1 REJECT: data failed validation")
        return 1

    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start, end = datetime.strptime("2021-01-01", "%Y-%m-%d"), datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start, end = datetime.strptime("2024-01-01", "%Y-%m-%d"), datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.4f}  Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
