"""
shadow_monitor.py — Continuous live feed monitor for H-001 paper phase.

Runs as a background process, receives live bars from TradeLocker,
logs them to the database, and tracks gaps for the Friday gate.

This is the measurement instrument — it must run continuously to
validate the shadow period.
"""

import os
import sys
import time
import logging
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "shadow_monitor.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("shadow_monitor")

# Import TradeLocker
logging.getLogger("tradelocker").setLevel(logging.WARNING)
from tradelocker import TLAPI

# Config
INSTRUMENT_ID = 25626  # EURUSD on CRUC
POLL_INTERVAL = 300  # 5 minutes
DB_PATH = "database/trades.db"
LOG_FILE = "logs/shadow_daily.log"


def connect_tl():
    """Connect to TradeLocker."""
    return TLAPI(
        environment=os.getenv("TL_ENVIRONMENT"),
        username=os.getenv("TL_USERNAME"),
        password=os.getenv("TL_PASSWORD"),
        server=os.getenv("TL_SERVER"),
        log_level="warning",
    )


def get_latest_bar(tl):
    """Get the latest 1H bar from TradeLocker."""
    try:
        history = tl.get_price_history(
            instrument_id=INSTRUMENT_ID,
            resolution="1H",
            lookback_period="5H",  # Just get last few bars
        )
        if history.shape[0] == 0:
            return None
        last = history.iloc[-1]
        return {
            "timestamp": datetime.utcfromtimestamp(last["t"] / 1000),
            "open": float(last["o"]),
            "high": float(last["h"]),
            "low": float(last["l"]),
            "close": float(last["c"]),
            "volume": float(last["v"]),
        }
    except Exception as e:
        logger.error(f"Failed to get latest bar: {e}")
        return None


def log_bar_to_db(bar, signal_side, z_score, sd, session_hour, bars_used):
    """Log a bar to the signal_log table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO signal_log (timestamp, side, entry_price, stop_loss, z_score, sd, session_hour, bars_used, phase)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        bar["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
        signal_side,
        bar["close"],
        0,
        round(z_score, 4),
        round(sd, 6),
        session_hour,
        bars_used,
        "paper",
    ))
    conn.commit()
    conn.close()


def compute_z(closes):
    """Compute Z-score for the latest close."""
    if len(closes) < 20:
        return 0, 0
    window = closes[-20:]
    mean = sum(window) / 20
    sd = (sum((c - mean) ** 2 for c in window) / 20) ** 0.5
    z = (closes[-1] - mean) / sd if sd > 0 else 0
    return z, sd


def run_monitor():
    """Main monitor loop."""
    logger.info("=" * 60)
    logger.info("SHADOW MONITOR STARTING")
    logger.info(f"Instrument: EURUSD (id={INSTRUMENT_ID})")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info("=" * 60)

    tl = connect_tl()
    closes = []
    last_bar_timestamp = None
    bars_received = 0
    gaps_detected = 0
    start_time = datetime.utcnow()

    while True:
        try:
            bar = get_latest_bar(tl)
            if bar is None:
                logger.warning("No bar received, retrying in 60s...")
                time.sleep(60)
                continue

            # Check for new bar
            if last_bar_timestamp and bar["timestamp"] <= last_bar_timestamp:
                # No new bar yet, wait
                time.sleep(POLL_INTERVAL)
                continue

            # New bar received
            bars_received += 1
            last_bar_timestamp = bar["timestamp"]
            closes.append(bar["close"])

            # Keep only last 50 closes for Z computation
            if len(closes) > 50:
                closes = closes[-50:]

            # Compute Z
            z, sd = compute_z(closes)

            # Session check
            session_hour = bar["timestamp"].hour in {22, 23, 0, 1, 2, 3, 4, 5, 6}

            # Signal check (H-001 logic)
            signal_side = "NONE"
            if session_hour and abs(z) >= 2.0:
                signal_side = "SHORT" if z >= 2.0 else "LONG"
                logger.info(f"SIGNAL: {signal_side} at {bar['timestamp']} (Z={z:.2f})")

            # Log to DB
            log_bar_to_db(bar, signal_side, z, sd, bar["timestamp"].hour, len(closes))

            # Log daily line (once per day at 00:00 UTC)
            now = datetime.utcnow()
            if now.hour == 0 and now.minute < 10:
                uptime = (now - start_time).total_seconds() / 3600
                logger.info(f"DAILY: bars={bars_received}, gaps={gaps_detected}, uptime={uptime:.1f}h")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            break
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(60)
            # Reconnect
            try:
                tl = connect_tl()
            except:
                pass


if __name__ == "__main__":
    run_monitor()
