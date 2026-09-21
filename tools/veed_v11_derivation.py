#!/usr/bin/env python3
"""
tools/veed_v11_derivation.py — PHASE 1B: VEED v1.1 parameter derivation.

Implements EXACTLY §4 of factory/preregistrations/VOLUME_EXTREME_EVENT_DETECTOR_v1.1.md
on the RETIRED holdout (2019-12-31 .. 2020-12-31 effective, see FLAG-5).

Calibration ONLY:
- NO detector code (no event stream is emitted or persisted).
- NO kernel code. NO backtest. NO batch/luck budget consumption.

Steps:
  STEP 1: grid X over {0.5%, 1%, 2%, 3%, 5%} -> qualifying-bar rate
          (bars/day); select per declared rule (inside 3-8/day;
          tie-break |rate-5.5|; else closest distance).
  STEP 2: grid Y over {10%, 15%, 20%, 25%, 33%} applied ONLY to
          derived-X passers -> combined event count; select per declared
          rule (inside 250-750; tie-break |count-500|; else closest).
  STEP 3: freeze + log to ledger as parameter-derivation event.

Conventions (spec-declared): linear-interpolation quantiles; strict
inequality Rule 1; guards per §1 (range==0 skip, trades==0 skip, first N
skip, reference <99% complete skip); guard-excluded bars REMAIN in
reference sets (FLAG-3); Rule 2 two-sided with direction recorded (FLAG-2).
"""

import csv
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "research", "data", "crypto",
                    "btcusdt_5m_tradecount_holdout_2019_2020.csv")
LEDGER = os.path.join(PROJECT, "factory", "batch_ledger.csv")
REPORT = os.path.join(PROJECT, "research", "data", "probes",
                      "phase1b_veed_derivation_report.txt")

N_REF = 4032            # 14 days of 5m bars
REF_COMPLETE_MIN = 0.99
X_GRID = [0.005, 0.01, 0.02, 0.03, 0.05]
Y_GRID = [0.10, 0.15, 0.20, 0.25, 0.33]
BARS_PER_DAY = 288
TARGET_X_LO, TARGET_X_HI = 3.0, 8.0     # outlier bars/day interval
TARGET_Y_LO, TARGET_Y_HI = 250, 750     # combined candidates interval


def load_bars(path):
    bars = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bars.append((
                datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                float(row["high"]), float(row["low"]), float(row["close"]),
                int(row["trades"]),
            ))
    bars.sort(key=lambda b: b[0])
    return bars


def main():
    bars = load_bars(DATA)
    n = len(bars)
    ts = np.array([b[0] for b in bars])
    highs = np.array([b[1] for b in bars])
    lows = np.array([b[2] for b in bars])
    closes = np.array([b[3] for b in bars])
    trades = np.array([b[4] for b in bars], dtype=np.int64)
    logtrades = np.log(trades.astype(float) + 1.0)
    rng = highs - lows
    with np.errstate(invalid="ignore", divide="ignore"):
        closepos = np.where(rng > 0, (closes - lows) / np.where(rng > 0, rng, 1), np.nan)

    print("=" * 74)
    print("PHASE 1B — VEED v1.1 PARAMETER DERIVATION (holdout, RETIRED after run)")
    print(f"Data: {os.path.basename(DATA)}")
    print(f"Bars: {n}  range: {bars[0][0]} .. {bars[-1][0]}")
    print(f"Reference N = {N_REF} bars (14d rolling, bar(t) excluded, >=99% complete)")
    print("=" * 74)

    # ---- evaluate guards + Rule 1 for every bar once (quantile per X) ----
    # eligible(t): index >= N_REF, trades>0, rng>0, |R(t)|>=0.99*N_REF
    eligible = np.zeros(n, dtype=bool)
    ref_counts = np.zeros(n, dtype=np.int64)
    for i in range(N_REF, n):
        lo = ts[i] - timedelta(days=14)
        # count bars strictly inside (t-14d, t)
        j = np.searchsorted(ts, lo, side="right")
        cnt = i - j
        ref_counts[i] = cnt
        if cnt >= REF_COMPLETE_MIN * N_REF and trades[i] > 0 and rng[i] > 0:
            eligible[i] = True

    n_elig = int(eligible.sum())
    print(f"Eligible candidate bars: {n_elig} / {n} "
          f"(guards: first-N, trades==0: {int((trades==0).sum())}, "
          f"range==0: {int((rng==0).sum())}, ref<99%: {n - N_REF - n_elig + int(((trades>0)&(rng>0)).sum() - n_elig)})")

    # Rule 1 pass per X: logtrades(t) > (1-X) quantile of reference logtrades
    passers = {}
    for x in X_GRID:
        ok = np.zeros(n, dtype=bool)
        for i in np.nonzero(eligible)[0]:
            lo = ts[i] - timedelta(days=14)
            j = np.searchsorted(ts, lo, side="right")
            ref = logtrades[j:i]
            if ref.size and logtrades[i] > np.quantile(ref, 1.0 - x):
                ok[i] = True
        passers[x] = ok

    # ---- STEP 1: X grid table ----
    print("\nSTEP 1 — X GRID (Rule 1 qualifying-bar rate)")
    print(f"{'X':>6} | {'pass bars':>10} | {'bars/day':>9} | in 3-8/day")
    print("-" * 46)
    x_rows = []
    for x in X_GRID:
        cnt = int(passers[x].sum())
        per_day = cnt / BARS_PER_DAY
        inside = TARGET_X_LO <= per_day <= TARGET_X_HI
        x_rows.append((x, cnt, per_day, inside))
        print(f"{x*100:>5}% | {cnt:>10} | {per_day:>9.2f} | {'YES' if inside else 'no'}")

    def pick_x(rows):
        inside = [r for r in rows if r[3]]
        if inside:
            return min(inside, key=lambda r: abs(r[2] - (TARGET_X_LO + TARGET_X_HI) / 2))
        return min(rows, key=lambda r: min(abs(r[2] - TARGET_X_LO), abs(r[2] - TARGET_X_HI)))

    X = pick_x(x_rows)
    x_star = X[0]
    print(f"\nCHOSEN X = {x_star*100:g}%  "
          f"(rate {X[2]:.2f} bars/day, {X[1]} bars)")

    # ---- STEP 2: Y grid table (applied ONLY to X passers) ----
    xpass = passers[x_star]
    print(f"\nSTEP 2 — Y GRID (Rule 2 applied to the {int(xpass.sum())} X-passing bars)")
    print(f"{'Y':>6} | {'combined':>9} | {'sell-side':>10} | {'buy-side':>9} | in 250-750")
    print("-" * 60)
    y_rows = []
    for y in Y_GRID:
        sell = 0
        buy = 0
        for i in np.nonzero(xpass)[0]:
            cp = closepos[i]
            if np.isnan(cp):
                continue
            if cp <= y:
                sell += 1
            elif cp >= 1.0 - y:
                buy += 1
        comb = sell + buy
        inside = TARGET_Y_LO <= comb <= TARGET_Y_HI
        y_rows.append((y, comb, sell, buy, inside))
        print(f"{y*100:>5}% | {comb:>9} | {sell:>10} | {buy:>9} | {'YES' if inside else 'no'}")

    def pick_y(rows):
        inside = [r for r in rows if r[4]]
        if inside:
            return min(inside, key=lambda r: abs(r[1] - (TARGET_Y_LO + TARGET_Y_HI) / 2))
        return min(rows, key=lambda r: min(abs(r[1] - TARGET_Y_LO), abs(r[1] - TARGET_Y_HI)))

    Y = pick_y(y_rows)
    y_star = Y[0]
    print(f"\nCHOSEN Y = {y_star*100:g}%  (combined {Y[1]} candidates: "
          f"sell-side {Y[2]}, buy-side {Y[3]})")

    # ---- STEP 3: freeze + ledger ----
    now = datetime.now(timezone.utc)
    doc = {
        "event": "VEED-v1.1-PARAMETER-DERIVATION",
        "spec": "factory/preregistrations/VOLUME_EXTREME_EVENT_DETECTOR_v1.1.md",
        "spec_sha256": hashlib.sha256(open(os.path.join(
            PROJECT, "factory", "preregistrations",
            "VOLUME_EXTREME_EVENT_DETECTOR_v1.1.md"), "rb").read()).hexdigest(),
        "data_file": os.path.relpath(DATA, PROJECT).replace("\\", "/"),
        "data_sha256": hashlib.sha256(open(DATA, "rb").read()).hexdigest(),
        "holdout_window_requested": "2019-09-01..2020-12-31",
        "holdout_window_effective": f"{bars[0][0]:%Y-%m-%d}..{bars[-1][0]:%Y-%m-%d}",
        "holdout_note": ("5m archive begins 2019-12-31 (single daily file); "
                         "2019-09..2019-12 does not exist at 5m granularity "
                         "(S3-listed). Effective window = full available."),
        "N_reference": N_REF,
        "eligible_candidate_bars": n_elig,
        "X_grid": [{"X": r[0], "pass_bars": r[1], "bars_per_day": round(r[2], 4),
                    "inside_3_8": bool(r[3])} for r in x_rows],
        "Y_grid": [{"Y": r[0], "combined": r[1], "sell_side": r[2],
                    "buy_side": r[3], "inside_250_750": bool(r[4])} for r in y_rows],
        "chosen_X": x_star,
        "chosen_Y": y_star,
        "achieved_outlier_bars_per_day": round(X[2], 4),
        "achieved_combined_candidates": Y[1],
        "budget_note": "calibration only — consumes NO batch/luck budget",
        "run_utc": now.isoformat(),
    }
    derivation_hash = hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=2) + "\n")
    report_sha = hashlib.sha256(open(REPORT, "rb").read()).hexdigest()

    with open(LEDGER, "a", newline="") as f:
        csv.writer(f).writerow(["VEED-DERIVE-1B", "VEED-v1.1", "derivation",
                                now.isoformat(), report_sha, derivation_hash,
                                "COMPLETED"])

    print("\nSTEP 3 — FROZEN AND LOGGED")
    print(f"X = {x_star}  Y = {y_star}  N = {N_REF}")
    print(f"holdout effective: {doc['holdout_window_effective']}")
    print(f"derivation event hash: {derivation_hash}")
    print(f"report: {os.path.relpath(REPORT, PROJECT)}  sha256: {report_sha}")
    print("LEDGER ROW APPENDED: VEED-DERIVE-1B (parameter-derivation event)")
    print("Budget consumed: NONE (calibration, not verdict).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
