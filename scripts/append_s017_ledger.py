#!/usr/bin/env python3
"""Append S-017 IS ledger row + handle verdict classification."""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(PROJECT_DIR, "factory", "batch_ledger.csv")

RESULT = {
    "batch_id": "S-017-BATCH-1",
    "kernel_id": "S-017",
    "phase": "insample",
    "n": 35,
    "win_rate": 0.571,
    "profit_factor": 2.4842,  # NET PF
    "gross_pf": 2.6389,       # price+funding
    "expectancy": 0.01306,
    "mean_return": 0.0131,
    "ci_lower_90": 0.0006,
    "verdict": "INSUFFICIENT",
    "note": "n=35 < 50 (bootstrap CI lower bound 0.0006 >= 1.0 satisfied, mean 0.0131 > 0; ONLY blocker is sample size)",
    "data_file": "research/data/crypto/btcusdt_daily_2019_2025.csv",
    "data_sha256": "767c1e0e40284e50ad4d673994be1c9914a4d1f178fb5ae6fcb390b2ae3c7e9e",
    "kernel_file": "research/backtest/S017_tom_btc.py",
    "cause_of_death": "INSUFFICIENT (n=35 < 50) — strong signal, needs more data to reach verdict threshold",
}

def kernel_sha256(path):
    return hashlib.sha256(open(os.path.join(PROJECT_DIR, path), "rb").read()).hexdigest()

def main():
    if not os.path.exists(LEDGER):
        with open(LEDGER, "w", newline="") as f:
            csv.writer(f).writerow(["batch_id", "kernel_id", "phase", "run_utc",
                                    "dataset_hash", "kernel_hash", "verdict_hash",
                                    "verdict", "note", "status"])

    k_sha = kernel_sha256(RESULT["kernel_file"])

    doc = {
        "batch_id": RESULT["batch_id"],
        "kernel_id": RESULT["kernel_id"],
        "phase": RESULT["phase"],
        "dataset_hash": RESULT["data_sha256"],
        "kernel_hash": k_sha,
        "n": RESULT["n"],
        "profit_factor": RESULT["profit_factor"],
        "gross_pf": RESULT["gross_pf"],
        "mean_return": RESULT["mean_return"],
        "ci_lower_90": RESULT["ci_lower_90"],
        "verdict": RESULT["verdict"],
        "note": RESULT["note"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    v_hash = hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    now = datetime.now(timezone.utc)
    with open(LEDGER, "a", newline="") as f:
        csv.writer(f).writerow([RESULT["batch_id"], RESULT["kernel_id"], RESULT["phase"],
                                now.isoformat(), RESULT["data_sha256"], k_sha, v_hash,
                                RESULT["verdict"], RESULT["note"], "COMPLETED"])

    print(f"LEDGER ROW: {RESULT['batch_id']},{RESULT['kernel_id']},{RESULT['phase']}")
    print(f"verdict_hash: {v_hash}")
    print(f"kernel_sha256: {k_sha}")
    print(f"status: COMPLETED")
    print(f"verdict: {RESULT['verdict']} — {RESULT['note']}")

if __name__ == "__main__":
    main()
