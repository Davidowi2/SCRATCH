"""
research/backtest/run_b004.py — B-004 (FINAL YouTube-backlog batch): S-006 + S-007.

Two-kernel IS ladder runner on EURUSD H1 (Gate 1 FX branch). One shot per
kernel per window enforced via factory/batch_ledger.csv.

FROZEN GATES (identical to B-001/B-002/B-003):
- IS: n<50 INSUFFICIENT | PF<1.0 KILL | WR<45% KILL | 1.0<=PF<1.15 DANGER | >=1.15 PASS
- Verdict gate = NET PF (B-002 gross-display bug NOT inherited; gross and
  net both reported explicitly; B-003 convention continues).
- Autopsy classifier on GROSS (friction=0): gross clears ALL gates
  (PF>=1.15, WR>=45%, Exp>0) -> TUNING-SHORT else MECHANISM-DEAD.

LIFETIME COUNTING RULE (ratified, Directive T v1): resolved graveyard rows
excluding SMOKE-TEST/UNTESTED. Epoch: 23 post-B-003. B-004: 23 + effective.

Clone-collapse: exact parameter_hash (= kernel file sha256) collision check
pairwise before runs. 80%-similarity threshold remains UNCALIBRATED.
No parameter changes. Single authoritative evaluation: kernel.run_backtest
called exactly once per phase.
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

IS_START = "2021-01-01"
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
OOS_END = "2025-05-13"

MIN_IS_TRADES = 50
MIN_OOS_TRADES = 50
MIN_PF = 1.0
MIN_PF_PASS = 1.15
MIN_WR = 0.45
MAX_WR_DROP_PP = 15

COOL_OFF_HOURS = 0  # waived (charter amendment, SHA-lock lineage)

BATCH_ID = "B-004"
PHASE_IS = "insample"
PHASE_OOS = "oos"

DATASET = os.path.join(RESEARCH_DIR, "data", "eurusd_1h.csv")
RAW_DIR = os.path.join(RESEARCH_DIR, "data", "raw", "EURUSD_H1")
GATE1_LOG = os.path.join(RESEARCH_DIR, "data", "data_audit.log")

# FINAL YOUTUBE BACKLOG SLATE (Directive U/V). S-009/S-011 reserved.
KERNELS = [
    ("S-006", "S006_ema_trendfilter", "EMA50/200 regime + pullback re-cross, 1.5ATR stop, 2R target"),
    ("S-007", "S007_regression_stoch", "50-bar 2sd regression channel fade + stoch(14,3,3), anchor stop, 2R target"),
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
    Gross block = friction=0 from gross_pips (B4 lineage)."""
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_pips": 0, "max_dd_pips": 0, "exits": {},
                "gross_pf": 0, "gross_wr": 0, "gross_expectancy": 0,
                "net_pf": 0, "net_expectancy": 0}

    net_list = [t.pips for t in trades]
    wins = [p for p in net_list if p > 0]
    net_profit = sum(p for p in net_list if p > 0)
    net_loss = -sum(p for p in net_list if p <= 0)
    net_pf = net_profit / net_loss if net_loss > 0 else float("inf")
    net_expectancy = sum(net_list) / len(trades)

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
        "profit_factor": net_pf,
        "expectancy_pips": net_expectancy,
        "max_dd_pips": max_dd, "exits": exits,
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
    """Overseer autopsy classifier on GROSS metrics (friction=0)."""
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
        "metrics": {k: (float(v) if isinstance(v, (int, float)) else v)
                    for k, v in metrics.items() if k != "exits"},
        "exits": metrics.get("exits", {}),
        "verdict": verdict[0],
        "note": verdict[1],
        "timestamp_utc": datetime.utcnow().isoformat(),
    }
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def evaluate_phase(kernel_module, dataset_path, phase):
    dataset_hash = compute_file_hash(dataset_path)
    gate1_result = kernel_module.gate1_audit(GATE1_LOG, RAW_DIR, dataset_path)
    if gate1_result == "REJECT":
        return False, {}, ("GATE1-REJECT", "Data failed validation"), dataset_hash

    bars = kernel_module.load_dataset(dataset_path)
    if phase == PHASE_IS:
        start = datetime.strptime(IS_START, "%Y-%m-%d")
        end = datetime.strptime(IS_END, "%Y-%m-%d")
    else:
        start = datetime.strptime(OOS_START, "%Y-%m-%d")
        end = datetime.strptime(OOS_END, "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23, minute=59, second=59)]

    trades = kernel_module.run_backtest(bars)   # ONE authoritative call (B2 lineage)
    metrics = compute_metrics(trades)
    verdict = apply_gates(metrics, phase)
    return True, metrics, verdict, dataset_hash


def get_lifetime_tested():
    graveyard_path = os.path.join(PROJECT_DIR, "factory", "graveyard.csv")
    if not os.path.exists(graveyard_path):
        return 0
    count = 0
    with open(graveyard_path, newline="") as f:
        for row in csv.DictReader(f):
            status = row.get("status", "")
            if "SMOKE" in status.upper() or status.upper() == "UNTESTED":
                continue
            if status:
                count += 1
    return count


def append_ledger(ledger_path, row):
    if not os.path.exists(ledger_path):
        with open(ledger_path, "w", newline="") as f:
            csv.writer(f).writerow(["batch_id", "kernel_id", "phase", "run_utc",
                                    "dataset_hash", "verdict_hash", "status"])
    with open(ledger_path, "a", newline="") as f:
        csv.writer(f).writerow(row)


def ledger_is_completed(ledger_path, kernel_id, phase):
    if not os.path.exists(ledger_path):
        return False
    with open(ledger_path, newline="") as f:
        for row in csv.DictReader(f):
            if (row["batch_id"] == BATCH_ID and row["kernel_id"] == kernel_id
                    and row["phase"] == phase and row["status"] == "COMPLETED"):
                return True
    return False


def run_batch(phase_filter=None):
    print("=" * 78)
    print(f"B-004 BATCH — FINAL YOUTUBE BACKLOG — {BATCH_ID}")
    print("=" * 78)

    ledger_path = os.path.join(PROJECT_DIR, "factory", "batch_ledger.csv")

    # ---- Clone-collapse: pairwise EXACT parameter_hash (= file sha) ----
    kernel_shas = {}
    for kid, kfile, _ in KERNELS:
        p = os.path.join(SCRIPT_DIR, f"{kfile}.py")
        kernel_shas[kid] = compute_file_hash(p)
        print(f"kernel {kid}: sha256 {kernel_shas[kid]}")
    collisions = []
    ids = list(kernel_shas)
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            if kernel_shas[ids[a]] == kernel_shas[ids[b]]:
                collisions.append((ids[a], ids[b]))
    print(f"CLONE-COLLAPSE (exact parameter_hash): collisions = {collisions if collisions else 'NONE'}")
    print(f"DATASET: {DATASET}")
    print(f"Dataset sha256: {compute_file_hash(DATASET)}")
    print("NOTE: 80% similarity threshold remains UNCALIBRATED (exact-hash only).")

    # ---- mechanism hashes (fingerprint_v2, 16-prefix lineage) ----
    sys.path.insert(0, PROJECT_DIR)
    from factory.fingerprint_v2 import mechanism_hash
    MECH_PARAMS = {
        "S-006": {
            "signal_family": "EMA_REGIME_REENTRY",
            "entry_trigger_class": "pullback_recross_fastEMA_in_regime",
            "exit_logic_class": "stop_target_maxhold",
            "session_hours": [],
            "timeframe": "H1",
            "instrument_class": "FX_MAJOR",
        },
        "S-007": {
            "signal_family": "REGRESSION_CHANNEL_FADE",
            "entry_trigger_class": "band_touch_with_stoch_kd_cross_extreme",
            "exit_logic_class": "anchor_stop_target_maxhold",
            "session_hours": [],
            "timeframe": "H1",
            "instrument_class": "FX_MAJOR",
        },
    }
    mech16 = {kid: mechanism_hash(p)[:16] for kid, p in MECH_PARAMS.items()}
    for kid, mh in mech16.items():
        print(f"mechanism_hash {kid}: {mh}")

    results = []
    killed = 0
    survived_to_oos = 0
    causes = {}

    for kernel_id, kernel_file, description in KERNELS:
        print(f"\n--- {kernel_id}: {description} ---")

        if ledger_is_completed(ledger_path, kernel_id, PHASE_IS):
            print("  IS already completed — SKIPPED (one-shot)")
            continue

        km = load_kernel(kernel_file)
        if not km:
            print("  PLUMBING-ERROR: kernel file not found")
            v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, "error", {}, ("PLUMBING-ERROR", "kernel file missing"))
            append_ledger(ledger_path, [BATCH_ID, kernel_id, PHASE_IS,
                                        datetime.utcnow().isoformat(), "error", v_hash,
                                        "PLUMBING-ERROR"])
            results.append({"kernel_id": kernel_id, "description": description,
                            "is_verdict": "PLUMBING-ERROR", "is_note": "kernel file missing",
                            "metrics": {}, "verdict_hash": v_hash, "cause": "PLUMBING-ERROR",
                            "param16": kernel_shas.get(kernel_id, "")[:16]})
            killed += 1
            causes["PLUMBING-ERROR"] = causes.get("PLUMBING-ERROR", 0) + 1
            continue

        try:
            success, metrics, verdict, ds_hash = evaluate_phase(km, DATASET, PHASE_IS)
        except Exception as e:
            print(f"  IS ERROR: {e}")
            v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, "error", {}, ("ERROR", str(e)))
            append_ledger(ledger_path, [BATCH_ID, kernel_id, PHASE_IS,
                                        datetime.utcnow().isoformat(), "error", v_hash,
                                        "PLUMBING-ERROR"])
            results.append({"kernel_id": kernel_id, "description": description,
                            "is_verdict": "PLUMBING-ERROR", "is_note": str(e),
                            "metrics": {}, "verdict_hash": v_hash, "cause": "PLUMBING-ERROR",
                            "param16": kernel_shas.get(kernel_id, "")[:16]})
            killed += 1
            causes["PLUMBING-ERROR"] = causes.get("PLUMBING-ERROR", 0) + 1
            continue

        v_hash = make_verdict_hash(kernel_id, BATCH_ID, PHASE_IS, ds_hash, metrics, verdict)
        append_ledger(ledger_path, [BATCH_ID, kernel_id, PHASE_IS,
                                    datetime.utcnow().isoformat(), ds_hash, v_hash,
                                    "COMPLETED"])
        cause = classify_cause(metrics) if verdict[0] != "PASS-INSAMPLE" else None
        print(f"  Gate1: {'PASS' if success else 'REJECT'}")
        print(f"  IS: n={metrics['n']}, NET PF={metrics['net_pf']:.4f}, "
              f"WR={metrics['win_rate']:.2%} -> {verdict[0]}"
              + (f" | autopsy: {cause}" if cause else ""))
        print("  LEDGER ROW APPENDED (one-shot consumed)")

        results.append({"kernel_id": kernel_id, "description": description,
                        "is_verdict": verdict[0], "is_note": verdict[1],
                        "metrics": metrics, "verdict_hash": v_hash,
                        "cause": cause, "ds_hash": ds_hash,
                        "param16": kernel_shas[kernel_id][:16]})

        if verdict[0] != "PASS-INSAMPLE":
            killed += 1
            causes[verdict[0]] = causes.get(verdict[0], 0) + 1

    # ---------------- §11 REPORT ----------------
    lifetime_before = get_lifetime_tested()
    n_effective = len(results)
    lifetime_total = lifetime_before + n_effective

    print("\n" + "=" * 78)
    print(f"{BATCH_ID} BATCH REPORT — SPEC §11")
    print("=" * 78)
    print(f"BATCH: {BATCH_ID} (Final YouTube Backlog)")
    print(f"DATE: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"KERNELS REQUESTED: {len(KERNELS)}")
    print(f"KERNELS EFFECTIVE: {n_effective}")
    print("  CLONE-COLLAPSE: exact parameter_hash collision check only — "
          f"{'COLLAPSED ' + str(collisions) if collisions else 'NONE found'}")
    print(f"KILLED: {killed}")
    print("  CAUSE OF DEATH (gate-verdict breakdown):")
    for c, cnt in sorted(causes.items()):
        print(f"    {c}: {cnt}")
    print(f"SURVIVED TO OOS: {survived_to_oos}")
    print(f"LIFETIME TOTAL TESTED: {lifetime_total}")
    print(f"  (before batch: {lifetime_before}, this batch: {n_effective})")
    print("  (ratified rule: resolved rows excl. SMOKE-TEST/UNTESTED)")
    print(f"NULL PASS RATE: 0% (calibrated 2026-09-13, B-000: 0/10)")
    print(f"CUMULATIVE LUCK-EXPECTED SURVIVORS: 0.00")

    for r in results:
        m = r["metrics"]
        print("\nAUTOPSY BLOCK " + r["kernel_id"] + ":")
        print(f"  n: {m.get('n')}")
        print(f"  WR net (unrounded): {m.get('win_rate', 0):.4%}")
        gp = m.get("gross_pf", 0)
        print(f"  GROSS PF: {gp:.4f}  GROSS WR: {m.get('gross_wr', 0):.4%}  "
              f"GROSS expectancy: {m.get('gross_expectancy', 0):+.4f}")
        print(f"  NET PF: {m.get('net_pf', 0):.4f}  NET expectancy: {m.get('net_expectancy', 0):+.4f}")
        print("  GROSS vs NET:")
        print(f"    {'':10} {'GROSS':>10} {'NET':>10}")
        print(f"    {'PF':<10} {(f'{gp:.4f}' if gp != float('inf') else 'inf'):>10} "
              f"{m.get('net_pf', 0):>10.4f}")
        print(f"    {'WR':<10} {m.get('gross_wr', 0):>10.2%} {m.get('win_rate', 0):>10.2%}")
        print(f"    {'Exp':<10} {m.get('gross_expectancy', 0):>+10.2f} {m.get('net_expectancy', 0):>+10.2f}")
        print(f"  EXIT BREAKDOWN: {m.get('exits', {})}")
        print(f"  VERDICT: {r['is_verdict']} — {r['is_note']}")
        if r.get("cause"):
            print(f"  CAUSE (autopsy classifier): {r['cause']}")
        print(f"  VERDICT HASH: {r['verdict_hash']}")

    print("\nGRAVEYARD DIFF PROPOSAL (NOT WRITTEN — Overseer confirms labels):")
    for r in results:
        if r.get("is_verdict") == "PASS-INSAMPLE":
            print(f"  {r['kernel_id']}: SURVIVED — no row")
            continue
        m = r["metrics"]
        cod = f"{r.get('cause', 'PENDING-OVERSEER')}: IS n={m.get('n')}, netPF={m.get('net_pf', 0):.4f}, grossPF={m.get('gross_pf', 0):.4f}, grossWR={m.get('gross_wr', 0):.2%}"
        print("  " + ",".join([
            r["kernel_id"],
            {"S-006": "S006_ema_trendfilter", "S-007": "S007_regression_stoch"}.get(r["kernel_id"], ""),
            {"S-006": "EMA50/200 regime pullback re-cross EURUSD H1",
             "S-007": "RegChan 2sd fade + stoch(14,3,3) EURUSD H1"}.get(r["kernel_id"], ""),
            r["is_verdict"], "",
            mech16.get(r["kernel_id"], "N/A"),
            r.get("param16", ""),
            cod,
            datetime.utcnow().strftime("%Y-%m-%d"),
            r["verdict_hash"], BATCH_ID,
        ]))
    print("=" * 78)
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description=f"{BATCH_ID} runner (2 kernels)")
    parser.add_argument("--phase", choices=["is", "oos", "all"], default="is",
                        help="OOS requires Overseer audit of IS report (Directive V item 4)")
    args = parser.parse_args()
    if args.phase == "oos":
        print("HOLD: OOS blocked until Overseer audits the IS report; "
              "killed-in-IS kernels are permanently ineligible.")
        return 2
    return run_batch(phase_filter=PHASE_IS if args.phase == "is" else None)


if __name__ == "__main__":
    sys.exit(main())
