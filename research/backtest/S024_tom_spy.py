#!/usr/bin/env python3
"""
research/backtest/S024_tom_spy.py — S-024 Turn-of-Month Pension Flow Harvest.

LOCKED (N,M) = (3,3). LONG SPY at open of first TOM window day,
exit at close of last. Fees: 0.02% round-trip.

IS: 2016-2020, OOS: 2021-2025 (one-shot gated, held).

Per factory/preregistrations/S024_tom_spy.md.
"""

import csv
import hashlib
import math
import os
import sys
from datetime import datetime, timezone, date
import statistics

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXPERIMENT_ID = "S-024"
STRATEGY_FAMILY = "TOM_PENSION_FLOW"
PARAM_DESC = "N3_M3_locked_long_spy_open_to_close_0.02pct_fee"

# LOCKED from holdout
N = 3
M = 3
L = N + M  # 6
FEE = 0.0002

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


def get_tom_windows(rows, start_date, end_date):
    """Get TOM windows: last N days of month + first M days of next month."""
    filtered = [r for r in rows if start_date <= r["date"] <= end_date]

    by_month = {}
    for r in filtered:
        mkey = (r["date"].year, r["date"].month)
        if mkey not in by_month:
            by_month[mkey] = []
        by_month[mkey].append(r)

    months = sorted(by_month.keys())
    windows = []
    for i in range(len(months) - 1):
        curr_month = months[i]
        next_month = months[i + 1]
        curr_days = sorted(by_month[curr_month], key=lambda r: r["date"])
        next_days = sorted(by_month[next_month], key=lambda r: r["date"])
        tom_days = curr_days[-N:] + next_days[:M]
        if len(tom_days) == L and len(tom_days) >= 2:
            entry = tom_days[0]["open"]
            exit_p = tom_days[-1]["close"]
            ret = (exit_p - entry) / entry - FEE
            windows.append({
                "start_date": tom_days[0]["date"],
                "end_date": tom_days[-1]["date"],
                "year": curr_month[0],
                "entry": entry,
                "exit": exit_p,
                "ret": ret,
            })
    return windows


def get_all_windows(rows, start_date, end_date, length=L):
    """Get all L-day windows for baseline."""
    filtered = [r for r in rows if start_date <= r["date"] <= end_date]
    rets = []
    for i in range(len(filtered) - length):
        e = filtered[i]["open"]
        x = filtered[i + length - 1]["close"]
        rets.append((x - e) / e)
    return rets


def compute_metrics(returns):
    n = len(returns)
    if n == 0:
        return {}
    mean_ret = statistics.mean(returns)
    std_ret = statistics.stdev(returns) if n > 1 else 0
    # Sharpe: annualized (TOM windows ~ monthly, so sqrt(12) annualization)
    sharpe = (mean_ret / std_ret) * math.sqrt(12) if std_ret > 0 else 0
    wr = sum(1 for r in returns if r > 0) / n * 100

    # Max DD
    cum = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        cum *= (1 + r)
        peak = max(peak, cum)
        if peak > 0:
            max_dd = min(max_dd, (cum - peak) / peak)

    return {
        "n": n,
        "mean_ret": mean_ret,
        "std": std_ret,
        "sharpe": sharpe,
        "wr": wr,
        "max_dd": max_dd,
    }


def report_phase(label, windows, all_bars, start_date, end_date):
    """Report §11 metrics for a phase."""
    rets = [w["ret"] for w in windows]
    metrics = compute_metrics(rets)
    baseline = get_all_windows(all_bars, start_date, end_date)
    base_mean = statistics.mean(baseline)
    excess = metrics["mean_ret"] - base_mean

    print(f"\n{'='*72}")
    print(f"S-024 TOM PENSION FLOW — {label} (N,M)={N},{M} LOCKED")
    print(f"Window: {start_date} .. {end_date}")
    print(f"{'='*72}")

    print(f"\nTHREE-DIMENSIONAL SUMMARY:")
    print(f"  n_windows:    {metrics['n']}")
    print(f"  mean net ret: {metrics['mean_ret']*100:.4f}%")
    print(f"  win rate:     {metrics['wr']:.1f}%")
    print(f"  Sharpe:       {metrics['sharpe']:.4f}  (annualized, sqrt(12))")
    print(f"  max DD:       {metrics['max_dd']*100:.4f}%")
    print(f"  baseline:     {base_mean*100:.4f}% (all {L}-day windows)")
    print(f"  EXCESS:       {excess*100:.4f}%")

    print(f"\nPER-YEAR BREAKDOWN:")
    print(f"  {'Year':<8} | {'n':>4} | {'mean%':>8} | {'WR':>6}")
    print(f"  {'-'*35}")
    by_year = {}
    for w in windows:
        y = w["year"]
        if y not in by_year:
            by_year[y] = []
        by_year[y].append(w["ret"])
    for y in sorted(by_year.keys()):
        yr_rets = by_year[y]
        yr_mean = statistics.mean(yr_rets)
        yr_wr = sum(1 for r in yr_rets if r > 0) / len(yr_rets) * 100
        print(f"  {y:<8} | {len(yr_rets):>4} | {yr_mean*100:>+7.3f}% | {yr_wr:>5.1f}%")

    print(f"\nTHREE-DECOMPOSITION (per-window):")
    print(f"  {'Decomp':<18} | {'total':>10} | {'mean/window':>13} | {'annual%':>9}")
    print(f"  {'-'*55}")
    gross_total = sum(w["ret"] + FEE for w in windows)  # gross before fee
    net_total = sum(rets)
    costs = gross_total - net_total
    print(f"  {'gross (pre-fee)':<18} | {gross_total:>+9.4f} | {gross_total/metrics['n']:+12.6f} | {gross_total/metrics['n']*100*12:+8.4f}%")
    print(f"  {'minus_fees':<18} | {costs:>+9.4f} | {costs/metrics['n']:+12.6f} | -")
    print(f"  {'net':<18} | {net_total:>+9.4f} | {net_total/metrics['n']:+12.6f} | {net_total/metrics['n']*100*12:+8.4f}%")

    print(f"\nVERDICT:")
    net_pos = metrics["mean_ret"] > 0
    excess_pos = excess > 0
    wr_ok = metrics["wr"] > 55
    print(f"  mean > 0?     {net_pos} ({metrics['mean_ret']*100:.4f}%)")
    print(f"  excess > 0?   {excess_pos} ({excess*100:.4f}%)")
    print(f"  WR > 55%?     {wr_ok} ({metrics['wr']:.1f}%)")

    if label == "INSAMPLE" and net_pos and excess_pos and wr_ok:
        print(f"  SURVIVE — hold for OOS")
    elif label == "INSAMPLE":
        kills = []
        if not net_pos: kills.append("mean<=0")
        if not excess_pos: kills.append("excess<=0")
        if not wr_ok: kills.append(f"WR {metrics['wr']:.1f}%<=55%")
        print(f"  KILL — {' + '.join(kills)}")

    return metrics, excess


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    spy = load_daily(args.data)
    print(f"SPY daily: {len(spy)} bars")
    print(f"Range: {spy[0]['date']} .. {spy[-1]['date']}")

    if args.phase == "insample":
        start, end = IS_START, IS_END
        phase_label = "INSAMPLE"
    else:
        start, end = OOS_START, OOS_END
        phase_label = "OOS (ONE-SHOT GATED)"

    windows = get_tom_windows(spy, start, end)
    if not windows:
        print(f"No TOM windows in {phase_label} period")
        return 1

    metrics, excess = report_phase(phase_label, windows, spy, start, end)

    print(f"\n{'='*72}")
    print(f"Window samples:")
    print(f"{'='*72}")
    for w in windows[:5]:
        print(f"  {w['start_date']} → {w['end_date']}: entry={w['entry']:.2f}, exit={w['exit']:.2f}, ret={w['ret']*100:+.3f}%")
    print(f"  ... ({len(windows)} total)")

    # Verdict hash
    import json
    doc = {
        "kernel_id": "S-024",
        "phase": args.phase,
        "n_windows": len(windows),
        "mean_ret": metrics["mean_ret"],
        "wr": metrics["wr"],
        "sharpe": metrics["sharpe"],
        "max_dd": metrics["max_dd"],
        "excess": excess,
    }
    v_hash = hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print(f"\n  verdict_hash: {v_hash}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
