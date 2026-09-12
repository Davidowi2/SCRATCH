"""
research/backtest/run_noise_batch.py — Phase 2 Noise Control Batch Runner

Executes the 10 noise kernels through the IS -> OOS ladder and generates
the official Phase 2 Batch Report (Spec §11).

FROZEN GATES (applied mechanically):
- IS: n<50 INSUFFICIENT, PF<1.0 KILL, WR<45% KILL, PF 1.0-1.15 DANGER, PF>=1.15 PASS
- OOS: n<50 INSUFFICIENT, PF<1.0 KILL, WR<45% KILL, WR drop>15pp KILL, PF 1.0-1.15 DANGER, PF>=1.15 PASS-OOS

One shot per window per kernel. 24h cool-off between IS and OOS.
No parameter changes. No double execution.
"""

import csv
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESEARCH_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(RESEARCH_DIR)

# Frozen windows
IS_START = "2021-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2025-05-13"

# Frozen gates (DO NOT change without owner approval)
MIN_IS_TRADES = 50
MIN_OOS_TRADES = 50
MIN_PF = 1.0
MIN_PF_PASS = 1.15
MIN_WR = 0.45
MAX_WR_DROP_PP = 15

# Cool-off
COOL_OFF_HOURS = 24

# Batch config
BATCH_ID = "B-000"
PHASE_IS = "insample"
PHASE_OOS = "oos"

# Noise kernels (in order)
NOISE_KERNELS = [
    ("N01_inverted", "Inverted entry (continuation with inverted exit)"),
    ("N02_random_entry", "Random entry every 10th bar"),
    ("N03_shuffled_returns", "Shuffled close prices (destroyed time-series)"),
    ("N04_fixed_stop", "Fixed random pip SL/TP"),
    ("N05_mean_avoidance", "Enters only when |Z|<0.5"),
    ("N06_lag_entry", "Enters 3 bars AFTER signal (stale edge)"),
    ("N07_opposite_session", "Trades London/NY only"),
    ("N08_random_stop", "Random SD multiplier for stop"),
    ("N09_half_sized", "Exit at 0.5 SD instead of 1.0 SD"),
    ("N10_always_long", "Always LONG on every Asian bar"),
]


def load_kernel(name):
    """Dynamically load a noise kernel module."""
    path = os.path.join(SCRIPT_DIR, f"{name}.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compute_file_hash(path):
    """Compute sha256 hash of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def compute_metrics(trades):
    """Compute performance metrics from trades."""
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "exits": {}}

    wins = [t for t in trades if t.pips > 0]
    gross_profit = sum(t.pips for t in wins)
    gross_loss = -sum(t.pips for t in trades if t.pips <= 0)

    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        equity += t.pips
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1

    return {
        "n": len(trades), "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "gross_profit_pips": gross_profit, "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades),
        "max_dd_pips": max_dd, "exits": exits,
    }


def apply_gates(metrics, phase):
    """Apply frozen kill criteria. Returns (verdict, note)."""
    n = metrics.get("n", 0)
    pf = metrics.get("profit_factor", 0)
    wr = metrics.get("win_rate", 0)

    if phase == PHASE_IS:
        if n < MIN_IS_TRADES:
            return "INSUFFICIENT", f"n={n} < {MIN_IS_TRADES}"
        if pf == float("inf"):
            return "SUSPICIOUS", "zero losses - debug for leakage"
        if pf < MIN_PF:
            return "KILL", f"PF {pf:.4f} < {MIN_PF}"
        if wr < MIN_WR:
            return "KILL", f"WR {wr:.0%} < {MIN_WR:.0%}"
        if pf < MIN_PF_PASS:
            return "DANGER-ZONE", f"PF {pf:.4f} in {MIN_PF}-{MIN_PF_PASS} band"
        return "PASS-INSAMPLE", f"PF {pf:.4f}: passes IS floor"
    else:
        if n < MIN_OOS_TRADES:
            return "INSUFFICIENT", f"OOS n={n} < {MIN_OOS_TRADES}"
        if pf == float("inf"):
            return "SUSPICIOUS", "zero OOS losses - debug"
        if pf < MIN_PF:
            return "KILL", f"OOS PF {pf:.4f} < {MIN_PF}"
        if wr < MIN_WR:
            return "KILL", f"OOS WR {wr:.0%} < {MIN_WR:.0%}"
        if pf < MIN_PF_PASS:
            return "DANGER-ZONE", f"OOS PF {pf:.4f} in {MIN_PF}-{MIN_PF_PASS} band"
        return "PASS-OOS", f"OOS PF {pf:.4f} >= {MIN_PF_PASS}"


def make_verdict_hash(kernel_id, batch_id, phase, dataset_hash, metrics, verdict):
    """Create a canonical verdict document and hash it."""
    doc = {
        "kernel_id": kernel_id,
        "batch_id": batch_id,
        "phase": phase,
        "dataset_hash": dataset_hash,
        "metrics": {k: v for k, v in metrics.items() if k != "exits"},
        "exits": metrics.get("exits", {}),
        "verdict": verdict[0],
        "note": verdict[1],
        "timestamp_utc": datetime.utcnow().isoformat(),
    }
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def evaluate_phase(kernel_module, dataset_path, raw_dir, phase, gate1_log):
    """Single authoritative evaluation path for one phase.
    
    Returns: (success, metrics, verdict, note, dataset_hash)
    """
    dataset_hash = compute_file_hash(dataset_path)
    
    # Gate 1: data validation
    gate1_result = kernel_module.gate1_audit(gate1_log, raw_dir, dataset_path)
    if gate1_result == "REJECT":
        return False, {}, ("GATE1-REJECT", "Data failed validation"), dataset_hash

    # Load and filter data
    bars = kernel_module.load_dataset(dataset_path)
    if phase == PHASE_IS:
        start = datetime.strptime(IS_START, "%Y-%m-%d")
        end = datetime.strptime(IS_END, "%Y-%m-%d")
    else:
        start = datetime.strptime(OOS_START, "%Y-%m-%d")
        end = datetime.strptime(OOS_END, "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    # Run backtest
    trades = kernel_module.run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict = apply_gates(metrics, phase)
    
    return True, metrics, verdict, dataset_hash


def get_lifetime_tested():
    """Count resolved graveyard rows (excluding SMOKE-TEST and UNTESTED)."""
    graveyard_path = os.path.join(PROJECT_DIR, "factory", "graveyard.csv")
    if not os.path.exists(graveyard_path):
        return 0
    
    count = 0
    with open(graveyard_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("status", "")
            # Exclude smoke tests and untested rows
            if "SMOKE" in status.upper() or status.upper() == "UNTESTED":
                continue
            # Include all resolved rows (LIVE, DEAD, INSUFFICIENT, etc.)
            if status:
                count += 1
    return count


def check_cool_off(batch_id, kernel_id):
    """Check if 24h cool-off has elapsed since IS completion."""
    ledger_path = os.path.join(PROJECT_DIR, "factory", "batch_ledger.csv")
    if not os.path.exists(ledger_path):
        return True, None
    
    is_complete = None
    with open(ledger_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row["batch_id"] == batch_id and 
                row["kernel_id"] == kernel_id and 
                row["phase"] == PHASE_IS and
                row["status"] == "COMPLETED"):
                is_complete = datetime.fromisoformat(row["run_utc"])
                break
    
    if is_complete is None:
        return False, "No IS completion found in ledger"
    
    elapsed = (datetime.utcnow() - is_complete).total_seconds() / 3600
    if elapsed < COOL_OFF_HOURS:
        return False, f"Cool-off: {elapsed:.1f}h elapsed, {COOL_OFF_HOURS}h required"
    
    return True, None


def run_batch(phase_filter=None):
    """Run the full noise batch and generate the report.
    
    Args:
        phase_filter: None for all phases, or 'is'/'oos' to run only that phase.
    """
    print("=" * 78)
    print(f"PHASE 2 NOISE CONTROL BATCH — {BATCH_ID}")
    print("=" * 78)

    dataset_path = os.path.join(RESEARCH_DIR, "data", "eurusd_1h.csv")
    raw_dir = os.path.join(RESEARCH_DIR, "data", "raw", "EURUSD_H1")
    gate1_log = os.path.join(RESEARCH_DIR, "data", "data_audit.log")
    ledger_path = os.path.join(PROJECT_DIR, "factory", "batch_ledger.csv")
    graveyard_path = os.path.join(PROJECT_DIR, "factory", "graveyard.csv")

    if not os.path.exists(dataset_path):
        print(f"ERROR: Dataset not found: {dataset_path}")
        return 1

    # Initialize ledger
    if not os.path.exists(ledger_path):
        with open(ledger_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["batch_id", "kernel_id", "phase", "run_utc", "dataset_hash", "verdict_hash", "status"])

    results = []
    killed = 0
    survived_to_oos = 0
    oos_survivors = 0
    causes = {}

    for kernel_id, description in NOISE_KERNELS:
        print(f"\n--- {kernel_id}: {description} ---")
        
        if phase_filter != PHASE_OOS:
            # Check one-shot: IS already completed?
            with open(ledger_path, newline="") as f:
                reader = csv.DictReader(f)
                is_done = any(
                    r["batch_id"] == BATCH_ID and r["kernel_id"] == kernel_id 
                    and r["phase"] == PHASE_IS and r["status"] == "COMPLETED"
                    for r in reader
                )
            if is_done:
                print(f"  IS already completed — skipped (one-shot)")
                continue

        kernel_module = load_kernel(kernel_id)
        if not kernel_module:
            print(f"  PLUMBING-ERROR: Kernel file not found")
            results.append({
                "kernel_id": kernel_id, "description": description,
                "is_verdict": "PLUMBING-ERROR", "is_note": "Kernel file not found",
                "oos_verdict": None, "oos_note": None, "dataset_hash": None,
            })
            continue

        # IS phase
        try:
            success, is_metrics, is_verdict, ds_hash = evaluate_phase(
                kernel_module, dataset_path, raw_dir, PHASE_IS, gate1_log
            )
            if not success:
                print(f"  IS: {is_verdict[0]} - {is_verdict[1]}")
                v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, ds_hash, is_metrics, is_verdict)
                # Append to ledger
                with open(ledger_path, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([BATCH_ID, kernel_id, PHASE_IS, datetime.utcnow().isoformat(), ds_hash, v_hash, "COMPLETED"])
                results.append({
                    "kernel_id": kernel_id, "description": description,
                    "is_verdict": is_verdict[0], "is_note": is_verdict[1],
                    "oos_verdict": None, "oos_note": None, "dataset_hash": ds_hash,
                    "verdict_hash": v_hash,
                })
                continue
        except Exception as e:
            print(f"  IS ERROR: {e}")
            v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, "error", {}, ("ERROR", str(e)))
            with open(ledger_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([BATCH_ID, kernel_id, PHASE_IS, datetime.utcnow().isoformat(), "error", v_hash, "PLUMBING-ERROR"])
            results.append({
                "kernel_id": kernel_id, "description": description,
                "is_verdict": "PLUMBING-ERROR", "is_note": str(e),
                "oos_verdict": None, "oos_note": None, "dataset_hash": None,
            })
            continue

        print(f"  IS: n={is_metrics['n']}, PF={is_metrics['profit_factor']:.4f}, "
              f"WR={is_metrics['win_rate']:.1%} -> {is_verdict[0]}")
        v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, ds_hash, is_metrics, is_verdict)
        with open(ledger_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([BATCH_ID, kernel_id, PHASE_IS, datetime.utcnow().isoformat(), ds_hash, v_hash, "COMPLETED"])

        if is_verdict[0] != "PASS-INSAMPLE":
            results.append({
                "kernel_id": kernel_id, "description": description,
                "is_verdict": is_verdict[0], "is_note": is_verdict[1],
                "oos_verdict": None, "oos_note": None, "dataset_hash": ds_hash,
                "verdict_hash": v_hash,
            })
            continue

        # OOS phase (if requested)
        if phase_filter == PHASE_IS:
            results.append({
                "kernel_id": kernel_id, "description": description,
                "is_verdict": is_verdict[0], "is_note": is_verdict[1],
                "oos_verdict": None, "oos_note": None, "dataset_hash": ds_hash,
                "verdict_hash": v_hash,
            })
            continue

        # Check cool-off
        cool_ok, cool_msg = check_cool_off(BATCH_ID, kernel_id)
        if not cool_ok:
            print(f"  OOS: BLOCKED - {cool_msg}")
            results.append({
                "kernel_id": kernel_id, "description": description,
                "is_verdict": is_verdict[0], "is_note": is_verdict[1],
                "oos_verdict": "COOL-OFF", "oos_note": cool_msg,
                "dataset_hash": ds_hash, "verdict_hash": v_hash,
            })
            continue

        # Check one-shot: OOS already completed?
        with open(ledger_path, newline="") as f:
            reader = csv.DictReader(f)
            oos_done = any(
                r["batch_id"] == BATCH_ID and r["kernel_id"] == kernel_id 
                and r["phase"] == PHASE_OOS and r["status"] == "COMPLETED"
                for r in reader
            )
        if oos_done:
            print(f"  OOS already completed — skipped (one-shot)")
            continue

        # Run OOS
        survived_to_oos += 1
        try:
            success, oos_metrics, oos_verdict, oos_ds_hash = evaluate_phase(
                kernel_module, dataset_path, raw_dir, PHASE_OOS, gate1_log
            )
            if not success:
                oos_verdict = ("GATE1-REJECT", "OOS data failed validation")
            else:
                # Additional OOS gate: WR drop > 15pp vs IS
                if oos_verdict[0] == "PASS-OOS":
                    wr_drop_pp = (is_metrics["win_rate"] - oos_metrics["win_rate"]) * 100
                    if wr_drop_pp > MAX_WR_DROP_PP:
                        oos_verdict = ("KILL", f"WR drop {wr_drop_pp:.1f}pp > {MAX_WR_DROP_PP}pp vs IS")
        except Exception as e:
            oos_verdict = ("ERROR", str(e))
            oos_metrics = {}

        oos_v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_OOS, oos_ds_hash if 'oos_ds_hash' in dir() else ds_hash, oos_metrics if oos_metrics else {}, oos_verdict)
        with open(ledger_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([BATCH_ID, kernel_id, PHASE_OOS, datetime.utcnow().isoformat(), oos_ds_hash if 'oos_ds_hash' in dir() else ds_hash, oos_v_hash, "COMPLETED"])

        print(f"  OOS: n={oos_metrics.get('n', 0)}, PF={oos_metrics.get('profit_factor', 0):.4f}, "
              f"WR={oos_metrics.get('win_rate', 0):.1%} -> {oos_verdict[0]}")

        if oos_verdict[0] == "PASS-OOS":
            oos_survivors += 1

        results.append({
            "kernel_id": kernel_id, "description": description,
            "is_verdict": is_verdict[0], "is_note": is_verdict[1],
            "oos_verdict": oos_verdict[0], "oos_note": oos_verdict[1],
            "dataset_hash": ds_hash, "verdict_hash": v_hash,
            "oos_verdict_hash": oos_v_hash,
        })

    # Count killed
    for r in results:
        final = r.get("oos_verdict") or r.get("is_verdict")
        if final == "PASS-OOS":
            continue
        killed += 1
        cause = r.get("oos_verdict") or r.get("is_verdict")
        causes[cause] = causes.get(cause, 0) + 1

    # Calculate metrics
    n_requested = len(NOISE_KERNELS)
    n_effective = n_requested  # All 10 are effective (no clone collapse for noise)
    null_pass_rate = oos_survivors / n_requested if n_requested else 0
    
    lifetime_before = get_lifetime_tested()
    lifetime_total = lifetime_before + n_effective
    luck_expected = lifetime_total * null_pass_rate

    # Print official batch report
    print("\n" + "=" * 78)
    print("PHASE 2 BATCH REPORT")
    print("=" * 78)
    print(f"BATCH: {BATCH_ID} (Noise Calibration)")
    print(f"DATE: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"STATUS: PROVISIONAL (append-only enforcement and clone calibration pending)")
    print(f"KERNELS REQUESTED: {n_requested}")
    print(f"KERNELS EFFECTIVE: {n_effective}")
    print(f"  NOTE: 80% clone-similarity threshold UNCALIBRATED. Exact parameter_hash collision check only.")
    print(f"KILLED: {killed}")
    print(f"  CAUSE OF DEATH:")
    for cause, count in sorted(causes.items()):
        print(f"    {cause}: {count}")
    print(f"SURVIVED TO OOS: {survived_to_oos}")
    print(f"OOS SURVIVORS: {oos_survivors}")
    print(f"LIFETIME TOTAL TESTED: {lifetime_total}")
    print(f"  (before batch: {lifetime_before}, this batch: {n_effective})")
    print(f"NULL PASS RATE (calibrated {datetime.utcnow().strftime('%Y-%m-%d')}): {null_pass_rate:.0%}")
    print(f"CUMULATIVE LUCK-EXPECTED SURVIVORS: {luck_expected:.2f}")
    print(f"COOL-OFF: {COOL_OFF_HOURS}h (enforced)")
    print()
    print("DETAILED RESULTS:")
    print("-" * 78)
    for r in results:
        print(f"  {r['kernel_id']}:")
        print(f"    IS: {r['is_verdict']} - {r['is_note']}")
        if r.get('oos_verdict'):
            print(f"    OOS: {r['oos_verdict']} - {r['oos_note']}")
    print()
    print("GRAVEYARD DIFF (proposed rows, NOT written):")
    for r in results:
        final = r.get('oos_verdict') or r.get('is_verdict')
        v_hash = r.get('oos_verdict_hash') or r.get('verdict_hash', 'N/A')
        print(f"  {r['kernel_id']}: {final} (verdict_hash={v_hash[:12]}...)")
    print()
    print("VERDICT HASHES:")
    for r in results:
        v_hash = r.get('verdict_hash', 'N/A')
        print(f"  {r['kernel_id']}/IS: {v_hash[:12]}...")
        if r.get('oos_verdict_hash'):
            print(f"  {r['kernel_id']}/OOS: {r['oos_verdict_hash'][:12]}...")
    print("=" * 78)

    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 2 Noise Control Batch Runner")
    parser.add_argument("--phase", choices=["is", "oos", "all"], default="all",
                        help="Run only IS, only OOS, or all phases")
    args = parser.parse_args()
    
    if args.phase == "is":
        return run_batch(phase_filter=PHASE_IS)
    elif args.phase == "oos":
        return run_batch(phase_filter=PHASE_OOS)
    else:
        return run_batch(phase_filter=None)


if __name__ == "__main__":
    sys.exit(main())
