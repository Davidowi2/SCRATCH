"""
research/backtest/S010_banklevel_fx.py — S-010 Bank-Level FX Arm

Implements the exact math from Directive K v1 Task 2:

1. Bank Level = Asian range: high/low of H1 bars stamped 00:00-05:00 UTC.
   The 06:00 UTC bar belongs to neither range nor window.
2. If the range is already closed beyond BEFORE the window opens: skip day.
3. Trigger window: bars stamped 07:00-10:00 UTC.
4. Signal: FIRST bar in window closing beyond the range (cross-event:
   prior close inside) AND (high-low) >= 1.0 * ATR14(H1).
5. Entry: open of next bar. One trade per day max.
6. Stop: opposite extreme of trigger bar. Target: 1.5R.
7. Hard flat: close of bar stamped 11:00 UTC.
8. Friction 0.5 pips. Prices are bid-side; friction covers spread.

RULINGS:
- R1: stop evaluated before target; one bar touching both = loss;
  open gapping through stop fills at open; max-hold/flat checked after.
- R3: entry-bar open gapping through planned stop discards signal.
- M5: bid-side prices; friction 0.5 pips.
- M2: 2020 slice (OUTSIDE frozen windows) may be used for audit-only
  smoke tests after Overseer approval. Consumes no one-shot, records no verdict.
- M4: pre-window violation skips day.

CALIBRATION PURPOSE: Hypothesis test. Expected to pass or die cleanly based
on whether Asian range breakouts produce predictable continuation in EURUSD H1.
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
PARAM_DESC = "Bank-level FX arm: Asian range breakout, London open window"

FRICTION_PIPS = 0.5
PIP = 0.0001
MAX_HOLD_BARS = 72
ATR_PERIOD = 14
TARGET_R = 1.5

# Session hours (UTC)
ASIAN_RANGE_HOURS = {0, 1, 2, 3, 4, 5}  # 00:00-05:00 UTC
TRIGGER_WINDOW_HOURS = {7, 8, 9, 10}     # 07:00-10:00 UTC
HARD_FLAT_HOUR = 11                       # 11:00 UTC


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
    """Compute ATR14 using only bars up to and including j."""
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


def compute_asian_range(bars, day_start_idx):
    """
    Compute Asian range high/low from H1 bars stamped 00:00-05:00 UTC.
    Returns (range_high, range_low) or None if insufficient data.
    """
    range_high = float("-inf")
    range_low = float("inf")
    found = False
    
    for i in range(day_start_idx, len(bars)):
        hour = bars[i]["time"].hour
        if hour in ASIAN_RANGE_HOURS:
            range_high = max(range_high, bars[i]["high"])
            range_low = min(range_low, bars[i]["low"])
            found = True
        elif hour >= 6:
            break
    
    return (range_high, range_low) if found else None


def is_range_closed_before_window(bars, day_start_idx, range_high, range_low):
    """
    Check if price already closed beyond the Asian range BEFORE the
    trigger window opens (07:00 UTC). If so, skip the day (M4).
    """
    for i in range(day_start_idx, len(bars)):
        hour = bars[i]["time"].hour
        if hour == 6:
            # 06:00 bar - check if it closed beyond range
            if bars[i]["close"] > range_high or bars[i]["close"] < range_low:
                return True
        elif hour >= 7:
            break
    return False


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
    trade_today = False
    current_day = None
    
    i = 0
    while i < n:
        bar_time = bars[i]["time"]
        bar_date = bar_time.date()
        
        # New day reset
        if bar_date != current_day:
            current_day = bar_date
            trade_today = False
        
        # Check existing position
        if position_open:
            t = trades[-1]
            j = i
            exited = False
            
            # R1: Evaluate STOP before TARGET
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
            
            # R1: Max-hold checked AFTER stop/target, at the close
            # Hard flat at 11:00 UTC
            if not exited and (j - t.entry_idx) >= MAX_HOLD_BARS:
                t.exit_idx, t.exit_price = j, closes[j]
                t.exit_reason = "MAXHOLD"
                exited = True
            
            if not exited and bar_time.hour >= HARD_FLAT_HOUR:
                t.exit_idx, t.exit_price = j, closes[j]
                t.exit_reason = "HARDFLAT"
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
        
        # Look for signals (only if no trade today)
        if trade_today:
            i += 1
            continue
        
        # Compute Asian range for this day
        asian_range = compute_asian_range(bars, i)
        if asian_range is None:
            i += 1
            continue
        
        range_high, range_low = asian_range
        
        # Check if we're in trigger window (07:00-10:00 UTC)
        if bar_time.hour in TRIGGER_WINDOW_HOURS:
            # Check M4: skip if range already closed beyond before window
            if is_range_closed_before_window(bars, i, range_high, range_low):
                trade_today = True  # Mark as processed (skipped)
                i += 1
                continue
            
            # Cross-event rule: first bar closing beyond range
            prior_close_inside = (closes[i - 1] >= range_low and closes[i - 1] <= range_high) if i > 0 else True
            
            if prior_close_inside:
                # Check LONG signal
                if closes[i] > range_high:
                    bar_range = highs[i] - lows[i]
                    atr = atr14(highs, lows, closes, i)
                    if atr is not None and bar_range >= 1.0 * atr:
                        # R3: check entry-bar open doesn't gap through stop
                        if i + 1 < n:
                            entry_price = opens[i + 1]
                            stop_price = lows[i]  # opposite extreme of trigger bar
                            risk = entry_price - stop_price
                            if risk > 0 and entry_price > stop_price:
                                target_price = entry_price + TARGET_R * risk
                                t = Trade(i + 1, entry_price, "LONG", stop_price, target_price)
                                t.gross_pips = 0
                                trades.append(t)
                                position_open = True
                                trade_today = True
                                i += 2
                                continue
                
                # Check SHORT signal
                if closes[i] < range_low:
                    bar_range = highs[i] - lows[i]
                    atr = atr14(highs, lows, closes, i)
                    if atr is not None and bar_range >= 1.0 * atr:
                        if i + 1 < n:
                            entry_price = opens[i + 1]
                            stop_price = highs[i]  # opposite extreme of trigger bar
                            risk = stop_price - entry_price
                            if risk > 0 and entry_price < stop_price:
                                target_price = entry_price - TARGET_R * risk
                                t = Trade(i + 1, entry_price, "SHORT", stop_price, target_price)
                                t.gross_pips = 0
                                trades.append(t)
                                position_open = True
                                trade_today = True
                                i += 2
                                continue
        
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
