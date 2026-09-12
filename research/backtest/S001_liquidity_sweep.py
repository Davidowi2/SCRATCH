"""
research/backtest/S001_liquidity_sweep.py — S-001 Liquidity Sweep Fade

Implements the exact math from the Overseer's locked spec:

1. Fractal high at i: H[i] > H[i-1], H[i-2], H[i+1], H[i+2].
   Confirmed at bar i+2, usable only from bar i+2 onward (no lookahead).
   Fractal low mirrored.
2. Active level = most recent confirmed fractal. Superseded levels discarded.
3. Sweep (short) at bar j (j >= i+2): H[j] > level AND C[j] < level.
   Level consumed on sweep. Long mirrored: L[j] < level AND C[j] > level.
4. Entry: open of bar j+1, fading the sweep.
5. Stop: short = H[j] + 0.5*ATR14[j]; long = L[j] - 0.5*ATR14[j].
6. Target: fixed 1.5R.
7. One position at a time.

R1 — STOP BEFORE TARGET (enforced in exit evaluation order):
   On any bar after entry, evaluate the STOP before the TARGET.
   An open gapping through the stop fills at the open.
   If a single bar touches both stop and target, the trade counts as a LOSS.
   Max-hold exit is checked after stop/target for that bar, at the close.

R2 — SWEEP vs BREAKOUT:
   A level pierced but CLOSED BEYOND (C[j] >= level for highs,
   C[j] <= level for lows) is a breakout: discard the level, NO trade.
   A sweep requires a wick beyond AND a close strictly back inside.

Risk Rails:
- Max hold 72 bars (Overseer-added safety rail; owner may veto)
- Friction 0.5 pips/trade

CALIBRATION PURPOSE: Hypothesis test (not noise). Expected to pass or
die cleanly based on whether liquidity sweep reversions exist in EURUSD H1.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "S-001"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "SWEEP"
PARAM_DESC = "Liquidity sweep fade: fractal level sweep, fade back to range"

FRICTION_PIPS = 0.5
PIP = 0.0001
MAX_HOLD_BARS = 72
ATR_PERIOD = 14
STOP_ATR_MULT = 0.5
TARGET_R = 1.5


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


def is_fractal_high(highs, i):
    """Check if bar i is a fractal high: H[i] > H[i-1], H[i-2], H[i+1], H[i+2]."""
    if i < 2 or i >= len(highs) - 2:
        return False
    return (highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and
            highs[i] > highs[i + 1] and highs[i] > highs[i + 2])


def is_fractal_low(lows, i):
    """Check if bar i is a fractal low: L[i] < L[i-1], L[i-2], L[i+1], L[i+2]."""
    if i < 2 or i >= len(lows) - 2:
        return False
    return (lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and
            lows[i] < lows[i + 1] and lows[i] < lows[i + 2])


def run_backtest(bars, friction_override=None):
    """Run the liquidity sweep fade backtest."""
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS

    last_confirmed_high = None  # (index, price)
    last_confirmed_low = None   # (index, price)
    position_open = False

    i = 2
    while i < n:
        # Confirm fractals at i-2 (fractal at i-2 is now confirmed at bar i)
        confirm_idx = i - 2
        if confirm_idx >= 2 and confirm_idx < n - 2:
            if is_fractal_high(highs, confirm_idx):
                last_confirmed_high = (confirm_idx, highs[confirm_idx])
            if is_fractal_low(lows, confirm_idx):
                last_confirmed_low = (confirm_idx, lows[confirm_idx])

        if position_open:
            t = trades[-1]
            j = i
            exited = False

            if t.side == "SHORT":
                # R1: Evaluate STOP before TARGET
                if opens[j] >= t.stop:  # Open gaps through stop -> fills at open
                    t.exit_idx, t.exit_price = j, opens[j]
                    t.exit_reason = "STOP"
                    exited = True
                elif highs[j] >= t.stop:  # High touches stop
                    t.exit_idx, t.exit_price = j, t.stop
                    t.exit_reason = "STOP"
                    exited = True
                elif lows[j] <= t.target:  # Low touches target
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
            if not exited and (j - t.entry_idx) >= MAX_HOLD_BARS:
                t.exit_idx, t.exit_price = j, closes[j]
                t.exit_reason = "MAXHOLD"
                exited = True

            if exited:
                position_open = False
                t.bars_held = t.exit_idx - t.entry_idx
                if t.side == "SHORT":
                    gross = t.entry_price - t.exit_price
                else:
                    gross = t.exit_price - t.entry_price
                t.pips = gross / PIP - friction
                i = t.exit_idx + 1
                continue

            i += 1
            continue

        # Look for sweep setups
        # R2: Sweep requires wick beyond AND close strictly back inside.
        #     If level pierced but closed beyond -> breakout, discard level, NO trade.
        if last_confirmed_high is not None:
            h_idx, h_level = last_confirmed_high
            # R2: C[j] >= level for highs = breakout (discard, no trade)
            if highs[i] > h_level and closes[i] < h_level:
                atr = atr14(highs, lows, closes, i)
                if atr is not None and atr > 0:
                    stop_price = highs[i] + STOP_ATR_MULT * atr
                    if i + 1 < n:
                        risk = stop_price - opens[i + 1]
                        if risk > 0:
                            target_price = opens[i + 1] - TARGET_R * risk
                            t = Trade(i + 1, opens[i + 1], "SHORT", stop_price, target_price)
                            trades.append(t)
                            position_open = True
                            last_confirmed_high = None  # Level consumed
                            i += 2
                            continue
            # R2: Breakout detection - discard level if closed beyond
            elif highs[i] > h_level and closes[i] >= h_level:
                last_confirmed_high = None  # Breakout, discard level

        if last_confirmed_low is not None:
            l_idx, l_level = last_confirmed_low
            # R2: C[j] <= level for lows = breakout (discard, no trade)
            if lows[i] < l_level and closes[i] > l_level:
                atr = atr14(highs, lows, closes, i)
                if atr is not None and atr > 0:
                    stop_price = lows[i] - STOP_ATR_MULT * atr
                    if i + 1 < n:
                        risk = opens[i + 1] - stop_price
                        if risk > 0:
                            target_price = opens[i + 1] + TARGET_R * risk
                            t = Trade(i + 1, opens[i + 1], "LONG", stop_price, target_price)
                            trades.append(t)
                            position_open = True
                            last_confirmed_low = None  # Level consumed
                            i += 2
                            continue
            # R2: Breakout detection - discard level if closed beyond
            elif lows[i] < l_level and closes[i] <= l_level:
                last_confirmed_low = None  # Breakout, discard level

        i += 1

    # Close any open position at end of data
    if position_open:
        t = trades[-1]
        t.exit_idx, t.exit_price = n - 1, closes[-1]
        t.exit_reason = "EOD"
        t.bars_held = t.exit_idx - t.entry_idx
        if t.side == "SHORT":
            gross = t.entry_price - t.exit_price
        else:
            gross = t.exit_price - t.entry_price
        t.pips = gross / PIP - friction

    return trades


def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "exits": {}}

    wins = [t for t in trades if t.pips > 0]
    gross_profit = sum(t.pips for t in wins)
    gross_loss = -sum(t.pips for t in trades if t.pips <= 0)

    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        equity += t.pips
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1

    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "gross_profit_pips": gross_profit, "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades),
        "max_dd_pips": max_dd, "exits": exits,
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
