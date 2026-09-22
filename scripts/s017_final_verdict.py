#!/usr/bin/env python3
"""
Combined IS+OOS gate + final verdict for S-017.

Imports the LOCKED kernel functions (sha b577b29d) directly to
re-compute trades on both IS and OOS windows with the REAL parameters.
NO parameter changes. One-shot aggregation only.
"""

import csv
import hashlib
import json
import os
import sys
import random
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from research.backtest.S017_tom_btc import (
    load_prices, load_funding, identify_tom_windows,
    run_backtest, compute_metrics, bootstrap_ci, IS_START, IS_END
)
from factory.graveyard_chain import append_row as graveyard_append

LEDGER = os.path.join(PROJECT_DIR, "factory", "batch_ledger.csv")
BATCH_ID = "S-017-PHASE3"
KERNEL_ID = "S-017"
DATA_SHA = "767c1e0e40284e50ad4d673994be1c9914a4d1f178fb5ae6fcb390b2ae3c7e9e"


def make_verdict_hash(data_hash, returns_hash, metrics, verdict):
    doc = {
        "kernel_id": KERNEL_ID,
        "batch_id": BATCH_ID,
        "phase": "oos+combined",
        "dataset_hash": data_hash,
        "returns_hash": returns_hash,
        "n_combined": metrics["n_combined"],
        "net_pf_combined": metrics["net_pf_combined"],
        "mean_combined": metrics["mean_combined"],
        "ci_lower_90": metrics["ci_lower_90"],
        "oos_pf": metrics["oos_pf"],
        "oos_mean": metrics["oos_mean"],
        "verdict": verdict[0],
        "note": verdict[1],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def main():
    prices = load_prices(os.path.join(PROJECT_DIR, "research/data/crypto/btcusdt_daily_2019_2025.csv"))
    funding = load_funding(os.path.join(PROJECT_DIR, "research/data/crypto/btcusdt_fundingrate_8h.csv"))

    # IS trades (2021-2023)
    is_trades, _ = run_backtest(prices, funding, IS_START, IS_END)
    # OOS trades (2024-2025)
    oos_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    oos_end = datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc)
    oos_trades, _ = run_backtest(prices, funding, oos_start, oos_end)

    combined = is_trades + oos_trades

    print("=" * 72)
    print("S-017 PHASE 3 — OOS CONFIRMATION + COMBINED GATE (REAL RETURNS)")
    print("=" * 72)

    # --- OOS metrics (from real trades) ---
    oos_returns = [t.ret for t in oos_trades]
    oos_n = len(oos_trades)
    oos_wins = sum(1 for t in oos_trades if t.net > 0)
    oos_wr = oos_wins / oos_n if oos_n else 0
    oos_nm = compute_metrics(oos_trades, "net")
    pm = compute_metrics(oos_trades, "price_only")
    fm = compute_metrics(oos_trades, "price_plus_funding")

    print(f"\n--- OOS (2024-01-01..2025-05-13) ---")
    print(f"n={oos_n}  WR={oos_wr:.1%}  WR(price_only)={pm['win_rate']:.1%}")

    print(f"\nTHREE-DECOMPOSITION (OOS):")
    print(f"  price_only:     n={pm['n']}  PF={pm['profit_factor']:.4f}  Ret%={pm['avg_ret']*100:+.4f}")
    print(f"  price+funding:  n={fm['n']}  PF={fm['profit_factor']:.4f}  Ret%={fm['avg_ret']*100:+.4f}")
    print(f"  net:            n={oos_nm['n']}  PF={oos_nm['profit_factor']:.4f}  Ret%={oos_nm['avg_ret']*100:+.4f}")

    # Per-year
    print(f"\nPER-YEAR (OOS net):")
    from collections import defaultdict
    yr_trades = defaultdict(list)
    for t in oos_trades:
        yr_trades[t.year].append(t)
    for yr in sorted(yr_trades):
        ym = compute_metrics(yr_trades[yr], "net")
        pf_str = f"{ym['profit_factor']:.4f}" if ym['profit_factor'] != float('inf') else "inf"
        print(f"  {yr}: n={ym['n']}  mean={ym['avg_ret']*100:+.4f}%  WR={ym['win_rate']:.1%}  PF={pf_str}")

    # Baseline comparison
    all_6d = []
    for i in range(len(prices) - 6 + 1):
        entry = prices[i]["open"]
        exit_price = prices[i + 6 - 1]["close"]
        if oos_start <= prices[i]["time"] <= oos_end:
            all_6d.append((exit_price - entry) / entry)
    baseline_mean = sum(all_6d) / len(all_6d) if all_6d else 0
    oos_mean = sum(oos_returns) / oos_n if oos_n else 0
    print(f"\nBASELINE COMPARISON (OOS):")
    print(f"  TOM mean (n={oos_n}): {oos_mean*100:+.4f}%")
    print(f"  Baseline 6-day (n={len(all_6d)}): {baseline_mean*100:+.4f}%")
    print(f"  Excess: {(oos_mean - baseline_mean)*100:+.4f}%")

    # OOS gate
    print(f"\n--- OOS GATE ---")
    oos_pass = oos_nm["profit_factor"] >= 1.0 and oos_mean > 0
    print(f"  net PF {oos_nm['profit_factor']:.4f} >= 1.0? {oos_nm['profit_factor'] >= 1.0}")
    print(f"  mean {oos_mean:.4f} > 0? {oos_mean > 0}")
    print(f"  OOS GATE: {'PASS' if oos_pass else 'FAIL'}")

    # --- Combined ---
    combined_returns = [t.ret for t in combined]
    cn = len(combined)
    cnm = compute_metrics(combined, "net")
    ci_lower, ci_upper = bootstrap_ci(combined_returns, n_boot=10000, conf=0.90)

    print(f"\n--- COMBINED (IS+OOS) ---")
    print(f"  n={cn}")
    print(f"  net PF={cnm['profit_factor']:.4f}")
    print(f"  mean={cnm['mean']:.4f}")
    print(f"  Bootstrap 90% CI: [{ci_lower:.4f}, {ci_upper:.4f}]")

    print(f"\n--- COMBINED GATES ---")
    g1 = cn >= 50
    g2 = cnm["profit_factor"] >= 1.0
    g3 = ci_lower > 0
    print(f"  n >= 50? {cn >= 50} ({'PASS' if g1 else 'FAIL'})")
    print(f"  net PF >= 1.0? {cnm['profit_factor'] >= 1.0} ({'PASS' if g2 else 'FAIL'})")
    print(f"  CI lower > 0? {ci_lower > 0} ({'PASS' if g3 else 'FAIL'})")

    # --- Final verdict ---
    print(f"\n{'='*72}")
    print("FINAL VERDICT")
    print(f"{'='*72}")

    if oos_pass and g1 and g2 and g3:
        verdict = ("SURVIVE", "OOS PASS + Combined PASS (n>=50, PF>=1.0, CI>0)")
    else:
        reasons = []
        if not oos_pass:
            reasons.append(f"OOS FAIL (PF={oos_nm['profit_factor']:.4f}, mean={oos_mean:.4f})")
        if not g1:
            reasons.append(f"combined n={cn} < 50")
        if not g2:
            reasons.append(f"combined PF={cnm['profit_factor']:.4f} < 1.0")
        if not g3:
            reasons.append(f"CI lower={ci_lower:.4f} <= 0")
        verdict = ("KILL", " + ".join(reasons) + " — S-017 KILLED")

    print(f"  VERDICT: {verdict[0]} — {verdict[1]}")

    returns_hash = hashlib.sha256(
        json.dumps(combined_returns, sort_keys=True).encode()
    ).hexdigest()[:16]

    metrics = {
        "n_combined": cn,
        "net_pf_combined": cnm["profit_factor"],
        "mean_combined": cnm["mean"],
        "ci_lower_90": ci_lower,
        "oos_pf": oos_nm["profit_factor"],
        "oos_mean": oos_mean,
    }
    v_hash = make_verdict_hash(DATA_SHA, returns_hash, metrics, verdict)
    print(f"\n  verdict_hash: {v_hash}")
    print(f"  returns_hash: {returns_hash}")

    # Append ledger
    now = datetime.now(timezone.utc)
    ksha = hashlib.sha256(open(os.path.join(PROJECT_DIR, "research/backtest/S017_tom_btc.py"), "rb").read()).hexdigest()

    if not os.path.exists(LEDGER):
        with open(LEDGER, "w", newline="") as f:
            csv.writer(f).writerow(["batch_id", "kernel_id", "phase", "run_utc",
                                    "dataset_hash", "kernel_hash", "verdict_hash",
                                    "verdict", "note", "status"])
    with open(LEDGER, "a", newline="") as f:
        csv.writer(f).writerow([BATCH_ID, KERNEL_ID, "oos+combined", now.isoformat(),
                                DATA_SHA, ksha, v_hash, verdict[0], verdict[1], "COMPLETED"])
    print(f"\n  LEDGER APPENDED: {BATCH_ID},{KERNEL_ID},oos+combined")

    # Tombstone append if KILL
    if verdict[0] == "KILL":
        print(f"\n--- TOMBSTONE (S017 closure) ---")
        tombstone_row = {
            "id": "S-017",
            "name": "S017_tom_btc",
            "one_liner": "Turn-of-Month LONG swap (3,3) on BTCUSDT perp daily",
            "status": "KILL",
            "parent_id": "",
            "mechanism_hash": "c536fd81f7ce53e9",
            "parameter_hash": "ace65f2c2e85949c",
            "cause_of_death": f"MECHANISM-DEAD: OOS {verdict[1]}",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "verdict_hash": v_hash,
            "batch_id": "S-017-PHASE3",
        }
        result = graveyard_append(tombstone_row)
        print(f"  Graveyard append: {result}")
        print(f"  S-017 KILLED. Thesis 'TOM on BTC' CLOSED permanently.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
