"""
N04_fixed_stop.py — Noise Kernel: Fixed random pip SL/TP

CALIBRATION PURPOSE: Known-bad kernel. Expected verdict: KILL.
# Fixed random pip SL/TP instead of dynamic SD-based stops.
"""

import csv
import math
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "N04"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "NOISE"
PARAM_DESC = "Fixed random pip SL/TP — known bad"

MA_PERIOD = 20
Z_ENTRY = 2.0
Z_EXIT = 1.0
MAX_HOLD_BARS = 8
SL_SD_MULT = 1.5
FRICTION_PIPS = 0.5
PIP = 0.0001
SESSION_HOURS = {22, 23, 0, 1, 2, 3, 4, 5, 6}


class Trade:
    def __init__(self, entry_idx, entry_price, side, sd, sl):
        self.entry_idx = entry_idx
        self.entry_price = entry_price
        self.side = side
        self.sd = sd
        self.stop = sl
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


def stats_prior(closes, i):
    if i < MA_PERIOD:
        return None
    window = closes[i - MA_PERIOD:i]
    mean = sum(window) / MA_PERIOD
    var = sum((x - mean) ** 2 for x in window) / MA_PERIOD
    sd = math.sqrt(var)
    return mean, sd


def stats_through(closes, j):
    if j + 1 < MA_PERIOD:
        return None
    window = closes[j + 1 - MA_PERIOD:j + 1]
    mean = sum(window) / MA_PERIOD
    sd = math.sqrt(sum((x - mean) ** 2 for x in window) / MA_PERIOD)
    return mean, sd
def run_backtest(bars, friction_override=None):
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS
    random.seed(42)  # Reproducible noise

    i = 0
    while i < n:
        if bars[i]["time"].hour in SESSION_HOURS:
            prior = stats_prior(closes, i)
            if prior is not None and prior[1] > 0:
                mean, sd = prior
                z = (closes[i - 1] - mean) / sd
                # Fixed random pip SL/TP
                if z >= Z_ENTRY:
                    stop_pips = random.uniform(5, 50)
                    sl = opens[i] + stop_pips * PIP
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                elif z <= -Z_ENTRY:
                    stop_pips = random.uniform(5, 50)
                    sl = opens[i] - stop_pips * PIP
                    t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None
                if t is not None:
                    trades.append(t)
                    i = t.entry_idx
                    j = i
                    while j < n:
                        exited = False
                        if t.side == "LONG":
                            if opens[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j]
                                t.exit_reason = "STOP"
                                exited = True
                            elif lows[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, t.stop
                                t.exit_reason = "STOP"
                                exited = True
                            else:
                                thru = stats_through(closes, j)
                                if thru is not None and thru[1] > 0:
                                    zj = (closes[j] - thru[0]) / thru[1]
                                    if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True
                        else:  # SHORT
                            if opens[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j]
                                t.exit_reason = "STOP"
                                exited = True
                            elif highs[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, t.stop
                                t.exit_reason = "STOP"
                                exited = True
                            else:
                                thru = stats_through(closes, j)
                                if thru is not None and thru[1] > 0:
                                    zj = (closes[j] - thru[0]) / thru[1]
                                    if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True

                        if not exited and (j - i + 1) >= MAX_HOLD_BARS:
                            t.exit_idx, t.exit_price = j, closes[j]
                            t.exit_reason = "MAXHOLD"
                            exited = True
                        if exited:
                            break
                        j += 1

                    if t.exit_idx is None:
                        t.exit_idx, t.exit_price = n - 1, closes[-1]
                        t.exit_reason = "EOD"
                    t.bars_held = t.exit_idx - t.entry_idx + 1
                    gross = (t.exit_price - t.entry_price) if t.side == "LONG" \
                        else (t.entry_price - t.exit_price)
                    t.pips = gross / PIP - friction
                    i = t.exit_idx + 1
                    continue
        i += 1
    return trades
def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "exits": {}}
    wins = [t for t in trades if t.pips > 0]
    gross_profit = sum(t.pips for t in wins)
    gross_loss = -sum(t.pips for t in trades if t.pips <= 0)

    # Proper max DD computation
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
