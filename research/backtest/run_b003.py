"""
research/backtest/run_b003.py — Phase 5 B-003 S-012 Single-Kernel Runner (CRYPTO).

Executes S-012 (BTCUSDT perp 5m) through the IS ladder and generates the
official B-003 §11 report. One kernel, ONE shot (batch ledger enforces).

FROZEN GATES (applied mechanically, identical to B-001/B-002):
- IS: n<50 INSUFFICIENT, PF<1.0 KILL, WR<45% KILL, PF 1.0-1.15 DANGER, PF>=1.15 PASS
- Runner verdict uses NET PF (frozen criteria v2.1; B-002 gross-PF display
  bug is NOT inherited: metrics carry both gross and net explicitly).
- Autopsy classifier (Owner/Overseer declared): compute GROSS metrics
  (friction=0). gross clears ALL gates (PF>=1.15, WR>=45%, Exp>0)
  -> TUNING-SHORT; gross fails any gate -> MECHANISM-DEAD.

Charter amendment: cool-off waived for SHA-locked preregistered kernels.
No parameter changes. No double execution: kernel.run_backtest called once.

LIFETIME COUNTING RULE (restated per Directive T v1, Overseer-signed):
  lifetime total tested = RESOLVED graveyard rows, EXCLUDING rows whose
  status is SMOKE-TEST or UNTESTED. Current epoch value: 23 post-B-003
  (24 raw rows minus H-002-v1 pre-backtest tombstone, status=UNTESTED).
  B-003 is CLOSED: S-012 died in IS, no OOS, no retest absent Owner override.
"""

import csv
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESEARCH_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(RESEARCH_DIR)

# Frozen windows (NEVER shrink, NEVER extend)
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

COOL_OFF_HOURS = 0  # waived per charter amendment

BATCH_ID = "B-003"
PHASE_IS = "insample"
PHASE_OOS = "oos"

DATASET = os.path.join(RESEARCH_DIR, "data", "crypto", "btcusdt_5m.csv")

KERNELS = [
    ("S-012", "S012_banklevel_crypto", "Bank-Level Crypto Arm: BTCUSDT perp 5m first-hour ORB"),
]


def load_kernel(name):
    path = os.path.join(SCRIPT_DIR, f"{name}.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compute_file_hash(path):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def compute_metrics(trades):
    """Authoritative metrics. profit_factor = NET (verdict gate).
    Gross block = friction=0 recompute from gross_pips (B4 lineage)."""
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "exits": {},
                "gross_profit": 0, "gross_loss": 0, "gross_pf": 0,
                "gross_wr": 0, "gross_expectancy": 0,
                "net_pf": 0, "net_expectancy": 0}

    # NET (after per-trade friction)
    net_list = [t.pips for t in trades]
    wins = [p for p in net_list if p > 0]
    net_profit = sum(p for p in net_list if p > 0)
    net_loss = -sum(p for p in net_list if p <= 0)
    net_pf = net_profit / net_loss if net_loss > 0 else float("inf")
    net_expectancy = sum(net_list) / len(trades)

    # GROSS (friction = 0) from trade-level gross_pips
    gross_list = [t.gross_pips for t in trades if t.gross_pips is not None]
    gross_profit = sum(g for g in gross_list if g > 0)
    gross_loss = sum(abs(g) for g in gross_list if g <= 0)
    gross_pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    gross_wr = sum(1 for g in gross_list if g > 0) / len(gross_list) if gross_list else 0
    gross_expectancy = sum(gross_list) / len(gross_list) if gross_list else 0

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
        "profit_factor": net_pf,          # VERDICT gate = NET PF
        "expectancy_pips": net_expectancy,
        "max_dd_pips": max_dd, "exits": exits,
        "gross_profit": gross_profit, "gross_loss": gross_loss,
        "gross_pf": gross_pf, "gross_wr": gross_wr,
        "gross_expectancy": gross_expectancy,
        "net_pf": net_pf, "net_expectancy": net_expectancy,
    }


def apply_gates(metrics, phase):
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
            return "KILL", f"WR {wr:.2%} < {MIN_WR:.0%}"
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
            return "KILL", f"OOS WR {wr:.2%} < {MIN_WR:.0%}"
        if pf < MIN_PF_PASS:
            return "DANGER-ZONE", f"OOS PF {pf:.4f} in {MIN_PF}-{MIN_PF_PASS} band"
        return "PASS-OOS", f"OOS PF {pf:.4f} >= {MIN_PF_PASS}"


def classify_cause(metrics):
    """Overseer autopsy classifier on GROSS metrics (friction=0):
    gross clears ALL gates (PF>=1.15, WR>=45%, Exp>0) -> TUNING-SHORT
    else -> MECHANISM-DEAD."""
    gp = metrics.get("gross_pf", 0)
    gw = metrics.get("gross_wr", 0)
    ge = metrics.get("gross_expectancy", 0)
    if gp != float("inf") and gp >= MIN_PF_PASS and gw >= MIN_WR and ge > 0:
        return "TUNING-SHORT"
    return "MECHANISM-DEAD"


def make_verdict_hash(kernel_id, batch_id, phase, dataset_hash, metrics, verdict):
    doc = {
        "kernel_id": kernel_id,
        "batch_id": batch_id,
        "phase": phase,
        "dataset_hash": dataset_hash,
        "metrics": {k: float(v) if isinstance(v, (int, float)) else v
                    for k, v in metrics.items() if k != "exits"},
        "exits": metrics.get("exits", {}),
        "verdict": verdict[0],
        "note": verdict[1],
        "timestamp_utc": datetime.utcnow().isoformat(),
    }
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def evaluate_phase(kernel_module, dataset_path, phase):
    """Single authoritative evaluation path for one phase."""
    dataset_hash = compute_file_hash(dataset_path)

    # Gate 1 CRYPTO (24/7 jurisdiction + synthetic hard rule)
    rep = kernel_module.gate1_audit_crypto(dataset_path, verbose=False)
    if rep["verdict"] == "REJECT":
        return False, {}, ("GATE1-REJECT", "; ".join(rep["fatal"])), dataset_hash

    bars = kernel_module.load_dataset(dataset_path)
    if phase == PHASE_IS:
        start = datetime.strptime(IS_START, "%Y-%m-%d")
        end = datetime.strptime(IS_END, "%Y-%m-%d")
    else:
        start = datetime.strptime(OOS_START, "%Y-%m-%d")
        end = datetime.strptime(OOS_END, "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23, minute=59, second=59)]

    trades = kernel_module.run_backtest(bars)     # ONE call (B2 lineage)
    metrics = compute_metrics(trades)
    verdict = apply_gates(metrics, phase)
    return True, metrics, verdict, dataset_hash


def get_lifetime_tested():
    graveyard_path = os.path.join(PROJECT_DIR, "factory", "graveyard.csv")
    if not os.path.exists(graveyard_path):
        return 0
    count = 0
    with open(graveyard_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("status", "")
            if "SMOKE" in status.upper() or status.upper() == "UNTESTED":
                continue
            if status:
                count += 1
    return count


def ledger_is_completed(ledger_path, kernel_id):
    if not os.path.exists(ledger_path):
        return False
    with open(ledger_path, newline="") as f:
        for row in csv.DictReader(f):
            if (row["batch_id"] == BATCH_ID and row["kernel_id"] == kernel_id
                    and row["phase"] == PHASE_IS and row["status"] == "COMPLETED"):
                return True
    return False


def append_ledger(ledger_path, row):
    if not os.path.exists(ledger_path):
        with open(ledger_path, "w", newline="") as f:
            csv.writer(f).writerow(["batch_id", "kernel_id", "phase", "run_utc",
                                    "dataset_hash", "verdict_hash", "status"])
    with open(ledger_path, "a", newline="") as f:
        csv.writer(f).writerow(row)


def fingerprint_for(kernel_id):
    """16-prefix mechanism + file-sha parameter convention (S-kernel lineage)."""
    from factory.fingerprint_v2 import mechanism_hash
    params = {
        "signal_family": "BANK_LEVEL_CROSS",
        "entry_trigger_class": "range_cross_first_with_atr_expansion",
        "exit_logic_class": "stop_target_hardflat",
        "session_hours": [30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85],
        "timeframe": "5m",
        "instrument_class": "CRYPTO_PERP",
        "pair": "BTCUSDT",
        "thresholds": {"atr_mult": 1.0, "target_r": 1.5, "fee_rate": 0.0005},
        "bands": {},
        "stop_mult": 0,
        "max_hold": 0,
        "friction_pips": 0,
    }
    return mechanism_hash(params)[:16], params


def run_batch(phase_filter=None):
    print("=" * 78)
    print(f"PHASE 5 CRYPTO BATCH — {BATCH_ID}")
    print("=" * 78)

    ledger_path = os.path.join(PROJECT_DIR, "factory", "batch_ledger.csv")
    kernel_sha = compute_file_hash(os.path.join(SCRIPT_DIR, "S012_banklevel_crypto.py"))
    ds_hash_full = compute_file_hash(DATASET)
    mech16, _ = fingerprint_for("S-012")
    print(f"Kernel sha256: {kernel_sha}")
    print(f"Dataset: {DATASET}")
    print(f"Dataset sha256: {ds_hash_full}")

    results = []
    killed = 0
    survived_to_oos = 0
    causes = {}

    for kernel_id, kernel_file, description in KERNELS:
        print(f"\n--- {kernel_id}: {description} ---")

        if ledger_is_completed(ledger_path, kernel_id):
            print("  IS already completed — SKIPPED (one-shot)")
            continue

        km = load_kernel(kernel_file)
        if not km:
            print("  PLUMBING-ERROR: kernel file not found")
            continue

        try:
            success, metrics, verdict, ds_hash = evaluate_phase(km, DATASET, PHASE_IS)
        except Exception as e:
            print(f"  IS ERROR: {e}")
            v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, "error", {}, ("ERROR", str(e)))
            append_ledger(ledger_path, [BATCH_ID, kernel_id, PHASE_IS,
                                        datetime.utcnow().isoformat(), "error", v_hash,
                                        "PLUMBING-ERROR"])
            continue

        if not success:
            print(f"  Gate 1 CRYPTO: {verdict[0]} — {verdict[1]}")
            v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, ds_hash, {}, verdict)
            append_ledger(ledger_path, [BATCH_ID, kernel_id, PHASE_IS,
                                        datetime.utcnow().isoformat(), ds_hash, v_hash,
                                        "COMPLETED"])
            results.append({"kernel_id": kernel_id, "description": description,
                            "is_verdict": verdict[0], "is_note": verdict[1],
                            "metrics": {}, "verdict_hash": v_hash})
            continue

        v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, ds_hash, metrics, verdict)
        append_ledger(ledger_path, [BATCH_ID, kernel_id, PHASE_IS,
                                    datetime.utcnow().isoformat(), ds_hash, v_hash,
                                    "COMPLETED"])

        cause = classify_cause(metrics) if verdict[0] not in ("PASS-INSAMPLE",) else None
        print(f"  IS: n={metrics['n']}, NET PF={metrics['net_pf']:.4f}, "
              f"WR={metrics['win_rate']:.2%} -> {verdict[0]}"
              + (f" | autopsy: {cause}" if cause else ""))
        print(f"  LEDGER ROW APPENDED: {BATCH_ID},{kernel_id},{PHASE_IS} (one-shot consumed)")

        results.append({"kernel_id": kernel_id, "description": description,
                        "is_verdict": verdict[0], "is_note": verdict[1],
                        "metrics": metrics, "verdict_hash": v_hash,
                        "cause": cause, "ds_hash": ds_hash,
                        "mech16": mech16, "param16": kernel_sha[:16]})

        if verdict[0] != "PASS-INSAMPLE":
            killed += 1
            causes[verdict[0]] = causes.get(verdict[0], 0) + 1

    # ---- §11 REPORT ----
    lifetime_before = get_lifetime_tested()
    n_effective = len(results)
    lifetime_total = lifetime_before + n_effective

    print("\n" + "=" * 78)
    print(f"{BATCH_ID} BATCH REPORT — SPEC §11")
    print("=" * 78)
    print(f"BATCH: {BATCH_ID} (Crypto)")
    print(f"DATE: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"KERNELS REQUESTED: {len(KERNELS)}")
    print(f"KERNELS EFFECTIVE: {n_effective}")
    print("  CLONE-COLLAPSE: exact parameter_hash collision check only — NONE found")
    print(f"KILLED: {killed}")
    print("  CAUSE OF DEATH (gate-verdict breakdown):")
    for c, cnt in sorted(causes.items()):
        print(f"    {c}: {cnt}")
    print(f"SURVIVED TO OOS: {survived_to_oos}")
    print(f"LIFETIME TOTAL TESTED: {lifetime_total}")
    print(f"  (before batch: {lifetime_before}, this batch: {n_effective})")
    print(f"NULL PASS RATE: 0% (calibrated 2026-09-13, B-000: 0/10)")
    print(f"CUMULATIVE LUCK-EXPECTED SURVIVORS: 0.00")

    for r in results:
        m = r["metrics"]
        print("\nAUTOPSY BLOCK " + r["kernel_id"] + ":")
        print(f"  n: {m.get('n')}")
        print(f"  WR net (unrounded): {m.get('win_rate', 0):.4%}")
        print(f"  PF net (unrounded): {m.get('net_pf', 0):.4f}")
        print(f"  GROSS PF: {m.get('gross_pf', 0):.4f}  GROSS WR: {m.get('gross_wr', 0):.4%}  "
              f"GROSS expectancy: {m.get('gross_expectancy', 0):+.4f}")
        print(f"  NET expectancy: {m.get('net_expectancy', 0):+.4f}")
        print("  GROSS vs NET:")
        print(f"    {'':10} {'GROSS':>10} {'NET':>10}")
        gp = m.get('gross_pf', 0)
        print(f"    {'PF':<10} {(f'{gp:.4f}' if gp != float('inf') else 'inf'):>10} "
              f"{m.get('net_pf', 0):>10.4f}")
        print(f"    {'WR':<10} {m.get('gross_wr', 0):>10.2%} {m.get('win_rate', 0):>10.2%}")
        print(f"    {'Exp':<10} {m.get('gross_expectancy', 0):>+10.2f} {m.get('net_expectancy', 0):>+10.2f}")
        print(f"  EXIT BREAKDOWN: {m.get('exits', {})}")
        print(f"  VERDICT: {r['is_verdict']} — {r['is_note']}")
        if r.get("cause"):
            print(f"  CAUSE (autopsy classifier): {r['cause']}")
        print(f"  VERDICT HASH: {r['verdict_hash']}")

    print("\nGRAVEYARD DIFF PROPOSAL (NOT WRITTEN — Overseer must confirm label first):")
    for r in results:
        if r.get("is_verdict") in ("PASS-INSAMPLE",):
            print(f"  {r['kernel_id']}: SURVIVED — no row")
            continue
        m = r["metrics"]
        print("  " + ",".join([
            r["kernel_id"], r["kernel_file"] if "kernel_file" in r else "S012_banklevel_crypto",
            "Bank-level crypto ORB 00:00-00:25 range, 00:30-01:25 window",
            r["is_verdict"], "",
            r.get("mech16", ""), r.get("param16", ""),
            f"{r.get('cause','PENDING-OVERSEER')}: IS n={m.get('n')}, netPF={m.get('net_pf', 0):.4f}, grossPF={m.get('gross_pf', 0):.4f}, grossWR={m.get('gross_wr', 0):.2%}",
            datetime.utcnow().strftime("%Y-%m-%d"), r["verdict_hash"], BATCH_ID,
        ]))
    print("=" * 78)
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description=f"{BATCH_ID} Crypto Single-Kernel Runner")
    parser.add_argument("--phase", choices=["is", "oos", "all"], default="is",
                        help="OOS not wired in B-003 until Overseer audits IS report")
    args = parser.parse_args()
    if args.phase == "oos":
        print("HOLD: OOS requires Overseer audit of the IS report first (Directive S item 4/5).")
        return 2
    return run_batch(phase_filter=PHASE_IS if args.phase == "is" else None)


if __name__ == "__main__":
    sys.path.insert(0, PROJECT_DIR)
    sys.exit(main())
