"""
run_h1.py - Hypothesis #1 (H-001): Mean reversion on EURUSD 1H, Asian session.

Pre-committed parameter set - Variant A from the roadmap. Per Gate 4 this is
the ONE set we run first: no grid search, no tuning after seeing results.
If it fails, exactly one alternative may be tried AFTER pre-committing it.
Do NOT edit the parameters below after reading a result - that is the exact
behavior Gate 4 exists to prevent.

  Instrument:    EURUSD, 1H (bid OHLCV from the Dukascopy pipeline)
  Session:       entries only when the bar opens in 22:00-07:00 UTC
                 (candle-start hours 22, 23, 0, 1, 2, 3, 4, 5, 6)
  Signal:        Z = (close - SMA20) / SD20, computed from CLOSED bars only
                 (no lookahead). |Z| >= 2.0 -> fade the overshoot:
                 Z >= +2 -> SHORT, Z <= -2 -> LONG.
  Target:        exit when close reverts inside the 1 SD band
                 (short: Z <= +1.0, long: Z >= -1.0)
  Stop-loss:     1.5 x entry-SD distance on the adverse side
  Max hold:      8 bars (exit at close of the 8th bar if still open)
  Friction:      0.5 pips per round trip (0.3 spread + 0.2 slippage buffer)
  Fill model:    entries at bar open; SL checked intrabar (gap-through fills
                 at the open, pessimistic); reversion/exit targets at bar close.

Exits are evaluated in priority order per bar: SL first (intrabar, worst
case), then reversion target / max hold at the close.

Gate enforcement: Gate 1 (data validation) runs first via validate_data.audit();
if the verdict is REJECT the backtest refuses to run. Kill criteria and the
kill log follow Gate 5 and the roadmap's sentry rules.

Usage:
    python run_h1.py --dataset research/data/eurusd_1h.csv \
                     --raw-dir research/data/raw/EURUSD_H1
    # in-sample / out-of-sample splits are plain date ranges:
    python run_h1.py --dataset ... --start 2021-01-01 --end 2023-12-31
"""

import argparse
import csv
import math
import os
import sys
from datetime import datetime

# Ensure research/ is importable for validate_data
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from data.validate_data import audit as gate1_audit  # noqa: E402

# ---------------------------------------------------------------------------
# PRE-COMMITTED PARAMETERS (Variant A) - do not tune after seeing results
# ---------------------------------------------------------------------------
EXPERIMENT_ID = "H-001"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "MR"  # mean reversion
PARAM_DESC = "Z>2 SMA20 1SD-band reversion, Asian 22:00-07:00, maxhold 8, SL 1.5xSD"

MA_PERIOD = 20
Z_ENTRY = 2.0            # |Z| threshold to fade
Z_EXIT = 1.0             # reversion target: close back inside 1 SD band
MAX_HOLD_BARS = 8
SL_SD_MULT = 1.5         # stop-loss = entry +/- 1.5 * entry-SD
FRICTION_PIPS = 0.5      # 0.3 spread + 0.2 slippage, per round trip
PIP = 0.0001             # EURUSD

# Entry window: bar opens at hour in 22:00..06:59 UTC (the 07:00 bar belongs
# to the next window's tail and starts exactly at the 07:00 boundary).
SESSION_HOURS = {22, 23, 0, 1, 2, 3, 4, 5, 6}

# WHY (mandatory for a falsifiable kill log): why this should work at all.
WHY = ("Asian-session liquidity is the thinnest of the day, so |Z|>=2 deviations of "
       "price from the 20-bar mean are mostly low-liquidity overshoots that revert to "
       "the 1-SD band within a few hours; 8-bar max hold and 1.5xSD stop cap the tail.")


class Trade:
    def __init__(self, entry_idx, entry_price, side, sd, sl):
        self.entry_idx = entry_idx
        self.entry_price = entry_price
        self.side = side            # "LONG" / "SHORT"
        self.sd = sd
        self.stop = sl
        self.exit_idx = None
        self.exit_price = None
        self.exit_reason = None
        self.bars_held = None
        self.pips = None            # net of friction


def load_dataset(path: str) -> list[dict]:
    bars = []
    with open(path, newline="") as f:
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


def stats_prior(closes: list[float], i: int) -> tuple[float, float] | None:
    """SMA/SD of closes strictly before index i (no lookahead)."""
    if i < MA_PERIOD:
        return None
    window = closes[i - MA_PERIOD:i]
    mean = sum(window) / MA_PERIOD
    var = sum((x - mean) ** 2 for x in window) / MA_PERIOD  # population SD
    sd = math.sqrt(var)
    return mean, sd


def stats_through(closes: list[float], j: int) -> tuple[float, float] | None:
    """SMA/SD of closes up to and including index j (for exit checks at close j)."""
    if j + 1 < MA_PERIOD:
        return None
    window = closes[j + 1 - MA_PERIOD:j + 1]
    mean = sum(window) / MA_PERIOD
    sd = math.sqrt(sum((x - mean) ** 2 for x in window) / MA_PERIOD)
    return mean, sd


def run_backtest(bars: list[dict], friction_override: float = None) -> list[Trade]:
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)
    trades: list[Trade] = []
    friction = friction_override if friction_override is not None else FRICTION_PIPS
    i = 0
    while i < n:
        # --- Flat: look for an entry at the open of bar i -----------------
        if bars[i]["time"].hour in SESSION_HOURS:
            prior = stats_prior(closes, i)
            if prior is not None and prior[1] > 0:
                mean, sd = prior
                z = (closes[i - 1] - mean) / sd
                if z >= Z_ENTRY:
                    # fade the overextension: SHORT
                    sl = opens[i] + SL_SD_MULT * sd
                    t = Trade(i, opens[i], "SHORT", sd, sl)
                elif z <= -Z_ENTRY:
                    sl = opens[i] - SL_SD_MULT * sd
                    t = Trade(i, opens[i], "LONG", sd, sl)
                else:
                    t = None
                if t is not None:
                    trades.append(t)
                    i = t.entry_idx
                    # --- Manage the open position bar by bar --------------
                    j = i
                    while j < n:
                        exited = False
                        if t.side == "LONG":
                            # SL intrabar, pessimistic on gaps
                            if opens[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j]
                                t.exit_reason = "STOP"
                                exited = True
                            elif lows[j] <= t.stop:
                                t.exit_idx, t.exit_price = j, t.stop
                                t.exit_reason = "STOP"
                                exited = True
                            else:
                                thru = stats_through(closes, j)
                                if thru is not None and thru[1] > 0:
                                    zj = (closes[j] - thru[0]) / thru[1]
                                    if zj >= -Z_EXIT:  # reverted inside 1 SD
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True
                        else:  # SHORT
                            if opens[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, opens[j]
                                t.exit_reason = "STOP"
                                exited = True
                            elif highs[j] >= t.stop:
                                t.exit_idx, t.exit_price = j, t.stop
                                t.exit_reason = "STOP"
                                exited = True
                            else:
                                thru = stats_through(closes, j)
                                if thru is not None and thru[1] > 0:
                                    zj = (closes[j] - thru[0]) / thru[1]
                                    if zj <= Z_EXIT:  # reverted inside 1 SD
                                        t.exit_idx, t.exit_price = j, closes[j]
                                        t.exit_reason = "REVERT"
                                        exited = True
                        if not exited and (j - i + 1) >= MAX_HOLD_BARS:
                            t.exit_idx, t.exit_price = j, closes[j]
                            t.exit_reason = "MAXHOLD"
                            exited = True
                        if exited:
                            break
                        j += 1
                    if t.exit_idx is None:  # data ran out while still open
                        t.exit_idx, t.exit_price = n - 1, closes[-1]
                        t.exit_reason = "EOD"
                    t.bars_held = t.exit_idx - t.entry_idx + 1
                    gross = (t.exit_price - t.entry_price) if t.side == "LONG" \
                        else (t.entry_price - t.exit_price)
                    t.pips = gross / PIP - friction
                    i = t.exit_idx + 1  # one position at a time
                    continue
        i += 1
    return trades


def compute_metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {"n": 0, "wins": 0, "win_rate": 0, "profit_factor": 0, "expectancy_pips": 0,
                "max_dd_pips": 0, "gross_profit_pips": 0, "gross_loss_pips": 0,
                "avg_bars_held": 0, "exits": {}}
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
        "n": len(trades),
        "wins": len(wins),
        "win_rate": len(wins) / len(trades),
        "gross_profit_pips": gross_profit,
        "gross_loss_pips": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_pips": sum(t.pips for t in trades) / len(trades),
        "max_dd_pips": max_dd,
        "avg_bars_held": sum(t.bars_held for t in trades) / len(trades),
        "exits": exits,
    }


def decide(metrics: dict, phase: str) -> tuple[str, str]:
    """
    Apply pre-committed kill criteria (Gate 5) + the roadmap sentry rules.
    Returns (verdict, note).
    """
    n = metrics["n"]
    if phase == "insample":
        if n < 50:
            return "INSUFFICIENT", "n<50: below the Gate 3 statistical floor - not a valid verdict"
        pf = metrics["profit_factor"]
        if pf == float("inf"):
            return "SUSPICIOUS", "zero losing trades - almost certainly a bug or leakage, debug before trusting"
        if pf < 1.0:
            return "KILL", "OOS-style hard kill: PF<1.0"
        if pf > 2.0:
            return "SUSPICIOUS", "PF>2.0: be suspicious, not excited - likely leakage or friction-model bug"
        if metrics["win_rate"] < 0.45:
            return "KILL", f"win rate {metrics['win_rate']:.0%} < 45% floor"
        if pf < 1.15:
            return "KILL", f"PF {pf:.2f} < 1.15 in-sample floor (live costs erode the edge)"
        if pf <= 1.8:
            return "DANGER-ZONE", (f"PF {pf:.2f} in 1.2-1.8 band: log it, stop, do NOT tweak; "
                                   "decide tomorrow whether it earns an OOS run")
        return "PASS-INSAMPLE", f"PF {pf:.2f}: survives in-sample floor; next gate is OOS (separate pre-committed run)"
    if phase == "oos":
        pf = metrics["profit_factor"]
        if n < 30:
            return "INSUFFICIENT", "OOS n<30: not a valid OOS verdict"
        if pf == float("inf"):
            return "SUSPICIOUS", "zero OOS losses - debug before trusting"
        if pf < 1.0:
            return "KILL", "OOS hard kill: PF<1.0, no exceptions"
        return "PASS-OOS", f"OOS PF {pf:.2f} >= 1.0; escalate to paper trading per the roadmap"
    return "UNKNOWN", "unknown phase"


def fmt_row(metrics: dict) -> str:
    pf = metrics["profit_factor"]
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    return (f"n={metrics['n']}  wins={metrics['wins']}  win_rate={metrics['win_rate']:.1%}  "
            f"PF={pf_s}  expectancy={metrics['expectancy_pips']:+.2f} pips/trade  "
            f"maxDD={metrics['max_dd_pips']:.1f} pips  avg_hold={metrics['avg_bars_held']:.1f} bars")


def append_kill_log(metrics: dict, data_range: str, verdict: str, note: str) -> None:
    pf = metrics["profit_factor"]
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    path = os.path.join("research", "kill_log.csv")
    header = ("experiment,date,process_version,family,params,data_range,WHY,n,win_rate,"
              "profit_factor,expectancy_pips,max_dd_pips,verdict,note")
    row = (f"{EXPERIMENT_ID},{datetime.now().strftime('%Y-%m-%d')},{PROCESS_VERSION},"
           f"{STRATEGY_FAMILY},\"{PARAM_DESC}\",\"{data_range}\",\"{WHY}\","
           f"{metrics['n']},{metrics['win_rate']:.3f},{pf_s},{metrics['expectancy_pips']:.2f},"
           f"{metrics['max_dd_pips']:.1f},{verdict},\"{note}\"")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        if new:
            f.write(header + "\n")
        f.write(row + "\n")
    print(f"\nKill log appended to: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="H-001 mean-reversion backtest (Variant A, pre-committed)")
    parser.add_argument("--dataset", required=True, help="Cleaned dataset CSV (from validate_data.py)")
    parser.add_argument("--raw-dir", required=True, help="Raw per-day dir (Gate 1 re-run enforced before backtesting)")
    parser.add_argument("--start", type=str, default=None, help="Start YYYY-MM-DD (default: dataset start)")
    parser.add_argument("--end", type=str, default=None, help="End YYYY-MM-DD inclusive (default: dataset end)")
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample",
                        help="Which pre-committed verdict gates to apply")
    args = parser.parse_args()

    # Gate 1: no backtest on dirty data. Refuses to run on a REJECT verdict.
    if not os.path.isdir(args.raw_dir):
        print(f"ERROR: raw dir not found: {args.raw_dir}", file=sys.stderr)
        return 1
    verdict = gate1_audit(os.path.join("research", "data", "data_audit.log"),
                          args.raw_dir, args.dataset)
    if verdict == "REJECT":
        print("\nGate 1 REJECT: data failed validation (see data_audit.log). Backtest refused.", file=sys.stderr)
        return 1

    bars = load_dataset(args.dataset)
    if not bars:
        print("ERROR: empty dataset", file=sys.stderr)
        return 1

    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d")
        bars = [b for b in bars if b["time"] >= start]
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d")
        bars = [b for b in bars if b["time"] <= end.replace(hour=23)]
    if not bars:
        print("ERROR: no bars in the requested window", file=sys.stderr)
        return 1

    data_range = f"{bars[0]['time'].date()}..{bars[-1]['time'].date()}"
    print("=" * 78)
    print(f"{EXPERIMENT_ID} | Mean reversion EURUSD 1H | {PARAM_DESC}")
    print(f"Data: {len(bars)} H1 bars, {data_range} | phase={args.phase}")
    print("=" * 78)

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\nTrades: {len(trades)}")
    print("  #   entry_time        side  entry     exit      reason   pips    held")
    for idx, t in enumerate(trades[:15], 1):
        print(f"  {idx:2d}   {bars[t.entry_idx]['time']:%Y-%m-%d %H:%M}  {t.side:5s} "
              f"{t.entry_price:.5f}  {t.exit_price:.5f}  {t.exit_reason:8s} {t.pips:+7.1f}  {t.bars_held}")
    if len(trades) > 15:
        print(f"  ... ({len(trades) - 15} more)")
    print(f"\nExit reasons: {metrics['exits']}")
    print(f"\nMETRICS [{args.phase}]: {fmt_row(metrics)}")
    print(f"\nVERDICT: {verdict}")
    print(f"  {note}")

    append_kill_log(metrics, data_range, verdict, note)
    print("\nTip: next gates per roadmap - OOS run (separate --phase oos on unseen "
          "2024-2025 data) only if this verdict is PASS-INSAMPLE. No tweaking in between.")
    return 0


if __name__ == "__main__":
    sys.exit(main())