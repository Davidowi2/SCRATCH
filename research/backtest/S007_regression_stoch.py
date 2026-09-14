"""
research/backtest/S007_regression_stoch.py — S-007 Regression Channel + Stochastic Fade (EURUSD H1)

Implements the exact math from factory/preregistrations/S007.md (Directive U v1):

1. Zone: 50-bar linear regression of closes over i-49..i; bands = fitted
   midline +/- 2.0 * population std-dev of residuals over the same window.
2. Stochastic standard (14,3,3): rawK over 14 bars (flat-window guard:
   denominator 0 -> rawK=0); K = SMA3(rawK); D = SMA3(K). Simple SMA,
   consistent with repo lineage (no Wilder).
3. Entry LONG: close[i] <= lower band AND K[i] < 20 AND
   K[i-1] <= D[i-1] AND K[i] > D[i].  SHORT mirrored at upper band, K>80,
   K crossing below D. Entry at open[i+1].
4. Stop LONG = min(low[i-9..i]) - 0.5*ATR14[i]; SHORT mirrored. Target 2.0R.
5. Rails: friction 0.5 pips, max hold 72, one position, one trade/event.

RULINGS:
- R1 / R3 / B3 / B4: factory-wide (see S006/S001 lineage). R3 note:
  RISK = |entry - anchor stop|; risk <= 0 (or anchor stop beyond entry in
  the wrong direction) discards the signal entirely.
- ATR14 inclusive-at-bar convention (S001/S010 EURUSD lineage).
- INTERPRETATION (preregistered): video's "custom settings" never stated;
  standard (14,3,3) declared; "cross back inside" = K/D cross while K in
  the extreme zone.

CALIBRATION PURPOSE: band-fade + oscillator-timing hypothesis from the
YouTube backlog. Passes or dies cleanly.
"""

import csv
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.validate_data import audit as gate1_audit

EXPERIMENT_ID = "S-007"
PROCESS_VERSION = "v1"
STRATEGY_FAMILY = "REGCHAN"
PARAM_DESC = "50-bar 2.0sd regression channel fade + stoch(14,3,3) cross, target 2R"

FRICTION_PIPS = 0.5
PIP = 0.0001
MAX_HOLD_BARS = 72
ATR_PERIOD = 14
REG_WINDOW = 50
BAND_SD_MULT = 2.0
STOCH_K_PERIOD = 14
STOCH_SMOOTH_K = 3
STOCH_SMOOTH_D = 3
OS_LEVEL = 20.0
OB_LEVEL = 80.0
STOP_LOOKBACK = 10      # bars i-9..i
STOP_ATR_PAD = 0.5
TARGET_R = 2.0


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
        self.pips = None
        self.gross_pips = None


def load_dataset(path):
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


def atr14(highs, lows, closes, j):
    """ATR14 using bars up to and including j (S001/S010 lineage)."""
    if j < ATR_PERIOD:
        return None
    trs = []
    for k in range(j - ATR_PERIOD + 1, j + 1):
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


def sma_series(values, period):
    n = len(values)
    out = [None] * n
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def regression_bands(closes, i):
    """Least-squares line over window i-49..i; returns (lower, upper, mid)
    with bands = mid +/- BAND_SD_MULT * population std of residuals at x=i.
    None until window complete."""
    if i + 1 < REG_WINDOW:
        return None
    xs = list(range(REG_WINDOW))
    ys = closes[i - REG_WINDOW + 1:i + 1]
    n = REG_WINDOW
    sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    mid_at_end = intercept + slope * (n - 1)          # fitted at x=i
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    var = sum(r * r for r in resid) / n                # population variance
    sd = math.sqrt(var)
    return (mid_at_end - BAND_SD_MULT * sd, mid_at_end + BAND_SD_MULT * sd, mid_at_end)


def stochastic_series(highs, lows, closes):
    """Standard (14,3,3): rawK -> K=SMA3 -> D=SMA3. Flat window -> rawK=0."""
    n = len(closes)
    rawk = [None] * n
    for i in range(n):
        if i + 1 < STOCH_K_PERIOD:
            continue
        hh = max(highs[i - STOCH_K_PERIOD + 1:i + 1])
        ll = min(lows[i - STOCH_K_PERIOD + 1:i + 1])
        rng = hh - ll
        rawk[i] = 0.0 if rng == 0 else 100.0 * (closes[i] - ll) / rng
    k = sma_series(rawk, STOCH_SMOOTH_K)
    d = sma_series(k, STOCH_SMOOTH_D)
    return k, d


def run_backtest(bars):
    opens = [b["open"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    n = len(bars)

    k, d = stochastic_series(highs, lows, closes)
    atrs = [atr14(highs, lows, closes, i) for i in range(n)]

    trades = []
    position_open = False
    i = 0
    while i < n:
        if position_open:
            t = trades[-1]
            j = i
            exited = False

            # R1: STOP before TARGET
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

            if not exited and (j - t.entry_idx) >= MAX_HOLD_BARS:
                t.exit_idx, t.exit_price = j, closes[j]
                t.exit_reason = "MAXHOLD"
                exited = True

            if exited:
                position_open = False
                t.bars_held = t.exit_idx - t.entry_idx
                if t.side == "SHORT":
                    gross = (t.entry_price - t.exit_price) / PIP
                else:
                    gross = (t.exit_price - t.entry_price) / PIP
                t.gross_pips = gross
                t.pips = gross - FRICTION_PIPS
                i = t.exit_idx + 1
                continue

            i += 1
            continue

        # --- signal search ---
        if (i + 1 < n and i >= STOP_LOOKBACK - 1 and atrs[i] is not None
                and k[i] is not None and d[i] is not None
                and k[i - 1] is not None and d[i - 1] is not None):
            bands = regression_bands(closes, i)
            if bands:
                lower, upper, _mid = bands
                # LONG: lower band touch + oversold K/D cross up
                if (closes[i] <= lower and k[i] < OS_LEVEL
                        and k[i - 1] <= d[i - 1] and k[i] > d[i]):
                    entry_price = opens[i + 1]
                    stop_price = min(lows[i - STOP_LOOKBACK + 1:i + 1]) - STOP_ATR_PAD * atrs[i]
                    risk = entry_price - stop_price
                    if risk > 0:  # R3
                        target_price = entry_price + TARGET_R * risk
                        trades.append(Trade(i + 1, entry_price, "LONG",
                                            stop_price, target_price))
                        position_open = True
                        i += 1  # B3
                        continue
                # SHORT: upper band touch + overbought K/D cross down
                elif (closes[i] >= upper and k[i] > OB_LEVEL
                        and k[i - 1] >= d[i - 1] and k[i] < d[i]):
                    entry_price = opens[i + 1]
                    stop_price = max(highs[i - STOP_LOOKBACK + 1:i + 1]) + STOP_ATR_PAD * atrs[i]
                    risk = stop_price - entry_price
                    if risk > 0:  # R3
                        target_price = entry_price - TARGET_R * risk
                        trades.append(Trade(i + 1, entry_price, "SHORT",
                                            stop_price, target_price))
                        position_open = True
                        i += 1
                        continue

        i += 1

    if position_open:
        t = trades[-1]
        t.exit_idx, t.exit_price = n - 1, closes[n - 1]
        t.exit_reason = "EOD"
        t.bars_held = t.exit_idx - t.entry_idx
        if t.side == "SHORT":
            gross = (t.entry_price - t.exit_price) / PIP
        else:
            gross = (t.exit_price - t.entry_price) / PIP
        t.gross_pips = gross
        t.pips = gross - FRICTION_PIPS

    return trades


def compute_metrics(trades):
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
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--phase", choices=["insample", "oos"], default="insample")
    args = parser.parse_args()

    verdict = gate1_audit(os.path.join("research", "data", "data_audit.log"),
                          args.raw_dir, args.dataset)
    if verdict == "REJECT":
        print("Gate 1 REJECT: data failed validation")
        return 1

    bars = load_dataset(args.dataset)
    if args.phase == "insample":
        start = datetime.strptime("2021-01-01", "%Y-%m-%d")
        end = datetime.strptime("2023-12-31", "%Y-%m-%d")
    else:
        start = datetime.strptime("2024-01-01", "%Y-%m-%d")
        end = datetime.strptime("2025-05-13", "%Y-%m-%d")
    bars = [b for b in bars if start <= b["time"] <= end.replace(hour=23)]

    trades = run_backtest(bars)
    metrics = compute_metrics(trades)
    verdict, note = decide(metrics, args.phase)

    print(f"\nTrades: {len(trades)}")
    print(f"  wins={metrics['wins']}  WR={metrics['win_rate']:.2%}  "
          f"net PF={metrics['profit_factor']:.4f}  gross PF={metrics['gross_pf']:.4f}  "
          f"Exp={metrics['expectancy_pips']:+.2f} pips")
    print(f"  exits: {metrics['exits']}")
    print(f"\nVERDICT: {verdict}")
    print(f"  {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
