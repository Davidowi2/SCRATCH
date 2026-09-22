#!/usr/bin/env python3
"""
research/backtest/S014_funding_fade.py — S-014 FRMR (Funding Rate Mean Reversion) Kernel.

Per factory/preregistrations/S014_funding_fade.md (owner-approved, Phase 3B).

Mean-revert the funding rate:
  F >= +0.05% → SHORT (collect funding credit)
  F <= -0.05% → LONG  (collect funding credit)

Entry at first 5m bar after settlement, hold exactly one 8h interval,
exit at next settlement open. No management, no early exit.

PnL decompositions: price_only, price_plus_funding, net (after taker fees).
Reports short-arm and long-arm separately.
"""

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data_crypto import gate1_audit_crypto

EXPERIMENT_ID = "S-014"
STRATEGY_FAMILY = "FRMR"
PARAM_DESC = "Funding Rate Mean Reversion: fade F>=+0.05% (SHORT) and F<=-0.05% (LONG), fixed 8h horizon"

THRESHOLD = 0.0005  # 0.05%
TAKER_FEE = 0.0005  # per leg (0.05%)
HORIZON_HOURS = 8


class Trade:
    def __init__(self, entry_time, exit_time_target, side, entry_price, exit_price, funding_rate):
        self.entry_time = entry_time
        self.exit_time_target = exit_time_target
        self.side = side
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.funding_rate = funding_rate
        self.price_only = 0.0
        self.funding_credit = 0.0
        self.fees = 0.0
        self.net = 0.0
        self.ret = 0.0


def load_funding(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rate = float(row["funding_rate"])
            rows.append({"time": ts, "rate": rate})
    rows.sort(key=lambda r: r["time"])
    return rows


def load_prices(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({
                "time": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    rows.sort(key=lambda r: r["time"])
    return rows


def get_price_at_or_after(prices, target_time):
    """Get the open price of the first bar at or after target_time."""
    for p in prices:
        if p["time"] >= target_time:
            return p["open"], p["time"]
    return None, None


def run_backtest(funding, prices, start, end):
    trades = []
    position_open = False
    current_exit_time = None

    for f in funding:
        ft = f["time"]
        fr = f["rate"]

        if ft < start or ft > end:
            continue

        # If in position, check if this settlement is the exit
        if position_open and current_exit_time and ft >= current_exit_time:
            if trades:
                t = trades[-1]
                exit_price, exit_time = get_price_at_or_after(prices, t.exit_time_target)
                if exit_price is not None:
                    t.exit_price = exit_price
                    # Funding credit uses the rate at the EXIT settlement
                    t.funding_credit = fr * t.entry_price
                    if t.side == "SHORT":
                        t.price_only = t.entry_price - exit_price
                    else:
                        t.price_only = exit_price - t.entry_price
                    t.net = t.price_only + t.funding_credit - t.fees
                    t.ret = t.net / t.entry_price
            position_open = False
            current_exit_time = None

        # If not in position, check for trigger
        if not position_open:
            if fr >= THRESHOLD:
                side = "SHORT"
            elif fr <= -THRESHOLD:
                side = "LONG"
            else:
                continue

            entry_price, entry_time = get_price_at_or_after(prices, ft)
            if entry_price is None:
                continue

            exit_time_target = ft + timedelta(hours=HORIZON_HOURS)
            exit_price, _ = get_price_at_or_after(prices, exit_time_target)
            if exit_price is None:
                continue

            t = Trade(entry_time, exit_time_target, side, entry_price, exit_price, fr)
            t.fees = 2 * TAKER_FEE * entry_price
            # Initial estimate (will be updated at exit with actual funding rate)
            t.funding_credit = fr * entry_price
            if side == "SHORT":
                t.price_only = entry_price - exit_price
            else:
                t.price_only = exit_price - entry_price
            t.net = t.price_only + t.funding_credit - t.fees
            t.ret = t.net / entry_price

            trades.append(t)
            position_open = True
            current_exit_time = exit_time_target

    return trades


def compute_metrics(trades, key="net"):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy": 0, "avg_ret": 0}

    if key == "price_only":
        pnls = [t.price_only for t in trades]
    elif key == "price_plus_funding":
        pnls = [t.price_only + t.funding_credit for t in trades]
    else:
        pnls = [t.net for t in trades]

    wins = [p for p in pnls if p > 0]
    profit = sum(p for p in pnls if p > 0)
    loss = -sum(p for p in pnls if p <= 0)
    pf = profit / loss if loss > 0 else float("inf")

    returns = [p / t.entry_price for p, t in zip(pnls, trades)]
    avg_ret = sum(returns) / len(returns)

    return {
        "n": len(trades),
        "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "profit_factor": pf,
        "expectancy": sum(pnls) / len(trades),
        "avg_ret": avg_ret,
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
    parser.add_argument("--funding", required=True)
    parser.add_argument("--prices", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    rep = gate1_audit_crypto(args.prices, verbose=False)
    if rep["verdict"] == "REJECT":
        print("Gate 1 CRYPTO REJECT: price data failed validation")
        return 1
    print(f"Gate 1 CRYPTO (prices): {rep['verdict']}")

    funding = load_funding(args.funding)
    prices = load_prices(args.prices)

    if args.phase == "insample":
        start = datetime(2021, 1, 1, tzinfo=timezone.utc)
        end = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    else:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc)

    trades = run_backtest(funding, prices, start, end)

    short_trades = [t for t in trades if t.side == "SHORT"]
    long_trades = [t for t in trades if t.side == "LONG"]

    print(f"\n{'='*72}")
    print(f"S-014 FRMR — {args.phase.upper()}")
    print(f"{'='*72}")
    print(f"Total trades: {len(trades)} (SHORT: {len(short_trades)}, LONG: {len(long_trades)})")
    print(f"Threshold: ±{THRESHOLD*100}%  |  Taker fee: {TAKER_FEE*100}%/leg  |  Horizon: {HORIZON_HOURS}h")

    # Three decompositions
    print(f"\n{'='*72}")
    print(f"THREE-DECOMPOSITION TABLE")
    print(f"{'='*72}")
    print(f"{'Arm':<12} | {'n':>4} | {'WR':>7} | {'PF':>8} | {'Exp($)':>10} | {'Ret%':>8}")
    print("-" * 65)

    for label, subset in [("SHORT", short_trades), ("LONG", long_trades), ("TOTAL", trades)]:
        if not subset:
            continue
        for key, name in [("price_only", "price"), ("price_plus_funding", "price+fund"), ("net", "net")]:
            m = compute_metrics(subset, key)
            pf_str = f"{m['profit_factor']:.4f}" if m['profit_factor'] != float('inf') else "inf"
            print(f"{label:<12} | {m['n']:>4} | {m['win_rate']:>6.1%} | {pf_str:>8} | {m['expectancy']:>+10.2f} | {m['avg_ret']*100:>+7.3f}%")
        print()

    # Short arm verdict
    print(f"\n{'='*72}")
    print(f"SHORT ARM VERDICT (primary test, F >= +{THRESHOLD*100}%)")
    print(f"{'='*72}")
    sm = compute_metrics(short_trades, "net")
    verdict, note = decide(sm)
    cause = classify_cause({
        "gross_pf": compute_metrics(short_trades, "price_plus_funding")["profit_factor"],
        "gross_wr": compute_metrics(short_trades, "price_plus_funding")["win_rate"],
        "gross_exp": compute_metrics(short_trades, "price_plus_funding")["expectancy"],
    })
    print(f"n={sm['n']}  WR={sm['win_rate']:.2%}  net PF={sm['profit_factor']:.4f}")
    print(f"price_only PF={compute_metrics(short_trades, 'price_only')['profit_factor']:.4f}")
    print(f"price+fund PF={compute_metrics(short_trades, 'price_plus_funding')['profit_factor']:.4f}")
    print(f"VERDICT: {verdict} — {note}")
    print(f"Autopsy: {cause}")

    # Long arm
    print(f"\n{'='*72}")
    print(f"LONG ARM (pre-flagged INSUFFICIENT, F <= -{THRESHOLD*100}%)")
    print(f"{'='*72}")
    lm = compute_metrics(long_trades, "net")
    long_verdict, long_note = decide(lm)
    long_cause = classify_cause({
        "gross_pf": compute_metrics(long_trades, "price_plus_funding")["profit_factor"],
        "gross_wr": compute_metrics(long_trades, "price_plus_funding")["win_rate"],
        "gross_exp": compute_metrics(long_trades, "price_plus_funding")["expectancy"],
    })
    print(f"n={lm['n']}  WR={lm['win_rate']:.2%}  net PF={lm['profit_factor']:.4f}")
    print(f"VERDICT: {long_verdict} — {long_note}")
    print(f"Autopsy: {long_cause}")

    # Hash
    result_doc = {
        "kernel_id": "S-014",
        "phase": args.phase,
        "short_n": sm['n'],
        "short_net_pf": sm['profit_factor'],
        "short_gross_pf": compute_metrics(short_trades, "price_plus_funding")["profit_factor"],
        "long_n": lm['n'],
        "long_net_pf": lm['profit_factor'],
        "verdict": verdict,
        "autopsy": cause,
    }
    v_hash = hashlib.sha256(json.dumps(result_doc, sort_keys=True).encode()).hexdigest()
    print(f"\nverdict_hash: {v_hash}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
