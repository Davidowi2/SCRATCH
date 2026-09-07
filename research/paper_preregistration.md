# Paper Trading Preregistration — H-001

**Status:** FROZEN at commit `PENDING`
**Created:** 2026-09-07
**Owner:** David Owi

---

## 1. Frozen Strategy

- **Engine:** `research/backtest/run_h1.py` (sha256: `6226222c1eb076fb2f6fe4862d1992a80c5f68fe54a6353697312d160cf8f291`)
- **Config:**
  - MA_PERIOD = 20
  - Z_ENTRY = 2.0
  - Z_EXIT = 1.0
  - MAX_HOLD_BARS = 8
  - SL_SD_MULT = 1.5
  - FRICTION_PIPS = 0.5
- **Session:** Asian 22:00–07:00 UTC (hours `{22, 23, 0, 1, 2, 3, 4, 5, 6}`)
- **No day-of-week filter** (frozen, disclosed)
- **Fidelity gate (anti-drift core):** Every fill MUST match session hours, Z 2.0/1.0 entry/exit, hold ≤8 bars, SL 1.5×SD. Any drift = VOID measurement, adapter fix, restart.

---

## 2. Execution Architecture

- **H-001 live adapter:** Does not exist yet (P2 build).
- **scratch_bot.py:** BANNED for H-001 execution. It contains a different strategy (M5 breakout scalper).
- **Order path:** Adapter → TradeLocker TLAPI → fills written to `database/trades.db` by execution engine ONLY.
- **Dashboard:** Read-only display. Never writes orders.
- **Cloudflare tunnel:** OFF during paper phase.

---

## 3. Measurement Rules

- **Window opens:** At P1 commit timestamp.
- **Pre-existing trades (98 from 2026-08-31):** PRE-BASELINE. Kept forever. Excluded from measurement.
  - Trades dump sha256: `5796a2ebe8a6ad141a62daacd6fa979b822e97ce231437c1c30b2bb34ed71896`
- **Duration:** ≥40 trades AND ≥6 months (expected finish ~9–10 months).
- **Position sizing:** 0.25% fixed-fractional per trade.
- **Circuit breakers:** 2 losses in a day = done for the day. One open position max.
- **Per-fill log:** slippage + spread + swap. Measuring real costs vs 0.5-pip assumption is the entire point.

---

## 4. Kill Criteria (Paper)

- PF (with real swap/spread) < 1.0 after 40 trades = KILL
- MaxDD > 10% of starting equity = KILL
- Fidelity gate failure = VOID (not a kill — a measurement restart)

---

## 5. Weekly Heartbeat

- Paste fill-log excerpt + sha256
- No silent failures
- No edits to frozen files
- All fixes in separate commits with hashes

---

## 6. P2 Prerequisites (before P3 first fill)

1. Build `live_h1.py` — imports signal logic from frozen `run_h1.py`, never edits it
2. Shadow mode ≥14 days or ≥10 signals, signal-only, zero orders
3. Parity table: live signal vs backtest on same data
4. Kill switch documented and tested
5. Adapter frozen with new sha256

---

## 7. Security

- `.env` in `.gitignore` ✓
- Default API key fallback to be removed (env-only)
- No secrets in chat/commits/build output
- Tunnel stays off
