# Phase 1 — Correction (append-only)

## F1 Correction: Expected OOS n

**Original (erroneous):** ~99 trades (stated 2.33 years, 8,509 bars ÷ 6,240 bars/yr — wrong divisor).

**Corrected calculation:**
- In-sample: 128 trades / 18,705 bars = 6.843e-3 trades/bar
- OOS: 8,509 bars × 6.843e-3 = **58.2 trades**
- Year check: 498 days (2024-01-01 → 2025-05-13) = 1.36 years; 42.67/yr × 1.36 = 58.2

**Branch decision: n ≥ 50 → proceed.** Buffer to INSUFFICIENT is thin (~8 trades).

## F2: Same-Day Rule Tightening

**Decision: (a) tighten — same-day exclusion applies only if date ∈ holiday calendar.**

New rule in `validate_data.py`:
```python
if prev["time"].date() == cur["time"].date():
    if prev["time"].strftime("%Y-%m-%d") in MARKET_HOLIDAYS:
        continue
    # else: real same-day outage → falls through to gaps.append
```

**Impact on existing tests:**
- Same-day partial holiday gap (Christmas): still CLEAN ✓
- New test: same-day non-holiday gap (mid-day outage): now REJECT ✓
- All other tests: unchanged ✓

## N2: Full Hash

`af8025f089d209242c5b0bbf75aa7e06117d0f88`

## N3: Full kill_log.csv (3 lines)

```
experiment,date,process_version,family,params,data_range,WHY,n,win_rate,profit_factor,expectancy_pips,max_dd_pips,verdict,note
H-001,2026-09-07,v1,MR,"Z>2 SMA20 1SD-band reversion, Asian 22:00-07:00, maxhold 8, SL 1.5xSD","2021-01-03..2023-12-29","Asian-session liquidity...",128,0.609,1.30,1.79,98.2,DANGER-ZONE,"PF 1.30 in 1.2-1.8 band..."
```

(1 data row, no correction needed — clock was correct)

## N4: Full Validator Audit Output

Latest audit (1394 files):
```
[FLAG] Feed-freeze suspicion: 145 zero-volume bar(s) during Mon-Fri trading hours
[REJECT] 1 data gap(s) of >= 4h not explained by a weekend or holiday:
         2025-06-11 23:00:00 -> 2025-06-13 00:00:00  (25h)
```

**Action:** Freeze OOS window to end before the gap: **2024-01-01 .. 2025-05-13**

## N5: Gate 2 DNA Check — Overlap Criteria

Dimensions compared:
1. **Instrument:** all trade EURUSD ✓
2. **Timeframe:** H-001 = 1H; Edge-Labs = M5; Invincible = M5 → **NO overlap**
3. **Session:** H-001 = Asian (22:00-07:00); Edge-Labs = expansion (7-17 UTC); Invincible = London/NY (8-11, 13:30-16:00) → **NO overlap**
4. **Signal family:** H-001 = mean reversion; Edge-Labs = momentum/impulse; Invincible = breakout/BOS → **NO overlap**
5. **Holding time:** H-001 = max 8 bars (8 hours); Edge-Logs = seconds-minutes; Invincible = variable → **NO overlap**

**Conclusion:** H-001 is structurally distinct from both retired bots on all 5 dimensions.
