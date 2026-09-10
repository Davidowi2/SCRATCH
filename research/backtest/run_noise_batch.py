"""
research/backtest/run_noise_batch.py — Phase 2 Noise Control Batch Runner

Executes the 10 noise kernels through the IS -> OOS ladder and generates
the official Phase 2 Batch Report (Spec §11).

FROZEN GATES (applied mechanically):
- IS: n<50 INSUFFICIENT, PF<1.0 KILL, WR<45% KILL, PF 1.0-1.15 DANGER, PF>=1.15 PASS
- OOS: n<30 INSUFFICIENT, PF<1.0 KILL, WR<45% KILL, WR drop>15pp KILL, PF 1.0-1.15 DANGER, PF>=1.15 PASS-OOS

One shot per window per kernel. No parameter changes.
"""

import csv
import importlib.util
import os
import sys
import sqlite3
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESEARCH_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(RESEARCH_DIR, "database", "trades.db")

# Frozen windows
IS_START = "2021-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2025-05-13"

# Frozen gates
MIN_IS_TRADES = 50
MIN_OOS_TRADES = 30
MIN_PF = 1.0
MIN_PF_PASS = 1.15
MIN_WR = 0.45
MAX_WR_DROP_PP = 15

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
        print(f"  ERROR: Kernel file not found: {path}")
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_kernel_phase(kernel_module, dataset_path, raw_dir, phase):
    """Run a single kernel's backtest for a given phase."""
    try:
        # Override sys.argv to simulate CLI args
        old_argv = sys.argv
        sys.argv = [
            f"{kernel_module.EXPERIMENT_ID}.py",
            "--dataset", dataset_path,
            "--raw-dir", raw_dir,
            "--phase", phase,
        ]
        exit_code = kernel_module.main()
        sys.argv = old_argv
        return exit_code == 0
    except SystemExit as e:
        sys.argv = old_argv
        return e.code == 0
    except Exception as e:
        sys.argv = old_argv
        print(f"  ERROR: {e}")
        return False


def apply_gates(metrics, phase):
    """Apply frozen kill criteria. Returns (verdict, note)."""
    n = metrics.get("n", 0)
    pf = metrics.get("profit_factor", 0)
    wr = metrics.get("win_rate", 0)

    if phase == "insample":
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
    else:  # oos
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


def run_batch():
    """Run the full noise batch and generate the report."""
    print("=" * 78)
    print("PHASE 2 NOISE CONTROL BATCH — EXECUTION")
    print("=" * 78)

    dataset_path = os.path.join(RESEARCH_DIR, "data", "eurusd_1h.csv")
    raw_dir = os.path.join(RESEARCH_DIR, "data", "raw", "EURUSD_H1")

    if not os.path.exists(dataset_path):
        print(f"ERROR: Dataset not found: {dataset_path}")
        return 1

    results = []
    killed = 0
    survived_to_oos = 0
    oos_survivors = 0

    for kernel_id, description in NOISE_KERNELS:
        print(f"\n--- {kernel_id}: {description} ---")
        kernel_module = load_kernel(kernel_id)
        if not kernel_module:
            results.append({
                "kernel_id": kernel_id,
                "description": description,
                "is_verdict": "ERROR",
                "is_note": "Kernel file not found",
                "oos_verdict": None,
                "oos_note": None,
            })
            killed += 1
            continue

        # IS phase
        success = run_kernel_phase(kernel_module, dataset_path, raw_dir, "insample")
        if not success:
            results.append({
                "kernel_id": kernel_id,
                "description": description,
                "is_verdict": "ERROR",
                "is_note": "IS execution failed",
                "oos_verdict": None,
                "oos_note": None,
            })
            killed += 1
            continue

        # Read IS metrics from the kernel's output (parse from stdout capture)
        # For now, we re-run and capture metrics directly
        # Since kernels print to stdout, we need to capture their metrics
        # Alternative: import and call run_backtest directly
        try:
            bars = kernel_module.load_dataset(dataset_path)
            from datetime import datetime as dt
            start = dt.strptime(IS_START, "%Y-%m-%d")
            end = dt.strptime(IS_END, "%Y-%m-%d")
            bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]
            trades = kernel_module.run_backtest(bars)
            is_metrics = kernel_module.compute_metrics(trades)
            is_verdict, is_note = apply_gates(is_metrics, "insample")
        except Exception as e:
            print(f"  IS ERROR: {e}")
            is_verdict = "ERROR"
            is_note = str(e)
            is_metrics = {"n": 0, "profit_factor": 0, "win_rate": 0}

        print(f"  IS: n={is_metrics['n']}, PF={is_metrics['profit_factor']:.4f}, "
              f"WR={is_metrics['win_rate']:.1%} -> {is_verdict}")

        if is_verdict not in ("PASS-INSAMPLE",):
            results.append({
                "kernel_id": kernel_id,
                "description": description,
                "is_verdict": is_verdict,
                "is_note": is_note,
                "is_metrics": is_metrics,
                "oos_verdict": None,
                "oos_note": None,
            })
            killed += 1
            continue

        # OOS phase
        survived_to_oos += 1
        try:
            bars = kernel_module.load_dataset(dataset_path)
            start = dt.strptime(OOS_START, "%Y-%m-%d")
            end = dt.strptime(OOS_END, "%Y-%m-%d")
            bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]
            trades = kernel_module.run_backtest(bars)
            oos_metrics = kernel_module.compute_metrics(trades)
            oos_verdict, oos_note = apply_gates(oos_metrics, "oos")

            # Additional OOS gate: WR drop > 15pp vs IS
            if oos_verdict == "PASS-OOS":
                wr_drop_pp = (is_metrics["win_rate"] - oos_metrics["win_rate"]) * 100
                if wr_drop_pp > MAX_WR_DROP_PP:
                    oos_verdict = "KILL"
                    oos_note = f"WR drop {wr_drop_pp:.1f}pp > {MAX_WR_DROP_PP}pp vs IS"
        except Exception as e:
            print(f"  OOS ERROR: {e}")
            oos_verdict = "ERROR"
            oos_note = str(e)
            oos_metrics = {"n": 0, "profit_factor": 0, "win_rate": 0}

        print(f"  OOS: n={oos_metrics['n']}, PF={oos_metrics['profit_factor']:.4f}, "
              f"WR={oos_metrics['win_rate']:.1%} -> {oos_verdict}")

        if oos_verdict == "PASS-OOS":
            oos_survivors += 1

        results.append({
            "kernel_id": kernel_id,
            "description": description,
            "is_verdict": is_verdict,
            "is_note": is_note,
            "is_metrics": is_metrics,
            "oos_verdict": oos_verdict,
            "oos_note": oos_note,
            "oos_metrics": oos_metrics,
        })

    # Calculate null_pass_rate
    null_pass_rate = oos_survivors / len(NOISE_KERNELS) if NOISE_KERNELS else 0

    # Count lifetime tested (from graveyard + this batch)
    lifetime_tested = len(NOISE_KERNELS)  # This batch only for now

    # Cumulative luck-expected survivors
    luck_expected = lifetime_tested * null_pass_rate

    # Print official batch report
    print("\n" + "=" * 78)
    print("PHASE 2 BATCH REPORT")
    print("=" * 78)
    print(f"BATCH ID: B-000 (Noise Calibration)")
    print(f"DATE: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"KERNELS REQUESTED: {len(NOISE_KERNELS)}")
    print(f"KERNELS EFFECTIVE (post clone-collapse): {len(NOISE_KERNELS)}")
    print(f"KILLED: {killed}")
    print(f"SURVIVED TO OOS: {survived_to_oos}")
    print(f"OOS SURVIVORS: {oos_survivors}")
    print(f"LIFETIME TOTAL TESTED: {lifetime_tested}")
    print(f"NULL PASS RATE (calibrated {datetime.utcnow().strftime('%Y-%m-%d')}): {null_pass_rate:.0%}")
    print(f"CUMULATIVE LUCK-EXPECTED SURVIVORS: {luck_expected:.2f}")
    print()
    print("DETAILED RESULTS:")
    print("-" * 78)
    for r in results:
        print(f"  {r['kernel_id']}:")
        print(f"    IS: {r['is_verdict']} - {r['is_note']}")
        if r['oos_verdict']:
            print(f"    OOS: {r['oos_verdict']} - {r['oos_note']}")
    print()
    print("GRAVEYARD DIFF:")
    for r in results:
        status = r['oos_verdict'] if r['oos_verdict'] else r['is_verdict']
        print(f"  {r['kernel_id']}: {status}")
    print()
    print("VERDICT HASHES: [to be committed after verification]")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    sys.exit(run_batch())
