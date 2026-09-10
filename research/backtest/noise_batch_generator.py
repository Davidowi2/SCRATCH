"""
research/backtest/noise_batch_generator.py — Phase 2 Calibration: Noise Control Batch

Generates 10-15 known-random/known-bad kernel files for null_pass_rate calibration.
These use the exact same data pipeline and SMA20/SD math as H-001, but with
fundamentally broken/randomized logic. They should NOT pass the gates.

This script generates the kernel files. It does NOT run backtests.

NOISE KERNELS:
- N01_inverted.py: Entry logic inverted (Z>=2 -> LONG, Z<=-2 -> SHORT)
- N02_random_entry.py: Ignores Z-score, enters randomly every 10th bar
- N03_shuffled_returns.py: Shuffles close prices before SMA/SD calculation
- N04_fixed_stop.py: Fixed random pip SL/TP instead of dynamic SD
- N05_mean_avoidance.py: Enters only when |Z| < 0.5 (trading the noise)
"""

import os
import textwrap

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def write_kernel(filename, body):
    """Write a kernel file to the backtest directory."""
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w") as f:
        f.write(body)
    print(f"  Generated: {path}")


# =============================================================================
# N01: INVERTED ENTRY LOGIC
# =============================================================================
N01 = '''\
"""
N01_inverted.py — Noise Kernel: Inverted Entry Logic

Same as H-001 but entry is reversed (continuation instead of reversion).
Should NOT pass — this is the opposite of a mean-reversion edge.

CALIBRATION PURPOSE: Known-bad kernel. Expected verdict: KILL.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "N01"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "NOISE"
PARAM_DESC = "Inverted entry (Z>=2->LONG, Z<=-2->SHORT) — known bad"

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

    i = 0
    while i < n:
        if bars[i]["time"].hour in SESSION_HOURS:
            prior = stats_prior(closes, i)
            if prior is not None and prior[1] > 0:
                mean, sd = prior
                z = (closes[i - 1] - mean) / sd

                # INVERTED: Z>=2 -> LONG (continuation), Z<=-2 -> SHORT
                if z >= Z_ENTRY:
                    sl = opens[i] - SL_SD_MULT * sd  # stop below for LONG
                    t = Trade(i, opens[i], "LONG", sd, sl)
                elif z <= -Z_ENTRY:
                    sl = opens[i] + SL_SD_MULT * sd  # stop above for SHORT
                    t = Trade(i, opens[i], "SHORT", sd, sl)
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
                    gross = (t.exit_price - t.entry_price) if t.side == "LONG" \\
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
    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "gross_profit_pips": gross_profit, "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades) if trades else 0,
        "max_dd_pips": 0, "exits": exits,
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

    print(f"\\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.4f}  Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"\\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# =============================================================================
# N02: RANDOM ENTRY
# =============================================================================
N02 = '''\
"""
N02_random_entry.py — Noise Kernel: Random Entry

Ignores Z-score entirely. Enters LONG or SHORT at random on every 10th bar.
Should NOT pass — pure noise trading.

CALIBRATION PURPOSE: Known-bad kernel. Expected verdict: KILL.
"""

import csv
import math
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "N02"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "NOISE"
PARAM_DESC = "Random entry every 10th bar — known bad"

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

    bar_count = 0
    i = 0
    while i < n:
        if bars[i]["time"].hour in SESSION_HOURS:
            bar_count += 1
            # Random entry every 10th bar
            if bar_count % 10 == 0:
                side = "LONG" if random.random() > 0.5 else "SHORT"
                prior = stats_prior(closes, i)
                if prior is not None and prior[1] > 0:
                    mean, sd = prior
                    if side == "LONG":
                        sl = opens[i] - SL_SD_MULT * sd
                    else:
                        sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], side, sd, sl)
                    trades.append(t)
                    i = t.entry_idx
                    j = i
                    while j < n:
                        exited = False
                        if t.side == "LONG":
                            if opens[j] <= t.stop or lows[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] <= t.stop else t.stop
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
                        else:
                            if opens[j] >= t.stop or highs[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] >= t.stop else t.stop
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
                    gross = (t.exit_price - t.entry_price) if t.side == "LONG" \\
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
    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "gross_profit_pips": gross_profit, "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades) if trades else 0,
        "max_dd_pips": 0, "exits": exits,
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
        print("Gate 1 REJECT"); return 1

    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start, end = datetime.strptime("2021-01-01", "%Y-%m-%d"), datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start, end = datetime.strptime("2024-01-01", "%Y-%m-%d"), datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    random.seed(42)  # Reproducible noise
    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.4f}  Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"\\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# =============================================================================
# N03: SHUFFLED RETURNS
# =============================================================================
N03 = '''\
"""
N03_shuffled_returns.py — Noise Kernel: Shuffled Returns

Shuffles close prices before calculating SMA/SD, destroying the time-series
edge. The entry signal is computed on randomized data.

CALIBRATION PURPOSE: Known-bad kernel. Expected verdict: KILL.
"""

import csv
import math
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "N03"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "NOISE"
PARAM_DESC = "Shuffled close prices (destroyed time-series) — known bad"

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

    # SHUFFLE the close prices (destroy time-series structure)
    shuffled_closes = closes.copy()
    random.seed(42)
    random.shuffle(shuffled_closes)

    n = len(bars)
    trades = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS

    i = 0
    while i < n:
        if bars[i]["time"].hour in SESSION_HOURS:
            prior = stats_prior(shuffled_closes, i)  # Use SHUFFLED closes for signal
            if prior is not None and prior[1] > 0:
                mean, sd = prior
                z = (shuffled_closes[i - 1] - mean) / sd  # Z from shuffled data

                if z >= Z_ENTRY:
                    sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                elif z <= -Z_ENTRY:
                    sl = opens[i] - SL_SD_MULT * sd
                    t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None

                if t is not None:
                    trades.append(t)
                    i = t.entry_idx
                    j = i
                    while j < n:
                        exited = False
                        # Exit checks use REAL closes (not shuffled)
                        if t.side == "LONG":
                            if opens[j] <= t.stop or lows[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] <= t.stop else t.stop
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
                        else:
                            if opens[j] >= t.stop or highs[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] >= t.stop else t.stop
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
                    gross = (t.exit_price - t.entry_price) if t.side == "LONG" \\
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
    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "gross_profit_pips": gross_profit, "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades) if trades else 0,
        "max_dd_pips": 0, "exits": exits,
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
        print("Gate 1 REJECT"); return 1

    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start, end = datetime.strptime("2021-01-01", "%Y-%m-%d"), datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start, end = datetime.strptime("2024-01-01", "%Y-%m-%d"), datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.4f}  Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"\\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# =============================================================================
# N04: FIXED STOP/TP
# =============================================================================
N04 = '''\
"""
N04_fixed_stop.py — Noise Kernel: Fixed Random Stop Loss and Take Profit

Uses H-001 entry logic but replaces dynamic SD-based stops with fixed
random pip values. Destroys the risk/reward calibration.

CALIBRATION PURPOSE: Known-bad kernel. Expected verdict: KILL.
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
PARAM_DESC = "Fixed random pip SL/TP (destroyed risk calibration) — known bad"

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

    i = 0
    while i < n:
        if bars[i]["time"].hour in SESSION_HOURS:
            prior = stats_prior(closes, i)
            if prior is not None and prior[1] > 0:
                mean, sd = prior
                z = (closes[i - 1] - mean) / sd

                if z >= Z_ENTRY:
                    # FIXED random stop (5-50 pips) instead of dynamic SD
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
                            if opens[j] <= t.stop or lows[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] <= t.stop else t.stop
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
                        else:
                            if opens[j] >= t.stop or highs[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] >= t.stop else t.stop
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
                    gross = (t.exit_price - t.entry_price) if t.side == "LONG" \\
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
    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "gross_profit_pips": gross_profit, "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades) if trades else 0,
        "max_dd_pips": 0, "exits": exits,
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
        print("Gate 1 REJECT"); return 1

    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start, end = datetime.strptime("2021-01-01", "%Y-%m-%d"), datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start, end = datetime.strptime("2024-01-01", "%Y-%m-%d"), datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    random.seed(42)
    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.4f}  Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"\\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


# =============================================================================
# N05: MEAN AVOIDANCE
# =============================================================================
N05 = '''\
"""
N05_mean_avoidance.py — Noise Kernel: Trade the Noise (Avoid the Edge)

Enters only when |Z| < 0.5 — the exact opposite of H-001's edge condition.
Trades in the chop/noise, avoiding the extreme moves where the edge lives.

CALIBRATION PURPOSE: Known-bad kernel. Expected verdict: KILL.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "N05"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "NOISE"
PARAM_DESC = "Enters only when |Z|<0.5 (trading the noise) — known bad"

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

    i = 0
    while i < n:
        if bars[i]["time"].hour in SESSION_HOURS:
            prior = stats_prior(closes, i)
            if prior is not None and prior[1] > 0:
                mean, sd = prior
                z = (closes[i - 1] - mean) / sd

                # ENTER ONLY IN NOISE: |Z| < 0.5
                if abs(z) < 0.5:
                    # Alternate sides based on sign of Z (momentum in noise)
                    if z >= 0:
                        sl = opens[i] + SL_SD_MULT * sd
                        t = Trade(i, opens[i], "SHORT", sd, sl)
                    else:
                        sl = opens[i] - SL_SD_MULT * sd
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
                            if opens[j] <= t.stop or lows[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] <= t.stop else t.stop
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
                        else:
                            if opens[j] >= t.stop or highs[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j] if opens[j] >= t.stop else t.stop
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
                    gross = (t.exit_price - t.entry_price) if t.side == "LONG" \\
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
    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1
    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "gross_profit_pips": gross_profit, "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades) if trades else 0,
        "max_dd_pips": 0, "exits": exits,
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
        print("Gate 1 REJECT"); return 1

    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start, end = datetime.strptime("2021-01-01", "%Y-%m-%d"), datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start, end = datetime.strptime("2024-01-01", "%Y-%m-%d"), datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.4f}  Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"\\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    print("=" * 60)
    print("NOISE BATCH GENERATOR — Phase 2 Calibration")
    print("=" * 60)
    print(f"Output directory: {OUT_DIR}")
    print()

    write_kernel("N01_inverted.py", N01)
    write_kernel("N02_random_entry.py", N02)
    write_kernel("N03_shuffled_returns.py", N03)
    write_kernel("N04_fixed_stop.py", N04)
    write_kernel("N05_mean_avoidance.py", N05)

    print()
    print("=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print("\nLEASH ACKNOWLEDGED:")
    print("  - These are scaffolding files only. No backtests run.")
    print("  - They use the same data pipeline and SMA20/SD math as H-001.")
    print("  - They will be run in Phase 2 (calibration) after H-003 resolves.")
    print("  - Frozen files (run_h1.py, validate_data.py, graveyard.csv) untouched.")


if __name__ == "__main__":
    main()
