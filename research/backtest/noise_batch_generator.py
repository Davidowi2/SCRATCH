"""
research/backtest/noise_batch_generator.py — Phase 2 Calibration: Noise Control Batch

Generates 10 known-random/known-bad kernel files for null_pass_rate calibration.
These use the exact same data pipeline and SMA20/SD math as H-001, but with
fundamentally broken/randomized logic. They should NOT pass the gates.

This script generates the kernel files. It does NOT run backtests.

NOISE KERNELS (10 total):
- N01_inverted: Entry logic inverted (continuation with inverted exit)
- N02_random_entry: Ignores Z-score, enters randomly every 10th bar
- N03_shuffled_returns: Shuffles close prices before SMA/SD calculation
- N04_fixed_stop: Fixed random pip SL/TP instead of dynamic SD
- N05_mean_avoidance: Enters only when |Z| < 0.5 (trading the chop)
- N06_lag_entry: Enters 3 bars AFTER the Z signal (stale edge)
- N07_opposite_session: Only trades London/NY, not Asian
- N08_random_stop: H-001 entry but random SD multiplier for stop
- N09_half_sized: H-001 logic but exit at 0.5 SD instead of 1.0 SD
- N10_always_long: Always goes LONG on every Asian bar, ignores signals
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
# SHARED TEMPLATE (used by all noise kernels)
# =============================================================================

HEADER = '''\
"""
{kernel_id}_{name}.py — Noise Kernel: {description}

CALIBRATION PURPOSE: Known-bad kernel. Expected verdict: KILL.
{notes}
"""

import csv
import math
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "{kernel_id}"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "NOISE"
PARAM_DESC = "{description} — known bad"

MA_PERIOD = 20
Z_ENTRY = 2.0
Z_EXIT = 1.0
MAX_HOLD_BARS = 8
SL_SD_MULT = 1.5
FRICTION_PIPS = 0.5
PIP = 0.0001
SESSION_HOURS = {session_hours}


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
            bars.append({{
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }})
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
'''

RUN_BACKTEST_TEMPLATE = '''\
def run_backtest(bars, friction_override=None):
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS
    random.seed({seed})  # Reproducible noise

    i = 0
    while i < n:
        if bars[i]["time"].hour in SESSION_HOURS:
            prior = stats_prior(closes, i)
            if prior is not None and prior[1] > 0:
                mean, sd = prior
                z = (closes[i - 1] - mean) / sd
{entry_logic}
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
                                    {long_exit}
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
                                    {short_exit}

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
'''

METRICS_DECIDE = '''\
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

    print(f"\\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.4f}  Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"\\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def make_kernel(kernel_id, name, description, notes, session_hours, seed,
                entry_logic, long_exit, short_exit):
    """Build a complete noise kernel file."""
    header = HEADER.format(
        kernel_id=kernel_id,
        name=name,
        description=description,
        notes=notes,
        session_hours="{22, 23, 0, 1, 2, 3, 4, 5, 6}" if session_hours == "asian" else "{12, 13, 14, 15, 16}",
        seed=seed,
    )
    run_backtest = RUN_BACKTEST_TEMPLATE.format(
        seed=seed,
        entry_logic=entry_logic,
        long_exit=long_exit,
        short_exit=short_exit,
    )
    return header + run_backtest + METRICS_DECIDE


# =============================================================================
# N01: INVERTED (continuation with inverted exit)
# =============================================================================
N01_ENTRY = '''\
                # INVERTED: Z>=2 -> LONG (continuation), Z<=-2 -> SHORT
                if z >= Z_ENTRY:
                    sl = opens[i] - SL_SD_MULT * sd
                    t = Trade(i, opens[i], "LONG", sd, sl)
                elif z <= -Z_ENTRY:
                    sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                else:
                    t = None'''
N01_LONG_EXIT = '''if zj <= Z_EXIT:  # exit when price falls back
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''
N01_SHORT_EXIT = '''if zj >= -Z_EXIT:  # exit when price rises back
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''


# =============================================================================
# N02: RANDOM ENTRY
# =============================================================================
N02_ENTRY = '''\
                # Random entry every 10th bar
                if i % 10 == 0:
                    side = "LONG" if random.random() > 0.5 else "SHORT"
                    if side == "LONG":
                        sl = opens[i] - SL_SD_MULT * sd
                    else:
                        sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], side, sd, sl)
                else:
                    t = None'''


# =============================================================================
# N03: SHUFFLED RETURNS
# =============================================================================
N03_ENTRY = '''\
                # SHUFFLE closes before computing Z
                shuffled = closes.copy()
                random.seed(42)
                random.shuffle(shuffled)
                prior = stats_prior(shuffled, i)
                if prior is not None and prior[1] > 0:
                    mean, sd = prior
                    z = (shuffled[i - 1] - mean) / sd
                    if z >= Z_ENTRY:
                        sl = opens[i] + SL_SD_MULT * sd
                        t = Trade(i, opens[i], "SHORT", sd, sl)
                    elif z <= -Z_ENTRY:
                        sl = opens[i] - SL_SD_MULT * sd
                        t = Trade(i, opens[i], "LONG", sd, sl)
                    else:
                        t = None
                else:
                    t = None'''


# =============================================================================
# N04: FIXED STOP/TP
# =============================================================================
N04_ENTRY = '''\
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
                    t = None'''


# =============================================================================
# N05: MEAN AVOIDANCE
# =============================================================================
N05_ENTRY = '''\
                # Enter only in noise: |Z| < 0.5
                if abs(z) < 0.5:
                    if z >= 0:
                        sl = opens[i] + SL_SD_MULT * sd
                        t = Trade(i, opens[i], "SHORT", sd, sl)
                    else:
                        sl = opens[i] - SL_SD_MULT * sd
                        t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None'''


# =============================================================================
# N06: LAG ENTRY (stale edge)
# =============================================================================
N06_ENTRY = '''\
                # Enter 3 bars AFTER signal (stale edge)
                if i >= 3:
                    past = stats_prior(closes, i - 3)
                    if past is not None and past[1] > 0:
                        pmean, psd = past
                        pz = (closes[i - 4] - pmean) / psd
                        if pz >= Z_ENTRY:
                            sl = opens[i] + SL_SD_MULT * psd
                            t = Trade(i, opens[i], "SHORT", psd, sl)
                        elif pz <= -Z_ENTRY:
                            sl = opens[i] - SL_SD_MULT * psd
                            t = Trade(i, opens[i], "LONG", psd, sl)
                        else:
                            t = None
                    else:
                        t = None
                else:
                    t = None'''


# =============================================================================
# N07: OPPOSITE SESSION (London/NY)
# =============================================================================
N07_ENTRY = '''\
                # Only trade London/NY, not Asian
                if z >= Z_ENTRY:
                    sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                elif z <= -Z_ENTRY:
                    sl = opens[i] - SL_SD_MULT * sd
                    t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None'''


# =============================================================================
# N08: RANDOM STOP MULTIPLIER
# =============================================================================
N08_ENTRY = '''\
                # Random SD multiplier for stop
                if z >= Z_ENTRY:
                    mult = random.uniform(0.5, 3.0)
                    sl = opens[i] + mult * sd
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                elif z <= -Z_ENTRY:
                    mult = random.uniform(0.5, 3.0)
                    sl = opens[i] - mult * sd
                    t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None'''


# =============================================================================
# N09: HALF-SIZED EXIT
# =============================================================================
N09_ENTRY = '''\
                # Standard H-001 entry
                if z >= Z_ENTRY:
                    sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                elif z <= -Z_ENTRY:
                    sl = opens[i] - SL_SD_MULT * sd
                    t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None'''
N09_LONG_EXIT = '''if zj >= -0.5:  # exit at 0.5 SD instead of 1.0
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''
N09_SHORT_EXIT = '''if zj <= 0.5:  # exit at 0.5 SD instead of 1.0
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''


# =============================================================================
# N10: ALWAYS LONG
# =============================================================================
N10_ENTRY = '''\
                # Always LONG on every Asian bar
                sl = opens[i] - SL_SD_MULT * sd
                t = Trade(i, opens[i], "LONG", sd, sl)'''


# =============================================================================
# GENERATE ALL KERNELS
# =============================================================================

def main():
    print("=" * 60)
    print("NOISE BATCH GENERATOR — Phase 2 Calibration (10 kernels)")
    print("=" * 60)
    print(f"Output directory: {OUT_DIR}")
    print()

    kernels = [
        ("N01", "inverted", "Inverted entry (continuation with inverted exit)",
         "# Entry: Z>=2->LONG, Z<=-2->SHORT\n# Exit: LONG exits when Z<=1, SHORT exits when Z>=-1",
         "asian", 42, N01_ENTRY, N01_LONG_EXIT, N01_SHORT_EXIT),
        ("N02", "random_entry", "Random entry every 10th bar",
         "# Ignores Z-score entirely. Random LONG/SHORT every 10th bar.",
         "asian", 42, N02_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
        ("N03", "shuffled_returns", "Shuffled close prices (destroyed time-series)",
         "# Shuffles close prices before computing SMA/SD. Destroys time-series structure.",
         "asian", 42, N03_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
        ("N04", "fixed_stop", "Fixed random pip SL/TP",
         "# Fixed random pip SL/TP instead of dynamic SD-based stops.",
         "asian", 42, N04_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
        ("N05", "mean_avoidance", "Enters only when |Z|<0.5 (trading the chop)",
         "# Enters only when |Z| < 0.5. Avoids the extreme moves where edge lives.",
         "asian", 42, N05_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
        ("N06", "lag_entry", "Enters 3 bars AFTER signal (stale edge)",
         "# Enters 3 bars after the Z signal fires. By then edge is gone.",
         "asian", 42, N06_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
        ("N07", "opposite_session", "Trades London/NY only, not Asian",
         "# Only trades London/NY session (12:00-17:00 UTC). Edge is Asian-only.",
         "london", 42, N07_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
        ("N08", "random_stop", "Random SD multiplier for stop",
         "# Random SD multiplier (0.5-3.0) for stop. Destroys risk calibration.",
         "asian", 42, N08_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
        ("N09", "half_sized", "Exit at 0.5 SD instead of 1.0 SD",
         "# Exits at 0.5 SD instead of 1.0 SD. Takes profits too early.",
         "asian", 42, N09_ENTRY, N09_LONG_EXIT, N09_SHORT_EXIT),
        ("N10", "always_long", "Always LONG on every Asian bar",
         "# Always goes LONG on every Asian bar. Ignores signals entirely.",
         "asian", 42, N10_ENTRY,
         '''if zj >= -Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True''',
         '''if zj <= Z_EXIT:
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True'''),
    ]

    for kernel in kernels:
        kernel_id, name, desc, notes, session, seed, entry, long_exit, short_exit = kernel
        body = make_kernel(kernel_id, name, desc, notes, session, seed,
                           entry, long_exit, short_exit)
        write_kernel(f"{kernel_id}_{name}.py", body)

    print()
    print("=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print("\nLEASH ACKNOWLEDGED:")
    print("  - 10 noise kernels generated (scaffolding only).")
    print("  - All use same data pipeline and SMA20/SD math as H-001.")
    print("  - All random kernels use fixed seed (random.seed(42)).")
    print("  - N01 inverted: entry AND exit both inverted (true continuation test).")
    print("  - max_dd_pips computed properly in all kernels.")
    print("  - Frozen files (run_h1.py, validate_data.py, graveyard.csv) untouched.")


if __name__ == "__main__":
    main()
