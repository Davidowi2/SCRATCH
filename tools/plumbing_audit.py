"""
tools/plumbing_audit.py — H-001 Plumbing Sanity Check (READ-ONLY)

Proves the shadow monitor and data pipeline are not silently failing.
Uses SELECT statements only. Does not modify any files or databases.

Audit checks:
1. Total bars received in last 7 days
2. Timestamp gaps > 6 hours (excluding weekends)
3. Last 5 Z-scores and entry-bar SDs (verify math is happening)
4. Signals generated vs trades taken
5. Duplicate bar detection
6. Timestamp range (monitor uptime)
7. Asian session Z-scores
"""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "database", "trades.db")


def connect():
    """Read-only connection to trades.db."""
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        return None
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def is_weekend_gap(t1, t2):
    """Check if a time gap spans a Saturday (forex weekend).
    
    Handles: Friday→Sunday, Friday→Monday, Saturday→Monday, etc.
    Also handles Friday close → Sunday/Monday open within 72h.
    """
    # Check each day between t1 and t2 for Saturday
    cur = t1.date() + timedelta(days=1)
    while cur < t2.date():
        if cur.weekday() == 5:  # Saturday
            return True
        cur += timedelta(days=1)
    
    # Friday close → Sunday/Monday open within 72h
    if t1.weekday() == 4 and (t2 - t1).total_seconds() < 72 * 3600:
        return True
    
    return False


def audit_bars_received(conn, days=7):
    """Count bars received in the last N days."""
    cursor = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        SELECT COUNT(*) as total FROM signal_log
        WHERE phase = 'paper' AND created_at >= ?
    """, (cutoff,))
    row = cursor.fetchone()
    total = row["total"] if row else 0
    print(f"=== BARS RECEIVED (last {days} days) ===")
    print(f"  Total: {total}")
    return total


def audit_gaps(conn, hours=6):
    """Check for timestamp gaps > N hours, excluding weekends."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp FROM signal_log
        WHERE phase = 'paper'
        ORDER BY timestamp ASC
    """)
    rows = cursor.fetchall()
    if len(rows) < 2:
        print("\n=== GAP CHECK ===")
        print("  Not enough data points for gap analysis")
        return []

    gaps = []
    for i in range(1, len(rows)):
        t1 = datetime.strptime(rows[i - 1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        t2 = datetime.strptime(rows[i]["timestamp"], "%Y-%m-%d %H:%M:%S")
        diff_hours = (t2 - t1).total_seconds() / 3600

        if diff_hours > hours:
            if not is_weekend_gap(t1, t2):
                gaps.append({
                    "from": rows[i - 1]["timestamp"],
                    "to": rows[i]["timestamp"],
                    "hours": diff_hours,
                })

    print(f"\n=== GAP CHECK (>{hours}h, excluding weekends) ===")
    print(f"  Gaps found: {len(gaps)}")
    for g in gaps:
        print(f"    {g['from']} -> {g['to']} ({g['hours']:.1f}h)")
    return gaps


def audit_zscores(conn, limit=5):
    """Print last N Z-scores and SDs to verify math is happening."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, z_score, sd, side, entry_price
        FROM signal_log
        WHERE phase = 'paper'
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()

    print(f"\n=== LAST {limit} Z-SCORES ===")
    for row in rows:
        price_str = f"{row['entry_price']:.5f}" if row['entry_price'] is not None else "NULL"
        print(f"  {row['timestamp']}  Z={row['z_score']:.4f}  SD={row['sd']:.6f}  "
              f"side={row['side']}  price={price_str}")
    return rows


def audit_asian_zscores(conn, limit=5):
    """Print last N Z-scores specifically from Asian session bars."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, z_score, sd, side, entry_price
        FROM signal_log
        WHERE phase = 'paper'
          AND CAST(strftime('%H', timestamp) AS INTEGER) IN (22, 23, 0, 1, 2, 3, 4, 5, 6)
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()

    print(f"\n=== LAST {limit} ASIAN SESSION Z-SCORES ===")
    for row in rows:
        price_str = f"{row['entry_price']:.5f}" if row['entry_price'] is not None else "NULL"
        print(f"  {row['timestamp']}  Z={row['z_score']:.4f}  SD={row['sd']:.6f}  "
              f"side={row['side']}  price={price_str}")
    return rows


def audit_signals_vs_trades(conn):
    """Check signals generated vs trades taken."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN side != 'NONE' THEN 1 ELSE 0 END) as signals,
            SUM(CASE WHEN side != 'NONE' AND entry_price > 0 THEN 1 ELSE 0 END) as trades
        FROM signal_log
        WHERE phase = 'paper'
    """)
    row = cursor.fetchone()
    total = row["total"] if row else 0
    signals = row["signals"] if row else 0
    trades = row["trades"] if row else 0

    print(f"\n=== SIGNALS VS TRADES ===")
    print(f"  Total bars logged: {total}")
    print(f"  Signals generated: {signals}")
    print(f"  Trades taken: {trades}")
    return {"total": total, "signals": signals, "trades": trades}


def audit_duplicates(conn):
    """Check for duplicate timestamps in paper phase."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, COUNT(*) as c
        FROM signal_log
        WHERE phase = 'paper'
        GROUP BY timestamp
        HAVING c > 1
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()

    print(f"\n=== DUPLICATE CHECK ===")
    if rows:
        print(f"  DUPLICATES FOUND: {len(rows)}")
        for row in rows:
            print(f"    {row['timestamp']} (count={row['c']})")
    else:
        print("  No duplicates.")
    return rows


def audit_timestamp_range(conn):
    """Print oldest and newest bar timestamps (monitor uptime)."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest
        FROM signal_log
        WHERE phase = 'paper'
    """)
    row = cursor.fetchone()

    print(f"\n=== TIMESTAMP RANGE ===")
    print(f"  Oldest bar: {row['oldest']}")
    print(f"  Newest bar: {row['newest']}")
    if row['oldest'] and row['newest']:
        t1 = datetime.strptime(row['oldest'], "%Y-%m-%d %H:%M:%S")
        t2 = datetime.strptime(row['newest'], "%Y-%m-%d %H:%M:%S")
        print(f"  Span: {(t2 - t1).total_seconds() / 3600:.1f} hours")
    return row


def main():
    print("=" * 60)
    print("H-001 PLUMBING AUDIT (READ-ONLY)")
    print("=" * 60)

    conn = connect()
    if not conn:
        return 1

    try:
        audit_bars_received(conn, days=7)
        audit_gaps(conn, hours=6)
        audit_zscores(conn, limit=5)
        audit_asian_zscores(conn, limit=5)
        audit_signals_vs_trades(conn)
        audit_duplicates(conn)
        audit_timestamp_range(conn)
        print("\n" + "=" * 60)
        print("AUDIT COMPLETE")
        print("=" * 60)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    exit(main())
