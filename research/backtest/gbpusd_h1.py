"""
gbpusd_h1.py — H-003: H-001 fade logic on GBPUSD, Asian session.

FROZEN SPEC: factory/CHARTER.md (Phase 1)
Parent: H-001 (pre-declared replication)
DNA: same mechanism_hash as H-001, different parameter_hash (GBPUSD vs EURUSD)

This engine imports signal logic from the frozen run_h1.py and adapts it for GBPUSD.
Frozen run_h1.py is NEVER edited.

FROZEN RULES:
- Instrument: GBPUSD, Timeframe: H1, Session: hours {22,23,0,1,2,3,4,5,6}
- Entry: |Z| >= 2.0 at bar open (fade: Z>=2 -> SHORT, Z<=-2 -> LONG)
- Stop: 1.5 x entry-bar SD
- Exit: close back inside 1.0 SD band, OR max hold 8 bars
- One position max, friction 1.0 pips/trade (fatter GBP Asia spreads)
"""

import csv
import hashlib
import logging
import os
import sys
from datetime import datetime
from typing import Optional

# Ensure research/backtest is importable
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

# Import frozen strategy — NEVER edit the frozen file
import run_h1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "gbpusd_h1.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("gbpusd_h1")

# ---------------------------------------------------------------------------
# PRE-COMMITTED PARAMETERS (H-003, preregistered)
# ---------------------------------------------------------------------------
EXPERIMENT_ID = "H-003"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "MR"  # mean reversion (same as H-001)
PARAM_DESC = "Z>2 SMA20 1SD-band reversion, Asian 22:00-07:00, GBPUSD, maxhold 8, SL 1.5xSD, friction 1.0"

# Inherited from frozen run_h1.py (read-only)
MA_PERIOD = run_h1.MA_PERIOD  # 20
Z_ENTRY = run_h1.Z_ENTRY  # 2.0
Z_EXIT = run_h1.Z_EXIT  # 1.0
MAX_HOLD_BARS = run_h1.MAX_HOLD_BARS  # 8
SL_SD_MULT = run_h1.SL_SD_MULT  # 1.5
FRICTION_PIPS = 1.0  # GBPUSD has wider spreads than EURUSD
PIP = run_h1.PIP  # 0.0001
SESSION_HOURS = run_h1.SESSION_HOURS  # {22,23,0,1,2,3,4,5,6}

# Frozen windows (identical to H-001)
IS_START = "2021-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2025-05-13"

# Fidelity gate
EXPECTED_ENGINE_HASH = "6226222c1eb076fb2f6fe4862d1992a80c5f68fe54a6353697312d160cf8f291"
EXPECTED_VALIDATOR_HASH = "662bd10ea2d10ee6dc1539e38a6fb3782785077b"


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


def verify_frozen_artifacts():
    """Verify frozen engine integrity at startup."""
    engine_path = os.path.join(_SCRIPT_DIR, "run_h1.py")
    with open(engine_path, "rb") as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    if actual != EXPECTED_ENGINE_HASH:
        raise RuntimeError(f"ENGINE TAMPERED: {actual[:12]}... != expected {EXPECTED_ENGINE_HASH[:12]}...")
    logger.info("Engine hash verified: %s...", actual[:12])


def stats_prior(closes, i):
    """SMA/SD of closes strictly before index i — copied from run_h1.py logic."""
    if i < MA_PERIOD:
        return None
    window = closes[i - MA_PERIOD:i]
    mean = sum(window) / MA_PERIOD
    var = sum((x - mean) ** 2 for x in window) / MA_PERIOD
    sd = var ** 0.5
    return mean, sd


def run_backtest(bars, friction_override=None):
    """Run H-003 backtest on bar list."""
    closes = [b["close"] for b in bars]
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
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
                    sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                elif z <= -Z_ENTRY:
                    sl = opens[i] - SL_SD_MULT * sd
                    t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None

                if t is not None:
                    trades.append(t)
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
                                thru = stats_prior(closes, j + 1)
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
                                thru = stats_prior(closes, j + 1)
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
    """Compute performance metrics."""
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "avg_bars_held": 0, "exits": {}}

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
        "n": len(trades),
        "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "gross_profit_pips": gross_profit,
        "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades),
        "max_dd_pips": max_dd,
        "avg_bars_held": sum(t.bars_held for t in trades) / len(trades),
        "exits": exits,
    }


def decide(metrics, phase):
    """Apply pre-committed kill criteria (H-001 v2.1 table)."""
    n = metrics["n"]
    if phase == "insample":
        if n < 50:
            return "INSUFFICIENT", f"n={n} < 50: below statistical floor"
        pf = metrics["profit_factor"]
        if pf == float("inf"):
            return "SUSPICIOUS", "zero losses - debug for leakage"
        if pf < 1.0:
            return "KILL", f"PF {pf:.2f} < 1.0"
        if metrics["win_rate"] < 0.45:
            return "KILL", f"win rate {metrics['win_rate']:.0%} < 45% floor"
        if pf <= 1.15:
            return "DANGER-ZONE", f"PF {pf:.2f} in 1.0-1.15 band: log, stop, owner decides"
        return "PASS-INSAMPLE", f"PF {pf:.2f}: passes IS floor"

    if phase == "oos":
        pf = metrics["profit_factor"]
        if n < 30:
            return "INSUFFICIENT", f"OOS n={n} < 30"
        if pf < 1.0:
            return "KILL", f"OOS PF {pf:.2f} < 1.0"
        if metrics["win_rate"] < 0.45:
            return "KILL", f"OOS win rate {metrics['win_rate']:.0%} < 45% floor"
        if pf <= 1.15:
            return "DANGER-ZONE", f"OOS PF {pf:.2f} in 1.0-1.15 band"
        return "PASS-OOS", f"OOS PF {pf:.2f} >= 1.15; escalate to paper"

    return "UNKNOWN", "unknown phase"


def load_dataset(path):
    """Load dataset CSV."""
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="H-003 GBPUSD mean-reversion backtest (preregistered)")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    # Fidelity gate
    verify_frozen_artifacts()

    # Load data
    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start, end = datetime.strptime(IS_START, "%Y-%m-%d"), datetime.strptime(IS_END, "%Y-%m-%d")
    else:
        start, end = datetime.strptime(OOS_START, "%Y-%m-%d"), datetime.strptime(OOS_END, "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    data_range = f"{bars[0]['time'].date()}..{bars[-1]['time'].date()}"
    print("=" * 78)
    print(f"{EXPERIMENT_ID} | Mean reversion GBPUSD H1 | {PARAM_DESC}")
    print(f"Data: {len(bars)} H1 bars, {data_range} | phase={args.phase}")
    print("=" * 78)

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  win_rate={metrics['win_rate']:.1%}  "
          f"PF={metrics['profit_factor']:.2f}  expectancy={metrics['expectancy_pips']:+.2f} pips  "
          f"maxDD={metrics['max_dd_pips']:.1f} pips  avg_hold={metrics['avg_bars_held']:.1f} bars")
    print(f"  Exit reasons: {metrics['exits']}")
    print(f"\nVERDICT: {verdict}")
    print(f"  {note}")

    # Output trade log
    output_path = os.path.join("research", f"trade_log_{args.phase}_h003.csv")
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["entry_time", "side", "entry_price", "exit_price", "exit_reason", "pips", "bars_held"])
        for t in trades:
            writer.writerow([
                bars[t.entry_idx]["time"].strftime("%Y-%m-%d %H:%M:%S"),
                t.side, f"{t.entry_price:.5f}", f"{t.exit_price:.5f}",
                t.exit_reason, f"{t.pips:.1f}", t.bars_held
            ])
    print(f"\nTrade log: {output_path}")

    return 0 if "KILL" not in verdict and "SUSPICIOUS" not in verdict else 1


if __name__ == "__main__":
    sys.exit(main())
