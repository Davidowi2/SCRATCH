#!/usr/bin/env python3
"""
research/backtest/S023_overnight_premium.py — S-023 Overnight Premium Test.

Tests 3 variants on SPY + VIX:
  A. Buy & Hold (Close-to-Close)
  B. Raw Overnight (Close -> Open, cash rest of day)
  C. Filtered Overnight (VIX Close < 20 to enter)

Metrics: CAGR, MaxDD, Sharpe, WinRate, crash-period performance.

Per factory/preregistrations/S023_overnight.md.
IS: 2010-01-01..2025-05-13 (full history — this is a data-availability
anomaly test, not a param optimization).
"""

import csv
import hashlib
import os
import sys
import math
import statistics
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# No sys.path insert needed — this is self-contained

SQRT_252 = math.sqrt(252)
TRADE_FEE = 0.0001  # 0.01% per trade (SPY is liquid)


def load_daily(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("close") or row["close"] in ("", "null", "None"):
                continue
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({
                "time": ts,
                "date": ts.date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    return sorted(rows, key=lambda r: r["time"])


def annualize_return(total_return, n_days, days_per_year=252):
    """CAGR from total return over n_days."""
    if total_return <= -1 or n_days == 0:
        return 0.0
    years = n_days / days_per_year
    if years == 0:
        return 0.0
    return (1 + total_return) ** (1 / years) - 1


def max_drawdown(returns):
    """Compute max drawdown from cumulative returns."""
    cum = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        cum *= (1 + r)
        peak = max(peak, cum)
        if peak > 0:
            dd = (cum - peak) / peak
            max_dd = min(max_dd, dd)
    return max_dd


def sharpe_ratio(returns):
    """Annualized Sharpe (risk-free = 0)."""
    if len(returns) < 2:
        return 0.0
    mean = statistics.mean(returns)
    std = statistics.stdev(returns)
    if std == 0:
        return float("inf") if mean > 0 else 0.0
    return (mean / std) * SQRT_252


def run_benchmark(spy):
    """A. Buy & Hold: Close-to-Close returns."""
    returns = []
    for i in range(1, len(spy)):
        r = (spy[i]["close"] - spy[i-1]["close"]) / spy[i-1]["close"]
        returns.append({"date": spy[i]["date"], "ret": r, "period": "c2c"})
    return returns


def run_raw_overnight(spy):
    """B. Raw Overnight: Close[t] -> Open[t+1], cash rest of day."""
    returns = []
    for i in range(1, len(spy)):
        # Overnight return: from close of day i-1 to open of day i
        ret = (spy[i]["open"] - spy[i-1]["close"]) / spy[i-1]["close"]
        # Subtract 2-way fees (exit at open, re-enter at close for next overnight)
        # Actually: hold cash intraday. One trade pair per overnight = 2 trades
        net_ret = ret - 2 * TRADE_FEE
        returns.append({"date": spy[i]["date"], "ret": net_ret, "period": "overnight", "raw": ret})
    return returns


def run_filtered_overnight(spy, vix, vix_threshold=20):
    """C. Filtered Overnight: only enter if VIX Close(t) < threshold."""
    vix_by_date = {v["date"]: v["close"] for v in vix}
    returns = []
    for i in range(1, len(spy)):
        vix_close_prev = vix_by_date.get(spy[i-1]["date"])
        if vix_close_prev is None:
            continue
        if vix_close_prev >= vix_threshold:
            # Hold cash (no return)
            returns.append({
                "date": spy[i]["date"],
                "ret": 0.0,  # cash = zero return
                "period": "cash",
                "entered": False,
            })
        else:
            ret = (spy[i]["open"] - spy[i-1]["close"]) / spy[i-1]["close"]
            net_ret = ret - 2 * TRADE_FEE
            returns.append({
                "date": spy[i]["date"],
                "ret": net_ret,
                "period": "overnight",
                "raw": ret,
                "entered": True,
            })
    return returns


def crash_period_analysis(returns, crisis_dates):
    """Analyze performance during named crash periods."""
    results = {}
    for label, (start, end) in crisis_dates.items():
        crises_returns = [r["ret"] for r in returns if start <= r["date"] <= end]
        if crises_returns:
            cr = sum(crises_returns)
            results[label] = {
                "n_days": len(crises_returns),
                "total_ret": cr,
                "win_rate": sum(1 for r in crises_returns if r > 0) / len(crises_returns) if crises_returns else 0,
            }
        else:
            results[label] = {"n_days": 0, "total_ret": 0, "win_rate": 0}
    return results


def report_strategy(name, returns, n_days_total):
    """Compute and return metrics for a strategy."""
    total_ret = sum(r["ret"] for r in returns)
    cagr = annualize_return(total_ret, n_days_total)
    max_dd = max_drawdown([r["ret"] for r in returns])
    sharpe = sharpe_ratio([r["ret"] for r in returns])

    # Win rate (long-only style: positive return = win)
    wins = sum(1 for r in returns if r["ret"] > 0)
    win_rate = wins / len(returns) if returns else 0

    return {
        "name": name,
        "cagr": cagr * 100,
        "max_dd": max_dd * 100,
        "sharpe": sharpe,
        "win_rate": win_rate * 100,
        "total_ret": total_ret,
        "n_periods": len(returns),
    }


def main():
    spy_path = os.path.join(PROJECT_DIR, "research", "data", "equity", "spy_daily_2010_2025.csv")
    vix_path = os.path.join(PROJECT_DIR, "research", "data", "equity", "vix_daily_2010_2025.csv")

    if not os.path.exists(spy_path):
        print("SPY data not found. Run tools/download_spy_daily.py")
        return 1
    if not os.path.exists(vix_path):
        print("VIX data not found. Run tools/download_equity_index.py")
        return 1

    spy = load_daily(spy_path)
    vix = load_daily(vix_path)

    spy_sha = hashlib.sha256(open(spy_path, "rb").read()).hexdigest()
    vix_sha = hashlib.sha256(open(vix_path, "rb").read()).hexdigest()

    print(f"SPY: {len(spy)} bars, sha={spy_sha[:16]}")
    print(f"VIX: {len(vix)} bars, sha={vix_sha[:16]}")
    print(f"Range: {spy[0]['date']} .. {spy[-1]['date']}")

    # Align: only use dates present in both
    spy_dates = set(s["date"] for s in spy)
    vix_dates = set(v["date"] for v in vix)
    common_dates = sorted(spy_dates & vix_dates)
    print(f"Aligned dates: {len(common_dates)}")

    # Crisis periods
    from datetime import date as ddate
    crisis_periods = {
        "2020 March (COVID)": (ddate(2020, 3, 1), ddate(2020, 3, 31)),
        "2022 Feb (Ukraine)": (ddate(2022, 2, 22), ddate(2022, 3, 15)),
    }

    # Run strategies
    bench_returns = run_benchmark(spy)
    raw_on_returns = run_raw_overnight(spy)
    filt_on_returns = run_filtered_overnight(spy, vix, vix_threshold=20)

    n_days_total = len(common_dates)

    print(f"\n{'='*72}")
    print("S-023 OVERNIGHT PREMIUM — COMPARATIVE ANALYSIS")
    print(f"{'='*72}")
    print(f"Period: 2010-01-01 .. 2025-05-13")
    print(f"Friction: 0.01% per trade (2 trades per overnight = 0.02% RT)")
    print(f"VIX Filter threshold: < 20.0 (enter overnight; >= 20 → cash)")

    print(f"\n{'='*72}")
    print(f"{'Strategy':<22} | {'CAGR':>7} | {'MaxDD':>7} | {'Sharpe':>7} | {'WinRt':>6} | {'Total':>9} | {'n':>6}")
    print(f"{'-'*72}")

    bench_metrics = report_strategy("A. Buy & Hold (C2C)", bench_returns, n_days_total)
    raw_metrics = report_strategy("B. Raw Overnight", raw_on_returns, n_days_total)
    filt_metrics = report_strategy("C. Filtered Overnight", filt_on_returns, n_days_total)

    for m in [bench_metrics, raw_metrics, filt_metrics]:
        print(f"{m['name']:<22} | {m['cagr']:>+6.2f}% | {m['max_dd']:>+6.2f}% | {m['sharpe']:+6.2f} | {m['win_rate']:>5.1f}% | {m['total_ret']:>+8.4f} | {m['n_periods']:>6}")

    print(f"\n{'='*72}")
    print("CRASH-PERIOD ANALYSIS")
    print(f"{'='*72}")
    print(f"\n{'Period':<24} | {'Strategy':<22} | {'Days':>5} | {'Ret':>8} | {'WR':>6}")
    print(f"{'-'*72}")
    for label, _ in crisis_periods.items():
        bench_crash = crash_period_analysis(bench_returns, {label: crisis_periods[label]})
        raw_crash = crash_period_analysis(raw_on_returns, {label: crisis_periods[label]})
        filt_crash = crash_period_analysis(filt_on_returns, {label: crisis_periods[label]})
        for name, crash in [("Buy & Hold", bench_crash), ("Raw Overnight", raw_crash), ("Filtered Overnight", filt_crash)]:
            c = crash[label]
            print(f"{label:<24} | {name:<22} | {c['n_days']:>5} | {c['total_ret']:>+7.4f} | {c['win_rate']*100:>5.1f}%")

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    # The VIX filter improves Sharpe if filt_sharpe > raw_sharpe
    sharpe_improvement = filt_metrics["sharpe"] - raw_metrics["sharpe"]
    dd_improvement = abs(filt_metrics["max_dd"]) - abs(raw_metrics["max_dd"])

    print(f"Raw Overnight Sharpe:      {raw_metrics['sharpe']:+.4f}")
    print(f"Filtered Overnight Sharpe: {filt_metrics['sharpe']:+.4f}")
    print(f"Sharpe improvement:        {sharpe_improvement:+.4f}")
    print(f"Raw Overnight MaxDD:       {raw_metrics['max_dd']:+.2f}%")
    print(f"Filtered Overnight MaxDD:  {filt_metrics['max_dd']:+.2f}%")
    print(f"DD improvement:            {dd_improvement:+.2f}%")

    # VIX filter statistics
    vix_filter_entered = sum(1 for r in filt_on_returns if r.get("entered", False))
    vix_filter_cash = len(filt_on_returns) - vix_filter_entered
    print(f"\nVIX Filter stats: entered {vix_filter_entered} nights, held cash {vix_filter_cash} nights ({vix_filter_cash/len(filt_on_returns)*100:.1f}%)")

    if sharpe_improvement > 0:
        verdict = "FILTER IMPROVES RISK-ADJUSTED RETURN (Sharpe +%.4f)" % sharpe_improvement
    else:
        verdict = "FILTER DEGRADES RISK-ADJUSTED RETURN (Sharpe %.4f)" % sharpe_improvement

    print(f"\n  VERDICT: {verdict}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
