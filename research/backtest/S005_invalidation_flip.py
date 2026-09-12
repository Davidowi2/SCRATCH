"""
research/backtest/S005_invalidation_flip.py — S-005 Invalidation Flip

Implements the exact math from the Overseer's locked spec:

COMMON DEFINITIONS:
- Swings: 5-bar fractals, identical to S-001, including confirmation lag.
- Trend state: DOWNTREND = last two confirmed swing highs strictly descending
  AND last two confirmed swing lows strictly descending. UPTREND mirrored.
  Otherwise: no state, no signals.
- Cross-event rule: any level-cross signal fires ONLY on the first crossing
  bar. No re-triggers.
- Fill conventions R1 and R3 apply factory-wide.
- Rails: friction 0.5 pips/trade; max hold 72 bars; one position at a time.

MATH:
1. Requires a BOS event and leg exactly as S-004 (S and E defined identically).
2. Invalidation: first bar m > j with close[m] > S (down leg) -> enter LONG
   at open[m+1]. Stop = entry - 1.0*ATR14[m]. Target = 1.5R.
3. Mirror: close[m] < S (up leg) -> SHORT; stop = entry + 1.0*ATR14[m].
4. Consume leg on invalidation. If a position is open at open[m+1], the
   signal is discarded (one-position rule; no deferral).

CALIBRATION PURPOSE: Hypothesis test. Expected to pass or die cleanly based
on whether invalidation flips exist in EURUSD H1.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "S-005"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "INVALIDATION"
PARAM_DESC = "Invalidation flip: close beyond structure extreme"

FRICTION_PIPS = 0.5
PIP = 0.0001
MAX_HOLD_BARS = 72
ATR_PERIOD = 14
STOP_ATR_MULT = 1.0
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
    if i < 2 or i >= len(highs) - 2:
        return False
    return (highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and
            highs[i] > highs[i + 1] and highs[i] > highs[i + 2])


def is_fractal_low(lows, i):
    if i < 2 or i >= len(lows) - 2:
        return False
    return (lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and
            lows[i] < lows[i + 1] and lows[i] < lows[i + 2])


def run_backtest(bars, friction_override=None):
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS

    confirmed_highs = []
    confirmed_lows = []
    position_open = False

    # Pending setup: leg defined by BOS, watching for invalidation
    pending_setup = None  # dict with S, E, side, bos_bar_idx

    i = 2
    while i < n:
        confirm_idx = i - 2
        if confirm_idx >= 2 and confirm_idx < n - 2:
            if is_fractal_high(highs, confirm_idx):
                confirmed_highs.append((confirm_idx, highs[confirm_idx]))
            if is_fractal_low(lows, confirm_idx):
                confirmed_lows.append((confirm_idx, lows[confirm_idx]))

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

        # Determine trend state
        downtrend = False
        uptrend = False
        if len(confirmed_highs) >= 2 and len(confirmed_lows) >= 2:
            sh_prev = confirmed_highs[-2][1]
            sh_last = confirmed_highs[-1][1]
            sl_prev = confirmed_lows[-2][1]
            sl_last = confirmed_lows[-1][1]
            if sh_prev > sh_last and sl_prev > sl_last:
                downtrend = True
            elif sh_prev < sh_last and sl_prev < sl_last:
                uptrend = True

        # DOWNTREND: BOS down, define leg S and E
        if downtrend and i >= 1:
            sl_last = confirmed_lows[-1][1]
            if closes[i] < sl_last and closes[i - 1] >= sl_last:
                sh_last = confirmed_highs[-1][1]
                sh_idx = confirmed_highs[-1][0]
                e_val = min(lows[sh_idx:i + 1])
                pending_setup = {
                    "side": "SHORT",
                    "S": sh_last,
                    "E": e_val,
                    "S_idx": sh_idx,
                    "bos_idx": i,
                }

        # UPTREND: BOS up, define leg S and E
        if uptrend and i >= 1:
            sh_last = confirmed_highs[-1][1]
            if closes[i] > sh_last and closes[i - 1] <= sh_last:
                sl_last = confirmed_lows[-1][1]
                sl_idx = confirmed_lows[-1][0]
                e_val = max(highs[sl_idx:i + 1])
                pending_setup = {
                    "side": "LONG",
                    "S": sl_last,
                    "E": e_val,
                    "S_idx": sl_idx,
                    "bos_idx": i,
                }

        # Check pending setup for invalidation signal
        if pending_setup is not None:
            ps = pending_setup
            # Invalidation: close beyond S
            if ps["side"] == "SHORT":
                # Down leg: invalidation is close > S
                if closes[i] > ps["S"] and i > ps["bos_idx"]:
                    # Check one-position rule: if position open, discard
                    if not position_open and i + 1 < n:
                        atr = atr14(highs, lows, closes, i)
                        if atr is not None and atr > 0:
                            entry_price = opens[i + 1]
                            stop_price = entry_price - STOP_ATR_MULT * atr
                            risk = entry_price - stop_price
                            if risk > 0:
                                target_price = entry_price + TARGET_R * risk
                                t = Trade(i + 1, entry_price, "LONG", stop_price, target_price)
                                trades.append(t)
                                position_open = True
                                pending_setup = None
                                i += 1
                                continue
            else:  # LONG leg (from uptrend)
                # Up leg: invalidation is close < S
                if closes[i] < ps["S"] and i > ps["bos_idx"]:
                    if not position_open and i + 1 < n:
                        atr = atr14(highs, lows, closes, i)
                        if atr is not None and atr > 0:
                            entry_price = opens[i + 1]
                            stop_price = entry_price + STOP_ATR_MULT * atr
                            risk = stop_price - entry_price
                            if risk > 0:
                                target_price = entry_price - TARGET_R * risk
                                t = Trade(i + 1, entry_price, "SHORT", stop_price, target_price)
                                trades.append(t)
                                position_open = True
                                pending_setup = None
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
