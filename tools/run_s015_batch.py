#!/usr/bin/env python3
"""
tools/run_s015_batch.py — Batch runner for GAP-1 (S-015) IS.

Appends ledger row with verdict hash for S-015.
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(PROJECT, "factory", "batch_ledger.csv")

RESULT = {
    "kernel_id": "S-015",
    "name": "S015_gap_fade",
    "one_liner": "Fade EURUSD overnight gaps: open<prev_close→LONG, open>prev_close→SHORT, ATR stop, target prev close",
    "description": "Fade overnight gaps on EURUSD daily (aggregated from H1), ATR(14) stop, target previous close, 1-day horizon",
    "window": "insample",
    "n": 473,
    "wins": 91,
    "win_rate": 0.1924,
    "net_pf": 0.3015,
    "gross_pf": 0.3233,
    "net_exp": -9.13,
    "gross_exp": -8.63,
    "exits": {"TARGET": 344, "HORIZON": 74, "STOP": 55},
    "verdict": "KILL",
    "note": "PF 0.3015 < 1.0",
    "cause_of_death": "MECHANISM-DEAD",
    "data_file": "research/data/eurusd_1h.csv",
    "data_sha256": "c90278f938bfde92c1658c378e6b6ed54b6bfe703595fcf88dd4ba1b4e10a053",
    "kernel_sha256": hashlib.sha256(open(os.path.join(
        PROJECT, "research", "backtest", "S015_gap_fade.py"), "rb").read()).hexdigest(),
    "batch_id": "GAP-1",
}


def make_verdict_hash(kernel_id, batch_id, phase, data_hash, metrics, verdict):
    doc = {
        "kernel_id": kernel_id,
        "batch_id": batch_id,
        "phase": phase,
        "dataset_hash": data_hash,
        "metrics": metrics,
        "verdict": verdict[0],
        "note": verdict[1],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def main():
    metrics = {
        "n": RESULT["n"],
        "win_rate": RESULT["win_rate"],
        "profit_factor": RESULT["net_pf"],
        "gross_pf": RESULT["gross_pf"],
        "net_exp": RESULT["net_exp"],
        "gross_exp": RESULT["gross_exp"],
        "exits": RESULT["exits"],
    }
    verdict = (RESULT["verdict"], RESULT["note"])
    v_hash = make_verdict_hash(
        RESULT["kernel_id"], RESULT["batch_id"], RESULT["window"],
        RESULT["data_sha256"], metrics, verdict
    )

    now = datetime.now(timezone.utc)
    row = [RESULT["batch_id"], RESULT["kernel_id"], RESULT["window"],
           now.isoformat(), RESULT["data_sha256"], v_hash, "COMPLETED"]

    if not os.path.exists(LEDGER):
        with open(LEDGER, "w", newline="") as f:
            csv.writer(f).writerow(["batch_id", "kernel_id", "phase", "run_utc",
                                    "dataset_hash", "verdict_hash", "status"])
    with open(LEDGER, "a", newline="") as f:
        csv.writer(f).writerow(row)

    print(f"LEDGER ROW APPENDED: {RESULT['batch_id']},{RESULT['kernel_id']},{RESULT['window']}")
    print(f"verdict_hash: {v_hash}")
    print(f"status: COMPLETED")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
