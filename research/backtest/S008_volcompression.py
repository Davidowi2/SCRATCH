"""
research/backtest/S008_volcompression.py — S-008 Volatility Compression Breakout

Implements the corrected spec per O3:

O3 CORRECTION:
- Range RH/RL computed over bars [i-20 .. i-1] (signal bar i EXCLUDED)
- Compression SMA window = mean ATR14 over bars [i-99 .. i] INCLUSIVE (100 bars)

MATH:
1. Compression at bar i: ATR14[i] < 0.70 * mean(ATR14[i-99..i])
2. Range: RH = max(high[i-20..i-1]), RL = min(low[i-20..i-1])
3. Long: close[i] > RH -> entry open[i+1]; stop = entry - 1.0*ATR14[i]; TP 1.5R
   Short: close[i] < RL -> mirrored
4. One position at a time; friction 0.5 pips; max hold 72 bars

CROSS-EVENT RULE: signal fires ONLY on first crossing bar
  (close[i] beyond level AND close[i-1] not beyond). No re-triggers.
R1: stop evaluated before target; max-hold checked at close after stop/target.
R3: entry open gapping through planned stop discards signal entirely.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "S-008"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "VOLCOMP"
PARAM_DESC = "Volatility compression breakout: balance -> imbalance"

FRICTION_PIPS = 0.5
PIP = 0.0001
MAX_HOLD_BARS = 72
ATR_PERIOD = 14
ATR_SMA_PERIOD = 100
STOP_ATR_MULT = 1.0
TARGET_R = 1.5
RANGE_LOOKBACK = 20
COMP_MULT = 0.70


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


def atr14_series(highs, lows, closes, n):
    """Precompute ATR14 for all bars."""
    atrs = [None] * n
    for j in range(n):
        if j >= ATR_PERIOD:
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
            atrs[j] = sum(trs) / ATR_PERIOD
    return atrs


def run_backtest(bars, friction_override=None):
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS

    atrs = atr14_series(highs, lows, closes, n)
    position_open = False

    i = 21  # need 20 bars lookback + at least bar 1 for cross-event
    while i < n:
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
                    gross = t.entry_price - t.exit_price
                else:
                    gross = t.exit_price - t.entry_price
                t.pips = gross / PIP - friction
                i = t.exit_idx + 1
                continue

            i += 1
            continue

        # O3: Compression check - ATR14[i] < 0.70 * mean(ATR14[i-99..i])
        if atrs[i] is not None and i >= ATR_SMA_PERIOD - 1:
            window = [atrs[k] for k in range(i - ATR_SMA_PERIOD + 1, i + 1) if atrs[k] is not None]
            if len(window) >= ATR_SMA_PERIOD:
                sma_atr = sum(window) / len(window)
                if atrs[i] < COMP_MULT * sma_atr:
                    # Compression confirmed - check range breakout
                    # O3: RH/RL over bars [i-20..i-1] (signal bar i EXCLUDED)
                    rh = max(highs[i - RANGE_LOOKBACK:i])
                    rl = min(lows[i - RANGE_LOOKBACK:i])

                    # Cross-event rule: first crossing bar only
                    if closes[i] > rh and i >= 1 and closes[i - 1] <= rh:
                        # Long signal
                        atr = atrs[i]
                        if atr is not None and atr > 0 and i + 1 < n:
                            entry_price = opens[i + 1]
                            stop_price = entry_price - STOP_ATR_MULT * atr
                            risk = entry_price - stop_price
                            if risk > 0:
                                target_price = entry_price + TARGET_R * risk
                                t = Trade(i + 1, entry_price, "LONG", stop_price, target_price)
                                trades.append(t)
                                position_open = True
                                i += 1
                                continue
                    elif closes[i] < rl and i >= 1 and closes[i - 1] >= rl:
                        # Short signal
                        atr = atrs[i]
                        if atr is not None and atr > 0 and i + 1 < n:
                            entry_price = opens[i + 1]
                            stop_price = entry_price + STOP_ATR_MULT * atr
                            risk = stop_price - entry_price
                            if risk > 0:
                                target_price = entry_price - TARGET_R * risk
                                t = Trade(i + 1, entry_price, "SHORT", stop_price, target_price)
                                trades.append(t)
                                position_open = True
                                i += 1
                                continue

        i += 1

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
