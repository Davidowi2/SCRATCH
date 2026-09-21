"""
research/detectors/veed_v11_detector.py — Volume Extreme Event Detector (VEED) v1.1.

Per factory/preregistrations/VOLUME_EXTREME_EVENT_DETECTOR_v1.1.md (sha 48001ab8).

FROZEN PARAMETERS (Phase 1B, derivation event hash 30f46eb0...):
  X = 0.01   (outlier tail)
  Y = 0.25   (close-position threshold, two-sided)
  N = 4032   (14-day rolling reference, bar(t) excluded)

Emits an event stream ONLY. NO entry/exit logic, NO kernel, NO verdict.
Two-sided Rule 2: sell-side (closepos <= Y) or buy-side (closepos >= 1-Y),
direction label emitted as event attribute.

Conventions: linear-interpolation quantile; strict inequality Rule 1;
edge-case guards per §1 (range==0, trades==0, first N bars, ref<99% complete);
guard-excluded bars remain in reference sets.
"""

import csv
import math
import os
from datetime import datetime, timedelta, timezone

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VEED_X = 0.01
VEED_Y = 0.25
VEED_N = 4032
REF_COMPLETE_MIN = 0.99


def load_bars(path):
    bars = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bars.append({
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "trades": int(row["trades"]),
            })
    bars.sort(key=lambda b: b["time"])
    return bars


def quantile(values, q):
    """Linear-interpolation quantile (numpy-default convention)."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def detect(bars):
    """Run the VEED detector. Returns list of events.

    Each event dict:
      time, side (sell/buy), trades, logtrades, closepos, quantile_Qx
    """
    n = len(bars)
    events = []
    # precompute arrays
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    trades = [b["trades"] for b in bars]
    times = [b["time"] for b in bars]

    rngs = [highs[i] - lows[i] for i in range(n)]
    with math_error_suppressed():
        closepos = [(closes[i] - lows[i]) / rngs[i] if rngs[i] > 0 else None
                    for i in range(n)]
        logtrades = [math.log(trades[i] + 1) if trades[i] >= 0 else None
                     for i in range(n)]

    for i in range(n):
        # ---- edge-case guards ----
        if i < VEED_N:
            continue   # first N bars: insufficient reference
        if rngs[i] <= 0:
            continue   # range == 0: skip
        if trades[i] <= 0:
            continue   # trades == 0: skip
        if closepos[i] is None:
            continue

        # ---- reference set: bars strictly inside (t - 14 days, t) ----
        cutoff = times[i] - timedelta(days=14)
        ref = []
        for j in range(i - 1, -1, -1):
            if times[j] <= cutoff:
                break
            ref.append(logtrades[j])
        if len(ref) < REF_COMPLETE_MIN * VEED_N:
            continue   # reference < 99% complete: skip

        # ---- Rule 1: logtrades(t) > (1-X) quantile of reference ----
        q = quantile(ref, 1.0 - VEED_X)
        if q is None or logtrades[i] <= q:
            continue

        # ---- Rule 2: close-position (two-sided) ----
        cp = closepos[i]
        if cp <= VEED_Y:
            side = "sell"
        elif cp >= 1.0 - VEED_Y:
            side = "buy"
        else:
            continue

        events.append({
            "time": times[i].strftime("%Y-%m-%d %H:%M:%S"),
            "side": side,
            "trades": trades[i],
            "logtrades": round(logtrades[i], 6),
            "closepos": round(cp, 6),
            "quantile_Qx": round(q, 6),
        })

    return events


class math_error_suppressed:
    def __enter__(self): return self
    def __exit__(self, *a): pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VEED v1.1 detector — emits event stream only")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", default=None, help="optional: write events to CSV")
    args = parser.parse_args()

    bars = load_bars(args.dataset)
    print(f"VEED v1.1 detector — bars: {len(bars)}  range: {bars[0]['time']}..{bars[-1]['time']}")
    print(f"FROZEN: X={VEED_X} Y={VEED_Y} N={VEED_N} ref_complete>={REF_COMPLETE_MIN}")

    events = detect(bars)
    sell = sum(1 for e in events if e["side"] == "sell")
    buy = sum(1 for e in events if e["side"] == "buy")
    print(f"events: {len(events)}  sell-side: {sell}  buy-side: {buy}")

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["time", "side", "trades", "logtrades", "closepos", "quantile_Qx"])
            w.writeheader()
            w.writerows(events)
        print(f"wrote: {args.output}")
    else:
        # print first/last 5 as sample
        for e in events[:5]:
            print(f"  {e}")
        if len(events) > 10:
            print("  ...")
        for e in events[-5:]:
            print(f"  {e}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
