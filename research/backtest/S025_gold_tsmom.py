#!/usr/bin/env python3
"""
research/backtest/S025_gold_tsmom.py — S-025 Gold Time-Series Momentum.

THESIS: Gold has long-term upward drift. TSMOM catches trends early:
  Signal = Close(t) > Close(t - Lookback) → LONG (else CASH).
  Hold 20 days, then re-evaluate.

Holdout (2010-2015): select best Lookback in {60, 120, 250} by Sharpe.
IS (2016-2020): apply locked Lookback.

Per factory/preregistrations/S025_gold_tsmom.md.
"""

import csv
import hashlib
import math
import os
import sys
from datetime import datetime, timezone, date, timedelta
import statistics

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXPERIMENT_ID = "S-025"
STRATEGY_FAMILY = "GOLD_TSMOM"
PARAM_DESC = "close_vs_close_lookback_long_or_cash_rebalancing_20d_fee_0.05pct"

LOOKBACKS = [60, 120, 250]
HOLD_DAYS = 20
FEE = 0.0005  # 0.05% round trip

HOLDOUT_START = date(2010, 1, 1)
HOLDOUT_END = date(2015, 12, 31)
IS_START = date(2016, 1, 1)
IS_END = date(2020, 12, 31)
OOS_START = date(2021, 1, 1)
OOS_END = date(2025, 5, 13)


def load_daily(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("close") or row["close"] in ("", "null", "None"):
                continue
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({"date": ts.date(), "open": float(row["open"]), "close": float(row["close"])})
    return sorted(rows, key=lambda r: r["date"])


def run_tsmom(data, lookback, start, end):
    """Run TSMOM with given lookback. Long if Close > Close[lookback] ago, else cash.
    Rebalance every HOLD_DAYS. Entry at open, exit at open (or close of last day)."""
    filtered = [r for r in data if start <= r["date"] <= end]
    filtered.sort(key=lambda r: r["date"])

    trades = []
    i = 0
    while i < len(filtered):
        # Need at least `lookback` bars of history before we can compute signal
        if i < lookback:
            i += 1
            continue

        signal_date = filtered[i]["date"]
        signal_close = filtered[i]["close"]
        ref_close = filtered[i - lookback]["close"]

        if signal_close > ref_close:
            direction = "LONG"
        else:
            direction = "CASH"

        # Hold for HOLD_DAYS
        entry_bar = filtered[i + 1] if i + 1 < len(filtered) else None
        if entry_bar is None:
            break

        hold_entry = entry_bar["open"]
        exit_idx = i + 1 + HOLD_DAYS
        if exit_idx >= len(filtered):
            exit_idx = len(filtered) - 1
        hold_exit = filtered[exit_idx]["close"]

        if direction == "LONG":
            gross_ret = (hold_exit - hold_entry) / hold_entry
            net_ret = gross_ret - FEE
        else:
            net_ret = -FEE  # cash position earns nothing, just pay fee

        trades.append({
            "entry_date": entry_bar["date"],
            "exit_date": filtered[exit_idx]["date"],
            "direction": direction,
            "entry": hold_entry,
            "exit": hold_exit,
            "gross_ret": gross_ret if direction == "LONG" else 0.0,
            "net_ret": net_ret,
        })

        i = exit_idx + 1

    return trades


def compute_metrics(trades):
    n = len(trades)
    if n == 0:
        return {}
    rets = [t["net_ret"] for t in trades]
    long_trades = [t for t in trades if t["direction"] == "LONG"]
    cash_trades = [t for t in trades if t["direction"] == "CASH"]

    mean_ret = statistics.mean(rets)
    std_ret = statistics.stdev(rets) if n > 1 else 0
    sharpe = (mean_ret / std_ret) * math.sqrt(252 / HOLD_DAYS) if std_ret > 0 else 0

    # CAGR
    total = 1.0
    for r in rets:
        total *= (1 + r)
    total_ret = total - 1
    years = n * HOLD_DAYS / 252
    cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 and total_ret > -1 else 0

    # Max DD on cumulative equity curve
    cum = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in rets:
        cum *= (1 + r)
        peak = max(peak, cum)
        if peak > 0:
            max_dd = min(max_dd, (cum - peak) / peak)

    win_rate = sum(1 for r in rets if r > 0) / n * 100

    # PF
    wins = sum(r for r in rets if r > 0)
    losses = abs(sum(r for r in rets if r < 0))
    pf = wins / losses if losses > 0 else float("inf")

    return {
        "n": n,
        "n_long": len(long_trades),
        "n_cash": len(cash_trades),
        "total_ret": total_ret,
        "cagr": cagr * 100,
        "mean_ret": mean_ret * 100,
        "std": std_ret * 100,
        "sharpe": sharpe,
        "max_dd": max_dd * 100,
        "wr": win_rate,
        "pf": pf,
        "rets": rets,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--phase", choices=["holdout", "insample"], default="holdout")
    args = parser.parse_args()

    data = load_daily(args.data)
    print(f"GLD: {len(data)} bars | Range: {data[0]['date']} .. {data[-1]['date']}")

    if args.phase == "holdout":
        start, end = HOLDOUT_START, HOLDOUT_END
        phase_label = "HOLDOUT (2010-2015)"
    else:
        start, end = IS_START, IS_END
        phase_label = "INSAMPLE (2016-2020)"

    if args.phase == "holdout":
        # Grid search
        print(f"\n{'='*72}")
        print(f"S-025 HOLDOUT GRID — LOOKBACK SELECTION")
        print(f"{'='*72}")
        print(f"{'Lookback':<10} | {'n_trades':>9} | {'CAGR':>7} | {'Sharpe':>7} | {'MaxDD':>7} | {'WR':>6}")
        print("-" * 60)

        results = {}
        for lb in LOOKBACKS:
            trades = run_tsmom(data, lb, start, end)
            m = compute_metrics(trades)
            results[lb] = m
            print(f"{lb:>8}d | {m['n']:>9} | {m['cagr']:>+6.2f}% | {m['sharpe']:+6.2f} | {m['max_dd']:>+6.2f}% | {m['wr']:>5.1f}%")

        # Select by Sharpe
        best_lb = max(results.keys(), key=lambda k: results[k]["sharpe"])
        best_sharpe = results[best_lb]["sharpe"]

        print(f"\nSelected: Lookback={best_lb}d, Sharpe={best_sharpe:.4f}")
        if best_sharpe < 0.3:
            print("VERDICT: NON-VIABLE (Sharpe < 0.3)")
        else:
            print("VERDICT: Viable — proceed to IS")

        return 0

    else:
        # IS test with LOCKED lookback
        # First determine the locked lookback from holdout
        holdout_results = {}
        for lb in LOOKBACKS:
            trades = run_tsmom(data, lb, HOLDOUT_START, HOLDOUT_END)
            m = compute_metrics(trades)
            holdout_results[lb] = m

        best_lb = max(holdout_results.keys(), key=lambda k: holdout_results[k]["sharpe"])
        best_sharpe = holdout_results[best_lb]["sharpe"]

        print(f"\nLocked lookback from holdout: {best_lb}d (Sharpe={best_sharpe:.4f})")

        if best_sharpe < 0.3:
            print("Holdout NON-VIABLE — not running IS")
            return 1

        print(f"\n{'='*72}")
        print(f"S-025 INSAMPLE (lookback={best_lb}d, {phase_label})")
        print(f"{'='*72}")

        trades = run_tsmom(data, best_lb, IS_START, IS_END)
        m = compute_metrics(trades)

        print(f"\nTHREE-DECOMPOSITION (per-trade):")
        print(f"  {'Decomp':<16} | {'total':>10} | {'mean/trade':>12}")
        print(f"  {'-'*45}")
        gross_total = sum(t["gross_ret"] for t in trades)
        fees_total = len(trades) * FEE
        net_total = sum(t["net_ret"] for t in trades)
        print(f"  {'gross':<16} | {gross_total:>+9.4f} | {gross_total/len(trades):>+11.6f}")
        print(f"  {'minus_fees':<16} | {fees_total:>+9.4f} | {fees_total/len(trades):>+11.6f}")
        print(f"  {'net':<16} | {net_total:>+9.4f} | {net_total/len(trades):>+11.6f}")

        print(f"\nSUMMARY:")
        print(f"  n_trades:         {m['n']} (LONG: {m['n_long']}, CASH: {m['n_cash']})")
        print(f"  mean net return:  {m['mean_ret']:.4f}%")
        print(f"  CAGR:             {m['cagr']:.2f}%")
        print(f"  Sharpe:           {m['sharpe']:.4f}")
        print(f"  Max DD:           {m['max_dd']:.4f}%")
        print(f"  Win rate:         {m['wr']:.1f}%")
        print(f"  Net PF:           {m['pf']:.4f}")

        # Per-year
        print(f"\nPER-YEAR (net trades):")
        print(f"  {'Year':<8} | {'n':>4} | {'CAGR%':>7} | {'WR':>6} | {'Sharpe':>7}")
        print(f"  {'-'*45}")
        by_year = {}
        for t in trades:
            y = t["entry_date"].year
            if y not in by_year:
                by_year[y] = []
            by_year[y].append(t)
        for y in sorted(by_year.keys()):
            yr_trades = by_year[y]
            yr_rets = [t["net_ret"] for t in yr_trades]
            yr_total = 1.0
            for r in yr_rets: yr_total *= (1 + r)
            yr_cagr = ((yr_total - 1) + 1) ** (252 / (len(yr_rets) * HOLD_DAYS)) - 1
            yr_wr = sum(1 for r in yr_rets if r > 0) / len(yr_rets) * 100
            yr_std = statistics.stdev(yr_rets) if len(yr_rets) > 1 else 0
            yr_sharpe = (statistics.mean(yr_rets)/yr_std)*math.sqrt(252/HOLD_DAYS) if yr_std > 0 else 0
            print(f"  {y:<8} | {len(yr_trades):>4} | {yr_cagr*100:>+6.2f}% | {yr_wr:>5.1f}% | {yr_sharpe:>+6.2f}")

        # Survive criteria
        print(f"\nSURVIVE CRITERIA:")
        print(f"  Sharpe > 0.5?    {m['sharpe'] > 0.5} ({m['sharpe']:.4f})")
        print(f"  CAGR > 4%?       {m['cagr'] > 4} ({m['cagr']:.2f}%)")
        print(f"  MaxDD < -20%?    {'✓' if m['max_dd'] > -20 else '✗'} ({m['max_dd']:.2f}%)")

        all_pass = m["sharpe"] > 0.5 and m["cagr"] > 4 and m["max_dd"] > -20
        if all_pass:
            print(f"\n  VERDICT: SURVIVE — hold for OOS")
        else:
            print(f"\n  VERDICT: KILL")

    return 0


if __name__ == "__main__":
    sys.exit(main())
