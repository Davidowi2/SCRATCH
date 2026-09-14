"""
research/backtest/S006_ema_trendfilter.py — S-006 EMA Trend Filter (EURUSD H1)

Implements the exact math from factory/preregistrations/S006.md (Directive U v1):

1. EMA50/EMA200 recursive, seeded with SMA of first N bars of the phase window.
2. Regime: UPTREND = EMA50>EMA200 AND (EMA50-EMA200) > 0.2*ATR14; DOWNTREND
   mirrored; SIDEWAYS (distance <= 0.2*ATR14) = no trades.
3. Entry LONG: UPTREND AND close[i-1] < EMA50[i-1] AND close[i] > EMA50[i].
   SHORT mirrored. Entry at open[i+1].
4. Stop DISTANCE = 1.5*ATR14 at signal bar (from entry); target = 2.0R.
5. Rails: friction 0.5 pips, max hold 72, one position, one trade per event.

RULINGS:
- R1: stop before target; one bar touching both = loss; open gapping through
  stop fills at open; max-hold checked after, at the close.
- R3: entry-bar open gapping through planned stop (risk <= 0) discards signal.
- B3 lineage: entry bar IS evaluated (i += 1 after trade creation).
- B4 lineage: gross metrics from pre-friction outcomes.
- ATR14: S001/S010 EURUSD lineage (bars up to AND including signal bar).
- Flat ATR=0 bars (2020 smoke has 1,272 OHLC-flat bars) => risk<=0 => discard.

CALIBRATION PURPOSE: trend-following regime + pullback re-entry hypothesis
from the YouTube backlog (S-006/S-007 pair). Passes or dies cleanly.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "S-006"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "EMATREND"
PARAM_DESC = "EMA50/200 regime + pullback re-cross, stop 1.5ATR target 2R"

FRICTION_PIPS = 0.5
PIP = 0.0001
MAX_HOLD_BARS = 72
ATR_PERIOD = 14
STOP_ATR_MULT = 1.5
TARGET_R = 2.0
EMA_FAST = 50
EMA_SLOW = 200
REGIME_DIST_ATR = 0.2


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
    """ATR14 using only bars up to and including j (S001/S010 lineage)."""
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


def ema_series(closes, period):
    """Recursive EMA seeded with SMA of the first `period` bars.
    List aligned to closes; None before seed completes."""
    n = len(closes)
    out = [None] * n
    if n < period:
        return out
    seed = sum(closes[:period]) / period
    out[period - 1] = seed
    mult = 2.0 / (period + 1)
    prev = seed
    for i in range(period, n):
        prev = (closes[i] - prev) * mult + prev
        out[i] = prev
    return out


def regime_at(i, ema_f, ema_s, atr):
    """UPTREND / DOWNTREND / SIDEWAYS / None (None = insufficient warmup)."""
    f, s = ema_f[i], ema_s[i]
    if f is None or s is None or atr is None:
        return None
    dist = f - s
    need = REGIME_DIST_ATR * atr
    if dist > need:
        return "UP"
    if -dist > need:
        return "DOWN"
    return "SIDEWAYS"


def run_backtest(bars):
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)

    ema_f = ema_series(closes, EMA_FAST)
    ema_s = ema_series(closes, EMA_SLOW)
    atrs = [atr14(highs, lows, closes, i) for i in range(n)]

    trades = []
    position_open = False
    i = 0
    while i < n:
        if position_open:
            t = trades[-1]
            j = i
            exited = False

            # R1: STOP before TARGET
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

            # max-hold AFTER stop/target, at the close
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
                t.pips = gross - FRICTION_PIPS
                i = t.exit_idx + 1
                continue

            i += 1
            continue

        # --- signal search ---
        reg = regime_at(i, ema_f, ema_s, atrs[i])
        if reg and i >= 1 and ema_f[i - 1] is not None and i + 1 < n:
            atr = atrs[i]
            if reg == "UP" and closes[i - 1] < ema_f[i - 1] and closes[i] > ema_f[i]:
                entry_price = opens[i + 1]
                risk = STOP_ATR_MULT * atr
                stop_price = entry_price - risk
                if risk > 0 and entry_price > stop_price:  # R3
                    target_price = entry_price + TARGET_R * risk
                    trades.append(Trade(i + 1, entry_price, "LONG",
                                        stop_price, target_price))
                    position_open = True
                    i += 1  # B3: entry bar evaluated
                    continue
            elif reg == "DOWN" and closes[i - 1] > ema_f[i - 1] and closes[i] < ema_f[i]:
                entry_price = opens[i + 1]
                risk = STOP_ATR_MULT * atr
                stop_price = entry_price + risk
                if risk > 0 and entry_price < stop_price:  # R3
                    target_price = entry_price - TARGET_R * risk
                    trades.append(Trade(i + 1, entry_price, "SHORT",
                                        stop_price, target_price))
                    position_open = True
                    i += 1
                    continue

        i += 1

    if position_open:
        t = trades[-1]
        t.exit_idx, t.exit_price = n - 1, closes[n - 1]
        t.exit_reason = "EOD"
        t.bars_held = t.exit_idx - t.entry_idx
        if t.side == "SHORT":
            gross = (t.entry_price - t.exit_price) / PIP
        else:
            gross = (t.exit_price - t.entry_price) / PIP
        t.gross_pips = gross
        t.pips = gross - FRICTION_PIPS

    return trades


def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "exits": {},
                "gross_pf": 0, "gross_wr": 0, "gross_expectancy": 0,
                "net_pf": 0, "net_expectancy": 0}

    net_list = [t.pips for t in trades]
    wins = [p for p in net_list if p > 0]
    net_profit = sum(p for p in net_list if p > 0)
    net_loss = -sum(p for p in net_list if p <= 0)
    net_pf = net_profit / net_loss if net_loss > 0 else float("inf")
    net_expectancy = sum(net_list) / len(trades)

    gross_list = [t.gross_pips for t in trades if t.gross_pips is not None]
    gross_profit = sum(g for g in gross_list if g > 0)
    gross_loss = sum(abs(g) for g in gross_list if g <= 0)
    gross_pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    gross_wr = sum(1 for g in gross_list if g > 0) / len(gross_list) if gross_list else 0
    gross_expectancy = sum(gross_list) / len(gross_list) if gross_list else 0

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
        "profit_factor": net_pf,
        "expectancy_pips": net_expectancy,
        "max_dd_pips": max_dd, "exits": exits,
        "gross_pf": gross_pf, "gross_wr": gross_wr,
        "gross_expectancy": gross_expectancy,
        "net_pf": net_pf, "net_expectancy": net_expectancy,
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
        return "KILL", f"WR {metrics['win_rate']:.2%} < 45%"
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

    verdict = gate1_audit(os.path.join("research", "data", "data_audit.log"),
                          args.raw_dir, args.dataset)
    if verdict == "REJECT":
        print("Gate 1 REJECT: data failed validation")
        return 1

    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start = datetime.strptime("2021-01-01", "%Y-%m-%d")
        end = datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start = datetime.strptime("2024-01-01", "%Y-%m-%d")
        end = datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.2%}  "
          f"net PF={metrics['profit_factor']:.4f}  gross PF={metrics['gross_pf']:.4f}  "
          f"Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"  exits: {metrics['exits']}")
    print(f"\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
