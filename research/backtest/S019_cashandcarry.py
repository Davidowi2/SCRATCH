#!/usr/bin/env python3
"""
research/backtest/S019_cashandcarry.py — S-019 Cash & Carry Funding Arbitrage.

Delta-neutral: LONG SPOT BTC + SHORT PERP BTC, collect funding.
Rebalance daily. No price prediction.

PnL per day = funding_received - basis_cost - fees.
THREE-DECOMPOSITION: gross_funding | minus_costs | net.

Per factory/preregistrations/S019_cashandcarry.md.
IS: 2021-01-01..2023-12-31. OOS: 2024-01-01..2025-05-13 (one-shot gated).
"""

import csv
import hashlib
import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from research.data.validate_data_crypto import gate1_audit_crypto

EXPERIMENT_ID = "S-019"
STRATEGY_FAMILY = "CASH_AND_CARRY"
PARAM_DESC = "Delta-neutral LONG spot + SHORT perp, collect 8h funding, daily rebalance, 0.20% fees"

# FEES
ENTRY_FEE_PER_LEG = 0.0005  # 0.05% taker
EXIT_FEE_PER_LEG = 0.0005
FOUR_LEGS_TOTAL = 4 * ENTRY_FEE_PER_LEG  # 0.20% total cost

# WINDOWS
IS_START = datetime(2021, 1, 1, tzinfo=timezone.utc)
IS_END = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
OOS_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
OOS_END = datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc)


def load_funding(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({"time": ts, "rate": float(row["funding_rate"])})
    rows.sort(key=lambda r: r["time"])
    return rows


def load_daily(path):
    """Load daily CSV (timestamp_utc, open, high, low, close, volume)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({
                "time": ts,
                "date": ts.date(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),
            })
    rows.sort(key=lambda r: r["time"])
    return rows


def aggregate_funding_by_day(funding):
    """Sum funding rates per calendar day."""
    daily = {}
    for f in funding:
        d = f["time"].date()
        if d not in daily:
            daily[d] = 0.0
        daily[d] += f["rate"]
    return daily


def run_carry(perp_daily, spot_daily, funding, start, end, friction=FOUR_LEGS_TOTAL):
    """Run delta-neutral cash-and-carry.

    Long spot, short perp. Each day:
      - Receive funding (short perp receives rate if positive)
      - Basis cost = entry (perp - spot) + exit (perp - spot)
      - Fees = friction * position_notional
    """
    funding_by_day = aggregate_funding_by_day(funding)

    # Align perp and spot by date
    perp_by_date = {p["date"]: p for p in perp_daily}
    spot_by_date = {s["date"]: s for s in spot_daily}

    days = sorted(funding_by_day.keys())
    days = [d for d in days if datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc) >= start
            and datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc) <= end]

    periods = []
    cumulative_carry = [0.0]
    cumulative_gross = [0.0]
    cumulative_costs = [0.0]
    neg_count = 0
    total_fees = 0.0

    peak = 0.0
    max_dd = 0.0

    for d in days:
        if d not in perp_by_date:
            continue

        perp = perp_by_date[d]
        spot = spot_by_date.get(d)
        fund_rate = funding_by_day[d]

        # Use perp price as notional (spot ≈ perp for pricing)
        notional = perp["close"]

        # Funding: SHORT perp receives funding when rate is positive
        # We are short perp, so we RECEIVE the funding rate
        gross_funding = fund_rate * notional

        # Basis cost: model perp-spot basis at entry/exit
        if spot is not None:
            basis = perp["close"] - spot["close"]
            basis_cost = abs(basis) * 2  # entry + exit basis cost
        else:
            basis_cost = 0.0  # FLAG: using perp as spot proxy, basis assumed ~0

        # Fees: 4 legs * 0.05% * notional
        fees = friction * notional

        net_carry = gross_funding - basis_cost - fees
        if gross_funding < 0:
            neg_count += 1
        total_fees += fees

        periods.append({
            "date": d,
            "notional": notional,
            "gross_funding": gross_funding,
            "basis_cost": basis_cost,
            "fees": fees,
            "net_carry": net_carry,
            "funding_rate": fund_rate,
        })

        cumulative_carry.append(cumulative_carry[-1] + net_carry)
        cumulative_gross.append(cumulative_gross[-1] + gross_funding)
        cumulative_costs.append(cumulative_costs[-1] + basis_cost + fees)
        peak = max(peak, cumulative_carry[-1])
        if peak > 0:
            dd = (cumulative_carry[-1] - peak) / peak
            max_dd = min(max_dd, dd)

    return periods, cumulative_carry, cumulative_gross, cumulative_costs


def compute_sharpe(returns, annualization_factor=365):
    import statistics
    if len(returns) < 2:
        return 0.0
    mean = statistics.mean(returns)
    std = statistics.stdev(returns)
    if std == 0:
        return float("inf") if mean > 0 else 0.0
    return (mean / std) * (annualization_factor ** 0.5)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--perp", required=True)
    parser.add_argument("--spot", required=True)
    parser.add_argument("--funding", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    # Gate-1 on perp daily
    rep = gate1_audit_crypto(args.perp, interval_minutes=1440, verbose=False)
    if rep["verdict"] == "REJECT":
        print("Gate 1 CRYPTO REJECT: perp data failed validation")
        return 1
    print(f"Gate 1 CRYPTO (perp): {rep['verdict']}")

    perp = load_daily(args.perp)
    spot = load_daily(args.spot)
    funding = load_funding(args.funding)

    perp_sha = hashlib.sha256(open(args.perp, "rb").read()).hexdigest()
    spot_sha = hashlib.sha256(open(args.spot, "rb").read()).hexdigest()
    fund_sha = hashlib.sha256(open(args.funding, "rb").read()).hexdigest()

    print(f"Perp daily: {len(perp)} bars, sha={perp_sha[:16]}")
    print(f"Spot daily: {len(spot)} bars, sha={spot_sha[:16]}")
    print(f"Funding: {len(funding)} settlements, sha={fund_sha[:16]}")

    if args.phase == "insample":
        start, end = IS_START, IS_END
    else:
        start, end = OOS_START, OOS_END

    periods, cum_carry, cum_gross, cum_costs = run_carry(perp, spot, funding, start, end)

    total_gross = sum(p["gross_funding"] for p in periods)
    total_basis = sum(p["basis_cost"] for p in periods)
    total_fees = sum(p["fees"] for p in periods)
    total_net = sum(p["net_carry"] for p in periods)

    net_returns = [p["net_carry"] / p["notional"] if p["notional"] > 0 else 0 for p in periods]
    gross_returns = [p["gross_funding"] / p["notional"] if p["notional"] > 0 else 0 for p in periods]

    sharpe = compute_sharpe(net_returns)
    max_dd = min(cum_carry) / max(cum_carry) if max(cum_carry) > 0 else 0
    neg_pct = sum(1 for p in periods if p["gross_funding"] < 0) / len(periods) if periods else 0

    print(f"\n{'='*72}")
    print(f"S-019 CASH & CARRY — {args.phase.upper()}")
    print(f"{'='*72}")
    print(f"Direction: LONG spot + SHORT perp | Rebalance: daily | Fees: {FOUR_LEGS_TOTAL*100}% total (4 legs)")
    print(f"Periods (days): {len(periods)}")
    print(f"Notional (per day): BTC price as proxy")

    print(f"\n{'='*72}")
    print("THREE-DECOMPOSITION TABLE (cumulative)")
    print(f"{'='*72}")
    print(f"{'Decomp':<16} | {'total':>12} | {'%/day':>8} | {'annualized%':>12}")
    print("-" * 55)

    for key, name in [("gross_funding", "gross_funding"), ("fees+basis", "minus_costs"), ("net_carry", "net")]:
        if key == "fross_funding":
            vals = [p["gross_funding"] for p in periods]
        elif key == "minus_costs":
            vals = [-(p["basis_cost"] + p["fees"]) for p in periods]
        else:
            vals = [p["net_carry"] for p in periods]
        total = sum(vals)
        daily_avg = total / len(periods) if periods else 0
        # Annualize: daily return * 365
        ann = sum(net_returns[i] for i in range(len(net_returns))) / len(net_returns) * 365 * 100 if key == "net_carry" else 0
        print(f"{name:<16} | {total:>+12.2f} | {daily_avg:>+7.2f} | {ann:>+11.4f}%")

    print(f"\n{'='*72}")
    print("SUMMARY METRICS")
    print(f"{'='*72}")
    print(f"  Cumulative net carry:      {cum_carry[-1]:>+12.2f} USD")
    print(f"  Total gross funding:       {total_gross:>+12.2f} USD")
    print(f"  Total fees:                {total_fees:>+12.2f} USD")
    print(f"  Total basis cost:          {total_basis:>+12.2f} USD")
    print(f"  Net Sharpe (annualized):   {sharpe:.4f}")
    print(f"  Max drawdown:              {max_dd*100:+.4f}%")
    print(f"  Neg-funding % of periods:  {neg_pct:.1%}")
    print(f"  Mean net carry/day:        {sum(net_returns)/len(net_returns)*100:+.4f}%")

    print(f"\n{'='*72}")
    print("NET CARRY CURVE (sampled)")
    print(f"{'='*72}")
    step = max(1, len(cum_carry) // 15)
    print(f"{'Date':<12} | {'gross':>10} | {'costs':>10} | {'net':>10} | {'cum_net':>10}")
    print("-" * 60)
    for i in range(0, len(periods), step):
        p = periods[i]
        cum = cum_carry[i+1] if i+1 < len(cum_carry) else cum_carry[-1]
        print(f"{p['date']:<12} | {p['gross_funding']:>+9.2f} | {p['basis_cost']+p['fees']:>+9.2f} | {p['net_carry']:>+9.2f} | {cum:>+9.2f}")

    # Verdict per prereg
    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    carry_positive = cum_carry[-1] > 0
    sharpe_positive = sharpe > 0
    dd_ok = abs(max_dd) < 0.05

    print(f"  Net carry curve positive?   {carry_positive} (final: {cum_carry[-1]:+.2f})")
    print(f"  Net Sharpe > 0?              {sharpe_positive} (Sharpe: {sharpe:.4f})")
    print(f"  Max DD < 5%?                 {dd_ok} (DD: {max_dd*100:.4f}%)")

    if carry_positive and sharpe_positive and dd_ok:
        verdict = ("SURVIVE", "positive carry + positive Sharpe + DD<5%")
    else:
        kills = []
        if not carry_positive:
            kills.append("negative carry")
        if not sharpe_positive:
            kills.append("negative Sharpe")
        if not dd_ok:
            kills.append(f"DD {max_dd*100:.2f}% >= 5%")
        verdict = ("KILL", " + ".join(kills))

    print(f"\n  VERDICT: {verdict[0]} — {verdict[1]}")

    import json
    doc = {
        "kernel_id": "S-019",
        "phase": args.phase,
        "perp_sha": perp_sha,
        "spot_sha": spot_sha,
        "funding_sha": fund_sha,
        "n_periods": len(periods),
        "net_carry": cum_carry[-1],
        "sharpe": sharpe,
        "max_dd": max_dd,
        "neg_pct": neg_pct,
        "verdict": verdict[0],
        "note": verdict[1],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    v_hash = hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print(f"\n  verdict_hash: {v_hash}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
