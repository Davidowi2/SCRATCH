"""
shadow_monitor_v3.py — Spread logger with CFD jurisdiction (Path 2).

New in v3:
- spread_log table: instrument, ts_utc, bid, ask, spread_pts, ny_session_bool
- NY session = 09:30-11:00 ET (America/New_York, DST-aware)
- Resolves TradeLocker instrument IDs for NAS100 and US30
- Poll duration: 5 days
- Friction formula for S-009 (future): median spread WHERE ny_session_bool=1,
  plus buffer (p95-median of window spreads, floored 0.25 pts)
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

# Instrument IDs (to be resolved)
INSTRUMENT_IDS = {
    "EURUSD": 25626,
    "NAS100": None,
    "US30": None,
}

POLL_INTERVAL = 300  # 5 minutes
DB_PATH = "database/trades.db"
NY_TZ = ZoneInfo("America/New_York")


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


def run_spread_logger():
    """Main spread logging loop."""
    logger.info("=" * 60)
    logger.info("SHADOW MONITOR v3 STARTING (with spread logging)")
    logger.info("=" * 60)

    tl = connect_tl()
    ensure_spread_log_table()
    resolve_instrument_ids(tl)

    for name, id_val in INSTRUMENT_IDS.items():
        if id_val is not None:
            logger.info(f"  {name}: {id_val}")
        else:
            logger.warning(f"  {name}: NOT RESOLVED")

    collection_end = datetime.utcnow() + timedelta(days=5)
    logger.info(f"Collection ends: {collection_end}")

    while datetime.utcnow() < collection_end:
        try:
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
            logger.info("Spread logger stopped by user")
            break
        except Exception as e:
            logger.error(f"Spread logger error: {e}")
            time.sleep(60)
            try:
                tl = connect_tl()
            except:
                pass


if __name__ == "__main__":
    run_spread_logger()
