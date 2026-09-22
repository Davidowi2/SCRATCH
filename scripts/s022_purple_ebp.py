#!/usr/bin/env python3
"""S-022 EBP rapid scan: raw signal truth-serum test on 3 timeframes."""
import csv
import os
import sys
from datetime import datetime, timezone
import statistics

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

def load_5m(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("close") or row["close"] in ("", "null", "None"):
                continue
            ts = datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append({
                "time": ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    return sorted(rows, key=lambda r: r["time"])

def aggregate(rows, n):
    """Aggregate n bars into 1."""
    out = []
    for i in range(0, len(rows), n):
        chunk = rows[i:i+n]
        if len(chunk) < 2:
            continue
        out.append({
            "time": chunk[0]["time"],
            "open": chunk[0]["open"],
            "high": max(c["high"] for c in chunk),
            "low": min(c["low"] for c in chunk),
            "close": chunk[-1]["close"],
        })
    return out

def run_ebp_scan(rows, fee=0.001):
    """Scan for EBP setups and compute metrics."""
    signals = []
    for i in range(2, len(rows) - 1):
        b_prev = rows[i - 1]
        b_curr = rows[i]
        b_next = rows[i + 1]

        # Bullish EBP: Low[t] < Low[t-1] AND Close[t] > Open[t-1]
        bullish = b_curr["low"] < b_prev["low"] and b_curr["close"] > b_prev["open"]
        # Bearish EBP: High[t] > High[t-1] AND Close[t] < Open[t-1]
        bearish = b_curr["high"] > b_prev["high"] and b_curr["close"] < b_prev["open"]

        entry = None
        stop = None
        direction = None
        target = None

        if bullish:
            direction = "LONG"
            stop = b_curr["low"]
            entry = b_next["open"]
            target = entry + 1.5 * (entry - stop)
        elif bearish:
            direction = "SHORT"
            stop = b_curr["high"]
            entry = b_next["open"]
            target = entry - 1.5 * (stop - entry)

        if entry is None or stop is None or target is None:
            continue

        # Find exit: check bars after entry for target or stop hit
        exit_price = None
        exit_reason = None
        risk = abs(entry - stop)
        if risk == 0:
            continue

        for j in range(i + 1, min(i + 50, len(rows))):
            b_future = rows[j]
            if direction == "LONG":
                if b_future["high"] >= target:
                    exit_price = target
                    exit_reason = "TARGET"
                    break
                if b_future["low"] <= stop:
                    exit_price = stop
                    exit_reason = "STOP"
                    break
            else:
                if b_future["low"] <= target:
                    exit_price = target
                    exit_reason = "TARGET"
                    break
                if b_future["high"] >= stop:
                    exit_price = stop
                    exit_reason = "STOP"
                    break

        if exit_price is None:
            # Max hold, exit at close of last bar
            exit_price = rows[min(i + 50, len(rows) - 1)]["close"]
            exit_reason = "MAX_HOLD"

        r_multiple = (exit_price - entry) / risk if direction == "LONG" else (entry - exit_price) / risk
        net_r = r_multiple - fee  # subtract round-trip fee as R%

        signals.append({
            "time": b_curr["time"],
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit": exit_price,
            "exit_reason": exit_reason,
            "r_multiple": r_multiple,
            "net_r": net_r,
        })

    n_signals = len(signals)
    if n_signals == 0:
        return {"n": 0, "wr": 0, "pf": 0, "exp": 0, "sigs": []}

    wins = sum(1 for s in signals if s["net_r"] > 0)
    win_rate = wins / n_signals
    gross_profits = sum(s["net_r"] for s in signals if s["net_r"] > 0)
    gross_losses = abs(sum(s["net_r"] for s in signals if s["net_r"] < 0))
    pf = gross_profits / gross_losses if gross_losses > 0 else float("inf")
    expectancy = sum(s["net_r"] for s in signals) / n_signals

    return {"n": n_signals, "wr": win_rate, "pf": pf, "exp": expectancy, "sigs": signals}

def main():
    path = os.path.join(PROJECT_DIR, "research", "data", "crypto", "btcusdt_5m.csv")
    if not os.path.exists(path):
        # Try find it
        candidates = [
            "research/data/crypto/btcusdt_5m.csv",
            "research/data/btcusdt_5m.csv",
        ]
        for c in candidates:
            full = os.path.join(PROJECT_DIR, c)
            if os.path.exists(full):
                path = full
                break
        else:
            print("BTCUSDT 5m data NOT FOUND")
            return 1

    print(f"Loading: {path}")
    rows_5m = load_5m(path)
    print(f"5m bars loaded: {len(rows_5m)}")
    print(f"Range: {rows_5m[0]['time']} .. {rows_5m[-1]['time']}")

    # IS window: 2021-2023
    is_start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    is_end = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    rows_is = [r for r in rows_5m if is_start <= r["time"] <= is_end]
    print(f"IS (2021-2023) 5m bars: {len(rows_is)}")

    # Aggregate to 15m, 1H, 4H
    rows_15m = aggregate(rows_is, 3)
    rows_1h = aggregate(rows_is, 12)
    rows_4h = aggregate(rows_is, 48)

    print(f"\nAggregated: 15m={len(rows_15m)}, 1H={len(rows_1h)}, 4H={len(rows_4h)}")

    print(f"\n{'='*72}")
    print("S-022 EBP TRUTH SERUM SCAN (RAW ENGINE, NO CONFLUENCE)")
    print(f"{'='*72}")
    print(f"Signal: Bullish (Low[t]<Low[t-1] & Close[t]>Open[t-1]) / Bearish (mirror)")
    print(f"Entry: Open[t+1] | Stop: sweep extreme | Target: 1.5R | Fee: 0.10% RT")
    print(f"Guru claim comparison: 87% Win Rate")

    print(f"\n{'='*72}")
    print(f"{'Timeframe':<12} | {'n_signals':>10} | {'Win_Rate':>9} | {'PF':>6} | {'Expectancy':>11}")
    print(f"{'-'*72}")

    results = {}
    for label, data in [("5m", rows_is), ("15m", rows_15m), ("1H", rows_1h), ("4H", rows_4h)]:
        r = run_ebp_scan(data)
        results[label] = r
        wr = f"{r['wr']*100:.1f}%"
        pf_str = f"{r['pf']:.2f}" if r["pf"] != float("inf") else "∞"
        print(f"{label:<12} | {r['n']:>10} | {wr:>8} | {pf_str:>6} | {'':>5}{r['exp']:+.3f}R")

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    guru_claim = 0.87
    kill = True
    for label in ["5m", "15m", "1H", "4H"]:
        r = results[label]
        if r["wr"] >= 0.55:
            kill = False
            break

    for label in ["5m", "15m", "1H", "4H"]:
        r = results[label]
        wr_str = f"{r['wr']*100:.1f}%"
        guru_gap = (r["wr"] - guru_claim) * 100
        above_55 = "✓" if r["wr"] >= 0.55 else "✗"
        print(f"  {label:>4}: WR={wr_str} vs guru 87% (gap={guru_gap:+.1f}pp), >55%? {above_55}")

    if kill:
        print(f"\n  VERDICT: KILL — WR < 55% on ALL timeframes")
        print(f"  MECHANISM-DEAD (Guru Claim Debunked): raw EBP engine fails truth serum")
        print(f"  Do NOT build confluence layers. Do NOT proceed to OOS.")
    else:
        surviving = [l for l in ["5m", "15m", "1H", "4H"] if results[l]["wr"] >= 0.55]
        print(f"\n  VERDICT: PROCEED TO CONFLUENCE on {surviving}")

    return 0

if __name__ == "__main__":
    main()
