"""
validate_data.py - Gate 1: Data Validation (roadmap v2)

Mandatory before ANY backtest. Audits per-day Dukascopy H1 CSVs, writes
research/data/data_audit.log, and emits a cleaned dataset for the backtest
engine. One dirty file should poison the whole run, not get silently averaged
out - so any fatal finding rejects the dataset.

Dukascopy conventions this validator is calibrated to (verified empirically):
  - The FX trading week runs Sunday 22:00 UTC -> Friday 22:00 UTC.
  - Outside those hours Dukascopy emits "flat" filler bars: volume = 0 and
    open=high=low=close = previous close. These are EXPECTED on Saturdays,
    on Sundays before ~22:00, and on Fridays after the rollover hour
    (22:00 UTC in US-winter, 21:00 UTC in US-summer). They carry no price
    information and are stripped from the cleaned dataset.
  - A bar with volume > 0 is a REAL traded bar.

Roadmap Gate 1 checks, mapped:
  1. Gap detection        >3 consecutive missing candles (not spanning a
                           weekend) -> REJECT. Rollover-hour drift across
                           seasons is tolerated by only flagging gaps whose
                           span contains no Saturday.
  2. Weekend contam.      Real bar on Saturday, or on Sunday before 21:00 UTC
                           -> stripped + FLAGGED (the roadmap allows strip).
  3. Zero-volume candles  Volume = 0 during Mon 00:00-Fri 21:59 UTC -> FLAGGED
                           as possible feed freeze (filler outside that window
                           is expected, not flagged). Known market holidays
                           (where Dukascopy emits no candles at all) are
                           excluded from the feed-freeze flag.
  4. OHLC integrity       High < Low, or Open/Close outside [Low, High]
                           -> row rejected + FLAGGED.
  5. Timestamp monotonic  Duplicates deduped + FLAGGED; out-of-order rows
                           sorted + FLAGGED loudly.
  6. Session coverage     <80% of expected Asian-session candles (22:00-07:00
                           UTC, 45 slots/week) present -> REJECT. First and
                           last week of the dataset are exempt from this check
                           (boundary effects from incomplete data).

Verdicts:  CLEAN | FLAGGED | REJECT   (written to data_audit.log)

Usage:
    python validate_data.py --raw-dir research/data/raw/EURUSD_H1 \
                            --dataset-out research/data/eurusd_1h.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta

# Asian session per the pre-committed Hypothesis #1 (Variant A): 22:00-07:00 UTC.
# Candle-start hours included: 22, 23, 0, 1, 2, 3, 4, 5, 6  (07:00 bar starts at 07:00,
# which is the END of the window, so entry hour 6 is the last 22:00-07:00 slot).
ASIAN_HOURS = {22, 23, 0, 1, 2, 3, 4, 5, 6}
EXPECTED_ASIAN_SLOTS_PER_WEEK = 45  # Sun 22-23 (2) + Mon-Thu 9*4 (36) + Fri 0-6 (7)
GAP_REJECT_HOURS = 4                # >3 consecutive missing candles -> reject
WEEKEND_SPAN_HOURS = 48             # Sat 00:00 -> Sun 24:00 (gap spans this = normal)

# Known market holidays where Dukascopy emits no candles (non-fatal).
# Feed-freeze checks skip these dates entirely.
MARKET_HOLIDAYS = {
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24", "2021-12-31",
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
    "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
    "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
}


def iso_week(dt: datetime) -> str:
    d = dt.date()
    return f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"


def audit(log_path: str, raw_dir: str, dataset_out: str) -> str:
    files = sorted(f for f in os.listdir(raw_dir) if f.endswith(".csv"))
    lines: list[str] = []
    all_bars: list[dict] = []          # every bar (real + flat), raw truth
    verdicts: list[str] = []
    fatal, flagged = 0, 0

    lines.append("=" * 72)
    lines.append("DATA AUDIT - Gate 1 (roadmap v2) - Dukascopy H1, calibrated to FX week Sun 22:00-Fri 22:00 UTC")
    lines.append("=" * 72)

    for fname in files:
        path = os.path.join(raw_dir, fname)
        day_flags: list[str] = []
        rows = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)

        bars = []
        for i, row in enumerate(rows):
            try:
                bar = {
                    "time": datetime.strptime(row["timestamp_utc"], "%Y-%m-%d %H:%M:%S"),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            except (ValueError, KeyError):
                day_flags.append(f"row {i}: unparseable, rejected")
                flagged += 1
                continue

            # OHLC integrity (Gate 1.4): reject bad row
            if bar["high"] < bar["low"]:
                day_flags.append(f"row {i} ({bar['time']}): high < low, rejected")
                flagged += 1
                continue
            for side, p in (("open", bar["open"]), ("close", bar["close"])):
                if not (bar["low"] <= p <= bar["high"]):
                    day_flags.append(f"row {i} ({bar['time']}): {side} outside [low, high], rejected")
                    flagged += 1
                    break
            else:
                bars.append(bar)

        if not bars:
            verdicts.append(f"{fname}: EMPTY (no valid bars)")
            continue

        # Timestamp monotonicity (Gate 1.5): dedupe + check order
        times = [b["time"] for b in bars]
        dups = len(times) - len(set(times))
        if dups:
            day_flags.append(f"{dups} duplicate timestamp(s) deduped")
            flagged += 1
        unique_times = sorted(set(times))
        if unique_times != times:
            day_flags.append(f"{len(times) - len(unique_times)} out-of-order rows sorted")
            flagged += 1

        all_bars.extend(bars)

        # Per-file summary line
        real = [b for b in bars if b["volume"] > 0]
        flat = [b for b in bars if b["volume"] == 0]
        note = "FLAGGED: " + "; ".join(day_flags) if day_flags else "ok"
        verdicts.append(f"{fname}: {len(bars)} bars ({len(real)} real, {len(flat)} flat) - {note}")

    # ---------------- Overall checks on the full merged series ----------------
    real_bars = sorted((b for b in all_bars if b["volume"] > 0), key=lambda b: b["time"])
    flat_bars = sorted((b for b in all_bars if b["volume"] == 0), key=lambda b: b["time"])

    if not real_bars:
        lines.append("\n[REJECT] No real (volume > 0) bars found in any file")
        _write_outcomes(lines, log_path)
        return "REJECT"

    # Strip weekend-contaminated real bars (Gate 1.2: strip + flag)
    contaminated = [b for b in real_bars
                    if b["time"].weekday() == 5  # Saturday: never real
                    or (b["time"].weekday() == 6 and b["time"].hour < 21)]  # Sun before 21:00
    kept = [b for b in real_bars if b not in contaminated]
    if contaminated:
        flagged += 1
        lines.append(f"\n[FLAG] Weekend contamination: {len(contaminated)} real bar(s) stripped "
                     f"(first: {contaminated[0]['time']}, last: {contaminated[-1]['time']})")

    # Zero-volume feed-freeze check (Gate 1.3): zero-vol during Mon 00:00-Fri 21:59
    # Skip known market holidays (Dukascopy emits no candles at all on these days)
    freeze = [b for b in flat_bars
              if b["time"].weekday() < 5 and b["time"].hour <= 21
              and b["time"].strftime("%Y-%m-%d") not in MARKET_HOLIDAYS]
    if freeze:
        flagged += 1
        lines.append(f"[FLAG] Feed-freeze suspicion: {len(freeze)} zero-volume bar(s) "
                     f"during Mon-Fri trading hours (first: {freeze[0]['time']})")

    # Gap detection (Gate 1.1): >3 consecutive missing candles, not spanning a weekend.
    # Also ignore gaps that span a known market holiday (no candles expected that day).
    # Also ignore same-day gaps (caused by stripping flat filler on partial days).
    gaps = []
    for prev, cur in zip(kept, kept[1:]):
        span_hours = (cur["time"] - prev["time"]).total_seconds() / 3600
        if span_hours >= GAP_REJECT_HOURS:
            # Does the span contain Saturday? (weekend gap = normal)
            contains_saturday = any(
                (prev["time"] + timedelta(hours=h)).weekday() == 5
                for h in range(1, int(span_hours))
            )
            if contains_saturday:
                continue
            # Does the span contain a market holiday? (no candles expected = normal)
            span_date_str = (prev["time"] + timedelta(days=1)).strftime("%Y-%m-%d")
            if span_date_str in MARKET_HOLIDAYS:
                continue
            # Ignore same-day gaps — ONLY if the date is a known market holiday
            # (partial holiday data causes flat-filler stripping gaps).
            # Non-holiday same-day gaps are real outages → must be flagged.
            if prev["time"].date() == cur["time"].date():
                if prev["time"].strftime("%Y-%m-%d") in MARKET_HOLIDAYS:
                    continue
                # else: real same-day outage → falls through to gaps.append
            gaps.append((prev["time"], cur["time"], span_hours))
    if gaps:
        fatal += 1
        lines.append(f"\n[REJECT] {len(gaps)} data gap(s) of >= {GAP_REJECT_HOURS}h not explained by a weekend or holiday:")
        for gt, ct, sh in gaps[:10]:
            lines.append(f"         {gt} -> {ct}  ({sh:.0f}h)")
    else:
        lines.append("\n[OK] No unexplained data gaps (>= 4h)")

    # Session coverage (Gate 1.6): Asian session slots per week.
    # Skip the first and last week of the dataset (boundary effects from
    # incomplete data at the edges).
    weekly: dict[str, list] = {}
    for b in kept:
        if b["time"].hour in ASIAN_HOURS:
            weekly.setdefault(iso_week(b["time"]), []).append(b)
    total_weeks = len(weekly)
    if total_weeks > 2:
        # Exclude first and last week (boundary effects)
        sorted_weeks = sorted(weekly.keys())
        interior_weeks = sorted_weeks[1:-1]
        bad_weeks = [w for w in interior_weeks
                     if len(weekly[w]) < 0.8 * EXPECTED_ASIAN_SLOTS_PER_WEEK]
        present = sum(len(weekly[w]) for w in interior_weeks)
        coverage = present / (len(interior_weeks) * EXPECTED_ASIAN_SLOTS_PER_WEEK) if interior_weeks else 0.0
    else:
        bad_weeks = []
        present = sum(len(b) for b in weekly.values())
        coverage = present / (total_weeks * EXPECTED_ASIAN_SLOTS_PER_WEEK) if total_weeks else 0.0
    lines.append(f"\n[CHECK] Asian-session coverage (22:00-07:00 UTC): {present} real slots over "
                 f"{total_weeks} week(s) = {coverage:.0%} (expect {EXPECTED_ASIAN_SLOTS_PER_WEEK}/week)")
    if bad_weeks:
        fatal += 1
        lines.append(f"[REJECT] {len(bad_weeks)} week(s) below 80% Asian-session coverage: {', '.join(bad_weeks[:10])}")
    else:
        lines.append("[OK] Every interior week meets the 80% Asian-session coverage floor")

    # ---------------- Write cleaned dataset (real bars only) ----------------
    os.makedirs(os.path.dirname(dataset_out) or ".", exist_ok=True)
    with open(dataset_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for b in kept:
            writer.writerow({
                "timestamp_utc": b["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "open": f"{b['open']:.5f}", "high": f"{b['high']:.5f}",
                "low": f"{b['low']:.5f}", "close": f"{b['close']:.5f}",
                "volume": b["volume"],
            })

    lines.append(f"\n[OK] Cleaned dataset written: {dataset_out} ({len(kept)} real H1 bars, "
                 f"{len(flat_bars)} flat filler stripped, {len(contaminated)} contaminated stripped)")

    # ---------------- Verdict ----------------
    lines.append("\n" + "-" * 72)
    lines.append("PER-FILE AUDIT:")
    lines.extend(verdicts)
    if fatal:
        verdict = "REJECT"
    elif flagged:
        verdict = "FLAGGED"
    else:
        verdict = "CLEAN"
    lines.append("-" * 72)
    lines.append(f"VERDICT: {verdict}  ({len(files)} file(s), {len(all_bars)} total bars, "
                 f"{len(real_bars)} real bars, {fatal} fatal, {flagged} flagged)")
    _write_outcomes(lines, log_path)
    return verdict


def _write_outcomes(lines: list, log_path: str) -> None:
    print("\n".join(lines))
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nAudit log written to: {log_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate 1 data validation for Dukascopy H1 data")
    parser.add_argument("--raw-dir", required=True, help="Directory of per-day H1 CSV files")
    parser.add_argument("--dataset-out", required=True, help="Cleaned merged dataset CSV output")
    parser.add_argument("--audit-log", default=os.path.join("research", "data", "data_audit.log"))
    args = parser.parse_args()

    if not os.path.isdir(args.raw_dir):
        print(f"ERROR: raw dir not found: {args.raw_dir}", file=sys.stderr)
        return 1

    verdict = audit(args.audit_log, args.raw_dir, args.dataset_out)
    return 0 if verdict in ("CLEAN", "FLAGGED") else 1


if __name__ == "__main__":
    sys.exit(main())
