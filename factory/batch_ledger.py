"""
factory/batch_ledger.csv — One-shot execution ledger (append-only)

Columns:
  batch_id: e.g., B-000
  kernel_id: e.g., N01_inverted
  phase: insample or oos
  run_utc: ISO timestamp
  dataset_hash: sha256 of dataset file
  verdict_hash: sha256 of canonical verdict document
  status: COMPLETED or PLUMBING-ERROR

Rules:
- Before running IS, check for existing COMPLETED IS row.
- Before running OOS, check for existing COMPLETED OOS row.
- If row exists, refuse to run.
- Plumbing errors before trade generation do not consume a one-shot window.
- Append only. Never overwrite.
"""

import csv
import hashlib
import os
from datetime import datetime

LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_ledger.csv")

HEADER = ["batch_id", "kernel_id", "phase", "run_utc", "dataset_hash", "verdict_hash", "status"]


def init_ledger():
    """Create ledger file with header if it doesn't exist."""
    if not os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(HEADER)
        print(f"Initialized: {LEDGER_PATH}")


def read_ledger():
    """Read all ledger rows."""
    rows = []
    if not os.path.exists(LEDGER_PATH):
        return rows
    with open(LEDGER_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def check_existing(batch_id, kernel_id, phase):
    """Check if a completed run already exists."""
    rows = read_ledger()
    for row in rows:
        if (row["batch_id"] == batch_id and 
            row["kernel_id"] == kernel_id and 
            row["phase"] == phase and
            row["status"] == "COMPLETED"):
            return True
    return False


def append_ledger(batch_id, kernel_id, phase, dataset_hash, verdict_hash, status):
    """Append a row to the ledger."""
    run_utc = datetime.utcnow().isoformat()
    with open(LEDGER_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([batch_id, kernel_id, phase, run_utc, dataset_hash, verdict_hash, status])


def get_is_anchor(batch_id, kernel_id):
    """Get the IS completion timestamp for cool-off check."""
    rows = read_ledger()
    for row in rows:
        if (row["batch_id"] == batch_id and 
            row["kernel_id"] == kernel_id and 
            row["phase"] == "insample" and
            row["status"] == "COMPLETED"):
            return datetime.fromisoformat(row["run_utc"])
    return None


if __name__ == "__main__":
    init_ledger()
    print("Ledger initialized.")
