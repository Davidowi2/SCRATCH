POPCORN MACHINE — BUILD DIRECTIVE v1.0 (self-contained; commit this
file as factory/CHARTER.md before any work; paste back commit hash)

CONTEXT RESTORED: You have no chat memory. This file is the authority.
Frozen artifacts you may reference but NEVER edit:
  run_h1.py sha256 6226222c1eb076fb2f6fe4862d1992a80c5f68fe54a6353697312d160cf8f291
  validator commit 662bd10ea2d10ee6dc1539e38a6fb3782785077b
  OOS_FROZEN content e97f30cca61608b9c93e7ea27a42c8a76ae45843207d83604d2e2bdad622d8f6
  H-002 spec 0ac2644aa4283e1de30a961dcca428cfe70edd398ee5cd2ddfa98cf37e3f6e12
  H-002 engine 6f16438e1b5beb418f6e3714389048bc44629549ca87e5897b73f937baaa12da
  H-002 IS log cee44753f99f8210119a9e1fb24d115f603d29cc73d09a9f57263b2096dd0dad
Windows (all real kernels): IS 2021-01-01..2023-12-31 /
OOS 2024-01-01..2025-05-13. One shot per window, per kernel, forever.

PHASE 0 — GRAVEYARD + FINGERPRINTS (do first)

0.1 Create factory/graveyard.csv, append-only via git commit only.
Head-hash of the file goes into every batch report and weekly
heartbeat (external anchor). Direct edits are a containment breach.
Backfill rows (commit in one commit, then never touch again):
  H-001 | fade Z>=2 SMA20 Asia 22-07 EURUSD H1 | LIVE | PRE-FACTORY
  H-002 | ESCAPE: ride closes >=2.5SD Asia | MECHANISM-DEAD |
         justification: PF 0.20, WR 14.5%, 85% reversal, diagnostic
         inversion of live H-001. Re-test forbidden absent owner
         override + new evidence.
  H-002-v1 | 4H trend London | UNTESTED (tombstoned pre-backtest)
  Edge-Labs | legacy scalper | LEGACY-RETIRED (pre-machine, no records)
  Invincible | legacy breakout | LEGACY-RETIRED (pre-machine)
  scratch_bot | M5 breakout stalling-exit | LEGACY-RETIRED
         (PRE-BASELINE, 98 trades, old account)
LEGACY-RETIRED and PRE-FACTORY rows are excluded from total_tested.

0.2 Two-tier fingerprint. Mechanism vector = {signal family, entry
trigger class, exit logic class, session window, timeframe class,
instrument class(FX-major)}. Canonical JSON -> sha256 = mechanism_hash.
parameter_hash = sha256(mechanism_hash + canonical JSON of exact
params {pair, thresholds, bands, stop mult, max hold, MA period,
friction}). Unit tests required:
  T1: H-003 computes mechanism_hash == H-001's stored hash
  T2: H-003 parameter_hash != H-001's
  T3: synthetic probe vs H-002 (MECHANISM-DEAD, no parent_id,
      no pre-declaration) -> BLOCKED
  T4: H-003 (parent_id=H-001, pre-declared replication) -> FLAGGED,
      ALLOWED, logged as sibling
  T5: attempted in-place edit of graveyard.csv -> rejected by process
T1-T4 use probe entries labeled SMOKE-TEST-PLUMBING-VALIDATION —
excluded from the luck ledger forever.

PHASE 1 — H-003 (single kernel; run only after 0.1-0.2 committed)

H-003 = H-001 fade logic on GBPUSD, Asian session. Parent: H-001.
Pre-declared replication (declared before submission, on record).
1. Fetch GBPUSD H1 2021-01-01..2025-05-13, same source as EURUSD.
2. Freeze: manifest + per-year counts + content sha256, PASTED.
3. Certified validator 662bd10 on GBPUSD data. Paste output.
   REJECT -> stop, report, no validator edits. Same law as always.
4. New engine file (escape/GBP engine), imports frozen logic, never
   edits run_h1.py. New commit + full sha256.
5. FRICTION = 1.0 pips/trade, frozen NOW (pre-test estimate: fatter
   GBP Asia spreads). Report net.
6. Gates = H-001 v2.1 table exactly: n<50 INSUFFICIENT / PF<1.0 KILL /
   WR drop>15pp KILL / PF 1.0-1.15 DANGER / >=1.15 pass phase.
7. IS first -> full artifact report (metric table, exit breakdown,
   trade log sha256, engine sha256) -> 24h cool-off -> OOS.
8. Resolution row appended to graveyard with verdict hash.

PHASE 2 — CALIBRATION (before any real batch)

2.1 Noise control batch: 10 kernels known-random by construction
(inverted-logic variants, randomized entry timing, shuffled-returns)
through the identical ladder, labeled CALIBRATION. Output:
null_pass_rate = survivors/10, recorded with artifact hashes.
GATE CHANGE LAW: anything this motivates applies only to kernels
tested after the change; versioned; never retroactive.
2.2 Clone ceiling: similarity defined ONLY within a shared
mechanism_hash (cross-mechanism = different by definition). v0 metric:
normalized parameter overlap; >=80% -> collapse to one effective
kernel. Calibrate against anchors: H-001 vs H-003 must score SIBLING
(different instrument); synthetic same-mechanism Z=2.0 vs Z=2.5 pair
must score CLONE. Report both raw N and effective N.
2.3 Cumulative luck ledger, lifetime scope, machine epoch onward:
  total_tested (excl. SMOKE/CALIBRATION/PRE-FACTORY)
  cumulative_luck_expected = total_tested x null_pass_rate
Every batch report prints both. Survivors <= expected -> all
survivors treated as unproven until paper proves them.

PHASE 3 — FIRST REAL BATCH (5 kernels)

3.1 Backlog seeds: (a) H-001 fade AUDUSD Asia; (b) H-001-family fade
with weaker entry trigger; (c) up to 2 HERMES-generated kernels —
provenance column mandatory (OWNER/AUDITOR/HERMES), machine-generated
<=70% of any batch, forever.
3.2 Batch report template: BATCH id / date / requested N / effective
N (post clone-collapse) / killed M by cause / survived K / lifetime
total_tested / null_pass_rate + calibration date / cumulative
luck-expected / graveyard diff with hashes / verdict hash per kernel.
3.3 Ladder unchanged: Audition -> OOS (one shot) -> Paper (max 3
concurrent slots) -> Real money (owner + verdict hash, always).
H-001 occupies one paper slot already; H-003 takes one if it passes.

H-001 SHADOW LANE ADDENDUM (Option B):
The shadow data collector is DIVORCED from the ladder.
It records live fills (timestamp, side, price, spread, slippage)
in a SEPARATE table (shadow_fills) and is used ONLY for:
  - Weekly heartbeats
  - Spread monitoring
  - Slippage analysis
Fills from the shadow lane are EXCLUDED from:
  - Ladder statistics (IS/OOS/Paper)
  - Graveyard verdicts
  - Luck ledger
  - null_pass_rate
The shadow lane has no gates. It collects whatever the live feed
produces. The ladder runs on frozen historical data only.
This separation is permanent and non-negotiable.

THE LEASH (frozen; renegotiation is a breach):
never edit criteria after results; never retest MECHANISM-DEAD
without owner override + new evidence in writing; never delete/
rewrite/reorder graveyard rows; never skip a ladder rung; never
touch real money; never hide or understate batch size; no graveyard
row without a pasted artifact and verdict hash.

H-001 SHADOW LANE RULING (Option B, Owner-approved):
H-001 remains LIVE-shadow as a data collector only. Divorced from ladder
promotion: ineligible for real money without a fresh OOS pass on a
re-preregistered kernel. Its logged fills are excluded from ladder
statistics (IS/OOS/Paper), graveyard verdicts, luck ledger, and
null_pass_rate.

## Addendums

H-001 SHADOW LANE ADDENDUM (Option B):
The shadow data collector is DIVORCED from the ladder.
It records live fills (timestamp, side, price, spread, slippage)
in a SEPARATE table (shadow_fills) and is used ONLY for:
  - Weekly heartbeats
  - Spread monitoring
  - Slippage analysis
Fills from the shadow lane are EXCLUDED from:
  - Ladder statistics (IS/OOS/Paper)
  - Graveyard verdicts
  - Luck ledger
  - null_pass_rate
The shadow lane has no gates. It collects whatever the live feed
produces. The ladder runs on frozen historical data only.
This separation is permanent and non-negotiable.

STANDING DEBTS (paste with Phase 0 delivery, third+ request):
  1. Day-0 balance on screen: $100,000 or $1,000,000 — which is real?
  2. Leverage from account settings (not assumed).
  3. Full 40-hex commit hash of the H-002 verdict commit (bdbf441...).
  4. Content sha256 of the rebuilt IS slice + explanation of the
     2021-2023 CSV disappearance/rebuild between runs.
