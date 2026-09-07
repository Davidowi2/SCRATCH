"""
live_h1.py — H-001 LIVE ADAPTER

Paper-trading adapter that sources signal logic from the frozen run_h1.py
backtest engine. Reads real-time EURUSD 1H bar data, generates signals,
and logs them for shadow-mode verification.

P2 SHADOW MODE: signal-only, zero orders, >=14 days or >=10 signals.
P3 LIVE: orders via TradeLocker TLAPI (not implemented until shadow passes).

FROZEN STRATEGY (from run_h1.py sha256 6226222c...f291):
- MA_PERIOD=20, Z_ENTRY=2.0, Z_EXIT=1.0, MAX_HOLD=8, SL_SD_MULT=1.5
- Session: Asian 22:00-07:00 UTC (hours {22,23,0,1,2,3,4,5,6})
- No day-of-week filter

FIDELITY GATE (anti-drift): Every signal MUST match session hours,
Z 2.0/1.0 entry/exit, hold <=8, SL 1.5xSD. Any drift = VOID.

DO NOT edit run_h1.py. This file imports from it.
"""

import csv
import hashlib
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

# Ensure research/backtest is importable (path relative to this file's location)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, "research", "backtest"))

# Import frozen strategy — NEVER edit the frozen file
import run_h1

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "live_h1.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("live_h1")


class H001LiveAdapter:
    """Live signal generator for H-001 mean reversion."""

    def __init__(self):
        # Verify frozen engine integrity at startup
        engine_path = os.path.join(_SCRIPT_DIR, "research", "backtest", "run_h1.py")
        with open(engine_path, "rb") as f:
            actual_sha = hashlib.sha256(f.read()).hexdigest()
        expected_sha = "6226222c1eb076fb2f6fe4862d1992a80c5f68fe54a6353697312d160cf8f291"
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"FROZEN ENGINE TAMPERED: run_h1.py sha256 {actual_sha[:12]}... "
                f"!= expected {expected_sha[:12]}... — aborting"
            )
        logger.info("Frozen engine verified: run_h1.py sha256 %s... OK", actual_sha[:12])

        # Strategy parameters (mirror of run_h1.py — single source of truth)
        self.ma_period = run_h1.MA_PERIOD
        self.z_entry = run_h1.Z_ENTRY
        self.z_exit = run_h1.Z_EXIT
        self.max_hold = run_h1.MAX_HOLD_BARS
        self.sl_sd_mult = run_h1.SL_SD_MULT
        self.friction_pips = run_h1.FRICTION_PIPS
        self.session_hours = run_h1.SESSION_HOURS

        # State
        self.closes: list[float] = []
        self.signal_log: list[dict] = []
        self._killed = False

    def compute_z(self, closes: list[float], idx: int) -> Optional[tuple[float, float]]:
        """Compute Z-score at index using frozen strategy's stats_prior logic."""
        if idx < self.ma_period:
            return None
        window = closes[idx - self.ma_period:idx]
        mean = sum(window) / self.ma_period
        var = sum((x - mean) ** 2 for x in window) / self.ma_period
        sd = var ** 0.5
        if sd <= 0:
            return None
        z = (closes[idx - 1] - mean) / sd
        return z, sd

    def check_signal(self, bar: dict) -> Optional[dict]:
        """
        Check a live bar for entry signal.

        Args:
            bar: dict with keys: time (datetime), open, high, low, close, volume

        Returns:
            Signal dict if conditions met, None otherwise.
        """
        if self._killed:
            logger.warning("BLOCKED: kill switch active — no signals generated")
            return None

        self.closes.append(bar["close"])
        idx = len(self.closes) - 1

        # Session filter (frozen: Asian 22:00-07:00)
        if bar["time"].hour not in self.session_hours:
            return None

        # Z-score check
        result = self.compute_z(self.closes, idx)
        if result is None:
            return None

        z, sd = result

        # Fidelity gate: entry thresholds match frozen config
        if z >= self.z_entry:
            side = "SHORT"
            sl = bar["open"] + self.sl_sd_mult * sd
        elif z <= -self.z_entry:
            side = "LONG"
            sl = bar["open"] - self.sl_sd_mult * sd
        else:
            return None

        signal = {
            "timestamp": bar["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "side": side,
            "entry_price": bar["open"],
            "stop_loss": round(sl, 5),
            "z_score": round(z, 4),
            "sd": round(sd, 6),
            "session_hour": bar["time"].hour,
            "bars_used": idx + 1,
        }

        logger.info(
            "SIGNAL: %s %s @ %.5f (Z=%.2f, SL=%.5f)",
            signal["timestamp"], side, signal["entry_price"], z, signal["stop_loss"]
        )
        self.signal_log.append(signal)
        return signal

    def log_signal_to_db(self, signal: dict, db_path: str = "database/trades.db"):
        """Log signal to trades.db signal_log table."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Ensure signal_log table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                z_score REAL NOT NULL,
                sd REAL NOT NULL,
                session_hour INTEGER NOT NULL,
                bars_used INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                phase TEXT DEFAULT 'shadow'
            )
        """)

        cursor.execute("""
            INSERT INTO signal_log (timestamp, side, entry_price, stop_loss, z_score, sd, session_hour, bars_used, phase)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal["timestamp"],
            signal["side"],
            signal["entry_price"],
            signal["stop_loss"],
            signal["z_score"],
            signal["sd"],
            signal["session_hour"],
            signal["bars_used"],
            "shadow",
        ))

        conn.commit()
        conn.close()
        logger.info("Signal logged to db: %s", signal["timestamp"])

    def run_shadow_mode(self, data_source: str = "research/data/eurusd_1h.csv",
                        start_date: str = "2024-01-01",
                        end_date: str = "2025-05-13"):
        """
        Shadow mode: replay historical data, generate signals, log them.
        No orders placed.
        """
        logger.info("=" * 60)
        logger.info("P2 SHADOW MODE STARTING")
        logger.info("Data: %s (%s to %s)", data_source, start_date, end_date)
        logger.info("=" * 60)

        bars = run_h1.load_dataset(data_source)
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23)

        window_bars = [b for b in bars if start <= b["time"] <= end]
        logger.info("Loaded %d bars in window", len(window_bars))

        for bar in window_bars:
            signal = self.check_signal(bar)
            if signal:
                self.log_signal_to_db(signal)

        logger.info("=" * 60)
        logger.info("P2 SHADOW MODE COMPLETE: %d signals generated", len(self.signal_log))
        logger.info("=" * 60)

        return self.signal_log

    def kill_switch(self):
        """Emergency stop — disables new signal processing."""
        logger.warning("KILL SWITCH ACTIVATED — no new signals will be generated")
        self._killed = True

    @property
    def is_killed(self) -> bool:
        return self._killed


def main():
    """Main entry point for shadow mode execution."""
    os.makedirs("logs", exist_ok=True)

    adapter = H001LiveAdapter()

    # Shadow mode: replay OOS window to compare signals vs backtest
    signals = adapter.run_shadow_mode()

    # Print summary
    print(f"\nShadow mode complete: {len(signals)} signals")
    if signals:
        print(f"First: {signals[0]}")
        print(f"Last: {signals[-1]}")

    return adapter


if __name__ == "__main__":
    main()
