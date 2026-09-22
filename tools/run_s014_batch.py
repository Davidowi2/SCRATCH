#!/usr/bin/env python3
"""
tools/run_s014_batch.py — Batch runner for S-014 FRMR IS.

Appends ledger row with verdict hash for S-014.
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(PROJECT, "factory", "batch_ledger.csv")

RESULT = {
    "kernel_id": "S-014",
    "name": "S014_funding_fade",
    "one_liner": "FRMR: F>=+0.05% SHORT, F<=-0.05% LONG, fixed 8h, taker+funding",
    "description": "Funding Rate Mean Reversion: SHORT when F>=+0.05%, LONG when F<=-0.05%, hold 8h, exit at next settlement",
    "window": "insample",
    "threshold": 0.0005,
    "short_n": 202,
    "short_wr": 0.4901,
    "short_net_pf": 0.9668,
    "short_price_only_pf": 0.9834,
    "short_price_fund_pf": 1.0758,
    "long_n": 5,
    "long_wr": 0.6000,
    "long_net_pf": 5.6216,
    "total_n": 207,
    "total_wr": 0.4928,
    "total_net_pf": 1.0041,
    "verdict": "KILL",
    "note": "PF 0.9668 < 1.0",
    "cause_of_death": "MECHANISM-DEAD",
    "frozen_params": {"threshold": 0.0005, "horizon_hours": 8},
    "data_file": "research/data/crypto/btcusdt_fundingrate_8h.csv",
    "data_sha256": "a6e42ffb4fa6f5ea046b9f28890869f69244d1a9607a992927e0854e83f9c436",
    "price_data_sha256": "63b02ddd852937aba35d3aae78388215b07b7ff20c18c945677a86e607639d5a",
    "kernel_sha256": hashlib.sha256(open(os.path.join(
        PROJECT, "research", "backtest", "S014_funding_fade.py"), "rb").read()).hexdigest(),
    "batch_id": "FRMR-1",
}


def make_verdict_hash():
    doc = {
        "kernel_id": RESULT["kernel_id"],
        "batch_id": RESULT["batch_id"],
        "phase": RESULT["window"],
        "dataset_hash": RESULT["data_sha256"],
        "short_n": RESULT["short_n"],
        "short_net_pf": RESULT["short_net_pf"],
        "short_gross_pf": RESULT["short_price_fund_pf"],
        "long_n": RESULT["long_n"],
        "long_net_pf": RESULT["long_net_pf"],
        "verdict": RESULT["verdict"],
        "autopsy": RESULT["cause_of_death"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def main():
    v_hash = make_verdict_hash()
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
