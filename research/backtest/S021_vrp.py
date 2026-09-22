#!/usr/bin/env python3
"""
research/backtest/S021_vrp.py — S-021 Volatility Risk Premium Harvest.

Persistent short-vol: collect VIX implied vol premium, pay SPX realized
moves. Always-on baseline (no timing filters). Pure VRP first.

PnL model (daily):
  gross_VRP = (VIX_{t-1}/100)/sqrt(252)   # implied vol premium collected
  realized = abs(SPX_return_t)            # absolute realized move paid
  gross = gross_VRP - realized
  fees = 0.05% per day
  net = gross - fees

Per factory/preregistrations/S021_vrp.md.
IS: 2015-01-01..2020-12-31. OOS: 2021-01-01..2025-05-13 (one-shot gated).
"""

import csv
import hashlib
import os
import sys
from datetime import datetime, timezone
import math

import statistics

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

EXPERIMENT_ID = "S-021"
STRATEGY_FAMILY = "VRP_HARVEST"
PARAM_DESC = "persistent_short_vol_daily_vix_minus_spx_abs_move_0.05pct_fees"

IS_START = datetime(2015, 1, 1, tzinfo=timezone.utc)
IS_END = datetime(2020, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
OOS_START = datetime(2021, 1, 1, tzinfo=timezone.utc)
OOS_END = datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc)

SQRT_252 = math.sqrt(252)
DAILY_FEE = 0.0005  # 0.05% per day


def load_daily(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("close") or row["close"] in ("", "null", "None"):
                continue  # skip non-trading days (e.g. VIX holidays)
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({"time": ts, "close": float(row["close"])})
    return sorted(rows, key=lambda r: r["time"])


def compute_returns(daily):
    """Compute simple returns: (close_t - close_{t-1}) / close_{t-1}."""
    returns = []
    for i in range(1, len(daily)):
        r = (daily[i]["close"] - daily[i-1]["close"]) / daily[i-1]["close"]
        returns.append({"time": daily[i]["time"], "close": daily[i]["close"], "return": r})
    return returns


def run_vrp(vix_daily, spx_daily, start, end):
    """Run persistent short-vol VRP harvest.

    daily_return = (VIX_{t-1}/100)/sqrt(252) - abs(SPX_return_t) - fee
    """
    vix_returns = compute_returns(vix_daily)
    spx_returns = compute_returns(spx_daily)

    vix_by_time = {r["time"].date(): r for r in vix_returns}
    spx_by_time = {r["time"].date(): r for r in spx_returns}

    common_dates = sorted(set(vix_by_time.keys()) & set(spx_by_time.keys()))
    common_dates = [d for d in common_dates
                    if datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc) >= start
                    and datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc) <= end]

    periods = []
    for i in range(1, len(common_dates)):
        d_prev = common_dates[i - 1]
        d_curr = common_dates[i]

        vix_prev = vix_by_time[d_prev]
        spx_curr = spx_by_time.get(d_curr)
        if spx_curr is None:
            continue

        # VIX_{t-1} is the previous day's VIX (implied vol for next period)
        vix_close = vix_prev["close"]
        spx_ret = spx_curr["return"]

        gross_vrp = (vix_close / 100.0) / SQRT_252  # implied vol premium
        realized_cost = abs(spx_ret)  # absolute realized move
        gross = gross_vrp - realized_cost
        fees = DAILY_FEE
        net = gross - fees

        periods.append({
            "date": d_curr,
            "vix": vix_close,
            "spx_return": spx_ret,
            "gross_vrp": gross_vrp,
            "realized_cost": realized_cost,
            "gross": gross,
            "fees": fees,
            "net": net,
        })

    return periods


def compute_sharpe(returns, annualization_factor=252):
    if len(returns) < 2:
        return 0.0
    mean = statistics.mean(returns)
    std = statistics.stdev(returns)
    if std == 0:
        return float("inf") if mean > 0 else 0.0
    return (mean / std) * (annualization_factor ** 0.5)


def max_drawdown(cum_returns):
    peak = 0.0
    max_dd = 0.0
    for cr in cum_returns:
        peak = max(peak, cr)
        if peak > 0:
            dd = (cr - peak) / peak
            max_dd = min(max_dd, dd)
    return max_dd


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--vix", required=True)
    parser.add_argument("--spx", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    vix = load_daily(args.vix)
    spx = load_daily(args.spx)

    vix_sha = hashlib.sha256(open(args.vix, "rb").read()).hexdigest()
    spx_sha = hashlib.sha256(open(args.spx, "rb").read()).hexdigest()

    print(f"VIX: {len(vix)} bars, sha={vix_sha[:16]}")
    print(f"SPX: {len(spx)} bars, sha={spx_sha[:16]}")

    if args.phase == "insample":
        start, end = IS_START, IS_END
    else:
        start, end = OOS_START, OOS_END

    periods = run_vrp(vix, spx, start, end)

    net_returns = [p["net"] for p in periods]
    gross_vrp_returns = [p["gross_vrp"] for p in periods]
    realized_costs = [p["realized_cost"] for p in periods]

    # Cumulative
    cum_net = [0.0]
    for p in periods:
        cum_net.append(cum_net[-1] + p["net"])

    total_gross_vrp = sum(gross_vrp_returns)
    total_realized = sum(realized_costs)
    total_fees = len(periods) * DAILY_FEE
    total_net = cum_net[-1]

    sharpe = compute_sharpe(net_returns)
    max_dd = max_drawdown(cum_net)
    worst_day = min(net_returns) if net_returns else 0

    # Skewness and kurtosis
    n = len(net_returns)
    mean = statistics.mean(net_returns)
    std = statistics.stdev(net_returns) if n > 1 else 0
    if std > 0:
        skew = statistics.mean([(r - mean) / std**3 for r in net_returns]) if n > 2 else 0
        # Population skew: sum((r-mean)^3)/n / std^3
        skew = sum((r - mean)**3 for r in net_returns) / (n * std**3) / std
        # Correct kurtosis
        m2 = sum((r - mean)**2 for r in net_returns) / n
        m4 = sum((r - mean)**4 for r in net_returns) / n
        kurtosis = (m4 / m2**2) - 3 if m2 > 0 else 0
    else:
        skew = 0
        kurtosis = 0

    profitable_days = sum(1 for r in net_returns if r > 0) / n if n > 0 else 0

    print(f"\n{'='*72}")
    print(f"S-021 VRP HARVEST — {args.phase.upper()}")
    print(f"{'='*72}")
    print(f"Model: (VIX_prev/100)/sqrt(252) - abs(SPX_return) - 0.05%")
    print(f"Position: ALWAYS-ON short vol (no timing filters)")
    print(f"Days: {len(periods)}")

    print(f"\n{'='*72}")
    print("THREE-DECOMPOSITION TABLE")
    print(f"{'='*72}")
    print(f"{'Decomp':<14} | {'total':>14} | {'mean/day':>10} | {'annual%':>10}")
    print("-" * 55)
    for key, label, vals in [
        ("gross_vrp", "gross_VRP", gross_vrp_returns),
        ("costs", "minus_costs", [-(p["realized_cost"] + p["fees"]) for p in periods]),
        ("net", "net", net_returns),
    ]:
        total = sum(vals)
        daily_mean = total / len(vals) if vals else 0
        ann = daily_mean * 252 * 100
        print(f"{label:<14} | {total:>+13.4f} | {daily_mean:>+9.6f} | {ann:>+9.4f}%")

    print(f"\n{'='*72}")
    print("SUMMARY METRICS")
    print(f"{'='*72}")
    print(f"  Total gross VRP collected:   {total_gross_vrp:+.4f}")
    print(f"  Total realized cost:         {total_realized:+.4f}")
    print(f"  Total fees:                  {total_fees:+.4f}")
    print(f"  Cumulative net return:       {total_net:+.4f}  ({total_net*100:.2f}%)")
    print(f"  Net Sharpe (annualized):     {sharpe:.4f}")
    print(f"  Max drawdown:                {max_dd*100:.4f}%")
    print(f"  Worst single-day loss:       {worst_day*100:.4f}%")
    print(f"  Return skewness:             {skew:.4f}")
    print(f"  Return kurtosis:             {kurtosis:.4f}")
    print(f"  % days profitable:           {profitable_days:.1%}")

    # Flag March 2020 and Feb 2018
    print(f"\n{'='*72}")
    print("TAIL-RISK FLAGS (IS window only)")
    print(f"{'='*72}")
    for flag_name, flag_dates in [
        ("March 2020", [(datetime(y, m, d, tzinfo=timezone.utc)) for y in [2020] for m in [3] for d in range(1, 32)]),
        ("Feb 2018", [(datetime(y, m, d, tzinfo=timezone.utc)) for y in [2018] for m in [2] for d in range(1, 29)]),
    ]:
        flag_set = set(d.date() for d in flag_dates)
        losses = [p for p in periods if p["date"] in flag_set and p["net"] < 0]
        worst = min(losses, key=lambda p: p["net"]) if losses else None
        if worst:
            print(f"  {flag_name}: worst day net={worst['net']*100:.2f}% on {worst['date']} (VIX={worst['vix']:.1f}, SPX_ret={worst['spx_return']*100:.2f}%)")
        else:
            print(f"  {flag_name}: no negative days in period")

    # Verdict
    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    sharpe_ok = sharpe > 0
    dd_ok = abs(max_dd) < 0.25
    tail_ok = abs(worst_day) < 0.08

    print(f"  Net Sharpe > 0?         {sharpe_ok} ({sharpe:.4f})")
    print(f"  Max DD < 25%?           {dd_ok} ({max_dd*100:.4f}%)")
    print(f"  Worst-day > -8%?        {tail_ok} ({worst_day*100:.4f}%)")

    all_pass = sharpe_ok and dd_ok and tail_ok
    if all_pass:
        verdict = "SURVIVE"
        note = "Sharpe>0, DD<25%, tail>-8%"
    else:
        kills = []
        if not sharpe_ok: kills.append("Sharpe<=0")
        if not dd_ok: kills.append(f"DD {max_dd*100:.1f}%>=25%")
        if not tail_ok: kills.append(f"tail {worst_day*100:.1f}%<-8%")
        verdict = "KILL"
        note = " + ".join(kills)

    print(f"\n  VERDICT: {verdict} — {note}")

    import json
    doc = {
        "kernel_id": "S-021",
        "phase": args.phase,
        "vix_sha": vix_sha,
        "spx_sha": spx_sha,
        "n_days": len(periods),
        "net_return": total_net,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "worst_day": worst_day,
        "verdict": verdict,
        "note": note,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    v_hash = hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print(f"\n  verdict_hash: {v_hash}")

    return 0, v_hash


if __name__ == "__main__":
    sys.exit(main()[0])
