"""
research/backtest/S013_veed_fade.py — S-013 VEED Fade Kernel (BTCUSDT 5m)

Per factory/preregistrations/S013_veed_fade.md (owner-approved, Phase 2B).

Fades VEED v1.1 events: sell-side event → LONG, buy-side event → SHORT.
Entry at next-bar open, stop at event-bar extreme, target 1.5R.
Taker fees (0.04%/leg) + funding (0.01%/8h) applied at exit.
R1/R3 fill conventions. Max hold 72 bars. One position.

Frozen params from VEED v1.1 (sha 48001ab8):
  X=0.01, Y=0.25, N=4032, ref_complete>=0.99
"""

import csv
import math
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data_crypto import gate1_audit_crypto
from detectors.veed_v11_detector import load_bars, quantile, VEED_X, VEED_Y, VEED_N, REF_COMPLETE_MIN

EXPERIMENT_ID = "S-013"
STRATEGY_FAMILY = "VEED-FADE"
PARAM_DESC = "Fade VEED v1.1 events (sell→LONG, buy→SHORT), stop at event extreme, 1.5R"

TAKER_FEE = 0.0004        # per leg (0.04%)
FUNDING_RATE = 0.0001     # per 8h settlement (0.01%)
MAX_HOLD = 72             # bars (12h)
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
        self.gross_points = None
        self.pips = None
        self.funding_charged = 0
        self.taker_fee_paid = 0


def detect_events(bars):
    """Re-implement VEED v1.1 detection inline (deterministic, no import drift).
    Returns list of (event_idx, side, trades_val, closepos_val)."""
    n = len(bars)
    events = []
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    trades = [b["trades"] for b in bars]
    times = [b["time"] for b in bars]
    rngs = [highs[i] - lows[i] for i in range(n)]
    closepos = [(closes[i] - lows[i]) / rngs[i] if rngs[i] > 0 else None
                for i in range(n)]
    logtrades = [math.log(trades[i] + 1) if trades[i] >= 0 else None
                 for i in range(n)]

    for i in range(VEED_N, n):
        if rngs[i] <= 0 or trades[i] <= 0 or closepos[i] is None:
            continue
        cutoff = times[i] - timedelta(days=14)
        ref = []
        for j in range(i - 1, -1, -1):
            if times[j] <= cutoff:
                break
            ref.append(logtrades[j])
        if len(ref) < REF_COMPLETE_MIN * VEED_N:
            continue
        q = quantile(ref, 1.0 - VEED_X)
        if q is None or logtrades[i] <= q:
            continue
        cp = closepos[i]
        if cp <= VEED_Y:
            events.append((i, "sell", trades[i], cp))
        elif cp >= 1.0 - VEED_Y:
            events.append((i, "buy", trades[i], cp))
    return events


def compute_funding(entry_price, bars_held):
    """Funding charged at each 8h settlement crossing.
    Binance settles at 00:00, 08:00, 16:00 UTC."""
    # every 48 bars (8h) of holding, charge FUNDING_RATE * notional
    settlements = bars_held // 48
    return settlements * FUNDING_RATE * entry_price


def run_backtest(bars):
    n = len(bars)
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    events = detect_events(bars)

    trades_list = []
    position_open = False
    ei = 0  # event index

    for i in range(n):
        if position_open:
            t = trades_list[-1]
            j = i
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
                elif highs[j] >= t.target:
                    t.exit_idx, t.exit_price = j, t.target
                    t.exit_reason = "TARGET"
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
                elif lows[j] <= t.target:
                    t.exit_idx, t.exit_price = j, t.target
                    t.exit_reason = "TARGET"
                    exited = True

            if not exited and (j - t.entry_idx) >= MAX_HOLD:
                t.exit_idx, t.exit_price = j, closes[j]
                t.exit_reason = "MAXHOLD"
                exited = True

            if exited:
                position_open = False
                t.bars_held = t.exit_idx - t.entry_idx
                if t.side == "LONG":
                    t.gross_points = t.exit_price - t.stop
                    gross_pips = (t.exit_price - t.entry_price)
                else:
                    t.gross_points = t.stop - t.exit_price
                    gross_pips = (t.entry_price - t.exit_price)
                # friction
                t.funding_charged = compute_funding(t.entry_price, t.bars_held)
                t.taker_fee_paid = 2 * TAKER_FEE * t.entry_price
                t.pips = gross_pips - t.taker_fee_paid - t.funding_charged
                continue

        # look for signal (if no position)
        if not position_open and ei < len(events):
            ev_idx, side, _, _ = events[ei]
            if ev_idx == i:  # event fires at this bar → enter next bar
                if i + 1 < n:
                    entry_price = opens[i + 1]
                    if side == "sell":
                        # LONG: fade dump
                        stop_price = lows[i]
                        risk = entry_price - stop_price
                        if risk > 0:  # R3
                            target_price = entry_price + TARGET_R * risk
                            trades_list.append(Trade(i + 1, entry_price, "LONG",
                                                    stop_price, target_price))
                            position_open = True
                    else:
                        # SHORT: fade rally
                        stop_price = highs[i]
                        risk = stop_price - entry_price
                        if risk > 0:  # R3
                            target_price = entry_price - TARGET_R * risk
                            trades_list.append(Trade(i + 1, entry_price, "SHORT",
                                                    stop_price, target_price))
                            position_open = True
                ei += 1
            elif ev_idx < i:
                ei += 1

    # close any open position at end of data
    if position_open:
        t = trades_list[-1]
        t.exit_idx, t.exit_price = n - 1, closes[n - 1]
        t.exit_reason = "EOD"
        t.bars_held = t.exit_idx - t.entry_idx
        if t.side == "LONG":
            gross_pips = t.exit_price - t.entry_price
        else:
            gross_pips = t.entry_price - t.exit_price
        t.funding_charged = compute_funding(t.entry_price, t.bars_held)
        t.taker_fee_paid = 2 * TAKER_FEE * t.entry_price
        t.pips = gross_pips - t.taker_fee_paid - t.funding_charged

    return trades_list


def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "exits": {},
                "gross_pf": 0, "gross_wr": 0, "gross_expectancy": 0,
                "avg_funding": 0, "avg_taker": 0}

    net_list = [t.pips for t in trades]
    wins = [p for p in net_list if p > 0]
    net_profit = sum(p for p in net_list if p > 0)
    net_loss = -sum(p for p in net_list if p <= 0)
    net_pf = net_profit / net_loss if net_loss > 0 else float("inf")

    # gross (friction = 0)
    gross_list = []
    for t in trades:
        if t.side == "LONG":
            gross_list.append(t.exit_price - t.entry_price)
        else:
            gross_list.append(t.entry_price - t.exit_price)
    gross_profit = sum(g for g in gross_list if g > 0)
    gross_loss = sum(abs(g) for g in gross_list if g <= 0)
    gross_pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    gross_wr = sum(1 for g in gross_list if g > 0) / len(gross_list)
    gross_exp = sum(gross_list) / len(gross_list)

    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1

    avg_fund = sum(t.funding_charged for t in trades) / len(trades)
    avg_taker = sum(t.taker_fee_paid for t in trades) / len(trades)

    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "profit_factor": net_pf,
        "expectancy_pips": sum(net_list) / len(trades),
        "gross_pf": gross_pf, "gross_wr": gross_wr,
        "gross_expectancy": gross_exp,
        "avg_funding": avg_fund, "avg_taker": avg_taker,
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
    ge = metrics.get("gross_expectancy", 0)
    if gp != float("inf") and gp >= 1.15 and gw >= 0.45 and ge > 0:
        return "TUNING-SHORT"
    return "MECHANISM-DEAD"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    # Gate 1 (crypto branch — 24/7 jurisdiction)
    rep = gate1_audit_crypto(args.dataset, verbose=False)
    if rep["verdict"] == "REJECT":
        print("Gate 1 CRYPTO REJECT: data failed validation")
        for f in rep["fatal"]:
            print(f"  ✗ {f}")
        return 1
    print(f"Gate 1 CRYPTO: {rep['verdict']} "
          f"(completeness={rep['stats'].get('completeness')}, "
          f"n_bars={rep['stats'].get('n_bars')})")

    bars = load_bars(args.dataset)
    if args.phase == "insample":
        start = datetime.strptime("2021-01-01", "%Y-%m-%d")
        end = datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start = datetime.strptime("2024-01-01", "%Y-%m-%d")
        end = datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23, minute=59, second=59)]

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics)
    cause = classify_cause(metrics)

    print(f"\nWindow: {args.phase}  bars={len(bars)}")
    print(f"Trades: {metrics['n']}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.2%}")
    print(f"  net PF={metrics['profit_factor']:.4f}  "
          f"gross PF={metrics['gross_pf']:.4f}  gross WR={metrics['gross_wr']:.2%}")
    print(f"  net Exp={metrics['expectancy_pips']:+.2f}  "
          f"gross Exp={metrics['gross_expectancy']:+.2f}")
    print(f"  avg taker fee={metrics['avg_taker']:.4f}  "
          f"avg funding={metrics['avg_funding']:.4f}")
    print(f"  exits: {metrics['exits']}")
    print(f"\nVERDICT: {verdict} — {note}")
    print(f"Autopsy: {cause}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
