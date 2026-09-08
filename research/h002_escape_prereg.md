# H-002 v2 = "ESCAPE" — Full Preregistration

**Status:** FROZEN — no backtest yet
**Created:** 2026-09-08
**Spec source:** Delivered in full by owner, committed verbatim

---

## H-002 v1 Tombstone (append-only, never deleted)

H-002 v1 (EURUSD 4H trend, London session): retired untested, zero backtests run, superseded by v2. Reason: spec delivered incomplete.

---

## Hypothesis

During the Asian session (22:00-07:00 UTC), when EURUSD H1 closes >=2.5 standard deviations beyond its SMA20 band (closing outside the band), price continues in the escape direction more often than it reverts. This is the deliberate inverse of H-001, seeded by H-001's 68 logged stop-loss exits (40 IS + 28 OOS) — its failures are this strategy's signal.

---

## Rules

| Parameter | Value |
|---|---|
| Instrument | EURUSD |
| Timeframe | H1 |
| Session | hours {22,23,0,1,2,3,4,5,6} |
| Entry | at close of the first bar where |Z| >= 2.5 AND close is outside the band, in the escape direction (close above band -> LONG, below -> SHORT) |
| Z definition | vs SMA20, 20-bar window, same as H-001 |
| Stop | 2.0 x entry-bar SD |
| Exit | close back inside the 1.0 SD band, OR max hold 24 bars |
| Max positions | 1 |
| Friction | 0.5 pips/trade, net figures reported |

---

## Frozen Windows (identical to H-001, hash-verified)

| Phase | Window |
|---|---|
| IS | 2021-01-01 .. 2023-12-31 |
| OOS | 2024-01-01 .. 2025-05-13 |
| Dataset hash | `e97f30cca61608b9c93e7ea27a42c8a76ae45843207d83604d2e2bdad622d8f6` |
| Engine baseline | `run_h1.py` sha256 `6226222c1eb076fb2f6fe4862d1992a80c5f68fe54a6353697312d160cf8f291` |
| Validator | certified H1 suite, commit `662bd10ea2d10ee6dc1539e38a6fb3782785077b` |

---

## DNA Check (rule inline for self-containment)

A new hypothesis is disqualified if it matches any existing strategy (H-001, Edge-Labs, Invincible) on >=3 of 5 dimensions {instrument, timeframe, session, signal family, holding time}, with at least one match being signal family or session.

| vs | Instrument | Timeframe | Session | Signal Family | Holding | Total | Disqualifies? |
|---|---|---|---|---|---|---|---|
| H-001 | ✓ | ✓ | ✓ | ✗ | ✗ | 3 | NO (signal family differs) |
| Edge-Labs | ✗ | ✗ | ✗ | ✗ | ✗ | 0 | NO |
| Invincible | ✓ | ✗ | ✗ | ✗ | ✗ | 1 | NO |

ESCAPE passes DNA — distinct signal family (continuation vs reversion) saves it despite sharing instrument + session with H-001.

---

## Gates (frozen now)

| Condition | Verdict |
|---|---|
| n < 40 trades | INSUFFICIENT |
| Win rate < 30% | KILL |
| PF < 1.0 | KILL (hard, no exceptions) |
| PF 1.0–1.15 | DANGER-ZONE |
| PF >= 1.15 | Passes that phase |
| OOS WR drop >15pp vs IS | KILL |

---

## Protocol

- One shot per window
- No parameter changes between runs, ever
- Any re-run requires tombstoning the prior version first
- All thresholds in this file were fixed before the first ESCAPE backtest existed
- Engine baseline: `run_h1.py` (read/import only — NEVER edited; ESCAPE engine is a NEW file)
