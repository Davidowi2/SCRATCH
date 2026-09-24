#!/usr/bin/env python3
"""
research/backtest/S032_qqq_tsmom.py — S-032 QQQ Time-Series Momentum Holdout Pulse.
STATUS: HOLDOUT PULSE ONLY. NO IS. NO OOS. NO TRADE KERNEL.
"""

import csv
import hashlib
import os
import sys
import random
from collections import defaultdict
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "equity")
QQQ_PATH = os.path.join(DATA_DIR, "qqq_daily_2010_2025.csv")
SPY_PATH = os.path.join(DATA_DIR, "spy_daily_2010_2025.csv")

LOOKBACKS = [63, 126, 250]
HOLD_DAYS = 21
FEES = 0.0005
HOLD_START = "2010-01-01"
HOLD_END = "2018-12-31"


def load_prices(path):
    prices = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row["timestamp_utc"][:10]
            prices[date_str] = {
                "date": datetime.strptime(date_str, "%Y-%m-%d").date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
    return prices


def bootstrap_ci_annual(returns, hold_days, n_years, n_bootstrap=2000, ci=0.90):
    random.seed(42)
    if len(returns) < 2:
        return 0, 0
    annualized = []
    for _ in range(n_bootstrap):
        sample = [returns[random.randint(0, len(returns)-1)] for _ in range(len(returns))]
        portfolio = 1.0
        for r in sample:
            portfolio *= (1 + r)
        cagr = portfolio ** (1.0 / n_years) - 1
        annualized.append(cagr)
    annualized.sort()
    alpha = 1 - ci
    lower_idx = int(alpha / 2 * n_bootstrap)
    upper_idx = int((1 - alpha / 2) * n_bootstrap)
    return annualized[lower_idx] * 100, annualized[upper_idx] * 100


def run_tsmom(prices, lookback, start_date, end_date, fees=FEES, vol_target=False):
    sorted_dates = sorted([d for d in prices if start_date <= d <= end_date])
    sorted_dates_set = set(sorted_dates)

    # Calculate trailing returns
    trailing = {}
    for i in range(lookback, len(sorted_dates)):
        ref_idx = i - lookback
        ref_close = prices[sorted_dates[ref_idx]]["close"]
        cur_close = prices[sorted_dates[i]]["close"]
        if ref_close > 0:
            trailing[sorted_dates[i]] = (cur_close - ref_close) / ref_close

    # Find rebalance dates (month-end)
    rebalance_dates = []
    for i, d in enumerate(sorted_dates):
        d_date = datetime.strptime(d, "%Y-%m-%d").date()
        if i < len(sorted_dates) - 1:
            next_d = datetime.strptime(sorted_dates[i + 1], "%Y-%m-%d").date()
            if next_d.month != d_date.month or next_d.year != d_date.year:
                rebalance_dates.append(d)
        else:
            rebalance_dates.append(d)

    trades = []
    portfolio = 1.0
    equity_curve = [portfolio]
    total_fees = 0
    long_only = False

    for rdate in rebalance_dates:
        if rdate not in trailing:
            continue

        signal = trailing[rdate]
        rdate_idx = sorted_dates.index(rdate)

        # Entry at open of T+1
        entry_idx = min(rdate_idx + 1, len(sorted_dates) - 1)
        exit_idx = min(rdate_idx + HOLD_DAYS, len(sorted_dates) - 1)
        if entry_idx >= len(sorted_dates) or exit_idx >= len(sorted_dates):
            continue
        entry_date = sorted_dates[entry_idx]
        exit_date = sorted_dates[exit_idx]

        entry_price = prices[entry_date]["open"]
        exit_price = prices[exit_date]["close"]

        if entry_price <= 0:
            continue

        if signal > 0:
            # Long
            if vol_target:
                # Compute realized vol
                vol_dates = sorted_dates[max(0, rdate_idx - 20):entry_idx]
                if len(vol_dates) >= 5:
                    vol_rets = []
                    for j in range(1, len(vol_dates)):
                        if vol_dates[j-1] in prices and vol_dates[j] in prices:
                            r = (prices[vol_dates[j]]["close"] - prices[vol_dates[j-1]]["close"]) / prices[vol_dates[j-1]]["close"]
                            vol_rets.append(r)
                    if vol_rets:
                        mean_r = sum(vol_rets) / len(vol_rets)
                        std_r = (sum((r - mean_r)**2 for r in vol_rets) / (len(vol_rets) - 1)) ** 0.5
                        ann_vol = std_r * (252 ** 0.5)
                        if ann_vol > 0:
                            scale = min(1.0, 0.12 / ann_vol)
                        else:
                            scale = 1.0
                    else:
                        scale = 1.0
                else:
                    scale = 1.0
            else:
                scale = 1.0

            gross_ret = scale * (exit_price - entry_price) / entry_price
            net_ret = gross_ret - FEES
        else:
            # Cash (long/cash) or short (long/short)
            if vol_target:
                net_ret = 0.0  # cash earns nothing
            else:
                net_ret = 0.0  # cash

        total_fees += FEES

        trades.append({
            "entry": entry_date,
            "exit": exit_date,
            "signal": signal,
            "gross": gross_ret if signal > 0 else 0,
            "net": net_ret,
        })

        portfolio *= (1 + net_ret)
        equity_curve.append(portfolio)

    n = len(trades)
    if n == 0:
        return None

    returns = [t["net"] for t in trades]
    mean_ret = sum(returns) / n
    wins = sum(1 for r in returns if r > 0)
    wr = wins / n
    std_ret = (sum((r - mean_ret)**2 for r in returns) / (n - 1)) ** 0.5 if n > 1 else 0
    sharpe = (mean_ret / std_ret) * (252 ** 0.5) if std_ret > 0 else 0

    n_years = 9
    cagr = (portfolio) ** (1.0 / n_years) - 1 if portfolio > 0 else -1

    peak = equity_curve[0]
    max_dd = 0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0
        if dd < max_dd:
            max_dd = dd

    # B&H comparison
    spy_entry = prices[sorted_dates[0]]["close"]
    spy_exit = prices[sorted_dates[-1]]["close"]
    spy_ret = (spy_exit - spy_entry) / spy_entry if spy_entry > 0 else 0
    spy_cagr = (1 + spy_ret) ** (1.0 / n_years) - 1
    excess = cagr - spy_cagr

    # Per-year
    by_year = defaultdict(list)
    for t in trades:
        yr = t["entry"][:4]
        by_year[yr].append(t["net"])

    years_positive = sum(1 for yr in by_year if sum(by_year[yr]) / len(by_year[yr]) > 0)
    pct_years_positive = years_positive / len(by_year) * 100

    ci_lower, ci_upper = bootstrap_ci_annual(returns, HOLD_DAYS, n_years)
    ci_lower_excess = ci_lower - spy_cagr * 100
    ci_upper_excess = ci_upper - spy_cagr * 100

    # Ex-outlier (remove best 2 and worst 2)
    sorted_rets = sorted(returns)
    if len(sorted_rets) > 4:
        trimmed = sorted_rets[2:-2]
    else:
        trimmed = sorted_rets
    trimmed_port = 1.0
    for r in trimmed:
        trimmed_port *= (1 + r)
    n_trim_years = len(trimmed) * HOLD_DAYS / 252
    trimmed_cagr = trimmed_port ** (1.0 / n_trim_years) - 1 if n_trim_years > 0 else 0
    trimmed_excess = trimmed_cagr - spy_cagr

    return {
        "n": n,
        "cagr": cagr * 100,
        "sharpe": sharpe,
        "maxdd": max_dd * 100,
        "wr": wr * 100,
        "excess": excess * 100,
        "ci_lower": ci_lower_excess,
        "ex_outlier_excess": trimmed_excess * 100,
        "pct_years_positive": pct_years_positive,
        "total_fees": total_fees * 100,
        "by_year": {yr: sum(rs)/len(rs)*100 for yr, rs in by_year.items()},
        "first_trade": trades[0] if trades else None,
        "last_trade": trades[-1] if trades else None,
    }


def main():
    print("=" * 80)
    print("S-032 QQQ TSMOM HOLDOUT PULSE (2010-2018)")
    print("STATUS: PULSE TEST ONLY — NO IS, NO OOS, NO TRADE KERNEL")
    print("=" * 80)

    prices = load_prices(QQQ_PATH)
    n_total = len(prices)
    dates = sorted(prices.keys())
    print(f"\nQQQ daily: {n_total} bars, {dates[0]}..{dates[-1]}")
    # Gate-1
    bad = sum(1 for d in prices.values() if d["close"] <= 0 or d["high"] < d["low"])
    print(f"Gate-1: bad={bad}, {'PASS' if bad == 0 else 'FAIL'}")

    print(f"\n{'=' * 80}")
    print(f"HOLDOUT PULSE TABLE (2010-2018)")
    print(f"{'=' * 80}")
    print(f"\n{'Variant':>12} {'n':>4} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'WR':>6} {'Excess':>8} {'CI_lower':>9} {'ExOutEx':>9}")
    print("-" * 75)

    variants = [
        ("A", "63d-L/C", lambda: run_tsmom(prices, 63, HOLD_START, HOLD_END)),
        ("B", "126d-L/C", lambda: run_tsmom(prices, 126, HOLD_START, HOLD_END)),
        ("C", "250d-L/C", lambda: run_tsmom(prices, 250, HOLD_START, HOLD_END)),
        ("D", "126d-VT", lambda: run_tsmom(prices, 126, HOLD_START, HOLD_END, vol_target=True)),
    ]

    results = {}
    for label, name, runner in variants:
        r = runner()
        if r:
            results[label] = r
            print(f"{label+' '+name:>12} {r['n']:>4} {r['cagr']:>7.2f}% {r['sharpe']:>7.2f} {r['maxdd']:>7.2f}% {r['wr']:>5.1f}% {r['excess']:>7.2f}% {r['ci_lower']:>8.2f}% {r['ex_outlier_excess']:>8.2f}%")

    # Selection
    print(f"\n{'=' * 80}")
    print(f"SELECTION RULE: Highest Sharpe, subject to:")
    print(f"  1. mean net return > 0")
    print(f"  2. MaxDD > -35%")
    print(f"  3. positive in >= 60% of holdout years")
    print(f"{'=' * 80}")

    selected = None
    best_sharpe = -999
    for label, r in results.items():
        if r["excess"] > 0 and r["maxdd"] > -35 and r["pct_years_positive"] >= 60:
            if r["sharpe"] > best_sharpe:
                best_sharpe = r["sharpe"]
                selected = label

    if not selected:
        print(f"\nNO_PULSE: No variant satisfies selection constraints")
        verdict = "NO_PULSE"
        print(f"\nVERDICT: {verdict}")
        return 1

    r = results[selected]
    print(f"\nSelected: Variant {selected} (Sharpe={r['sharpe']:.2f})")

    # --- Pulse criteria ---
    print(f"\n{'=' * 80}")
    print(f"PULSE CRITERIA (selected variant {selected}):")
    print(f"{'=' * 80}")

    checks = {
        "n_rebalances >= 80": r["n"] >= 80,
        "mean net return > 0": r["excess"] > 0,
        "CI lower bound > 0": r["ci_lower"] > 0,
        "Sharpe > 0.5": r["sharpe"] > 0.5,
        "MaxDD > -35%": r["maxdd"] > -35,
        "positive in >= 60% years": r["pct_years_positive"] >= 60,
        "ex-outlier excess > 0": r["ex_outlier_excess"] > 0,
    }

    for check, passed in checks.items():
        print(f"  {check}: {'PASS' if passed else 'FAIL'}")

    all_pass = all(checks.values())
    verdict = "PULSE_FOUND" if all_pass else "NO_PULSE"

    print(f"\n{'=' * 80}")
    print(f"VERDICT: {verdict}")
    print(f"{'=' * 80}")

    if all_pass:
        print(f"\n  Variant {selected} has a pulse on QQQ holdout (2010-2018).")
        print(f"  Awaiting Overseer review for NEW preregistration before IS/OOS.")
    else:
        print(f"\n  Variant {selected} does not meet all pulse criteria.")
        print(f"  S-032 is CLOSED.")

    import json
    payload = json.dumps({
        "experiment": "S-032",
        "selected": selected,
        "verdict": verdict,
        "n": r["n"],
        "sharpe": round(r["sharpe"], 6),
        "excess": round(r["excess"], 6),
        "maxdd": round(r["maxdd"], 6),
    }, sort_keys=True)
    verdict_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    print(f"\nverdict_hash: {verdict_hash}")

    return 0 if "PULSE" in verdict else 1


if __name__ == "__main__":
    sys.exit(main())
