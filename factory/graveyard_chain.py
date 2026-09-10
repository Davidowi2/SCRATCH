"""
factory/graveyard_chain.py — Manual hash-chain append-only mechanism for graveyard.csv.

This is the approved append-only mechanism (Option B from Spec §2).
It does NOT rely on git-signed commits.

How it works:
- Each row in graveyard.csv has a verdict_hash (sha256 of canonical verdict doc)
- Each row also has a chain_hash = sha256(previous_row's chain_hash + current row's verdict_hash)
- The genesis row has chain_hash = sha256("GENESIS" + verdict_hash)
- This creates a tamper-evident chain: modifying any row breaks all subsequent chain_hashes

Rules:
- Append only. Never modify or delete existing rows.
- To append: read last row's chain_hash, compute new row's chain_hash, write new row.
- To verify: recompute all chain_hashes and compare with stored values.
- If verification fails: the graveyard has been tampered with.
"""

import csv
import hashlib
import json
import os

GRAVEYARD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graveyard.csv")
GENESIS = "GENESIS"


def compute_chain_hash(prev_chain_hash, verdict_hash):
    """Compute chain hash from previous chain hash and current verdict hash."""
    return hashlib.sha256((prev_chain_hash + verdict_hash).encode()).hexdigest()


def read_graveyard():
    """Read all rows from graveyard.csv."""
    rows = []
    if not os.path.exists(GRAVEYARD_PATH):
        return rows
    with open(GRAVEYARD_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def verify_chain():
    """Verify the entire chain. Returns (valid, first_invalid_row)."""
    rows = read_graveyard()
    if not rows:
        return True, None
    
    # Genesis row
    expected = compute_chain_hash(GENESIS, rows[0]["verdict_hash"])
    if rows[0].get("chain_hash") != expected:
        return False, 0
    
    # Subsequent rows
    for i in range(1, len(rows)):
        expected = compute_chain_hash(rows[i - 1]["chain_hash"], rows[i]["verdict_hash"])
        if rows[i].get("chain_hash") != expected:
            return False, i
    
    return True, None


def append_row(new_row):
    """
    Append a new row to graveyard.csv with proper chain hashing.
    
    Args:
        new_row: dict with all graveyard columns including 'verdict_hash'
    
    Returns:
        True if successful, False if chain is broken (do not append)
    """
    # Verify existing chain before appending
    valid, bad_row = verify_chain()
    if not valid:
        print(f"CHAIN VERIFICATION FAILED at row {bad_row}. Aborting append.")
        return False
    
    rows = read_graveyard()
    
    # Compute chain hash for new row
    if rows:
        prev_chain_hash = rows[-1]["chain_hash"]
    else:
        prev_chain_hash = GENESIS
    
    new_row["chain_hash"] = compute_chain_hash(prev_chain_hash, new_row["verdict_hash"])
    
    # Append to file
    file_exists = os.path.exists(GRAVEYARD_PATH)
    with open(GRAVEYARD_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=new_row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(new_row)
    
    return True


def init_graveyard():
    """Initialize graveyard with proper headers if it doesn't exist."""
    if not os.path.exists(GRAVEYARD_PATH):
        with open(GRAVEYARD_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "kernel_id", "name", "one_liner", "status", "parent_id",
                "mechanism_hash", "parameter_hash", "cause_of_death",
                "date", "verdict_hash", "batch_id", "chain_hash"
            ])
        print("Initialized graveyard.csv")


if __name__ == "__main__":
    init_graveyard()
    valid, bad_row = verify_chain()
    if valid:
        print("Chain verified: VALID")
    else:
        print(f"Chain verification: FAILED at row {bad_row}")
