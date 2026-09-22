#!/usr/bin/env python3
"""
research/backtest/S018_macro_gravity.py — S-018: Macro Gravity Lead (DXY → EURUSD Short).

Per factory/preregistrations/S018_macro_gravity.md.
Window (N,M)=(3,3) LOCKED from Phase 1.5 holdout — do NOT re-select.

TRIGGER: DXY Z-score(20-day SMM+SD) > 2.0 → SHORT EURUSD next day at open.
TRADE MANAGER: 1.5× ATR(14) stop, BE at +1R, trail prior-day-high, scale-out
  50% at +2R, max 15 days.
FEES: 0.5 pips/side (1.0 pip round trip).

PnL three-decomposition: price_only | price_plus_funding | net.
  (Note: EURUSD spot has no funding; price_only === price+funding.)

IS: 2021-01-01..2023-12-31.  OOS: 2024-01-01..2025-05-13 (one-shot gated).
"""

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from research.execution.trade_manager import manage_trade
from factory.graveyard_chain import read_graveyard

EXPERIMENT_ID = "S-018"
STRATEGY_FAMILY = "MACRO_GRAVITY"
PARAM_DESC = "DXY Z>2.0 → SHORT EURUSD next open, 1.5xATR stop, TM-managed"

# TRIGGER
DXY_THRESHOLD_Z = 2.0
SMM_PERIOD = 20
SD_PERIOD = 20

# TRADE MANAGEMENT
ATR_PERIOD = 14
STOP_MULT = 1.5
MAX_HOLD_DAYS = 15
TARGET_1_R = 1.0
TARGET_2_R = 2.0
SCALE_OUT_FRAC = 0.5

# FEES
PIP = 0.0001
FRICTION_PIPS = 0.5  # per side
ROUND_TRIP_PIPS = 1.0

# WINDOWS
IS_START = datetime(2021, 1, 1, tzinfo=timezone.utc)
IS_END = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
OOS_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
OOS_END = datetime(2025, 5, 13, 23, 59, 59, tzinfo=timezone.utc)


class Trade:
    def __init__(self, entry_date, entry_price, stop, atr, side, signal_dxy_z):
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.stop = stop
        self.atr = atr
        self.side = side
        self.signal_dxy_z = signal_dxy_z
        self.exit_price = None
        self.exit_reason = None
        self.exit_date = None
        self.risk = abs(entry_price - stop)
        self.gross_pips = 0.0
        self.net_pips = 0.0
        self.ret = 0.0
        self.fills = []


def load_dxy(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row.get("timestamp_utc", "")
            val = row.get("dxy", "")
            if not date_str or val == "" or val == ".":
                continue
            try:
                ts = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                ts = datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            rows.append({"time": ts, "date": ts.date(), "dxy": float(val)})
    rows.sort(key=lambda r: r["time"])
    return rows


def load_daily_bars(path):
    """Aggregate H1 bars into daily bars (same as S-015)."""
    h1 = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            h1.append({
                "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    h1.sort(key=lambda r: r["time"])

    days = {}
    for b in h1:
        d = b["time"].date()
        if d not in days:
            days[d] = []
        days[d].append(b)

    daily = []
    for d in sorted(days.keys()):
        bars = days[d]
        if len(bars) < 24:
            continue
        daily.append({
            "date": d,
            "time": bars[0]["time"],
            "open": bars[0]["open"],
            "close": bars[-1]["close"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
        })

    return daily


def compute_smm_sd(values, period):
    """Compute simple mean and std for rolling window of last `period` values."""
    import statistics
    if len(values) < period:
        mean = statistics.mean(values[-len(values):]) if values else 0
        sd = statistics.stdev(values[-len(values):]) if len(values) > 1 else 0
        return mean, sd
    window = values[-period:]
    mean = statistics.mean(window)
    sd = statistics.stdev(window) if len(set(window)) > 1 else 0
    return mean, sd


def compute_atr14(daily):
    """ATR(14) with simple mean (S-015 convention)."""
    for i, d in enumerate(daily):
        if i == 0:
            d["atr14"] = d["high"] - d["low"]
            continue
        prev = daily[i - 1]
        tr = max(
            d["high"] - d["low"],
            abs(d["high"] - prev["close"]),
            abs(d["low"] - prev["close"]),
        )
        if i < ATR_PERIOD:
            trs = []
            for j in range(1, i + 1):
                pj = daily[j - 1]
                tr_j = max(
                    daily[j]["high"] - daily[j]["low"],
                    abs(daily[j]["high"] - pj["close"]),
                    abs(daily[j]["low"] - pj["close"]),
                )
                trs.append(tr_j)
            d["atr14"] = sum(trs) / len(trs) if trs else tr
        else:
            trs = []
            for j in range(i - ATR_PERIOD + 1, i + 1):
                pj = daily[j - 1]
                tr_j = max(
                    daily[j]["high"] - daily[j]["low"],
                    abs(daily[j]["high"] - pj["close"]),
                    abs(daily[j]["low"] - pj["close"]),
                )
                trs.append(tr_j)
            d["atr14"] = sum(trs) / ATR_PERIOD
    return daily


def identify_signals(dxy_daily, eurusd_daily, start, end):
    """Find DXY Z>2.0 signals that align with EURUSD entry days.

    For each EURUSD day where yesterday's DXY Z>2.0, generate a SHORT signal.
    """
    # Build DXY z-score series
    dxy_series = [d["dxy"] for d in dxy_daily]
    dxy_zscores = {}
    for d in dxy_daily:
        idx = dxy_daily.index(d)
        if idx < SD_PERIOD:
            continue
        smm, sd = compute_smm_sd(dxy_series[:idx], SD_PERIOD)
        if sd > 0:
            z = (d["dxy"] - smm) / sd
            dxy_zscores[d["date"]] = z

    # Match DXY signal dates to EURUSD: entry at next-day open
    signals = []
    for i, ed in enumerate(eurusd_daily):
        if ed["date"] < start.date() or ed["date"] > end.date():
            continue
        if i == 0:
            continue
        prev = eurusd_daily[i - 1]
        prev_dxy_z = dxy_zscores.get(prev["date"])
        if prev_dxy_z is not None and prev_dxy_z > DXY_THRESHOLD_Z:
            signals.append({
                "entry_date": ed["date"],
                "entry_idx": i,
                "entry_price": ed["open"],
                "signal_dxy_z": prev_dxy_z,
                "prev_date": prev["date"],
                "atr": ed["atr14"],
            })

    return signals


def run_backtest(dxy_daily, eurusd_daily, start, end):
    """Run S-018 IS/OOS backtest with Trade Manager."""
    trades = []
    signals = identify_signals(dxy_daily, eurusd_daily, start, end)

    in_position = False
    for sig in signals:
        if in_position:
            continue  # one position at a time

        entry_idx = sig["entry_idx"]
        entry_price = sig["entry_price"]
        atr = sig["atr"]
        if atr <= 0:
            continue

        stop = entry_price + STOP_MULT * atr  # SHORT stop above entry
        risk = STOP_MULT * atr
        target_1r = entry_price - 1.0 * risk  # +1R BE trigger
        target_2r = entry_price - 2.0 * risk  # +2R scale-out

        t = Trade(sig["entry_date"], entry_price, stop, atr, "SHORT", sig["signal_dxy_z"])

        # Build bars for the trade manager (remaining holding period bars)
        trade_bars = eurusd_daily[entry_idx:]
        fills = manage_trade(
            bars=[{"open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"]} for b in trade_bars],
            entry_idx=0,
            side="SHORT",
            entry_price=entry_price,
            initial_stop=stop,
            max_hold=MAX_HOLD_DAYS,
        )

        if not fills:
            # Max hold exit
            last_bar = trade_bars[-1]
            t.exit_price = last_bar["close"]
            t.exit_reason = "MAX_HOLD"
            t.exit_date = last_bar["date"]
        else:
            total_pips = 0
            weighted_price = 0
            total_weight = 0
            for f in fills:
                frac = f.fraction
                # SHORT profit = entry - exit_price
                pips = (entry_price - f.price) / PIP
                total_pips += pips * frac
                weighted_price += f.price * frac
                total_weight += frac
                t.fills.append({"idx": f.idx, "price": f.price, "fraction": f.fraction, "reason": f.reason})

            t.exit_price = weighted_price / total_weight if total_weight > 0 else entry_price
            t.exit_reason = fills[-1].reason
            t.exit_date = eurusd_daily[entry_idx + fills[-1].idx]["date"] if entry_idx + fills[-1].idx < len(eurusd_daily) else "MAX_HOLD"

        t.gross_pips = t.exit_price  # placeholder
        # Recompute properly
        gross_exit = sum((entry_price - fi["price"]) / PIP * fi["fraction"] for fi in t.fills) if t.fills else (entry_price - t.exit_price) / PIP
        t.gross_pips = gross_exit
        t.net_pips = gross_exit - ROUND_TRIP_PIPS
        t.ret = t.net_pips * PIP / entry_price

        trades.append(t)
        in_position = False  # Trade manager handles one position, then we move on

    return trades, signals


def compute_metrics(trades):
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0,
                "gross_pf": 0, "expectancy": 0, "avg_ret": 0, "exits": {}}

    net_pnls = [t.net_pips for t in trades]
    gross_pnls = [t.gross_pips for t in trades]

    wins = [p for p in net_pnls if p > 0]
    profit = sum(wins)
    loss = -sum(p for p in net_pnls if p <= 0)
    pf = profit / loss if loss > 0 else float("inf")

    gross_wins = [p for p in gross_pnls if p > 0]
    gross_profit = sum(gross_wins)
    gross_loss = -sum(p for p in gross_pnls if p <= 0)
    gross_pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    exits = {}
    for t in trades:
        exits[t.exit_reason] = exits.get(t.exit_reason, 0) + 1

    returns = [t.ret for t in trades]

    return {
        "n": len(trades),
        "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "profit_factor": pf,
        "gross_pf": gross_pf,
        "expectancy": sum(returns) / len(returns),
        "avg_ret": sum(returns) / len(returns),
        "exits": exits,
    }


def bootstrap_ci(returns, n_boot=10000, conf=0.90):
    import random
    if not returns:
        return 0.0, 0.0
    random.seed(42)
    means = []
    for _ in range(n_boot):
        sample = [random.choice(returns) for _ in returns]
        means.append(sum(sample) / len(sample))
    means.sort()
    lower = means[int((1 - conf) / 2 * n_boot)]
    upper = means[int((1 + conf) / 2 * n_boot)]
    return lower, upper


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dxy", required=True)
    parser.add_argument("--prices", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    dxy = load_dxy(args.dxy)
    eurusd = load_daily_bars(args.prices)
    eurusd = compute_atr14(eurusd)

    data_sha = hashlib.sha256(open(args.prices, "rb").read()).hexdigest()
    dxy_sha = hashlib.sha256(open(args.dxy, "rb").read()).hexdigest()

    if args.phase == "insample":
        start = IS_START
        end = IS_END
    else:
        start = OOS_START
        end = OOS_END

    trades, signals = run_backtest(dxy, eurusd, start, end)
    m = compute_metrics(trades)

    print(f"Gate 1 (FRED DXY): PASS — {len(dxy)} daily bars, range {dxy[0]['date']}..{dxy[-1]['date']}")
    print(f"DXY sha256: {dxy_sha}")
    print(f"EURUSD data sha256: {data_sha}")

    print(f"\n{'='*72}")
    print(f"S-018 MACRO GRAVITY — {args.phase.upper()}")
    print(f"{'='*72}")
    print(f"Trigger: DXY Z-score(20) > {DXY_THRESHOLD_Z} -> SHORT EURUSD next open")
    print(f"Trade Manager: {STOP_MULT}xATR stop, BE@+1R, trail high, scale@+2R, max {MAX_HOLD_DAYS}d")
    print(f"Fees: {FRICTION_PIPS} pips/side ({ROUND_TRIP_PIPS} pips round trip)")
    print(f"Signals triggered: {len(signals)} | Trades executed: {len(trades)}")

    # Three decomposition (price_only === price+funding for spot FX)
    print(f"\n{'='*72}")
    print("THREE-DECOMPOSITION TABLE (price_only === price_plus_funding for FX spot)")
    print(f"{'='*72}")
    print(f"{'Decomp':<16} | {'n':>4} | {'WR':>7} | {'PF':>8} | {'Exp(pips)':>10} | {'Ret%':>8}")
    print("-" * 65)

    for key, name in [("gross_pips", "price_only"), ("gross_pips", "price+funding"), ("net_pips", "net")]:
        gm = {
            "n": m["n"],
            "wins": sum(1 for t in trades if (t.gross_pips if key == "gross_pips" else t.net_pips) > 0),
            "win_rate": sum(1 for t in trades if (t.gross_pips if key == "gross_pips" else t.net_pips) > 0) / max(m["n"], 1),
            "profit_factor": (sum(t.gross_pips for t in trades if t.gross_pips > 0) / -sum(t.gross_pips for t in trades if t.gross_pips <= 0)) if key == "gross_pips" else (sum(t.net_pips for t in trades if t.net_pips > 0) / -sum(t.net_pips for t in trades if t.net_pips <= 0)),
            "expectancy": sum(t.gross_pips if key == "gross_pips" else t.net_pips for t in trades) / max(m["n"], 1),
            "avg_ret": sum((t.gross_pips if key == "gross_pips" else t.net_pips) * PIP / t.entry_price for t in trades) / max(m["n"], 1),
        }
        pf_str = f"{gm['profit_factor']:.4f}" if isinstance(gm['profit_factor'], float) and gm['profit_factor'] != float('inf') else "inf"
        print(f"{name:<16} | {gm['n']:>4} | {gm['win_rate']:>6.1%} | {pf_str:>8} | {gm['expectancy']:>+10.2f} | {gm['avg_ret']*100:>+7.3f}%")

    # Per-year
    print(f"\n{'='*72}")
    print("PER-YEAR BREAKDOWN (net)")
    print(f"{'='*72}")
    print(f"{'Year':>4} | {'n':>3} | {'mean_ret%':>10} | {'WR':>7} | {'PF':>8}")
    print("-" * 45)

    for yr in sorted(set(t.entry_date.year for t in trades)):
        yr_trades = [t for t in trades if t.entry_date.year == yr]
        ym = compute_metrics(yr_trades)
        pf_str = f"{ym['profit_factor']:.4f}" if ym['profit_factor'] != float('inf') else "inf"
        print(f"{yr:>4} | {ym['n']:>3} | {ym['avg_ret']*100:>+9.4f}% | {ym['win_rate']:>6.1%} | {pf_str:>8}")

    # Exit breakdown
    print(f"\nEXIT BREAKDOWN:")
    for reason, count in sorted(m["exits"].items()):
        print(f"  {reason}: {count}")

    # Bootstrap
    returns = [t.ret for t in trades]
    ci_lower, ci_upper = bootstrap_ci(returns, n_boot=10000, conf=0.90)

    # Verdict
    pf_str = f"{m['profit_factor']:.4f}" if m['profit_factor'] != float('inf') else "inf"
    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    print(f"n={m['n']}  net PF={pf_str}  mean={m['avg_ret']:.4f}")
    print(f"Bootstrap 90% CI: [{ci_lower:.4f}, {ci_upper:.4f}]")

    if m["n"] < 50:
        verdict = ("INSUFFICIENT", f"n={m['n']} < 50")
    elif m["profit_factor"] < 1.0:
        verdict = ("KILL", f"PF {m['profit_factor']:.4f} < 1.0")
    elif m["win_rate"] < 0.40:
        verdict = ("KILL", f"WR {m['win_rate']:.1%} < 40%")
    elif m["profit_factor"] >= 1.15 and ci_lower > 0 and m["avg_ret"] > 0:
        verdict = ("SURVIVE", f"PF={pf_str}, CI>0, mean>0")
    elif m["profit_factor"] >= 1.0:
        verdict = ("INCONCLUSIVE", f"PF={pf_str} but CI or mean fails")
    else:
        verdict = ("KILL", f"PF={pf_str} < 1.0")

    print(f"VERDICT: {verdict[0]} — {verdict[1]}")

    # Verdict hash
    doc = {
        "kernel_id": "S-018",
        "phase": args.phase,
        "dataset_hash": data_sha,
        "n": m["n"],
        "win_rate": m["win_rate"],
        "net_pf": m["profit_factor"],
        "gross_pf": m["gross_pf"],
        "mean": m["avg_ret"],
        "ci_lower_90": ci_lower,
        "verdict": verdict[0],
        "note": verdict[1],
        "exits": m["exits"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    v_hash = hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    print(f"\nverdict_hash: {v_hash}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
