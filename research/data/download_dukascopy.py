"""
download_dukascopy.py - Fetch EURUSD 1H OHLCV candles from Dukascopy's free public datafeed.

Verified endpoint (September 2026):
    https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM}/{DD}/BID_candles_min_1.bi5
  where MM is 0-indexed (00 = January) and DD is 1-indexed.
  The old per-day `BID_candles_hour_1.bi5` endpoint 404s; per-hour tick files
  exist but cost 24 requests/day vs 1 for minute candles.

Each .bi5 file is an LZMA-compressed binary stream of 24-byte candle records
(big-endian): int32 timestamp (seconds since midnight UTC of the file's date),
int32 open, int32 close, int32 low, int32 high, int32 volume.
Prices are stored scaled by 1e5 (EURUSD has 5 decimal places).

The server rate-limits hard (HTTP 503) and blocks plain HTTP — we use HTTPS
with a Mozilla user-agent and exponential backoff retries.

Design (per the roadmap's "one dirty file poisons the run" rule):
  - One CSV per calendar day is written to research/data/raw/, so a single bad
    day can be re-downloaded / audited independently.
  - Each day's M1 candles are resampled to H1 before writing (open=first,
    high=max, low=min, close=last, volume=sum).
  - Resumable: days whose raw file already exists are skipped.
  - Stdlib only (urllib + lzma + struct). No third-party dependencies.

Usage:
    python download_dukascopy.py --start 2021-01-01 --end 2025-12-31
"""

import argparse
import lzma
import os
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, date, timedelta

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
DEFAULT_SYMBOL = "EURUSD"
TIMEFRAME_FILE = "BID_candles_min_1"   # M1 candles, one file per calendar day
TARGET_TIMEFRAME = "H1"                # what we resample to
PRICE_SCALE = 1e5
RECORD_SIZE = 24
# The Dukascopy feed throttles this IP hard (HTTP 503) when requests arrive
# faster than roughly one per cooldown window. Crawl slowly: fixed spacing
# between requests plus patient fixed-delay retries on failure.
DEFAULT_DELAY = 6                      # seconds between HTTP requests (be polite)
MAX_RETRIES = 8
RETRY_BASE_DELAY = 12                  # fixed delay between failed attempts
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
PROGRESS_LOG = os.path.join("research", "data", "download_progress.log")


def raw_dir_for(symbol: str, timeframe: str) -> str:
    """Directory holding per-day raw CSVs."""
    return os.path.join("research", "data", "raw", f"{symbol}_{timeframe}")


def day_file_path(raw_dir: str, day: date) -> str:
    return os.path.join(raw_dir, f"{day.isoformat()}.csv")


def fetch_day(symbol: str, day: date, delay: float) -> list | None:
    """
    Download and parse one calendar day of M1 candles, resampled to H1.

    Returns:
        list of dicts {time, open, high, low, close, volume} for 1H bars,
        or None when the day has no data file (weekend / holiday).
    """
    url = f"{BASE_URL}/{symbol}/{day.year}/{day.month - 1:02d}/{day.day:02d}/{TIMEFRAME_FILE}.bi5"

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if not data:
                return []  # empty file -> no candles that day
            return resample_h1(parse_m1(day, data))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # no data for this day (weekend/holiday) - not an error
            if e.code == 503:
                last_error = "rate-limited (503)"
            else:
                last_error = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = str(e)[:120]
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY)
            continue
        except Exception as e:  # noqa: BLE001 - parse/decode bug: not transient, fail fast
            raise RuntimeError(f"Non-transient error fetching {url}: {e}") from e
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BASE_DELAY)
    raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts: {last_error}")


def parse_m1(file_date: date, raw: bytes) -> list:
    """Decode a .bi5 M1-candle blob into minute candle dicts, deduped by time."""
    payload = lzma.decompress(raw)
    count = len(payload) // RECORD_SIZE
    candles = []
    for i in range(count):
        rec = payload[i * RECORD_SIZE:(i + 1) * RECORD_SIZE]
        ts, open_, close_, low_, high_, volume = struct.unpack(">6i", rec)
        # NB: start from a datetime, not file_date + timedelta (date + timedelta
        # silently drops the time-of-day component - a nasty silent bug).
        candle_dt = datetime(file_date.year, file_date.month, file_date.day) + timedelta(seconds=ts)
        candles.append({
            "time": candle_dt,
            "open": open_ / PRICE_SCALE,
            "high": high_ / PRICE_SCALE,
            "low": low_ / PRICE_SCALE,
            "close": close_ / PRICE_SCALE,
            "volume": volume,
        })
    seen = set()
    unique = []
    for c in sorted(candles, key=lambda r: r["time"]):
        if c["time"] not in seen:
            seen.add(c["time"])
            unique.append(c)
    return unique


def resample_h1(m1: list) -> list:
    """Aggregate M1 candles into H1 bars (open=first, high=max, low=min, close=last, volume=sum)."""
    h1 = []
    for c in m1:
        hour_start = c["time"].replace(minute=0, second=0, microsecond=0)
        if h1 and h1[-1]["time"] == hour_start:
            bar = h1[-1]
            bar["high"] = max(bar["high"], c["high"])
            bar["low"] = min(bar["low"], c["low"])
            bar["close"] = c["close"]
            bar["volume"] += c["volume"]
        else:
            h1.append({
                "time": hour_start,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"],
            })
    return h1


def write_day_csv(path: str, candles: list) -> None:

    with open(path, "w", newline="") as f:
        f.write("timestamp_utc,open,high,low,close,volume\n")
        for c in candles:
            f.write(
                f"{c['time'].strftime('%Y-%m-%d %H:%M:%S')},"
                f"{c['open']:.5f},{c['high']:.5f},{c['low']:.5f},"
                f"{c['close']:.5f},{c['volume']}\n"
            )


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Dukascopy M1 -> H1 candles (one CSV per day)")
    parser.add_argument("--start", required=True, type=parse_date, help="First day, YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=parse_date, help="Last day, inclusive, YYYY-MM-DD")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between requests (be polite to the rate limiter)")
    args = parser.parse_args()

    raw_dir = raw_dir_for(args.symbol, TARGET_TIMEFRAME)
    os.makedirs(raw_dir, exist_ok=True)

    if args.end < args.start:
        print("ERROR: --end must be >= --start", file=sys.stderr)
        return 1

    total_days = (args.end - args.start).days + 1
    fetched, skipped, empty, errors = 0, 0, 0, 0
    day = args.start
    while day <= args.end:
        if day.weekday() == 5:  # Saturday files contain only zero-volume filler
            day += timedelta(days=1)
            continue
        out_path = day_file_path(raw_dir, day)
        if os.path.exists(out_path):
            skipped += 1  # already downloaded (resume)
        else:
            try:
                candles = fetch_day(args.symbol, day, args.delay)
                if candles is None or not candles:
                    empty += 1  # weekend / holiday, nothing to store
                else:
                    write_day_csv(out_path, candles)
                    fetched += 1
                    first = candles[0]["time"].strftime("%H:%M")
                    last = candles[-1]["time"].strftime("%H:%M")
                    line = f"{day.isoformat()} -> {len(candles):2d} H1 bars [{first}-{last}]"
                    print(line, flush=True)
                    with open(PROGRESS_LOG, "a") as plog:
                        plog.write(line + "\n")
            except RuntimeError as e:
                errors += 1
                line = f"{day.isoformat()} ERROR: {e}"
                print(line, flush=True)
                with open(PROGRESS_LOG, "a") as plog:
                    plog.write(line + "\n")
            time.sleep(args.delay)
        day += timedelta(days=1)

    summary = (
        "-" * 60 + "\n"
        f"Days in range:  {total_days} (Saturdays skipped - filler only)\n"
        f"Downloaded:     {fetched}\n"
        f"Skipped (have): {skipped}\n"
        f"No data day:    {empty}  (weekends/holidays)\n"
        f"Errors:         {errors}\n"
        f"Raw files in:   {raw_dir}\n"
    )
    print(summary, flush=True)
    with open(PROGRESS_LOG, "a") as plog:
        plog.write(summary)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())