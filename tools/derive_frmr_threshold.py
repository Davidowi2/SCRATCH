#!/usr/bin/env python3
"""
tools/derive_frmr_threshold.py — FRMR Phase 1: lookahead-free threshold derivation.

NO backtest, NO kernel, NO P&L. Data-only derivation on the 2020 HOLDOUT.

Per directive FRMR_PHASE1:
  - Signal: F_{T-8h} >= x (lookahead-free, previous settlement's rate)
  - Entry: at/after settlement T, capturing F_T
  - carry = mean(F_T | F_{T-8h} >= x)
  - Threshold rule: lowest x where carry > 0.10% AND n >= 50
"""

import csv
import os
from datetime import datetime, timedelta, timezone

HOLDOUT_START = datetime(2020, 1, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2020, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
THRESHOLDS = [0.0005, 0.00075, 0.0010, 0.0015]
FEE_ROUND_TRIP = 0.0010  # 0.10%


def load_funding(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rate = float(row["funding_rate"])
            rows.append({"time": ts, "rate": rate})
    rows.sort(key=lambda r: r["time"])
    return rows


def main():
    funding_path = "research/data/crypto/btcusdt_fundingrate_8h.csv"
    all_funding = load_funding(funding_path)

    # Restrict to 2020 holdout
    holdout = [f for f in all_funding if HOLDOUT_START <= f["time"] <= HOLDOUT_END]

    print("=" * 72)
    print("FRMR Phase 1 — Lookahead-Free Threshold Derivation")
    print("2020 HOLDOUT (2021-2023 IS reserved for test)")
    print("=" * 72)
    print(f"Total settlements in 2020 holdout: {len(holdout)}")
    print(f"Range: {holdout[0]['time']} .. {holdout[-1]['time']}")

    # Skew table
    pos = sum(1 for f in holdout if f["rate"] > 0)
    neg = sum(1 for f in holdout if f["rate"] < 0)
    zero = sum(1 for f in holdout if f["rate"] == 0)

    print(f"\n{'='*72}")
    print("HOLDOUT SKEW TABLE")
    print(f"{'='*72}")
    print(f"Positive rates: {pos} ({100*pos/len(holdout):.1f}%)")
    print(f"Negative rates: {neg} ({100*neg/len(holdout):.1f}%)")
    print(f"Zero rates:     {zero} ({100*zero/len(holdout):.1f}%)")
    print(f"Mean: {sum(f['rate'] for f in holdout)/len(holdout)*100:.6f}%")

    # Build F_{T-8h} -> F_T pairs
    # For each settlement at T, find the rate at T-8h (previous settlement)
    settlement_times = {f["time"]: f["rate"] for f in holdout}

    pairs = []
    for f in holdout:
        t = f["time"]
        t_minus_8h = t - timedelta(hours=8)
        if t_minus_8h in settlement_times:
            f_prev = settlement_times[t_minus_8h]
            f_curr = f["rate"]
            pairs.append({"signal": f_prev, "carry": f_curr, "time": t})

    print(f"\nPairs (F_{{T-8h}}, F_T) constructed: {len(pairs)}")

    # Per-threshold analysis
    print(f"\n{'='*72}")
    print("PER-THRESHOLD ANALYSIS")
    print(f"{'='*72}")
    print(f"{'Threshold':>10} | {'n':>5} | {'carry%':>10} | {'margin%':>10} | viable?")
    print("-" * 55)

    viable = None
    for x in THRESHOLDS:
        # Short arm: signal F_{T-8h} >= x
        matches = [p for p in pairs if p["signal"] >= x]
        n = len(matches)
        if n > 0:
            carry = sum(p["carry"] for p in matches) / n
            margin = carry - FEE_ROUND_TRIP
        else:
            carry = 0.0
            margin = -FEE_ROUND_TRIP

        is_viable = (carry > FEE_ROUND_TRIP) and (n >= 50)
        if is_viable and viable is None:
            viable = x

        print(f"{x*100:>9.4f}% | {n:>5} | {carry*100:>+9.6f}% | {margin*100:>+9.6f}% | {'YES' if is_viable else 'no'}")

    # Long arm (F_{T-8h} <= -x) for reference
    print(f"\n{'='*72}")
    print("LONG ARM (for reference only)")
    print(f"{'='*72}")
    print(f"{'Threshold':>10} | {'n':>5} | {'carry%':>10}")
    print("-" * 40)
    for x in THRESHOLDS:
        matches = [p for p in pairs if p["signal"] <= -x]
        n = len(matches)
        if n > 0:
            carry = sum(p["carry"] for p in matches) / n
        else:
            carry = 0.0
        print(f"{x*100:>9.4f}% | {n:>5} | {carry*100:>+9.6f}%")

    # Verdict
    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    if viable is not None:
        print(f"DERIVED THRESHOLD: {viable*100}% (lowest x where carry > 0.10% AND n >= 50)")
        print(f"FRMR is STRUCTURALLY VIABLE at threshold {viable*100}%")
    else:
        print("FRMR STRUCTURALLY NON-VIABLE")
        print("No threshold qualifies: carry <= 0.10% or n < 50 for all candidates.")
        print("Thesis CLOSED on BTC perps.")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
