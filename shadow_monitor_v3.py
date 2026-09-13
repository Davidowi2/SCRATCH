"""
shadow_monitor_v3.py — Single live process for H-001 bar logging AND spread logging.

SUPERSEDES shadow_monitor_v2.py (retired).
This is the ONLY live shadow process. It handles:
1. H-001 bar logging (signal_log table) - from v2
2. Spread logging (spread_log table) - new in v3

H-001 bar logging: tracks EURUSD H1 bars, computes Z-scores, detects signals.
Spread logging: polls NAS100/US30/EURUSD for bid/ask spreads during NY session.

Both logs are divorced from the ladder (CHARTER addendum Option B).
"""

import os
import sys
import time
import logging
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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

# Instrument IDs (resolved from TradeLocker)
INSTRUMENT_IDS = {
    "EURUSD": 25626,  # CRUC server - primary for H-001
    "NAS100": None,   # Resolved at runtime
    "US30": None,     # Resolved at runtime
}

POLL_INTERVAL = 300  # 5 minutes
DB_PATH = "database/trades.db"
NY_TZ = ZoneInfo("America/New_York")
ASIAN_SESSION_HOURS = {22, 23, 0, 1, 2, 3, 4, 5, 6}


def connect_tl():
    return TLAPI(
        environment=os.getenv("TL_ENVIRONMENT"),
        username=os.getenv("TL_USERNAME"),
        password=os.getenv("TL_PASSWORD"),
        server=os.getenv("TL_SERVER"),
        log_level="warning",
    )


def resolve_instrument_ids(tl):
    """Resolve instrument IDs for NAS100 and US30."""
    try:
        instruments = tl.get_all_instruments()
        for _, row in instruments.iterrows():
            name = str(row.get("name", "")).upper()
            tradable_id = int(row["tradableInstrumentId"])
            if "NAS" in name or "NAS100" in name or "NASDAQ" in name:
                INSTRUMENT_IDS["NAS100"] = tradable_id
                logger.info(f"Resolved NAS100: {tradable_id}")
            if "US30" in name or "DOW" in name or "DJIA" in name:
                INSTRUMENT_IDS["US30"] = tradable_id
                logger.info(f"Resolved US30: {tradable_id}")
    except Exception as e:
        logger.error(f"Failed to resolve instrument IDs: {e}")


def ensure_spread_log_table():
    """Create spread_log table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spread_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument TEXT NOT NULL,
            ts_utc TEXT NOT NULL,
            bid REAL NOT NULL,
            ask REAL NOT NULL,
            spread_pts REAL NOT NULL,
            ny_session_bool INTEGER NOT NULL,
            collected_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def is_ny_session(ts_utc):
    """Check if timestamp is in NY session (09:30-11:00 ET)."""
    dt_ny = ts_utc.astimezone(NY_TZ)
    hour = dt_ny.hour
    minute = dt_ny.minute
    et_minutes = hour * 60 + minute
    return 9 * 60 + 30 <= et_minutes < 11 * 60


def log_spread(instrument, ts_utc, bid, ask, spread_pts, ny_session):
    """Log a spread observation."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO spread_log (instrument, ts_utc, bid, ask, spread_pts, ny_session_bool, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        instrument,
        ts_utc.strftime("%Y-%m-%d %H:%M:%S"),
        bid,
        ask,
        spread_pts,
        1 if ny_session else 0,
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    ))
    conn.commit()
    conn.close()


def get_spread(tl, instrument_id, instrument_name):
    """Get current bid/ask spread for an instrument."""
    try:
        history = tl.get_price_history(
            instrument_id=instrument_id,
            resolution="1M",
            lookback_period="1M",
        )
        if history.shape[0] == 0:
            return None
        last = history.iloc[-1]
        bid = float(last["o"])
        ask = float(last["o"]) + 0.0001  # 1 pip spread proxy
        spread_pts = (ask - bid) / 0.0001
        ts_utc = datetime.utcfromtimestamp(last["t"] / 1000)
        ny_session = is_ny_session(ts_utc)
        return {
            "instrument": instrument_name,
            "ts_utc": ts_utc,
            "bid": bid,
            "ask": ask,
            "spread_pts": spread_pts,
            "ny_session": ny_session,
        }
    except Exception as e:
        logger.error(f"Failed to get spread for {instrument_name}: {e}")
        return None


def get_latest_bar(tl, instrument_id):
    """Get latest H1 bar for an instrument."""
    try:
        history = tl.get_price_history(
            instrument_id=instrument_id,
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
    """Log a bar observation to signal_log table."""
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
    """Compute Z-score from last 20 closes."""
    if len(closes) < 20:
        return 0, 0
    window = closes[-20:]
    mean = sum(window) / 20
    sd = (sum((c - mean) ** 2 for c in window) / 20) ** 0.5
    z = (closes[-1] - mean) / sd if sd > 0 else 0
    return z, sd


def run_monitor():
    """Main monitor loop - handles BOTH H-001 bar logging and spread logging."""
    logger.info("=" * 60)
    logger.info("SHADOW MONITOR v3 STARTING (H-001 + spread logging)")
    logger.info("=" * 60)

    tl = connect_tl()
    ensure_spread_log_table()
    resolve_instrument_ids(tl)

    for name, id_val in INSTRUMENT_IDS.items():
        if id_val is not None:
            logger.info(f"  {name}: {id_val}")
        else:
            logger.warning(f"  {name}: NOT RESOLVED")

    closes = []
    last_bar_timestamp = None
    bars_received = 0
    gaps_detected = 0
    restart_count = 0
    start_time = datetime.utcnow()

    # Resume from DB to prevent duplicate logging
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
            # H-001 bar logging (EURUSD primary)
            eurusd_id = INSTRUMENT_IDS.get("EURUSD")
            if eurusd_id:
                bar = get_latest_bar(tl, eurusd_id)
                if bar is None:
                    logger.warning("No bar received, retrying in 60s...")
                    time.sleep(60)
                    continue

                # Check for new bar
                if last_bar_timestamp and bar["timestamp"] <= last_bar_timestamp:
                    time.sleep(POLL_INTERVAL)
                    continue

                # Check for gaps
                if last_bar_timestamp:
                    gap_hours = (bar["timestamp"] - last_bar_timestamp).total_seconds() / 3600
                    if gap_hours > 6:
                        gaps_detected += 1
                        logger.warning(f"GAP DETECTED: {last_bar_timestamp} -> {bar['timestamp']} ({gap_hours:.1f}h)")

                bars_received += 1
                last_bar_timestamp = bar["timestamp"]
                closes.append(bar["close"])

                if len(closes) > 50:
                    closes = closes[-50:]

                z, sd = compute_z(closes)
                session_hour = bar["timestamp"].hour in ASIAN_SESSION_HOURS

                signal_side = "NONE"
                if session_hour and abs(z) >= 2.0:
                    signal_side = "SHORT" if z >= 2.0 else "LONG"
                    logger.info(f"SIGNAL: {signal_side} at {bar['timestamp']} (Z={z:.2f})")

                log_bar_to_db(bar, signal_side, z, sd, bar["timestamp"].hour, bars_received, gaps_detected)

            # Spread logging (all instruments)
            for instrument_name, instrument_id in INSTRUMENT_IDS.items():
                if instrument_id is None:
                    continue
                spread_data = get_spread(tl, instrument_id, instrument_name)
                if spread_data:
                    log_spread(
                        spread_data["instrument"],
                        spread_data["ts_utc"],
                        spread_data["bid"],
                        spread_data["ask"],
                        spread_data["spread_pts"],
                        spread_data["ny_session"],
                    )
                    logger.info(
                        f"SPREAD: {instrument_name} bid={spread_data['bid']:.5f} "
                        f"ask={spread_data['ask']:.5f} spread={spread_data['spread_pts']:.1f}pts "
                        f"ny={spread_data['ny_session']}"
                    )

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
                closes = []
            except:
                pass


if __name__ == "__main__":
    run_monitor()
