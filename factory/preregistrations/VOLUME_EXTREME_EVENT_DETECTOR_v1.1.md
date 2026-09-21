# VOLUME EXTREME EVENT DETECTOR — SPEC v1.1

- STATUS: PREREGISTERED (owner-approved via Phase 1B directive, 2026-09-21)
- INSTRUMENT/TF: BTCUSDT USD-M PERPETUAL, 5-minute bars (Binance UM klines)
- PURPOSE: Event detector for the forced-liquidation-cascade proxy.
  Detector ONLY — structural filtering and entry/exit logic are deferred
  to the kernel spec (§6).
- AMENDMENT v1.1 (owner, 2026-09-21): §1 definitions moved from
  notional-volume basis to trade-count basis after Phase 1A established
  that Binance never published liquidation history (probe verdict FAIL,
  ledger event PROBE-LIQ-1A).

## §0 PROVENANCE AND RECONSTRUCTION FLAGS (Overseer must read before Phase 2)

- **FLAG-1 (provenance):** The v1.0 spec text was authored in the Overseer
  channel and was never committed to this repository. This v1.1 file is the
  canonical in-repo text, composed from (a) the owner's §1 amendment quoted
  verbatim below, (b) the Rule 1 / Rule 2 mechanics as specified in the
  Phase 1A / Phase 1B directives, and (c) the Phase 1B derivation procedure.
  The Overseer must verify this reconstruction against the locked v1.0
  before Phase 2 (Isolation Protocol) fires.
- **FLAG-2 (interpretation, declared):** Rule 2 is read as TWO-SIDED with
  direction recorded: closepos(t) <= Y (sell-side event) OR
  closepos(t) >= 1-Y (buy-side event). Rationale: liquidation cascades
  occur in both directions and the kernel spec needs the direction
  attribute. If the locked v1.0 reads Rule 2 as one-sided, the Y derivation
  must be re-adjudicated before Phase 2 (holdout-retirement ruling required).
- **FLAG-3 (interpretation, declared):** The §1 edge-case guards
  (range==0, trades==0) exclude bars as EVENT CANDIDATES only. Such bars
  remain in the rolling reference set for Rule 1 quantile computation
  (they are real market states).
- **FLAG-4 (data, declared):** Phase 1B item 3 cites the validated 2021+
  dataset (459,072 bars, sha db2b863b...) as input, but that file
  (a) does not carry the trade-count column and (b) does not cover the
  2019-09..2020-12 holdout. The derivation therefore uses a NEWLY
  downloaded 2019-09..2020-12 kline file WITH col[8], Gate-1-CRYPTO
  validated and manifest-logged (synthetic: false). The 2021+ file remains
  the Phase 2 isolation input.

## §1 DEFINITIONS (v1.1, AMENDED — owner text verbatim)

```
vol(t)       → trades(t)   [number of trades in bar(t), Binance col[8]]
logvol(t)    → logtrades(t) = ln(trades(t) + 1)
```

Owner rationale (verbatim): "Binance never published liquidation history
(Phase 1A FAIL). Trade-count is the closest available proxy for
forced-order bursts. Raw volume is secondary; trade-count captures the
'many small forced fills' signature of a cascade more faithfully than
notional volume."

Additional definitions:

- range(t) = high(t) - low(t)
- closepos(t) = (close(t) - low(t)) / range(t)    [undefined if range(t)==0]
- Reference set R(t) = the N = 4032 bars (14 days) immediately preceding
  bar t (timestamps strictly inside (t - 14 days, t)), bar(t) excluded.
  Rolling, backward-looking, no lookahead.
- Q_x(t) = the (1 - x) quantile of { logtrades(u) : u in R(t) },
  linear-interpolation method (numpy-default convention).

EDGE-CASE GUARDS (v1.1 §1):
- range(t) == 0  → skip (not a candidate).
- trades(t) == 0 → skip.
- First N bars of window → skip (insufficient reference).
- Reference window < 99% complete → skip. Completeness = |R(t)| / 4032
  (|R(t)| counted by timestamp membership), require >= 0.99.

## §2 RULE 1 — VOLUME (TRADE-COUNT) OUTLIER

Bar t qualifies under Rule 1 iff:

    logtrades(t) > Q_X(t)

where X is the outlier-tail percentile (derived once in §4, then frozen).

## §3 RULE 2 — CLOSE-POSITION (conviction + direction)

Bar t qualifies under Rule 2 iff (two-sided, direction recorded — FLAG-2):

    closepos(t) <= Y          → sell-side event, or
    closepos(t) >= 1 - Y      → buy-side event

where Y is the close-position threshold (derived once in §4, then frozen).

**EVENT(t)** = Rule 1 AND Rule 2 AND all §1 guards passed.
Direction (sell-side / buy-side) is an event attribute carried to the
kernel spec.

## §4 DERIVATION PROCEDURE (holdout — RETIRED after this run)

- Holdout window: 2019-09-01 → 2020-12-31 (nominal). BTCUSDT perp
  inception 2019-09-08; this is the full available window.
- March 2020 crash stays IN. No outlier-day stripping.
- The window is RETIRED after derivation: never reused for isolation
  testing, OOS, or Paper. Parameter derivation and hypothesis evaluation
  do not share data.
- Reference set N = 4032 bars (14 days), rolling, bar(t) excluded.

**STEP 1 — DERIVE X.** Grid X over {0.5%, 1%, 2%, 3%, 5%}. For each
candidate, compute the qualifying-bar rate over the holdout (qualifying
bars per day; day-denominator = evaluated candidate bars / 288).
Selection rule (declared pre-run): the X whose rate lands INSIDE
3–8 outlier bars/day; tie-break among multiple inside: smallest
|rate − 5.5| (interval midpoint); if none inside: smallest distance to
the interval. Log the full grid table (all candidates).

**STEP 2 — DERIVE Y.** Grid Y over {10%, 15%, 20%, 25%, 33%}. Applied
ONLY to bars that already passed the derived X (and all guards).
Selection rule (declared pre-run): the Y whose COMBINED (Rule 1 AND
Rule 2) event count lands INSIDE 250–750 across the full holdout;
tie-break: smallest |count − 500|; if none inside: smallest distance to
the interval. Log the full grid table (with sell-side / buy-side split
as diagnostic decomposition).

**STEP 3 — FREEZE AND LOG.** Record X, Y, N, exact effective holdout
range (first eligible bar → last bar), and both grid tables in the
ledger as a parameter-derivation event. This derivation consumes NO
batch/luck budget (calibration, not verdict).

Conventions (declared): linear-interpolation quantiles; strict
inequality in Rule 1; guards per §1; guard-excluded bars remain in
reference sets (FLAG-3).

## §5 FALLBACK HIERARCHY (unchanged)

1. Exchange-native liquidation history — Phase 1A verdict: **FAIL**
   (data.binance.vision holds no liquidationSnapshot keys; allForceOrders
   REST dead; aggregators unreachable/paywalled from this network).
2. Tick-volume percentile spec (THIS document, v1.1 Rules 1–2) —
   **AVAILABLE** (kline trade-count column present and populated).
3. If both fail: mechanism declared UNTESTABLE. (Not met — fallback data
   confirmed available.)

## §6 OUT-OF-SCOPE (unchanged)

Structural-level filtering (trend, session, level context) and entry/exit
logic remain deferred to the kernel spec. This document defines the event
detector only.
