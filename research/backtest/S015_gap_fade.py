#!/usr/bin/env python3
"""
research/backtest/S015_gap_fade.py — S-015 Overnight Gap Fade (EURUSD)

Per factory/preregistrations/S015_gap_fade.md (owner-approved, Phase 3C).

Fade the overnight gap on EURUSD:
  - gap < 0 (open < prev close) → LONG
  - gap > 0 (open > prev close) → SHORT
Entry at daily open, stop at 1× daily ATR(14), target at previous close.
Fixed 1-day horizon. 0.5 pips friction.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "S-015"
STRATEGY_FAMILY = "GAP-FADE"
PARAM_DESC = "Fade overnight gaps: open<prev_close→LONG, open>prev_close→SHORT, ATR stop, target prev close"

PIP = 0.0001
FRICTION_PIPS = 0.5
ATR_PERIOD = 14


class Trade:
    def __init__(self, date, side, entry_price, stop, target):
        self.date = date
        self.side = side
        self.entry_price = entry_price
        self.stop = stop
        self.target = target
        self.exit_price = None
        self.exit_reason = None
        self.pips = None
        self.gross_pips = None


def load_daily_bars(path):
    """Aggregate H1 bars into daily bars."""
    h1_bars = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            h1_bars.append({
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })

    # Group by date
    days = {}
    for b in h1_bars:
        d = b["time"].date()
        if d not in days:
            days[d] = []
        days[d].append(b)

    # Aggregate
    daily = []
    for d in sorted(days.keys()):
        bars = days[d]
        if len(bars) < 24:
            continue  # skip incomplete days
        daily.append({
            "date": d,
            "open": bars[0]["open"],
            "close": bars[-1]["close"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
        })

    return daily


def compute_atr14(daily):
    """Compute ATR(14) with simple mean, consistent with S-001."""
    for i, d in enumerate(daily):
        if i == 0:
            d["atr14"] = d["high"] - d["low"]
            continue
        prev = daily[i - 1]
        tr = max(
            d["high"] - d["low"],
            abs(d["high"] - prev["close"]),
            abs(d["low"] - prev["close"]),
        )
        if i < ATR_PERIOD:
            # average of available TRs
            trs = []
            for j in range(1, i + 1):
                pj = daily[j - 1]
                tr_j = max(
                    daily[j]["high"] - daily[j]["low"],
                    abs(daily[j]["high"] - pj["close"]),
                    abs(daily[j]["low"] - pj["close"]),
                )
                trs.append(tr_j)
            d["atr14"] = sum(trs) / len(trs) if trs else tr
        else:
            trs = []
            for j in range(i - ATR_PERIOD + 1, i + 1):
                pj = daily[j - 1]
                tr_j = max(
                    daily[j]["high"] - daily[j]["low"],
                    abs(daily[j]["high"] - pj["close"]),
                    abs(daily[j]["low"] - pj["close"]),
                )
                trs.append(tr_j)
            d["atr14"] = sum(trs) / ATR_PERIOD
    return daily


def run_backtest(daily, start, end):
    trades = []
    for i, d in enumerate(daily):
        if d["date"] < start or d["date"] > end:
            continue
        if d["atr14"] is None or d["atr14"] <= 0:
            continue

        prev = daily[i - 1] if i > 0 else None
        if prev is None:
            continue

        gap = d["open"] - prev["close"]

        if gap < 0:
            side = "LONG"
        elif gap > 0:
            side = "SHORT"
        else:
            continue

        entry = d["open"]
        atr = d["atr14"]

        if side == "LONG":
            stop = entry - 1.0 * atr
            target = prev["close"]
            if target <= stop:
                continue  # target below stop, skip
        else:
            stop = entry + 1.0 * atr
            target = prev["close"]
            if target >= stop:
                continue

        t = Trade(d["date"], side, entry, stop, target)

        # Evaluate the day using the daily bar's high/low
        if side == "LONG":
            if d["low"] <= stop:
                t.exit_price = stop
                t.exit_reason = "STOP"
            elif d["high"] >= target:
                t.exit_price = target
                t.exit_reason = "TARGET"
            else:
                t.exit_price = d["close"]
                t.exit_reason = "HORIZON"
        else:
            if d["high"] >= stop:
                t.exit_price = stop
                t.exit_reason = "STOP"
            elif d["low"] <= target:
                t.exit_price = target
                t.exit_reason = "TARGET"
            else:
                t.exit_price = d["close"]
                t.exit_reason = "HORIZON"

        if side == "LONG":
            t.gross_pips = (t.exit_price - t.entry_price) / PIP
        else:
            t.gross_pips = (t.entry_price - t.exit_price) / PIP
        t.pips = t.gross_pips - FRICTION_PIPS

        trades.append(t)

    return trades


def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "gross_pf": 0, "gross_exp": 0,
                "exits": {}}

    wins = [t for t in trades if t.pips > 0]
    gross_wins = [t for t in trades if t.gross_pips > 0]
    net_profit = sum(t.pips for t in trades if t.pips > 0)
    net_loss = -sum(t.pips for t in trades if t.pips <= 0)
    gross_profit = sum(t.gross_pips for t in trades if t.gross_pips > 0)
    gross_loss = -sum(t.gross_pips for t in trades if t.gross_pips <= 0)

    pf = net_profit / net_loss if net_loss > 0 else float("inf")
    gross_pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1

    return {
        "n": len(trades),
        "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "profit_factor": pf,
        "gross_pf": gross_pf,
        "expectancy_pips": sum(t.pips for t in trades) / len(trades),
        "gross_exp": sum(t.gross_pips for t in trades) / len(trades),
        "exits": exits,
    }


def decide(metrics):
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


def classify_cause(metrics):
    gp = metrics.get("gross_pf", 0)
    gw = metrics.get("gross_wr", 0)
    ge = metrics.get("gross_exp", 0)
    if gp != float("inf") and gp >= 1.15 and gw >= 0.45 and ge > 0:
        return "TUNING-SHORT"
    return "MECHANISM-DEAD"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    parser.add_argument("--raw-dir", default=None)
    args = parser.parse_args()

    # Gate 1 (FX pipeline)
    gate1_log = os.path.join("research", "data", "data_audit.log")
    raw_dir = args.raw_dir or os.path.join("research", "data", "raw", "EURUSD_H1")
    verdict = gate1_audit(gate1_log, raw_dir, args.dataset)
    if verdict == "REJECT":
        print("Gate 1 REJECT: data failed validation")
        return 1
    print(f"Gate 1: {verdict}")

    daily = load_daily_bars(args.dataset)
    daily = compute_atr14(daily)

    if args.phase == "insample":
        start = datetime.strptime("2021-01-01", "%Y-%m-%d").date()
        end = datetime.strptime("2023-12-31", "%Y-%m-%d").date()
    else:
        start = datetime.strptime("2024-01-01", "%Y-%m-%d").date()
        end = datetime.strptime("2025-05-13", "%Y-%m-%d").date()

    trades = run_backtest(daily, start, end)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics)
    cause = classify_cause(metrics)

    print(f"\n{'='*72}")
    print(f"S-015 GAP FADE — {args.phase.upper()}")
    print(f"{'='*72}")
    print(f"Daily bars used: {len([d for d in daily if start <= d['date'] <= end])}")
    print(f"Trades: {metrics['n']}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.2%}")
    print(f"  net PF={metrics['profit_factor']:.4f}  gross PF={metrics['gross_pf']:.4f}")
    print(f"  net Exp={metrics['expectancy_pips']:+.2f} pips  gross Exp={metrics['gross_exp']:+.2f} pips")
    print(f"  exits: {metrics['exits']}")
    print(f"\nVERDICT: {verdict} — {note}")
    print(f"Autopsy: {cause}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
