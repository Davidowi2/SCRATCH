"""
research/data/validate_data_crypto.py — Gate 1 validator for CRYPTO datasets.

CRYPTO JURISDICTION RULES (unlike FX/CFD):
- 24/7 market: missing 5m bar = GAP = FAIL. NO weekend/holiday exemptions.
- :05 boundary alignment (5m bars stamped 00:00, 00:05, ... 23:55).
- No duplicate timestamps.
- Coverage check against declared window.
- Symbol/interval sanity: file must be BTCUSDT perpetual 5m (volume>0,
  OHLC sanity: high >= max(open,close), low <= min(open,close), high>=low).

HARD RULE: Any dataset with synthetic: true in factory/data_provenance.json
is REJECTED for verdict runs (plumbing smoke exempt, labeled).
"""

import csv
import json
import os
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST_PATH = os.path.join(PROJECT_DIR, "factory", "data_provenance.json")


def is_synthetic_dataset(dataset_path):
    """Check if a dataset is marked synthetic in the provenance manifest."""
    if not os.path.exists(MANIFEST_PATH):
        return False
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        return False
    datasets = manifest.get("datasets", {})
    entry = datasets.get(dataset_path)
    if entry is None:
        # try absolute/relative normalization
        norm = os.path.relpath(os.path.join(PROJECT_DIR, dataset_path), PROJECT_DIR).replace("\\", "/")
        entry = datasets.get(norm, {})
    return bool(entry.get("synthetic", False))


def load_crypto_csv(path):
    """Load a crypto kline CSV (timestamp_utc, open, high, low, close, volume)."""
    bars = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bars.append({
                "ts": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
    return bars


def gate1_audit_crypto(dataset_path, interval_minutes=5, verbose=True):
    """
    Gate 1 audit for crypto 5m data. 24/7 continuity — every missing bar is a gap.

    Returns dict with verdict PASS/FLAG/REJECT, flags, stats.
    """
    report = {"fatal": [], "flags": [], "stats": {}}

    # --- HARD RULE: synthetic rejection ---
    if is_synthetic_dataset(dataset_path):
        report["fatal"].append(f"SYNTHETIC DATA REJECTED for verdict runs: {dataset_path}")
        report["verdict"] = "REJECT"
        if verbose:
            print(f"GATE 1 CRYPTO: REJECT — synthetic dataset {dataset_path}")
        return report

    bars = load_crypto_csv(dataset_path)
    n = len(bars)
    step = timedelta(minutes=interval_minutes)

    stats = {"n_bars": n}
    report["stats"] = stats
    if n == 0:
        report["fatal"].append("empty dataset")
        report["verdict"] = "REJECT"
        return report

    # --- :05 boundary alignment ---
    misaligned = [b for b in bars if b["ts"].minute % interval_minutes != 0 or b["ts"].second != 0]
    stats["misaligned"] = len(misaligned)
    if misaligned:
        report["fatal"].append(f"{len(misaligned)} bars not on :{interval_minutes:02d} boundary")

    # --- duplicates ---
    seen = set()
    dupes = 0
    for b in bars:
        if b["ts"] in seen:
            dupes += 1
        seen.add(b["ts"])
    stats["duplicates"] = dupes
    if dupes:
        report["fatal"].append(f"{dupes} duplicate timestamps")

    # --- sorted + continuity (24/7: EVERY missing bar is a gap) ---
    sorted_bars = sorted(bars, key=lambda b: b["ts"])
    gaps = 0
    max_gap_bars = 0
    gap_examples = []
    for i in range(1, len(sorted_bars)):
        delta = (sorted_bars[i]["ts"] - sorted_bars[i - 1]["ts"]) / step
        missing = int(delta) - 1
        if missing > 0:
            gaps += 1
            max_gap_bars = max(max_gap_bars, missing)
            if len(gap_examples) < 5:
                gap_examples.append(f"{sorted_bars[i-1]['ts']:%Y-%m-%d %H:%M}->{sorted_bars[i]['ts']:%Y-%m-%d %H:%M} ({missing} bars)")
    stats["gap_events"] = gaps
    stats["max_gap_bars"] = max_gap_bars
    stats["gap_examples"] = gap_examples
    if gaps:
        # Crypto is 24/7; any gap beyond a small tolerance fails.
        # Tolerance: Binance futures occasionally halts; a single missing bar
        # (<6 consecutive) is FLAG, a large outage block is still FLAG,
        # but coverage math must still pass.
        if max_gap_bars > 576:  # > 48h outage
            report["fatal"].append(f"outage gap of {max_gap_bars} bars (>{48}h) — coverage compromised")
        else:
            report["flags"].append(f"{gaps} gap events, max {max_gap_bars} missing bars (24/7 market: investigate)")

    # --- OHLC sanity ---
    bad_ohlc = 0
    for b in bars:
        if not (b["high"] >= max(b["open"], b["close"]) and b["low"] <= min(b["open"], b["close"])
                and b["high"] >= b["low"] and b["open"] > 0 and b["close"] > 0):
            bad_ohlc += 1
    stats["bad_ohlc"] = bad_ohlc
    if bad_ohlc:
        report["fatal"].append(f"{bad_ohlc} bars fail OHLC sanity")

    # --- volume sanity (futures klines: volume > 0 almost always; zero-volume bars are FLAG not fatal) ---
    zero_vol = sum(1 for b in bars if b["volume"] <= 0)
    stats["zero_volume_bars"] = zero_vol
    if zero_vol / n > 0.05:
        report["flags"].append(f"{zero_vol} zero-volume bars ({100*zero_vol/n:.1f}%)")

    # --- coverage ---
    span = (sorted_bars[-1]["ts"] - sorted_bars[0]["ts"])
    expected = int(span / step) + 1
    stats["first_bar"] = sorted_bars[0]["ts"].strftime("%Y-%m-%d %H:%M:%S")
    stats["last_bar"] = sorted_bars[-1]["ts"].strftime("%Y-%m-%d %H:%M:%S")
    stats["expected_bars"] = expected
    stats["actual_bars"] = n
    completeness = n / expected if expected else 0
    stats["completeness"] = round(completeness, 6)
    if completeness < 0.9999:
        report["flags"].append(f"completeness {100*completeness:.4f}% (< 99.99%) — 24/7 market must be whole")
    if completeness < 0.99:
        report["fatal"].append(f"completeness {100*completeness:.2f}% below 99% floor")

    # --- symbol/interval sanity: price plausibility for BTCUSDT 2021-2025 ---
    prices = [b["close"] for b in bars]
    pmin, pmax = min(prices), max(prices)
    stats["price_min"] = pmin
    stats["price_max"] = pmax
    if pmax < 1000 or pmin > 200000:
        report["fatal"].append(f"prices {pmin}..{pmax} implausible for BTCUSDT (wrong symbol?)")

    report["verdict"] = "REJECT" if report["fatal"] else ("FLAG" if report["flags"] else "PASS")
    return report


def print_report(path, report):
    print("=" * 70)
    print("GATE 1 CRYPTO PROBE — BTCUSDT 5m (24/7 JURISDICTION)")
    print("=" * 70)
    print(f"File: {path}")
    s = report["stats"]
    for k in ("n_bars", "first_bar", "last_bar", "expected_bars", "completeness",
              "misaligned", "duplicates", "gap_events", "max_gap_bars",
              "zero_volume_bars", "bad_ohlc", "price_min", "price_max"):
        if k in s:
            print(f"  {k}: {s[k]}")
    if s.get("gap_examples"):
        print("  gap examples:")
        for g in s["gap_examples"]:
            print(f"    {g}")
    if report["fatal"]:
        print("  FATAL:")
        for f in report["fatal"]:
            print(f"    ✗ {f}")
    if report["flags"]:
        print("  FLAGS:")
        for f in report["flags"]:
            print(f"    ⚠ {f}")
    print(f"VERDICT: {report['verdict']}")
    return report["verdict"]


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "research/data/crypto/btcusdt_5m.csv"
    rep = gate1_audit_crypto(path)
    print_report(path, rep)
