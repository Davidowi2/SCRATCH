"""
research/backtest/S012_banklevel_crypto.py — S-012 Bank-Level Crypto Arm

Implements the exact math from factory/preregistrations/S012.md (Owner Ruling 4):

1. Bank range: high/low of 5m bars stamped 00:00:00-00:25:00 UTC inclusive
   (bars :00, :05, :10, :15, :20, :25).
2. Trigger window: bars stamped 00:30:00-01:25:00 UTC inclusive. No M4
   pre-window rule needed: bank ends :25, window begins :30, no unclaimed bar.
3. Signal: FIRST bar j in window with close[j] beyond range AND
   close[j-1] not beyond (cross-event, first crossing only) AND
   (high[j]-low[j]) >= 1.0 * ATR14(5m) — ATR over the 14 bars preceding j.
4. Entry: open of bar j+1. One trade per UTC day max.
5. Stop: opposite extreme of trigger bar. Target: 1.5R.
6. Hard flat: close of the bar stamped 01:30:00 UTC.
7. Friction: 2 * 0.0005 * entry_price (taker fee 5 bps per leg, per trade).
   PIP = 1.0 USD point. Prices are last-trade (futures klines); no spread
   term — the fee is the modeled cost floor (documented, not hidden).
8. 24/7 rule: a day missing ANY bar in the required clock span
   (00:00..01:30) is SKIPPED entirely (no partial-day ranges).

RULINGS:
- R1: stop before target; one bar touching both = loss; open gapping through
  stop fills at open; max-hold/flat checked after, at the close.
- R3: entry-bar open gapping through planned stop discards signal entirely.
- B3 lineage: entry bar IS evaluated (i += 1 after trade creation).
- B4 lineage: gross metrics derived from gross_pips (pre-friction).
- M2: a 2020 slice (OUTSIDE frozen windows) may be used for audit-only smoke
  after Overseer approval. REAL Binance UM klines start 2019-09-08, so no
  synthetic smoke data is needed or permitted.
- Synthetic data is REJECTED at Gate 1 (hard rule via provenance manifest).

Readability: expectancy printed in points AND % of mean entry price.
Verdict gates consume PF/WR only (unitless).
"""

import csv
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data_crypto import gate1_audit_crypto

EXPERIMENT_ID = "S-012"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "BANKLEVEL"
PARAM_DESC = "Bank-level crypto arm: BTCUSDT perp 5m, first-hour opening range breakout"

FEE_RATE = 0.0005          # 5 bps taker per leg
PIP = 1.0                  # 1 point = 1.0 USD
ATR_PERIOD = 14
TARGET_R = 1.5

# UTC clock (5m resolution) — card verbatim (prereg S012.md MATH §1-2,7)
RANGE_START = 0            # 00:00:00
RANGE_END_MIN = 25         # 00:25:00 inclusive (bars :00,:05,:10,:15,:20,:25)
WINDOW_START_MIN = 30      # 00:30:00 inclusive
WINDOW_END_MIN = 85        # 01:25:00 inclusive (= 1*60+25)
HARD_FLAT_MIN = 90         # 01:30:00 — exit at this bar's close


def minute_of_day(dt):
    return dt.hour * 60 + dt.minute


class Trade:
    def __init__(self, entry_idx, entry_price, side, stop, target):
        self.entry_idx = entry_idx
        self.entry_price = entry_price
        self.side = side
        self.stop = stop
        self.target = target
        self.exit_idx = None
        self.exit_price = None
        self.exit_reason = None
        self.bars_held = None
        self.pips = None          # net points after per-trade friction
        self.gross_pips = None    # points before friction
        self.friction = None


def load_dataset(path):
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
            })
    return bars


def atr14(highs, lows, closes, j):
    """ATR14 over the 14 bars PRECEDING j (indices j-14..j-1), same lineage
    convention as S-008/S-010 (simple mean of true ranges)."""
    if j < ATR_PERIOD:
        return None
    trs = []
    for k in range(j - ATR_PERIOD, j):
        if k == 0:
            tr = highs[k] - lows[k]
        else:
            tr = max(
                highs[k] - lows[k],
                abs(highs[k] - closes[k - 1]),
                abs(lows[k] - closes[k - 1]),
            )
        trs.append(tr)
    return sum(trs) / ATR_PERIOD


def friction_for(entry_price):
    """Per-trade friction: 2 legs * 5 bps * entry price, in points."""
    return 2 * FEE_RATE * entry_price


def day_indices(bars, day_start_idx):
    """Return dict minute_of_day -> index for this UTC day's available bars,
    plus the last index belonging to the day."""
    mins = {}
    i = day_start_idx
    while i < len(bars) and bars[i]["time"].date() == bars[day_start_idx]["time"].date():
        mins[minute_of_day(bars[i]["time"])] = i
        i += 1
    return mins, i


def compute_day_structure(bars, day_start_idx):
    """
    Validate the day's clock span and compute bank range (card verbatim).
    Required bars: range 00:00..00:25 (:00,:05,:10,:15,:20,:25), window
    00:30..01:25 (14 bars), hard-flat bar 01:30.
    A day missing ANY required bar is untradable (24/7 rule) -> ok=False.
    Returns dict with: ok, range_high, range_low, window_idxs, flat_idx.
    """
    range_mins = list(range(RANGE_START, RANGE_END_MIN + 1, 5))          # 0,5,10,15,20,25
    window_mins = list(range(WINDOW_START_MIN, WINDOW_END_MIN + 1, 5))  # 30..85
    flat_min = HARD_FLAT_MIN                                             # 90
    need = range_mins + window_mins + [flat_min]

    mins, day_end = day_indices(bars, day_start_idx)
    missing = [m for m in need if m not in mins]
    if missing:
        return {"ok": False, "reason": "missing_bars"}

    hi = max(bars[mins[m]]["high"] for m in range_mins)
    lo = min(bars[mins[m]]["low"] for m in range_mins)
    return {
        "ok": True,
        "range_high": hi,
        "range_low": lo,
        "window_idxs": [mins[m] for m in window_mins],
        "flat_idx": mins[flat_min],
    }


def run_backtest(bars):
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades = []

    position_open = False
    day_done = False          # one trade per UTC day (or day processed/skipped)
    current_day = None
    day_start_idx = 0
    struct = None

    i = 0
    while i < n:
        bar_time = bars[i]["time"]
        bar_date = bar_time.date()

        # New UTC day: reset
        if bar_date != current_day:
            current_day = bar_date
            day_done = False
            day_start_idx = i
            struct = None

        # --- manage open position (R1 ordering) ---
        if position_open:
            t = trades[-1]
            j = i
            exited = False

            if t.side == "SHORT":
                if opens[j] >= t.stop:
                    t.exit_idx, t.exit_price = j, opens[j]
                    t.exit_reason = "STOP"
                    exited = True
                elif highs[j] >= t.stop:
                    t.exit_idx, t.exit_price = j, t.stop
                    t.exit_reason = "STOP"
                    exited = True
                elif lows[j] <= t.target:
                    t.exit_idx, t.exit_price = j, t.target
                    t.exit_reason = "TARGET"
                    exited = True
            else:  # LONG
                if opens[j] <= t.stop:
                    t.exit_idx, t.exit_price = j, opens[j]
                    t.exit_reason = "STOP"
                    exited = True
                elif lows[j] <= t.stop:
                    t.exit_idx, t.exit_price = j, t.stop
                    t.exit_reason = "STOP"
                    exited = True
                elif highs[j] >= t.target:
                    t.exit_idx, t.exit_price = j, t.target
                    t.exit_reason = "TARGET"
                    exited = True

            # Hard flat: close of the bar stamped 01:30 UTC (after stop/target)
            if not exited and minute_of_day(bars[j]["time"]) >= HARD_FLAT_MIN:
                t.exit_idx, t.exit_price = j, closes[j]
                t.exit_reason = "HARDFLAT"
                exited = True

            if exited:
                position_open = False
                t.bars_held = t.exit_idx - t.entry_idx
                if t.side == "SHORT":
                    gross = (t.entry_price - t.exit_price) / PIP
                else:
                    gross = (t.exit_price - t.entry_price) / PIP
                t.gross_pips = gross
                t.friction = friction_for(t.entry_price)
                t.pips = gross - t.friction
                i = t.exit_idx + 1
                continue

            i += 1
            continue

        # --- day structure (computed lazily once per day) ---
        if struct is None:
            struct = compute_day_structure(bars, day_start_idx)
            if not struct["ok"]:
                day_done = True  # untradable day: skip entirely (24/7 rule)
        if day_done or not struct.get("ok", False):
            i += 1
            continue

        range_high = struct["range_high"]
        range_low = struct["range_low"]

        # --- signal search: window bars only (00:30..01:25 inclusive) ---
        # No M4 pre-window rule for S-012: bank ends :25, window begins :30,
        # so the cross-event prior close is fully defined by the data.
        win = struct["window_idxs"]
        if i in win:
            prior_close_inside = (i > 0 and closes[i - 1] >= range_low
                                  and closes[i - 1] <= range_high)
            if prior_close_inside:
                # LONG: first upside crossing
                if closes[i] > range_high:
                    atr = atr14(highs, lows, closes, i)
                    bar_range = highs[i] - lows[i]
                    if atr is not None and bar_range >= 1.0 * atr and i + 1 < n:
                        entry_price = opens[i + 1]
                        stop_price = lows[i]
                        risk = entry_price - stop_price
                        if risk > 0:  # R3: gap through stop => discard
                            target_price = entry_price + TARGET_R * risk
                            trades.append(Trade(i + 1, entry_price, "LONG",
                                                stop_price, target_price))
                            position_open = True
                            day_done = True
                            i += 1  # B3: entry bar evaluated
                            continue
                # SHORT: first downside crossing
                elif closes[i] < range_low:
                    atr = atr14(highs, lows, closes, i)
                    bar_range = highs[i] - lows[i]
                    if atr is not None and bar_range >= 1.0 * atr and i + 1 < n:
                        entry_price = opens[i + 1]
                        stop_price = highs[i]
                        risk = stop_price - entry_price
                        if risk > 0:  # R3
                            target_price = entry_price - TARGET_R * risk
                            trades.append(Trade(i + 1, entry_price, "SHORT",
                                                stop_price, target_price))
                            position_open = True
                            day_done = True
                            i += 1
                            continue

        i += 1

    # End-of-data open position cleanup
    if position_open and trades:
        t = trades[-1]
        t.exit_idx, t.exit_price = n - 1, closes[n - 1]
        t.exit_reason = "EOD"
        t.bars_held = t.exit_idx - t.entry_idx
        if t.side == "SHORT":
            gross = (t.entry_price - t.exit_price) / PIP
        else:
            gross = (t.exit_price - t.entry_price) / PIP
        t.gross_pips = gross
        t.friction = friction_for(t.entry_price)
        t.pips = gross - t.friction

    return trades


def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy_points": 0, "expectancy_pct": 0,
                "max_dd_points": 0, "exits": {},
                "gross_pf": 0, "gross_expectancy": 0,
                "net_pf": 0, "net_expectancy": 0}

    wins = [t for t in trades if t.pips > 0]

    # B4 lineage: gross from pre-friction outcomes
    gross_list = [t.gross_pips for t in trades if t.gross_pips is not None]
    gross_profit = sum(g for g in gross_list if g > 0)
    gross_loss = sum(abs(g) for g in gross_list if g <= 0)
    gross_pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    gross_expectancy = sum(gross_list) / len(gross_list) if gross_list else 0

    net_profit = sum(t.pips for t in trades if t.pips > 0)
    net_loss = -sum(t.pips for t in trades if t.pips <= 0)
    net_pf = net_profit / net_loss if net_loss > 0 else float("inf")
    net_expectancy = sum(t.pips for t in trades) / len(trades)

    mean_entry = sum(t.entry_price for t in trades) / len(trades)
    expectancy_pct = 100.0 * net_expectancy / mean_entry  # readability only

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
        "profit_factor": net_pf,  # gates use NET PF (frozen criteria v2.1)
        "expectancy_points": net_expectancy,
        "expectancy_pct": expectancy_pct,
        "max_dd_points": max_dd, "exits": exits,
        "gross_pf": gross_pf, "gross_expectancy": gross_expectancy,
        "net_pf": net_pf, "net_expectancy": net_expectancy,
        "mean_entry": mean_entry,
    }


def decide(metrics, phase):
    n = metrics["n"]
    if n < 50:
        return "INSUFFICIENT", f"n={n} < 50"
    pf = metrics["profit_factor"]
    if pf == float("inf"):
        return "SUSPICIOUS", "zero losses"
    if pf < 1.0:
        return "KILL", f"PF {pf:.4f} < 1.0"
    if metrics["win_rate"] < 0.45:
        return "KILL", f"WR {metrics['win_rate']:.2%} < 45%"
    if pf <= 1.15:
        return "DANGER-ZONE", f"PF {pf:.4f} in 1.0-1.15 band"
    return "PASS", f"PF {pf:.4f}"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--raw-dir", default=None, help="unused; batch-runner CLI parity")
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    parser.add_argument("--start", default=None, help="override window start (smoke only; YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="override window end (smoke only; YYYY-MM-DD)")
    args = parser.parse_args()

    # Gate 1 CRYPTO branch (24/7 jurisdiction + synthetic hard rule)
    rep = gate1_audit_crypto(args.dataset, verbose=False)
    if rep["verdict"] == "REJECT":
        print("Gate 1 CRYPTO REJECT: data failed validation")
        for f in rep["fatal"]:
            print(f"  ✗ {f}")
        return 1
    print(f"Gate 1 CRYPTO: {rep['verdict']} "
          f"(completeness={rep['stats'].get('completeness')}, "
          f"n_bars={rep['stats'].get('n_bars')})")

    bars = load_dataset(args.dataset)
    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d")
        end = datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    elif args.phase == "insample":
        start = datetime.strptime("2021-01-01", "%Y-%m-%d")
        end = datetime.strptime("2023-12-31", "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    else:
        start = datetime.strptime("2024-01-01", "%Y-%m-%d")
        end = datetime.strptime("2025-05-13", "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    bars = [b for b in bars if start <= b["time"] <= end]

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\nWindow: {start:%Y-%m-%d} .. {end:%Y-%m-%d}  ({len(bars)} bars)")
    print(f"Trades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.2%}  "
          f"net PF={metrics['profit_factor']:.4f}  "
          f"gross PF={metrics['gross_pf']:.4f}")
    print(f"  expectancy net: {metrics['expectancy_points']:+.2f} points/trade "
          f"({metrics['expectancy_pct']:+.4f}% of mean entry "
          f"{metrics.get('mean_entry', 0):,.2f})")
    print(f"  expectancy gross: {metrics['gross_expectancy']:+.2f} points/trade")
    print(f"  exits: {metrics['exits']}")
    print(f"\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
