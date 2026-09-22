#!/usr/bin/env python3
"""Append S-018 IS ledger row."""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(PROJECT_DIR, "factory", "batch_ledger.csv")

RESULT = {
    "batch_id": "S-018-BATCH-1",
    "kernel_id": "S-018",
    "phase": "insample",
    "n": 67,
    "win_rate": 0.418,
    "profit_factor": 0.6481,  # NET PF
    "gross_pf": 0.6586,       # price_only (= price+funding for FX spot)
    "mean_return": -0.00271,
    "ci_lower_90": -0.0053,
    "verdict": "KILL",
    "note": "IS n=67, net PF=0.6481 < 1.0, WR=41.8%, bootstrap CI [-0.0053, -0.0000]; DXY Z>2 signal does not predict EURUSD decline; 79% stop hits",
    "data_file": "research/data/eurusd_1h.csv",
    "data_sha256": "c90278f938bfde92c1658c378e6b6ed54b6bfe703595fcf88dd4ba1b4e10a053",
    "kernel_file": "research/backtest/S018_macro_gravity.py",
    "cause_of_death": "MECHANISM-DEAD: net PF 0.6481 < 1.0, stops dominate 53/67, DXY extreme signal fails to predict EURUSD decline",
}


def main():
    if not os.path.exists(LEDGER):
        with open(LEDGER, "w", newline="") as f:
            csv.writer(f).writerow(["batch_id", "kernel_id", "phase", "run_utc",
                                    "dataset_hash", "kernel_hash", "verdict_hash",
                                    "verdict", "note", "status"])

    k_sha = hashlib.sha256(open(os.path.join(PROJECT_DIR, RESULT["kernel_file"]), "rb").read()).hexdigest()

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
