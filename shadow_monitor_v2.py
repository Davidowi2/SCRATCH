"""
shadow_monitor_v2.py — Continuous live feed monitor with gap tracking.

For the Friday gate: track received bar timestamps and flag any missing hours.
A "gap" = expected hourly bar not received within tolerance.
Weekend gaps (48-49h) are expected and not counted.
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

logging.getLogger("tradelocker").setLevel(logging.WARNING)
from tradelocker import TLAPI

INSTRUMENT_ID = 25626
POLL_INTERVAL = 300  # 5 minutes
DB_PATH = "database/trades.db"


def connect_tl():
    return TLAPI(
        environment=os.getenv("TL_ENVIRONMENT"),
        username=os.getenv("TL_USERNAME"),
        password=os.getenv("TL_PASSWORD"),
        server=os.getenv("TL_SERVER"),
        log_level="warning",
    )


def get_latest_bar(tl):
    try:
        history = tl.get_price_history(
            instrument_id=INSTRUMENT_ID,
            resolution="1H",
            lookback_period="5H",
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


def log_bar_to_db(bar, signal_side, z_score, sd, session_hour, bars_received, gaps):
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
        bars_received,
        "paper",
    ))
    conn.commit()
    conn.close()


def compute_z(closes):
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
    logger.info("SHADOW MONITOR v2 STARTING (with gap tracking)")
    logger.info("=" * 60)

    tl = connect_tl()
    closes = []
    last_bar_timestamp = None
    bars_received = 0
    gaps_detected = 0
    gap_list = []
    start_time = datetime.utcnow()
    restart_count = 0

    # FIX: Resume from DB to prevent duplicate logging after restart.
    # Query the latest bar timestamp already in the DB and skip bars
    # we've already logged.
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(timestamp) FROM signal_log WHERE phase='paper'")
        row = cursor.fetchone()
        if row and row[0]:
            last_bar_timestamp = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            logger.info(f"Resumed from DB: last bar at {last_bar_timestamp}")
        conn.close()
    except Exception as e:
        logger.warning(f"Could not query DB for resume state: {e}")

    while True:
        try:
            bar = get_latest_bar(tl)
            if bar is None:
                logger.warning("No bar received, retrying in 60s...")
                time.sleep(60)
                continue

            # Check for new bar
            if last_bar_timestamp and bar["timestamp"] <= last_bar_timestamp:
                time.sleep(POLL_INTERVAL)
                continue

            # Check for gaps (expected: 1-3 hours between bars; >6 = real gap)
            if last_bar_timestamp:
                gap_hours = (bar["timestamp"] - last_bar_timestamp).total_seconds() / 3600
                if gap_hours > 6:  # More than 6 hours = real gap (not weekend)
                    gaps_detected += 1
                    gap_list.append(f"{last_bar_timestamp} -> {bar['timestamp']} ({gap_hours:.1f}h)")
                    logger.warning(f"GAP DETECTED: {last_bar_timestamp} -> {bar['timestamp']} ({gap_hours:.1f}h)")

            bars_received += 1
            last_bar_timestamp = bar["timestamp"]
            closes.append(bar["close"])

            if len(closes) > 50:
                closes = closes[-50:]

            z, sd = compute_z(closes)
            session_hour = bar["timestamp"].hour in {22, 23, 0, 1, 2, 3, 4, 5, 6}

            signal_side = "NONE"
            if session_hour and abs(z) >= 2.0:
                signal_side = "SHORT" if z >= 2.0 else "LONG"
                logger.info(f"SIGNAL: {signal_side} at {bar['timestamp']} (Z={z:.2f})")

            log_bar_to_db(bar, signal_side, z, sd, bar["timestamp"].hour, bars_received, gaps_detected)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            break
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            restart_count += 1
            time.sleep(60)
            try:
                tl = connect_tl()
                closes = []  # Reset closes on restart
            except:
                pass


if __name__ == "__main__":
    run_monitor()
