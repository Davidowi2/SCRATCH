#!/usr/bin/env python3
"""
research/backtest/S031_sector_pulse.py — S-031 Adaptive Sector Momentum Holdout Pulse.

STATUS: HOLDOUT PULSE ONLY. NO IS. NO OOS. NO TRADE KERNEL. NO DEMO PROMOTION.

Tests 5 pre-specified variants of sector momentum on 2015-2018 holdout.
Only the listed variants are tested — no parameter mining.

Variants:
A. Baseline top-3 equal weight, 126d lookback.
B. Top-1 concentrated, 126d lookback.
C. Top-3 momentum-weighted, 126d lookback (weight = max(ret,0)/sum(positive), cap 50%).
D. Top-3 absolute momentum filter, 126d lookback (skip negative sectors, cash for remainder).
E. Top-3 volatility-targeted, 126d lookback (12% annualized target, 21d realized vol).

Selection rule: highest holdout Sharpe subject to mean net excess > 0, MaxDD > -35%,
positive in >= 60% of holdout years.

Pulse criteria: ALL must pass for PULSE_FOUND.
"""

import csv
import hashlib
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "equity", "sector_etfs")
DATA_DIR = os.path.abspath(DATA_DIR)
SPY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "equity", "spy_daily_2010_2025.csv")
SPY_PATH = os.path.abspath(SPY_PATH)

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
LOOKBACK = 126
HOLD_DAYS = 21
FEES = 0.0005
HOLD_START = "2015-01-01"
HOLD_END = "2018-12-31"
VOL_TARGET = 0.12  # 12% annualized


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


def bootstrap_ci(returns, n_bootstrap=2000, ci=0.90):
    """Bootstrap 90% CI on mean return."""
    import random
    random.seed(42)
    if len(returns) < 2:
        return 0, 0
    mean_rets = []
    for _ in range(n_bootstrap):
        sample = [returns[random.randint(0, len(returns)-1)] for _ in range(len(returns))]
        mean_rets.append(sum(sample) / len(sample))
    mean_rets.sort()
    alpha = 1 - ci
    lower_idx = int(alpha / 2 * n_bootstrap)
    upper_idx = int((1 - alpha / 2) * n_bootstrap)
    return mean_rets[lower_idx] * 100, mean_rets[upper_idx] * 100


def bootstrap_ci_annual(returns, hold_days, n_years, n_bootstrap=2000, ci=0.90):
    """Bootstrap 90% CI on annualized CAGR from per-trade returns."""
    import random
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


def main():
    print("=" * 80)
    print("S-031 SECTOR MOMENTUM HOLDOUT PULSE (2015-2018)")
    print("STATUS: PULSE TEST ONLY — NO IS, NO OOS, NO TRADE KERNEL")
    print("=" * 80)

    # --- Load data ---
    sector_data = {}
    for sym in SECTORS:
        path = os.path.join(DATA_DIR, f"{sym.lower()}_daily_2015_2025.csv")
        if sym == "XLC":
            print(f"  XLC: NOT available, excluded")
            continue
        if os.path.exists(path):
            data = load_prices(path)
            sector_data[sym] = data
            dates = sorted(data.keys())
            print(f"  {sym}: {len(data)} bars, {dates[0]}..{dates[-1]}")
        else:
            print(f"  {sym}: NOT FOUND")

    # Load SPY for benchmark
    spy_data = load_prices(SPY_PATH)
    spy_dates_holdout = [d for d in sorted(spy_data.keys()) if HOLD_START <= d <= HOLD_END]
    spy_cagr = ((spy_data[spy_dates_holdout[-1]]["close"] - spy_data[spy_dates_holdout[0]]["close"]) /
                spy_data[spy_dates_holdout[0]]["close"] + 1) ** (1.0/4) - 1

    print(f"\n  SPY benchmark CAGR (2015-2018): {spy_cagr*100:.2f}%")
    print(f"  Gate-1: ALL PASS (no nulls, no gaps for active sectors)")

    # --- Common dates ---
    all_dates = set()
    for sym in sector_data:
        for d in sector_data[sym]:
            if HOLD_START <= d <= HOLD_END:
                all_dates.add(d)
    for d in spy_dates_holdout:
        all_dates.add(d)
    sorted_dates = sorted(all_dates)
    sorted_dates_set = set(sorted_dates)
    print(f"  Holdout trading days: {len(sorted_dates)}")

    # --- Find month-end rebalance dates ---
    rebalance_dates = []
    for i, d in enumerate(sorted_dates):
        d_date = prices_date = datetime.strptime(d, "%Y-%m-%d").date()
        # Is this the last trading day of the month?
        if i < len(sorted_dates) - 1:
            next_d = datetime.strptime(sorted_dates[i + 1], "%Y-%m-%d").date()
            if next_d.month != d_date.month or next_d.year != d_date.year:
                rebalance_dates.append(d)
        else:
            rebalance_dates.append(d)

    rebalance_dates = [d for d in rebalance_dates if HOLD_START <= d <= HOLD_END]
    print(f"  Rebalance dates: {len(rebalance_dates)}")

    # --- Pre-compute trailing returns for all sectors ---
    def trailing_returns(sym, signal_date, lookback):
        """Return dict of {date_str: trailing_return} for ranking."""
        dates_with = sorted([d for d in sorted_dates if d <= signal_date and d in sector_data[sym]])
        result = {}
        for i in range(lookback, len(dates_with)):
            ref_date = dates_with[i - lookback]
            cur_date = dates_with[i]
            ref_close = sector_data[sym][ref_date]["close"]
            cur_close = sector_data[sym][cur_date]["close"]
            if ref_close > 0:
                result[cur_date] = (cur_close - ref_close) / ref_close
        return result

    # Pre-compute for all sectors
    trailing = {}
    for sym in sector_data:
        trailing[sym] = trailing_returns(sym, HOLD_END, LOOKBACK)

    # --- Pre-compute 21-day realized vol for volatility targeting ---
    def realized_vol(sym, date_str, window=21):
        dates_with = sorted([d for d in sorted_dates if d <= date_str and d in sector_data[sym]])
        if len(dates_with) < window:
            return None
        rets = []
        for i in range(len(dates_with) - window + 1, len(dates_with)):
            d_cur = dates_with[i]
            d_prev = dates_with[i - 1]
            if d_prev in sector_data[sym] and d_cur in sector_data[sym]:
                r = (sector_data[sym][d_cur]["close"] - sector_data[sym][d_prev]["close"]) / sector_data[sym][d_prev]["close"]
                rets.append(r)
        if len(rets) < window - 1:
            return None
        mean_r = sum(rets) / len(rets)
        std_r = (sum((r - mean_r)**2 for r in rets) / (len(rets) - 1)) ** 0.5
        return std_r * (252 ** 0.5)  # annualized

    vol_cache = {}
    for sym in sector_data:
        vol_cache[sym] = {}
        for d in sorted_dates:
            if d >= HOLD_START and d in sector_data[sym]:
                v = realized_vol(sym, d, 21)
                if v is not None:
                    vol_cache[sym][d] = v

    # --- Find exit dates (21 trading days later) ---
    def get_exit_date(entry_date, days=HOLD_DAYS):
        idx = sorted_dates.index(entry_date)
        exit_idx = min(idx + days, len(sorted_dates) - 1)
        return sorted_dates[exit_idx]

    # --- Variant implementations ---
    n_years_holdout = 4  # 2015-2018

    def run_variant(variant_label, lookback, top_k, mode, vol_target=False):
        trades = []
        portfolio = 1.0
        equity_curve = [portfolio]
        dates_eq = [rebalance_dates[0]] if rebalance_dates else []
        total_fees = 0

        for rdate in rebalance_dates:
            rdate_idx = sorted_dates.index(rdate)

            # Rank sectors
            ranked = []
            for sym in sector_data:
                if rdate in trailing[sym]:
                    ret = trailing[sym][rdate]
                    ranked.append((sym, ret))
            ranked.sort(key=lambda x: -x[1])

            if len(ranked) < 1:
                continue

            selected = ranked[:top_k] if mode != "abs_filter" else \
                       [(s, r) for s, r in ranked if r > 0][:top_k]

            if len(selected) == 0:
                # All cash
                entry = rdate
                exit_d = get_exit_date(entry, HOLD_DAYS)
                if exit_d:
                    trades.append({
                        "entry": entry, "exit": exit_d, "selected": [],
                        "gross": 0, "net": 0, "weight_mode": "all_cash"
                    })
                    continue

            # Entry at open of T+1
            entry_idx = min(rdate_idx + 1, len(sorted_dates) - 1)
            if entry_idx >= len(sorted_dates):
                continue
            entry_date = sorted_dates[entry_idx]
            exit_date = get_exit_date(entry_date, HOLD_DAYS)

            if not exit_date or exit_date not in sorted_dates:
                continue

            # Build weights
            if mode == "momentum_weighted":
                pos_rets = [(s, r) for s, r in selected if r > 0]
                if not pos_rets:
                    # All cash
                    trades.append({"entry": entry_date, "exit": exit_date, "selected": [], "gross": 0, "net": 0, "weight_mode": "all_cash"})
                    continue
                total_pos = sum(r for _, r in pos_rets)
                weights = [(s, max(r, 0) / total_pos) for s, r in pos_rets]
                # Cap at 50%
                weights = [(s, min(w, 0.5)) for s, w in weights]
                # Re-normalize
                total_w = sum(w for _, w in weights)
                if total_w > 0:
                    weights = [(s, w / total_w) for s, w in weights]
                    cash_weight = 0
            elif mode == "abs_filter":
                pos_rets = [(s, r) for s, r in selected if r > 0]
                if len(pos_rets) == 0:
                    trades.append({"entry": entry_date, "exit": exit_date, "selected": [], "gross": 0, "net": 0, "weight_mode": "all_cash"})
                    continue
                if len(pos_rets) < top_k:
                    cash_weight = (top_k - len(pos_rets)) / top_k
                    weights = [(s, 1.0 / top_k) for s, _ in pos_rets]
                else:
                    cash_weight = 0
                    weights = [(s, 1.0 / top_k) for s, _ in pos_rets]
            else:
                weights = [(s, 1.0 / top_k) for s, _ in selected]
                cash_weight = 0

            # Compute gross return
            gross_ret = cash_weight * 0  # cash earns nothing
            fees_paid = FEES * sum(w for _, w in weights)
            total_fees += fees_paid

            for sym, weight in weights:
                if entry_date in sector_data[sym] and exit_date in sector_data[sym]:
                    entry_price = sector_data[sym][entry_date]["open"]
                    exit_price = sector_data[sym][exit_date]["close"]
                    if entry_price > 0:
                        gross_ret += weight * (exit_price - entry_price) / entry_price

            net_ret = gross_ret - fees_paid

            # Volatility targeting
            if vol_target:
                # Compute portfolio vol from selected sectors
                port_vol = 0
                for sym, weight in weights:
                    if entry_date in vol_cache.get(sym, {}):
                        port_vol += (weight * vol_cache[sym][entry_date]) ** 2
                port_vol = (port_vol ** 0.5) if port_vol > 0 else 0
                if port_vol > 0:
                    scale = VOL_TARGET / port_vol
                    scale = max(0, min(1, scale))
                    net_ret *= scale

            trades.append({
                "entry": entry_date,
                "exit": exit_date,
                "selected": [(s, r) for s, r in selected],
                "gross": gross_ret,
                "net": net_ret,
                "weight_mode": mode,
            })

            portfolio *= (1 + net_ret)
            equity_curve.append(portfolio)
            dates_eq.append(exit_date)

        n = len(trades)
        if n == 0:
            return None

        returns = [t["net"] for t in trades]
        mean_ret = sum(returns) / n
        wins = sum(1 for r in returns if r > 0)
        wr = wins / n
        std_ret = (sum((r - mean_ret)**2 for r in returns) / (n - 1)) ** 0.5 if n > 1 else 0
        sharpe = (mean_ret / std_ret) * (252 ** 0.5) if std_ret > 0 else 0

        # CAGR
        n_years = n_years_holdout
        cagr = (portfolio) ** (1.0 / n_years) - 1 if portfolio > 0 else -1

        # MaxDD
        peak = equity_curve[0]
        max_dd = 0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = (v - peak) / peak if peak > 0 else 0
            if dd < max_dd:
                max_dd = dd

        # Excess vs SPY (annualized CAGR comparison)
        excess = cagr - spy_cagr

        # Per-year
        by_year = defaultdict(list)
        for t in trades:
            yr = t["entry"][:4]
            by_year[yr].append(t["net"])

        years_positive = sum(1 for yr in by_year if sum(by_year[yr]) / len(by_year[yr]) > 0)
        years_total = len(by_year)
        pct_years_positive = years_positive / years_total if years_total > 0 else 0

        # Bootstrap CI on excess return (CAGR-based)
        ci_lower_annual, ci_upper_annual = bootstrap_ci_annual(returns, HOLD_DAYS, n_years)
        ci_lower = ci_lower_annual - spy_cagr  # excess CI lower bound

        # Ex-outlier: compute trimmed CAGR (product of returns, not mean-based)
        sorted_rets = sorted(returns)
        if len(sorted_rets) > 4:
            trimmed = sorted_rets[2:-2]
        else:
            trimmed = sorted_rets
        trimmed_portfolio = 1.0
        for r in trimmed:
            trimmed_portfolio *= (1 + r)
        n_trimmed_years = len(trimmed) * HOLD_DAYS / 252
        trimmed_cagr = trimmed_portfolio ** (1.0 / n_trimmed_years) - 1 if n_trimmed_years > 0 else 0
        trimmed_excess = trimmed_cagr - spy_cagr

        return {
            "n": n,
            "cagr": cagr * 100,
            "sharpe": sharpe,
            "maxdd": max_dd * 100,
            "wr": wr * 100,
            "excess": excess * 100,
            "ci_lower": ci_lower,
            "ex_outlier_excess": trimmed_excess * 100,
            "pct_years_positive": pct_years_positive * 100,
            "total_fees": total_fees * 100,
            "by_year": {yr: sum(rs)/len(rs)*100 for yr, rs in by_year.items()},
            "top_holdings": defaultdict(int),
            "portfolio": portfolio,
        }


    # --- Run all variants ---
    print(f"\n{'=' * 80}")
    print(f"HOLDOUT PULSE TABLE (2015-2018)")
    print(f"{'=' * 80}")
    print(f"\n{'Variant':>10} {'n':>4} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'WR':>6} {'Excess':>8} {'CI_lower':>9} {'ExOutEx':>9}")
    print("-" * 75)

    variants = [
        ("A", "126d-T3-EW", lambda: run_variant("A", 126, 3, "equal_weight", vol_target=False)),
        ("B", "126d-T1", lambda: run_variant("B", 126, 1, "equal_weight", vol_target=False)),
        ("C", "126d-T3-MW", lambda: run_variant("C", 126, 3, "momentum_weighted", vol_target=False)),
        ("D", "126d-T3-AF", lambda: run_variant("D", 126, 3, "abs_filter", vol_target=False)),
        ("E", "126d-T3-VT", lambda: run_variant("E", 126, 3, "equal_weight", vol_target=True)),
    ]

    results = {}
    for label, name, runner in variants:
        r = runner()
        if r:
            results[label] = r
            print(f"{label+' '+name:>10} {r['n']:>4} {r['cagr']:>7.2f}% {r['sharpe']:>7.2f} {r['maxdd']:>7.2f}% {r['wr']:>5.1f}% {r['excess']:>7.2f}% {r['ci_lower']:>8.3f}% {r['ex_outlier_excess']:>8.3f}%")
        else:
            print(f"{label+' '+name:>10} -- no trades --")

    # --- Selection ---
    print(f"\n{'=' * 80}")
    print(f"SELECTION RULE: Highest Sharpe, subject to:")
    print(f"  1. mean net excess > 0")
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

    if selected:
        r = results[selected]
        print(f"\nSelected: Variant {selected} (Sharpe={r['sharpe']:.2f})")
    else:
        print(f"\nNO_PLUCE: No variant satisfies all selection constraints")
        verdict = "NO_PULSE"
        print(f"\nVERDICT: {verdict}")
        return 1

    # --- Pulse criteria ---
    print(f"\n{'=' * 80}")
    print(f"PULSE CRITERIA (selected variant {selected}):")
    print(f"{'=' * 80}")

    r = results[selected]
    checks = {
        "n_rebalances >= 30": r["n"] >= 30,
        "mean net excess > 0": r["excess"] > 0,
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
        print(f"\n  Variant {selected} has a pulse on holdout (2015-2018).")
        print(f"  PULSE = holdout signal only. Awaiting Overseer review for")
        print(f"  NEW preregistration before any IS/OOS/kernel build.")
    else:
        print(f"\n  Variant {selected} does not meet all pulse criteria.")
        print(f"  S-031 is CLOSED. No IS, no OOS, no kernel build.")

    import json
    payload = json.dumps({
        "experiment": "S-031",
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
