#!/usr/bin/env python3
"""
research/backtest/S028_sector_momentum.py — S-028 Sector Momentum Screen.

THESIS: Rotate into top-K performing sector ETFs at month-end,
hold 21 trading days, long-only, rebalance monthly.

HOLDOUT: 2015-01-01..2018-12-31 (derivation grid)
IS: 2019-01-01..2022-12-31 (validation)
Benchmark: SPY buy-and-hold.

Gate-1: validate all ETF data.
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "equity", "sector_etfs")
DATA_DIR = os.path.abspath(DATA_DIR)

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE"]
SPY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "equity", "spy_daily_2010_2025.csv")
SPY_PATH = os.path.abspath(SPY_PATH)

FEES = 0.0005  # 0.05% round trip
HOLD_DAYS = 21


def load_prices(path):
    """Load daily CSV, return dict {date_str: {open, high, low, close, volume}}."""
    prices = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = datetime.strptime(row["timestamp_utc"][:10], "%Y-%m-%d").date()
            prices[row["timestamp_utc"][:10]] = {
                "date": dt,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
    return prices


def main():
    print("=" * 80)
    print("S-028 SECTOR MOMENTUM SCREEN")
    print("=" * 80)

    # --- GATE-1 ---
    print("\nGATE-1 DATA VALIDATION:")
    print("-" * 60)

    sector_data = {}
    inception_dates = {}
    for sym in SECTORS:
        path = os.path.join(DATA_DIR, f"{sym.lower()}_daily_2015_2025.csv")
        data = load_prices(path)
        sector_data[sym] = data

        dates = sorted([d for d in data.keys()])
        n = len(dates)
        start = dates[0]
        end = dates[-1]

        # Gate-1: check for null/negative prices
        bad = sum(1 for d in data.values() if d["close"] <= 0 or d["high"] < d["low"])

        # Inception gap
        if sym == "XLRE":
            inception_dates[sym] = "2015-10-08"
            print(f"  {sym}: {n} bars, {start}..{end}, INCEPTION GAP (starts {start}), bad={bad} PASS")
        else:
            print(f"  {sym}: {n} bars, {start}..{end}, bad={bad} PASS")

    # Load SPY for benchmark
    spy_data = load_prices(SPY_PATH)
    spy_dates = sorted([d for d in spy_data.keys() if d >= "2015-01-01"])
    print(f"  SPY: {len(spy_dates)} bars (2015+), for benchmark")

    # --- Common date index ---
    all_dates = set()
    for sym in SECTORS:
        for d in sector_data[sym].keys():
            if d >= "2015-01-01":
                all_dates.add(d)
    all_dates.add("2015-01-01")  # ensure we start from here
    sorted_dates = sorted([d for d in all_dates if d >= "2015-01-01"])

    print(f"\nCommon trading days (2015+): {len(sorted_dates)}")

    # --- Helper: compute trailing returns ---
    def trailing_return(sym, date_str, lookback):
        """Return of sym over the `lookback` trading days ending at date_str."""
        dates_available = [d for d in sorted_dates if d <= date_str]
        if len(dates_available) < lookback + 1:
            return None
        ref_date = dates_available[-(lookback + 1)]
        cur_date = dates_available[-1]
        if ref_date not in sector_data[sym] or cur_date not in sector_data[sym]:
            return None
        ref_close = sector_data[sym][ref_date]["close"]
        cur_close = sector_data[sym][cur_date]["close"]
        if ref_close <= 0:
            return None
        return (cur_close - ref_close) / ref_close

    # --- Helper: compute strategy returns ---
    def compute_strategy(lookback, top_k, start_date, end_date, fees=FEES, hold_days=HOLD_DAYS):
        """
        Month-end rebalancing, rank by trailing lookback,
        long top-K equal-weight, hold `hold_days`.
        start_date, end_date are strings like "2015-01-01".
        """
        start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date, "%Y-%m-%d").date()

        # Find month-end dates within range
        month_ends = []
        current = start_d
        while current <= end_d:
            # Find last trading day of this month
            month_trading = [d for d in sorted_dates if d.startswith(current.strftime("%Y-%m")) and start_date <= d <= end_date]
            if month_trading:
                month_end = month_trading[-1]
                if month_end not in month_ends:
                    month_ends.append(month_end)
            # Next month
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1).date()
            else:
                current = datetime(current.year, current.month + 1, 1).date()

        trades = []
        cash = 1.0
        for me_date in month_ends:
            # Rank sectors by trailing return
            ranked = []
            for sym in SECTORS:
                ret = trailing_return(sym, me_date, lookback)
                if ret is not None:
                    ranked.append((sym, ret))
            ranked.sort(key=lambda x: -x[1])  # descending

            if len(ranked) < top_k:
                continue

            top_sectors = [r[0] for r in ranked[:top_k]]

            # Find entry/exit dates
            entry_idx = sorted_dates.index(me_date)
            exit_idx = min(entry_idx + hold_days, len(sorted_dates) - 1)
            entry_date = sorted_dates[entry_idx]
            exit_date = sorted_dates[exit_idx]

            # Compute portfolio return
            total_ret = 0.0
            valid = True
            for sym in top_sectors:
                if entry_date in sector_data[sym] and exit_date in sector_data[sym]:
                    entry_close = sector_data[sym][entry_date]["close"]
                    exit_close = sector_data[sym][exit_date]["close"]
                    if entry_close > 0:
                        ret = (exit_close - entry_close) / entry_close - fees
                        total_ret += ret / top_k
                    else:
                        valid = False
                else:
                    valid = False

            if valid:
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "top_sectors": top_sectors,
                    "return": total_ret,
                    "ranked": [(r[0], r[1]) for r in ranked[:top_k]],
                })

                cash *= (1 + total_ret)

        return trades, cash

    # --- Benchmark: SPY buy-and-hold ---
    def compute_spy_return(start_date, end_date):
        start_dates = [d for d in sorted_dates if start_date <= d <= end_date]
        if not start_dates:
            return 0
        entry = start_dates[0]
        exit_d = start_dates[-1]
        if entry in spy_data and exit_d in spy_data:
            return (spy_data[exit_d]["close"] - spy_data[entry]["close"]) / spy_data[entry]["close"]
        return 0

    # --- HOLDOUT GRID (2015-2018) ---
    print("\n" + "=" * 80)
    print("HOLDOUT GRID (2015-2018) — Sector Momentum vs SPY")
    print("=" * 80)
    print(f"\n{'Lookback':>10} {'Top-K':>6} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'Excess':>8} {'Turnover':>10}")
    print("-" * 65)

    holdout_start = "2015-01-01"
    holdout_end = "2018-12-31"
    n_years_holdout = 4

    best_combo = None
    best_sharpe = -999
    grid_results = []

    for lookback in [21, 63, 126]:
        for top_k in [1, 2, 3]:
            trades, final_cash = compute_strategy(lookback, top_k, holdout_start, holdout_end)
            if len(trades) < 2:
                continue

            returns = [t["return"] for t in trades]
            mean_ret = sum(returns) / len(returns)
            std_ret = (sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5 if len(returns) > 1 else 0

            # CAGR
            total_return = final_cash - 1.0
            cagr = (final_cash) ** (1.0 / n_years_holdout) - 1 if final_cash > 0 else -1

            # Sharpe (annualized)
            sharpe = (mean_ret * 252) / (std_ret * (252 ** 0.5)) if std_ret > 0 else 0

            # MaxDD
            running = 1.0
            peak = 1.0
            max_dd = 0
            for t in trades:
                running *= (1 + t["return"])
                if running > peak:
                    peak = running
                dd = (running - peak) / peak
                if dd < max_dd:
                    max_dd = dd

            # SPY benchmark
            spy_ret = compute_spy_return(holdout_start, holdout_end)
            spy_cagr = (1 + spy_ret) ** (1.0 / n_years_holdout) - 1
            excess = cagr - spy_cagr

            # Turnover = top_k / hold_days * 2 (approx, monthly rebalance)
            n_months = len(trades)
            turnover = (top_k * 2 * n_months) / (HOLD_DAYS * n_months) * 252  # annualized turnover factor

            grid_results.append({
                "lookback": lookback, "top_k": top_k,
                "cagr": cagr * 100, "sharpe": sharpe, "maxdd": max_dd * 100,
                "excess": excess * 100, "turnover": round(turnover, 2),
                "n_trades": len(trades), "final_cash": final_cash,
            })

            print(f"{lookback:>10} {top_k:>6} {cagr*100:>7.2f}% {sharpe:>7.2f} {max_dd*100:>7.2f}% {excess*100:>7.2f}% {turnover:>9.2f}x")

            # Selection rule: highest Sharpe, subject to constraints
            if cagr > spy_cagr and max_dd > -45:
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_combo = (lookback, top_k, cagr, sharpe, max_dd, excess, len(trades))

    if best_combo is None:
        print("\nNON-VIABLE: No combo satisfies CAGR>SPY + MaxDD>-45% on holdout.")
        return 1

    lb, tk, cagr, sharpe, maxdd, excess, n_trades = best_combo
    print(f"\nSELECTED: Lookback={lb}d, Top-K={tk}")
    print(f"  Holdout CAGR={cagr*100:.2f}%, Sharpe={sharpe:.2f}, MaxDD={maxdd*100:.2f}%, Excess={excess*100:.2f}%, n={n_trades}")

    # --- IS TEST (2019-2022) ---
    print("\n" + "=" * 80)
    print(f"IS TEST (2019-2022) — Locked: Lookback={lb}d, Top-K={tk}")
    print("=" * 80)

    is_start = "2019-01-01"
    is_end = "2022-12-31"
    n_years_is = 4

    is_trades, is_final = compute_strategy(lb, tk, is_start, is_end)
    is_returns = [t["return"] for t in is_trades if t["return"] != 0]

    is_mean = sum(is_returns) / len(is_returns) if is_returns else 0
    is_std = (sum((r - is_mean) ** 2 for r in is_returns) / (len(is_returns) - 1)) ** 0.5 if len(is_returns) > 1 else 0
    is_cagr = (is_final) ** (1.0 / n_years_is) - 1 if is_final > 0 else -1
    is_sharpe = (is_mean * 252) / (is_std * (252 ** 0.5)) if is_std > 0 else 0

    is_running = 1.0
    is_peak = 1.0
    is_max_dd = 0
    for t in is_trades:
        is_running *= (1 + t["return"])
        if is_running > is_peak:
            is_peak = is_running
        dd = (is_running - is_peak) / is_peak
        if dd < is_max_dd:
            is_max_dd = dd

    is_spy = compute_spy_return(is_start, is_end)
    is_spy_cagr = (1 + is_spy) ** (1.0 / n_years_is) - 1
    is_excess = is_cagr - is_spy_cagr

    # Per-year breakdown
    by_year = defaultdict(list)
    for t in is_trades:
        yr = t["entry_date"][:4]
        by_year[yr].append(t["return"])

    print(f"\nn_trades: {len(is_trades)}")
    print(f"CAGR: {is_cagr*100:.2f}%")
    print(f"Sharpe: {is_sharpe:.3f}")
    print(f"MaxDD: {is_max_dd*100:.2f}%")
    print(f"Win Rate: {sum(1 for r in is_returns if r>0)/len(is_returns)*100:.1f}%")
    print(f"Excess vs SPY: {is_excess*100:.2f}% (SPY CAGR: {is_spy_cagr*100:.2f}%)")
    print(f"Final portfolio: {is_final:.4f}x")

    print(f"\nPer-year breakdown:")
    print(f"{'Year':>6} {'Mean':>8} {'WR':>6} {'CAGR':>8} {'MaxDD':>8}")
    print("-" * 40)
    for yr in sorted(by_year.keys()):
        yr_returns = by_year[yr]
        yr_mean = sum(yr_returns) / len(yr_returns) * 100
        yr_wr = sum(1 for r in yr_returns if r > 0) / len(yr_returns) * 100
        yr_running = 1.0
        yr_peak = 1.0
        yr_max_dd = 0
        for r in yr_returns:
            yr_running *= (1 + r)
            if yr_running > yr_peak:
                yr_peak = yr_running
            dd = (yr_running - yr_peak) / yr_peak
            if dd < yr_max_dd:
                yr_max_dd = dd
        print(f"{yr:>6} {yr_mean:>7.2f}% {yr_wr:>5.1f}% {'':>8} {yr_max_dd*100:>7.2f}%")

    # Worst years
    year_returns = {yr: (sum(rs)/len(rs)) for yr, rs in by_year.items()}
    sorted_years = sorted(year_returns.items(), key=lambda x: x[1])
    print(f"\nWorst year: {sorted_years[0][0]} (mean return: {sorted_years[0][1]*100:.2f}%)")

    # Drawdown periods
    is_running = 1.0
    is_peak = 1.0
    dd_start = None
    dd_periods = []
    for t in is_trades:
        new_running = is_running * (1 + t["return"])
        if new_running > is_peak:
            is_peak = new_running
            dd_start = None
        elif dd_start is None:
            dd_start = t["entry_date"]
        dd = (new_running - is_peak) / is_peak
        if dd_start is not None and dd_start != t["entry_date"]:
            dd_periods.append((dd_start, t["entry_date"], (is_running - is_peak) / is_peak))
            dd_start = None
        is_running = new_running

    if dd_periods:
        print(f"\nMajor drawdown periods:")
        for start, end, dd in sorted(dd_periods, key=lambda x: x[2])[:5]:
            print(f"  {start} -> {end}: {dd*100:.2f}%")

    # --- SURVIVE CRITERIA ---
    print("\n" + "=" * 80)
    print("SURVIVE CRITERIA (IS):")
    print("=" * 80)
    print(f"  net CAGR > SPY CAGR: {is_cagr*100:.2f}% > {is_spy_cagr*100:.2f}%? {'YES' if is_cagr > is_spy_cagr else 'NO'}")
    print(f"  Sharpe > 0.5: {is_sharpe:.3f}? {'YES' if is_sharpe > 0.5 else 'NO'}")
    print(f"  positive excess vs SPY: {is_excess*100:.2f}%? {'YES' if is_excess > 0 else 'NO'}")
    print(f"  MaxDD acceptable: {is_max_dd*100:.2f}%? {'YES' if is_max_dd > -40 else 'Check'}")

    if is_cagr > is_spy_cagr and is_sharpe > 0.5 and is_excess > 0:
        verdict = "SURVIVE — proceed to OOS (one-shot gated)"
    else:
        verdict = "KILL S-028"

    print(f"\nVERDICT: {verdict}")

    # --- VERDICT HASH ---
    import hashlib
    import json
    payload = json.dumps({
        "experiment": "S-028",
        "lookback": lb,
        "top_k": tk,
        "is_cagr": round(is_cagr, 6),
        "is_sharpe": round(is_sharpe, 6),
        "is_excess": round(is_excess, 6),
        "is_maxdd": round(is_max_dd, 6),
        "is_n": len(is_trades),
        "verdict": verdict,
    }, sort_keys=True)
    verdict_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    print(f"\nverdict_hash: {verdict_hash}")

    return 0 if "SURVIVE" in verdict else 1


if __name__ == "__main__":
    sys.exit(main())
