#!/usr/bin/env python3
"""
research/backtest/S017_tom_btc.py — S-017 Turn-of-Month Anomaly (BTC).

Per factory/preregistrations/S017_tom_btc.md (Phase 2 IS run).
(Window N,M)=(3,3) LOCKED from holdout — do NOT re-select.

Entry: open of first window day. Exit: close of last window day.
Hold ~6 days. One position per month boundary.
Direction: LONG only (per prereg).

PnL three-decomposition: price_only | price_plus_funding | net.
Funding model: long pays funding rate * notional over the 6-day hold
(approximate as sum of realized 8h funding rates during hold).

Fees: 0.05% taker each side (0.10% round trip).
"""

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
from research.data.validate_data_crypto import gate1_audit_crypto

N_DAYS = 3  # last N days of month
M_DAYS = 3  # first M days of next month
HOLD_DAYS = N_DAYS + M_DAYS  # 6
TAKER_FEE = 0.0005  # per leg
ROUND_TRIP_FEE = 2 * TAKER_FEE  # 0.10%

# IS window
IS_START = datetime(2021, 1, 1, tzinfo=timezone.utc)
IS_END = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


class Trade:
    def __init__(self, entry_time, exit_time, entry_price, exit_price, year):
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.year = year
        self.funding_rate = 0.0
        self.price_only = 0.0
        self.funding_credit = 0.0
        self.fees = 0.0
        self.net = 0.0
        self.ret = 0.0


def load_prices(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({
                "time": ts,
                "date": ts.date(),
                "year": ts.year,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    rows.sort(key=lambda r: r["time"])
    return rows


def load_funding(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({"time": ts, "rate": float(row["funding_rate"])})
    rows.sort(key=lambda r: r["time"])
    return rows


def identify_tom_windows(daily, n_days, m_days, start, end):
    """Identify TOM windows in the daily data."""
    months = {}
    for d in daily:
        ym = (d["date"].year, d["date"].month)
        if ym not in months:
            months[ym] = []
        months[ym].append(d)

    windows = []
    for ym in sorted(months.keys()):
        month_days = months[ym]
        last_n = month_days[-n_days:] if len(month_days) >= n_days else month_days

        if ym[1] == 12:
            next_ym = (ym[0] + 1, 1)
        else:
            next_ym = (ym[0], ym[1] + 1)

        if next_ym not in months:
            continue
        next_days = months[next_ym]
        first_m = next_days[:m_days] if len(next_days) >= m_days else next_days

        if not last_n or not first_m:
            continue

        window_days = last_n + first_m
        entry_day = window_days[0]
        exit_day = window_days[-1]

        if entry_day["time"] < start or exit_day["time"] > end:
            continue

        windows.append({
            "entry": entry_day,
            "exit": exit_day,
            "window_days": window_days,
            "year": entry_day["year"],
        })

    return windows


def get_funding_during_hold(funding, hold_start, hold_end):
    """Sum funding rates that settle during the hold window."""
    total = 0.0
    for f in funding:
        if hold_start <= f["time"] <= hold_end:
            total += f["rate"]
    return total


def bootstrap_ci(pnls, n_boot=10000, conf=0.90):
    """Bootstrap 90% CI lower bound for the mean."""
    import random
    if not pnls:
        return 0.0, 0.0
    random.seed(42)
    means = []
    for _ in range(n_boot):
        sample = [random.choice(pnls) for _ in pnls]
        means.append(sum(sample) / len(sample))
    means.sort()
    lower_idx = int((1 - conf) / 2 * n_boot)
    upper_idx = int((1 + conf) / 2 * n_boot)
    return means[lower_idx], means[upper_idx]


def compute_metrics(trades, key="net"):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy": 0, "avg_ret": 0, "mean": 0}

    pnls = []
    for t in trades:
        if key == "price_only":
            pnls.append(t.exit_price - t.entry_price)
        elif key == "price_plus_funding":
            pnls.append(t.exit_price - t.entry_price + t.funding_credit)
        else:
            pnls.append(t.net)

    wins = [p for p in pnls if p > 0]
    profit = sum(wins)
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
        "mean": sum(returns) / len(trades),
    }


def run_backtest(daily, funding, start, end):
    trades = []
    windows = identify_tom_windows(daily, N_DAYS, M_DAYS, start, end)

    for w in windows:
        entry = w["entry"]
        exit_day = w["exit"]
        hold_start = entry["time"]
        hold_end = exit_day["time"]

        t = Trade(entry["time"], exit_day["time"], entry["open"], exit_day["close"], w["year"])

        fund_rate = get_funding_during_hold(funding, hold_start, hold_end)
        t.funding_rate = fund_rate
        # LONG pays funding when rate positive
        t.funding_credit = -fund_rate * entry["open"]
        t.fees = ROUND_TRIP_FEE * entry["open"]

        t.price_only = t.exit_price - t.entry_price
        t.net = t.price_only + t.funding_credit - t.fees
        t.ret = t.net / t.entry_price

        trades.append(t)

    return trades, windows


def decide_survive(metrics, trades):
    n = metrics["n"]
    pf = metrics["profit_factor"]

    if n < 50:
        return "INSUFFICIENT", f"n={n} < 50"
    if pf == float("inf"):
        return "SUSPICIOUS", "zero losses"
    if pf < 1.0:
        return "KILL", f"PF {pf:.4f} < 1.0"

    pnls = [t.ret for t in trades]
    ci_lower, ci_upper = bootstrap_ci(pnls, n_boot=10000, conf=0.90)

    if ci_lower >= 1.0 and metrics["mean"] > 0:
        return "SURVIVE", f"net PF {pf:.4f} >= 1.0, CI90 [{ci_lower:.4f}, {ci_upper:.4f}], mean {metrics['mean']:.4f}"
    elif ci_lower < 1.0 and pf >= 1.0:
        return "INCONCLUSIVE", f"PF {pf:.4f} >= 1.0 but CI90 lower {ci_lower:.4f} < 1.0 (small sample)"
    else:
        return "KILL", f"PF {pf:.4f} but mean <= 0 or CI fails"


def make_verdict_hash(batch_id, kernel_id, phase, data_hash, metrics, trades, verdict):
    returns = [t.ret for t in trades]
    doc = {
        "kernel_id": kernel_id,
        "batch_id": batch_id,
        "phase": phase,
        "dataset_hash": data_hash,
        "n": metrics["n"],
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "mean_return": metrics["mean"],
        "verdict": verdict[0],
        "note": verdict[1],
        "returns_hash": hashlib.sha256(json.dumps(returns, sort_keys=True).encode()).hexdigest()[:16],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--funding", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    rep = gate1_audit_crypto(args.prices, interval_minutes=1440, verbose=False)
    if rep["verdict"] == "REJECT":
        print("Gate 1 CRYPTO REJECT: price data failed validation")
        return 1
    print(f"Gate 1 CRYPTO (prices): {rep['verdict']}")

    data_sha = hashlib.sha256(open(args.prices, "rb").read()).hexdigest()
    daily = load_prices(args.prices)
    funding = load_funding(args.funding)

    if args.phase == "insample":
        start = IS_START
        end = IS_END
    else:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc)

    trades, windows = run_backtest(daily, funding, start, end)

    print(f"\n{'='*72}")
    print(f"S-017 TOM BTC — {args.phase.upper()}")
    print(f"{'='*72}")
    print(f"Window: last {N_DAYS} of month + first {M_DAYS} of next (N,M=3,3), LONG")
    print(f"Hold: {HOLD_DAYS} days | Fee: {ROUND_TRIP_FEE*100}% round-trip | Taker fee: {TAKER_FEE*100}%/leg")
    print(f"Trades: {len(trades)}")

    # Three-decomposition
    print(f"\n{'='*72}")
    print("THREE-DECOMPOSITION TABLE")
    print(f"{'='*72}")
    print(f"{'Decomp':<16} | {'n':>4} | {'WR':>7} | {'PF':>8} | {'Exp($)':>10} | {'Ret%':>8}")
    print("-" * 65)

    for key, name in [("price_only", "price_only"), ("price_plus_funding", "price+funding"), ("net", "net")]:
        m = compute_metrics(trades, key)
        pf_str = f"{m['profit_factor']:.4f}" if m['profit_factor'] != float('inf') else "inf"
        print(f"{name:<16} | {m['n']:>4} | {m['win_rate']:>6.1%} | {pf_str:>8} | {m['expectancy']:>+10.2f} | {m['avg_ret']*100:>+7.3f}%")

    # Per-year breakdown
    print(f"\n{'='*72}")
    print("PER-YEAR BREAKDOWN (net)")
    print(f"{'='*72}")
    print(f"{'Year':>4} | {'n':>3} | {'mean_ret%':>10} | {'WR':>7} | {'PF':>8}")
    print("-" * 45)

    for yr in sorted(set(t.year for t in trades)):
        yr_trades = [t for t in trades if t.year == yr]
        m = compute_metrics(yr_trades, "net")
        pf_str = f"{m['profit_factor']:.4f}" if m['profit_factor'] != float('inf') else "inf"
        print(f"{yr:>4} | {m['n']:>3} | {m['avg_ret']*100:>+9.4f}% | {m['win_rate']:>6.1%} | {pf_str:>8}")

    # Baseline comparison
    print(f"\n{'='*72}")
    print("BASELINE COMPARISON (6-day windows)")
    print(f"{'='*72}")

    all_6d_windows = []
    for i in range(len(daily) - HOLD_DAYS + 1):
        entry = daily[i]["open"]
        exit_price = daily[i + HOLD_DAYS - 1]["close"]
        if start <= daily[i]["time"] <= end:
            all_6d_windows.append((exit_price - entry) / entry)

    baseline_mean = sum(all_6d_windows) / len(all_6d_windows) if all_6d_windows else 0
    tom_mean = sum(t.ret for t in trades) / len(trades) if trades else 0
    print(f"TOM windows (n={len(trades)}): mean net return = {tom_mean*100:+.4f}%")
    print(f"Baseline 6-day (n={len(all_6d_windows)}): mean return = {baseline_mean*100:+.4f}%")
    print(f"Excess: {(tom_mean - baseline_mean)*100:+.4f}%")

    # Bootstrap + verdict
    net_returns = [t.ret for t in trades]
    ci_lower, ci_upper = bootstrap_ci(net_returns, n_boot=10000, conf=0.90)

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    net_metrics = compute_metrics(trades, "net")
    verdict, note = decide_survive(net_metrics, trades)
    pf_str = f"{net_metrics['profit_factor']:.4f}" if net_metrics['profit_factor'] != float('inf') else "inf"
    print(f"n={net_metrics['n']}  net PF={pf_str}  mean={net_metrics['mean']:.4f}")
    print(f"Bootstrap 90% CI on mean: [{ci_lower:.4f}, {ci_upper:.4f}]")
    print(f"VERDICT: {verdict} — {note}")

    v_hash = make_verdict_hash("S-017-BATCH-1", "S-017", args.phase, data_sha,
                               net_metrics, trades, (verdict, note))
    print(f"verdict_hash: {v_hash}")
    print(f"data_sha256: {data_sha}")

    # Exit breakdown
    print(f"\n{'='*72}")
    print("EXIT BREAKDOWN")
    print(f"{'='*72}")
    from collections import Counter
    exits = Counter()
    for t in trades:
        if t.net > 0:
            exits["TARGET"] += 1
        elif t.net < 0:
            exits["STOP"] += 1
        else:
            exits["BREAKEVEN"] += 1
    for reason, count in sorted(exits.items()):
        print(f"  {reason}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
