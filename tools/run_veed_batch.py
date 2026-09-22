#!/usr/bin/env python3
"""
tools/run_veed_batch.py — Batch runner for VEED-1 (S-013) IS.

Appends ledger row with verdict hash for S-013.
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(PROJECT, "factory", "batch_ledger.csv")

# S-013 IS result (from logs/s013_is.log)
RESULT = {
    "kernel_id": "S-013",
    "name": "S013_veed_fade",
    "one_liner": "Fade VEED v1.1 events, stop at event extreme, 1.5R, taker+funding",
    "description": "Fade VEED v1.1 events (sell→LONG, buy→SHORT), stop at event-bar extreme, target 1.5R, taker 0.04%/leg + funding 0.01%/8h",
    "window": "insample",
    "n": 1229,
    "wins": 321,
    "win_rate": 0.2612,
    "net_pf": 0.3860,
    "gross_pf": 0.7287,
    "gross_wr": 0.2750,
    "gross_exp": -12.09,
    "net_exp": -39.92,
    "avg_taker_fee": 27.8234,
    "avg_funding": 0.0,
    "exits": {"TARGET": 338, "STOP": 891},
    "verdict": "KILL",
    "note": "PF 0.3860 < 1.0",
    "cause_of_death": "MECHANISM-DEAD",
    "frozen_params": {"X": 0.01, "Y": 0.25, "N": 4032},
    "data_file": "research/data/crypto/btcusdt_5m_tradecount_is_2021_2023.csv",
    "data_sha256": "63b02ddd852937aba35d3aae78388215b07b7ff20c18c945677a86e607639d5a",
    "kernel_sha256": hashlib.sha256(open(os.path.join(
        PROJECT, "research", "backtest", "S013_veed_fade.py"), "rb").read()).hexdigest(),
    "batch_id": "VEED-1",
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
        "gross_wr": RESULT["gross_wr"],
        "gross_exp": RESULT["gross_exp"],
        "net_exp": RESULT["net_exp"],
        "exits": RESULT["exits"],
        "avg_taker_fee": RESULT["avg_taker_fee"],
        "avg_funding": RESULT["avg_funding"],
    }
    verdict = (RESULT["verdict"], RESULT["note"])
    v_hash = make_verdict_hash(
        RESULT["kernel_id"], RESULT["batch_id"], RESULT["window"],
        RESULT["data_sha256"], metrics, verdict
    )

    now = datetime.now(timezone.utc)
    row = [RESULT["batch_id"], RESULT["kernel_id"], RESULT["window"],
           now.isoformat(), RESULT["data_sha256"], v_hash, "COMPLETED"]

    # Append to ledger
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
