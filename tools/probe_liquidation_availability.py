#!/usr/bin/env python3
"""
tools/probe_liquidation_availability.py — PHASE 1A: liquidation data probe.

Objective (Directive Phase 1A): determine whether historical BTCUSDT
PERPETUAL liquidation data is available for 2019-09-01 .. 2025-05-13.

Sources checked (in order):
  (a) Binance native: data.binance.vision liquidationSnapshot archive
      (official Binance public data repo, UM futures), monthly + daily zips.
      Plus fapi/v1/allForceOrders REST status (expected: dead/auth-gated —
      documented for the record).
  (b) Named aggregators: Coinalyze (documented pipeline, docs.coinalyze.com)
      — probed WITHOUT a key to document access requirements only.

PASS criteria (ALL must hold):
  1. >= 95% calendar coverage of 2019-09-01..2025-05-13
  2. no gap > 24h
  3. granularity <= 5 minutes (bar-alignable)
  4. source = the exchange itself OR a named aggregator with a documented
     data pipeline

RESTRAINTS honored: NO backtest code. NO detector code. NO grid searches.
This script produces a data-availability verdict ONLY.

Caveats surfaced for the Overseer (not verdict-relevant):
  - Binance forceOrder feeds are documented as at most ONE order per 1000ms
    per symbol (snapshot); the archive is named liquidationSnapshot,
    consistent with that feed -> cascade undercount risk is a data-QUALITY
    caveat for Phase 1B, not an availability failure.
  - BTCUSDT USD-M perp inception = 2019-09-08; pre-inception days are
    market absence, not data gaps.

Outputs:
  - Console RAW report
  - research/data/probes/phase1a_liquidation_availability_report.txt
  - Ledger row (data-availability event) in factory/batch_ledger.csv
  - Cache: research/data/probes/liq_probe_cache.json (re-run safe)
"""

import csv
import io
import json
import os
import sys
import time
import zipfile
import hashlib
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

WINDOW_START = date(2019, 9, 1)
WINDOW_END = date(2025, 5, 13)
SYMBOL = "BTCUSDT"

MONTHLY_URL = ("https://data.binance.vision/data/futures/um/monthly/"
               "liquidationSnapshot/{s}/{s}-liquidationSnapshot-{ym}.zip")
DAILY_URL = ("https://data.binance.vision/data/futures/um/daily/"
             "liquidationSnapshot/{s}/{s}-liquidationSnapshot-{d}.zip")

PROBE_DIR = "research/data/probes"
REPORT_PATH = os.path.join(PROBE_DIR, "phase1a_liquidation_availability_report.txt")
CACHE_PATH = os.path.join(PROBE_DIR, "liq_probe_cache.json")
LEDGER_PATH = "factory/batch_ledger.csv"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def url_status(url, retries=2):
    """GET-stream probe (headers only). True=200, False=404, None=unknown."""
    for attempt in range(retries + 1):
        try:
            with session.get(url, timeout=25, stream=True) as r:
                if r.status_code == 200:
                    return True
                if r.status_code == 404:
                    return False
                return None
        except Exception:
            if attempt == retries:
                return None
            time.sleep(0.4 * (attempt + 1))
    return None


def month_list(start, end):
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def day_list(start, end):
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"monthly": {}, "daily": {}}


def save_cache(cache):
    os.makedirs(PROBE_DIR, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, sort_keys=True)


def probe_many(urls, cache_bucket, cache, workers=5, label=""):
    """Probe URLs not in cache. Returns dict key->bool/None."""
    todo = {k: u for k, u in urls.items() if k not in cache[cache_bucket]}
    results = dict(cache[cache_bucket])
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(url_status, u): k for k, u in todo.items()}
            done = 0
            for fut in as_completed(futs):
                key = futs[fut]
                results[key] = fut.result()
                done += 1
                if done % 300 == 0:
                    print(f"    [{label}] {done}/{len(todo)} probed...")
        cache[cache_bucket] = {k: results[k] for k in urls}
        save_cache(cache)
    # one sequential re-probe pass for unknowns
    unk = [k for k, v in results.items() if v is None]
    for k in unk:
        results[k] = url_status(urls[k])
        time.sleep(0.2)
    cache[cache_bucket] = {k: results[k] for k in urls}
    save_cache(cache)
    return results


def fetch_zip_rows(url, max_rows=None):
    r = session.get(url, timeout=90)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    name = zf.namelist()[0]
    with zf.open(name) as f:
        text = io.TextIOWrapper(f, encoding="utf-8")
        if max_rows is None:
            rows = list(csv.reader(text))
        else:
            rows = []
            for i, row in enumerate(csv.reader(text)):
                rows.append(row)
                if i >= max_rows:
                    break
    return rows


def main():
    now = datetime.now(timezone.utc)
    print("=" * 74)
    print("PHASE 1A — LIQUIDATION DATA AVAILABILITY PROBE (BTCUSDT PERP)")
    print(f"Window: {WINDOW_START} .. {WINDOW_END}   probe run: {now.isoformat()}")
    print("=" * 74)

    cache = load_cache()

    # ---------- A. monthly archive ----------
    print("\n[A] data.binance.vision MONTHLY liquidationSnapshot (UM futures)")
    months = month_list(WINDOW_START, WINDOW_END)
    murls = {ym: MONTHLY_URL.format(s=SYMBOL, ym=ym) for ym in months}
    monthly = probe_many(murls, "monthly", cache, workers=5, label="monthly")
    m_avail = [ym for ym in months if monthly.get(ym) is True]
    m_missing = [ym for ym in months if monthly.get(ym) is not True]
    print(f"  months probed: {len(months)}  available: {len(m_avail)}  "
          f"missing/unknown: {len(m_missing)}")
    if m_avail:
        print(f"  earliest monthly file: {m_avail[0]}   latest: {m_avail[-1]}")
    if m_missing:
        print(f"  missing months: {', '.join(m_missing) if len(m_missing) <= 20 else str(m_missing[:20]) + ' ...'}")
    if not m_avail and any(v is None for v in monthly.values()):
        print("  DIAGNOSTIC (all-missing + unknowns present):")
        try:
            r = session.get(MONTHLY_URL.format(s=SYMBOL, ym="2021-01"), timeout=30)
            print(f"    full GET 2021-01: HTTP {r.status_code} body[:150]: {r.text[:150]!r}")
        except Exception as e:
            print(f"    full GET error: {e}")

    # ---------- B. daily archive ----------
    print("\n[B] data.binance.vision DAILY liquidationSnapshot (exact day coverage)")
    days = day_list(WINDOW_START, WINDOW_END)
    durls = {d.isoformat(): DAILY_URL.format(s=SYMBOL, d=d.isoformat()) for d in days}
    daily = probe_many(durls, "daily", cache, workers=5, label="daily")
    d_avail = [d for d in days if daily.get(d.isoformat()) is True]
    d_unknown = [d for d in days if daily.get(d.isoformat()) is None]
    print(f"  days probed: {len(days)}  daily files available: {len(d_avail)}  "
          f"unknown: {len(d_unknown)}")
    if d_avail:
        print(f"  earliest daily file: {d_avail[0]}   latest: {d_avail[-1]}")

    # ---------- C. union coverage + max gap ----------
    print("\n[C] UNION coverage (day covered if daily file OR monthly file exists)")
    covered = {}
    for d in days:
        ym = f"{d.year}-{d.month:02d}"
        covered[d.isoformat()] = (daily.get(d.isoformat()) is True) or (monthly.get(ym) is True)
    n_days = len(days)
    n_cov = sum(1 for v in covered.values() if v)
    coverage_pct = 100.0 * n_cov / n_days
    max_gap = run = 0
    gap_start = gap_best = None
    for d in days:
        if covered[d.isoformat()]:
            run = 0
        else:
            if run == 0:
                gap_start = d
            run += 1
            if run > max_gap:
                max_gap = run
                gap_best = gap_start
    first_cov = next((d for d in days if covered[d.isoformat()]), None)
    last_cov = next((d for d in reversed(days) if covered[d.isoformat()]), None)
    print(f"  covered days: {n_cov}/{n_days} = {coverage_pct:.2f}%")
    print(f"  first covered: {first_cov}   last covered: {last_cov}")
    print(f"  max contiguous gap: {max_gap} day(s)"
          + (f" starting {gap_best}" if gap_best else ""))

    # ---------- D. sample file parse (granularity) ----------
    print("\n[D] SAMPLE FILE PARSE (granularity / bar-alignability)")
    granularity_ok = False
    sample_meta = {}
    sample_days = []
    if first_cov:
        sample_days.append(first_cov)
        mid = days[(days.index(first_cov) + days.index(last_cov)) // 2] if first_cov != last_cov else first_cov
        sample_days.append(mid)
        sample_days.append(last_cov)
        sample_days = sorted(set(sample_days))
    cascade_day = date(2021, 5, 19)  # known heavy-liquidation day: density sanity
    if WINDOW_START <= cascade_day <= WINDOW_END:
        sample_days.append(cascade_day)
    for sd in sorted(set(sample_days)):
        url = DAILY_URL.format(s=SYMBOL, d=sd.isoformat())
        try:
            rows = fetch_zip_rows(url)
            header, data = rows[0], rows[1:]
            tcol = None
            for cand in ("time", "timestamp", "Time", "ts", "tradeTime"):
                if cand in header:
                    tcol = header.index(cand)
                    break
            if tcol is None and header:
                tcol = 0  # Binance liq CSVs lead with symbol; find numeric-ms col below
                for idx, h in enumerate(header):
                    if "time" in h.lower():
                        tcol = idx
                        break
            ts_min = ts_max = None
            if data and tcol is not None:
                try:
                    tss = [int(float(r[tcol])) for r in data if r and r[tcol]]
                    if tss:
                        # ms or us detection
                        if max(tss) > 10**14:
                            tss = [t // 1000 for t in tss]
                        ts_min = datetime.fromtimestamp(min(tss) / 1000, tz=timezone.utc)
                        ts_max = datetime.fromtimestamp(max(tss) / 1000, tz=timezone.utc)
                except Exception:
                    pass
            side_col = header.index("side") if "side" in header else None
            sides = {}
            if side_col is not None:
                for r in data:
                    sides[r[side_col]] = sides.get(r[side_col], 0) + 1
            print(f"  {sd}: rows={len(data)}  header={header}")
            if ts_min:
                print(f"    event ts span: {ts_min:%Y-%m-%d %H:%M:%S} .. {ts_max:%Y-%m-%d %H:%M:%S} UTC (ms-precision)")
            if sides:
                print(f"    sides: {sides}")
            if data:
                print(f"    first row: {data[0]}")
            sample_meta[sd.isoformat()] = {"rows": len(data), "header": header}
            if ts_min is not None:
                granularity_ok = True
        except FileNotFoundError:
            print(f"  {sd}: no daily file (covered by monthly only)")
        except Exception as e:
            print(f"  {sd}: parse error — {e}")

    # ---------- E. allForceOrders REST ----------
    print("\n[E] fapi/v1/allForceOrders REST (Binance native, expected dead)")
    try:
        r = session.get("https://fapi.binance.com/fapi/v1/allForceOrders",
                        params={"symbol": SYMBOL, "limit": 5}, timeout=15)
        print(f"  HTTP {r.status_code}  body: {r.text[:200]}")
        afo_status = f"HTTP {r.status_code}"
    except Exception as e:
        print(f"  ERROR: {e}")
        afo_status = f"error: {e}"

    # ---------- F. aggregator (Coinalyze) ----------
    print("\n[F] Coinalyze aggregator (documented pipeline; key-gated)")
    try:
        r = session.get("https://api.coinalyze.com/api/1/futures-markets",
                        params={"exchange": "BINANCE_F"}, timeout=15)
        print(f"  futures-markets (no key) HTTP {r.status_code}  body: {r.text[:120]}")
        ca_status = f"HTTP {r.status_code} without key (free key required; docs.coinalyze.com)"
    except Exception as e:
        print(f"  ERROR: {e}")
        ca_status = f"error: {e}"

    # ---------- G. fallback: kline trade-count column ----------
    print("\n[G] FALLBACK CHECK: Binance 5m kline archive trade-count column (tick-volume spec v1.1)")
    count_col_present = False
    try:
        url = ("https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/"
               "BTCUSDT-5m-2021-01.zip")
        rows = fetch_zip_rows(url, max_rows=2)
        header, first = rows[0], rows[1]
        print(f"  kline header: {header}")
        print(f"  kline first row: {first}")
        # Binance UM kline CSV: open_time,o,h,l,c,volume,close_time,quote_volume,count,...
        if len(first) >= 9:
            count_col_present = True
            print(f"  -> column[8] (trade count) PRESENT: {first[8]} trades in first bar")
    except Exception as e:
        print(f"  kline check error: {e}")

    # ---------- H. VERDICT ----------
    print("\n[H] VERDICT vs PASS criteria")
    crit1 = coverage_pct >= 95.0
    crit2 = max_gap <= 1
    crit3 = granularity_ok
    crit4 = len(m_avail) > 0  # exchange itself (data.binance.vision = Binance official)
    print(f"  crit1 coverage >= 95%: {'PASS' if crit1 else 'FAIL'} ({coverage_pct:.2f}%)")
    print(f"  crit2 no gap > 24h:    {'PASS' if crit2 else 'FAIL'} (max gap {max_gap}d)")
    print(f"  crit3 granularity <= 5m bar-alignable: {'PASS' if crit3 else 'FAIL'} "
          f"(event-level ms timestamps)" if granularity_ok else
          f"  crit3 granularity <= 5m bar-alignable: FAIL")
    print(f"  crit4 source = exchange/named aggregator: "
          f"{'PASS' if crit4 else 'FAIL'} (data.binance.vision = Binance official public archive)")
    verdict = "PASS" if (crit1 and crit2 and crit3 and crit4) else "FAIL"
    print(f"\n  PROBE VERDICT: {verdict}")

    if not crit1 or not crit2:
        print("  LIMITATION: see coverage/gap numbers above. Fallback per directive:")
        print("  tick-volume percentile spec (v1.1 Rules 1-2)."
              + (" Kline archive HAS the trade-count column -> fallback data AVAILABLE."
                 if count_col_present else
                 " Kline trade-count column NOT confirmed -> fallback needs re-check."))

    # ---------- report file + ledger ----------
    rep_lines = []
    rep_lines.append("PHASE 1A — LIQUIDATION DATA AVAILABILITY PROBE REPORT")
    rep_lines.append(f"run_utc: {now.isoformat()}")
    rep_lines.append(f"window: {WINDOW_START}..{WINDOW_END}")
    rep_lines.append(f"source: data.binance.vision liquidationSnapshot (Binance official), UM futures, {SYMBOL}")
    rep_lines.append(f"monthly files: {len(m_avail)}/{len(months)} available"
                     + (f" ({m_avail[0]} .. {m_avail[-1]})" if m_avail else ""))
    rep_lines.append(f"daily files: {len(d_avail)}/{len(days)} available")
    rep_lines.append(f"union coverage: {n_cov}/{n_days} = {coverage_pct:.2f}%")
    rep_lines.append(f"first covered: {first_cov}  last covered: {last_cov}")
    rep_lines.append(f"max gap: {max_gap} day(s)" + (f" from {gap_best}" if gap_best else ""))
    rep_lines.append(f"granularity: event-level ms timestamps, bar-alignable to <=5m buckets: {granularity_ok}")
    rep_lines.append(f"allForceOrders REST: {afo_status}")
    rep_lines.append(f"coinalyze: {ca_status}")
    rep_lines.append(f"kline trade-count column (fallback): {count_col_present}")
    rep_lines.append(f"samples: {json.dumps(sample_meta, default=str)}")
    rep_lines.append(f"VERDICT: {verdict}")
    rep_lines.append("CAVEATS: (1) Binance forceOrder feeds are 1-order/1000ms snapshot "
                     "streams; archive consistent with that feed -> cascade undercount "
                     "risk (data-quality caveat for Phase 1B, not availability). "
                     "(2) BTCUSDT perp inception 2019-09-08; pre-inception = market absence.")
    report_text = "\n".join(rep_lines) + "\n"
    os.makedirs(PROBE_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)
    report_sha = hashlib.sha256(report_text.encode()).hexdigest()

    vdoc = {
        "probe": "PHASE-1A-LIQUIDATION-DATA-AVAILABILITY",
        "source": "data.binance.vision liquidationSnapshot (Binance official public archive)",
        "symbol": SYMBOL,
        "window": f"{WINDOW_START}..{WINDOW_END}",
        "coverage_pct": round(coverage_pct, 4),
        "max_gap_days": max_gap,
        "granularity_ok": granularity_ok,
        "source_ok": crit4,
        "verdict": verdict,
        "report_sha256": report_sha,
        "run_utc": now.isoformat(),
    }
    verdict_hash = hashlib.sha256(
        json.dumps(vdoc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    row = ["PROBE-LIQ-1A", "LIQ-DATA-AVAIL", "availability", now.isoformat(),
           report_sha, verdict_hash, "COMPLETED"]
    with open(LEDGER_PATH, "a", newline="") as f:
        csv.writer(f).writerow(row)

    print(f"\nreport: {REPORT_PATH}")
    print(f"report sha256: {report_sha}")
    print(f"verdict_hash: {verdict_hash}")
    print(f"LEDGER ROW APPENDED: {row[:3]} ... status=COMPLETED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
