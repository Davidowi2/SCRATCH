#!/usr/bin/env python3
"""
research/execution/trade_manager.py — Modular exit engine (MVP).

NOT wired into any kernel yet. Standalone, unit-tested.

Logic (MVP):
  (a) Move stop to breakeven when unrealized >= +1R.
  (b) After BE trigger: trail stop behind prior bar's extreme
      (long: prior low; short: prior high).
  (c) Scale out 50% at +1.5R; trail remainder with (b).

Returns: list of (exit_idx, exit_price, fraction, reason) fills.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class ExitFill:
    idx: int
    price: float
    fraction: float
    reason: str


def manage_trade(bars: List[dict], entry_idx: int, side: str,
                 entry_price: float, initial_stop: float,
                 max_hold: int = 72) -> List[ExitFill]:
    """
    Manage a trade from entry to exit.

    Args:
        bars: list of dicts with keys open, high, low, close
        entry_idx: index of entry bar (trade entered at entry_price)
        side: "LONG" or "SHORT"
        entry_price: actual entry price
        initial_stop: stop price at entry
        max_hold: maximum bars before forced exit

    Returns list of ExitFill.
    """
    fills: List[ExitFill] = []
    n = len(bars)
    if entry_idx >= n:
        return fills

    risk = abs(entry_price - initial_stop)
    if risk <= 0:
        return [ExitFill(entry_idx, entry_price, 1.0, "INVALID_STOP")]

    be_triggered = False
    remaining_fraction = 1.0
    current_stop = initial_stop
    scale_out_done = False

    for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = bars[i]
        if side == "LONG":
            unrealized = bar["close"] - entry_price
        else:
            unrealized = entry_price - bar["close"]

        r_multiple = unrealized / risk

        # --- Check stop hit ---
        if side == "LONG" and bar["low"] <= current_stop:
            fill_price = bar["open"] if bar["open"] < current_stop else current_stop
            fills.append(ExitFill(i, fill_price, remaining_fraction, "STOP"))
            return fills
        if side == "SHORT" and bar["high"] >= current_stop:
            fill_price = bar["open"] if bar["open"] > current_stop else current_stop
            fills.append(ExitFill(i, fill_price, remaining_fraction, "STOP"))
            return fills

        # --- BE trigger (only before scale-out) ---
        if not be_triggered and not scale_out_done and r_multiple >= 1.0:
            current_stop = entry_price
            be_triggered = True

        # --- Scale-out at +1.5R ---
        if not scale_out_done and r_multiple >= 1.5 and remaining_fraction >= 0.5:
            scale_price = entry_price + 1.5 * risk if side == "LONG" else entry_price - 1.5 * risk
            fills.append(ExitFill(i, scale_price, 0.5, "SCALE_OUT_1.5R"))
            remaining_fraction -= 0.5
            scale_out_done = True
            current_stop = entry_price
            be_triggered = True

        # --- Trail stop after BE trigger ---
        if be_triggered and remaining_fraction > 0 and i > 0:
            if side == "LONG":
                prev_low = bars[i - 1]["low"]
                if prev_low > current_stop:
                    current_stop = prev_low
            else:
                prev_high = bars[i - 1]["high"]
                if prev_high < current_stop:
                    current_stop = prev_high

        # --- Target 2.0R ---
        if remaining_fraction > 0:
            target = entry_price + 2.0 * risk if side == "LONG" else entry_price - 2.0 * risk
            if side == "LONG" and bar["high"] >= target:
                fills.append(ExitFill(i, target, remaining_fraction, "TARGET_2R"))
                return fills
            if side == "SHORT" and bar["low"] <= target:
                fills.append(ExitFill(i, target, remaining_fraction, "TARGET_2R"))
                return fills

        # --- Max hold ---
        if i >= entry_idx + max_hold:
            fills.append(ExitFill(i, bar["close"], remaining_fraction, "MAX_HOLD"))
            return fills

    return fills
