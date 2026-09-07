# Trading Research Platform — Consolidated Roadmap (v2)

*Refined across four independent AI reviews (Claude, DeepSeek, Kimi, Gemini) on top of the original ChatGPT roadmap and Claude's first refinement. Built from 11 retired bots and one working research harness (Invincible).*

---

## Core Principle (unchanged)

> Optimize for building a machine that is good at **killing bad ideas cheaply** — not for finding a profitable strategy quickly.

---

## Sequencing Fix (Claude's original contribution, confirmed by all reviewers)

Don't build the full research platform before testing anything. Build only the minimum engine Hypothesis #1 needs, then extend on demand as later hypotheses require new capability. All four reviews agreed this was the single most important correction to the original plan.

## Strategy Family Ranking (unchanged, confirmed)

1. Momentum — solo-buildable now
2. Mean reversion — solo-buildable now ← **starting point**
3. Regime detection — build as a filter layered on top of 1–2, not standalone
4. Volatility — after 1–3, needs harder-to-source data
5. Event-driven — needs clean timestamped news data, high look-ahead-bias risk
6. Stat-arb / pairs — needs multi-leg execution TradeLocker likely can't support
7. Cross-sectional — professional-scale project, last if ever

---

## Phase 1.5 — Validation & Pre-Flight (new, inserted between Phase 1 and Phase 2)

All four reviews converged on the same five gates, in this order. Nothing runs until each gate passes.

```
DATA VALIDATION
      ↓ PASS
STRUCTURAL DNA CHECK vs. retired bots
      ↓ PASS
PRE-COMMIT PARAMETERS + KILL CRITERIA (locked, no changes after seeing results)
      ↓ LOCKED
IN-SAMPLE RUN → n ≥ 50 trades? → PASS / KILL
      ↓ PASS
OUT-OF-SAMPLE RUN → kill criteria met? → KILL / paper candidate
```

### Gate 1 — Data Validation (mandatory `validate_data()` before any backtest)

| Check | Rule | Action on Fail |
|---|---|---|
| Gap detection | >3 consecutive missing candles | Reject dataset, investigate source |
| Weekend contamination | Candle timestamped Fri 22:00–Sun 22:00 UTC | Strip or flag, don't assume broker alignment |
| Zero-volume candles | Volume = 0 during normal trading hours | Flag as possible feed freeze |
| OHLC integrity | High < Low, or Open/Close outside [Low, High] | Reject row |
| Timestamp monotonicity | Out-of-order or duplicate timestamps | Reject and deduplicate |
| Session coverage | <80% of expected Asian-session candles present | Reject — incomplete session data invalidates the hypothesis |

Log all of the above per file in a `data_audit.log`. One dirty file should poison the whole backtest run, not get silently averaged out.

### Gate 2 — Structural DNA Check vs. Retired Bots

Before Hypothesis #1 runs, explicitly answer: *does this hypothesis share any entry logic, filter, or price-shape trigger with any of the 11 retired bots?*

1. List each retired bot's core entry/exit mechanism.
2. Write down Hypothesis #1's trigger, session filter, and exit logic separately.
3. Compare element by element.

**Rule:** if entry logic overlaps with a retired bot that failed on the same asset class and timeframe, either (a) change the trigger to something structurally different, or (b) explicitly re-test the exact retired variant, confirm it still fails, and justify why the new parameter set is meaningfully different. Never skip this — it's the fastest way to unknowingly retest a corpse.

### Gate 3 — Statistical Significance Floor

**No verdict — kill or keep — is valid below these sample sizes:**

| Metric | Minimum n | Why |
|---|---|---|
| Win rate | ≥50 trades | Binomial variance collapses slowly; 50 gives ~±14% CI at 95% |
| Expectancy | ≥50 trades | Ratio of sums, needs enough samples |
| Profit factor | ≥50 in-sample, ≥30 OOS | Sensitive to one or two large outliers at small n |
| Sharpe / Sortino | ≥100 trades | Variance estimators are noisy below this |

If a hypothesis can't generate 50 in-sample trades over a reasonable data window (e.g., 2 years of 1H data), it's either too restrictive to ever trust the OOS result, or already over-fit to specific conditions. Kill or relax constraints until n ≥ 50 — don't evaluate below the floor.

### Gate 4 — Parameter Overfitting Guard (zero grid-search policy)

**Rule:** exactly one pre-committed parameter set for the first in-sample run. No grid search. If it fails, exactly one alternative may be tried, pre-committed *before* seeing results. After two attempts total: kill the hypothesis. The OOS test uses whichever set survived in-sample — never the best-performing set chosen after the fact.

Every parameter tuned in-sample is a degree of freedom. Five tunable parameters at even 3 values each is 243 backtests — the best one will look good by chance alone, and the OOS test becomes worthless if it's used to pick among many.

### Gate 5 — Numeric Kill Criteria (pre-committed, non-negotiable)

| Phase | Metric | Kill If | Rationale |
|---|---|---|---|
| In-sample | Profit Factor | < 1.15–1.2 | Below this, live costs erode the edge entirely |
| In-sample | Win Rate | < 45% (below break-even given the friction model) | Negative expectancy with typical R:R |
| In-sample | Max Drawdown | > 15% of starting equity | Risk of ruin too high for the edge size |
| In-sample | n (trades) | < 50 | Insufficient sample — see Gate 3 |
| Out-of-sample | Profit Factor | < 1.0 | **Hard kill, no exceptions** |
| Out-of-sample | Profit Factor | < 50% of in-sample PF | Catches severe overfitting even if still marginally profitable |
| Out-of-sample | Win Rate | Drops >15 percentage points vs. in-sample | Edge decayed or regime shifted |
| Paper | Profit Factor | < 1.0 after 30 trades | Live friction is always worse than simulated |

Write these down before running the backtest. If you find yourself arguing "but it's close" or "just one more tweak" — the system has already failed. Kill it.

---

## Additional Considerations From the Multi-AI Review Round

- **OOS reuse across many future hypotheses is its own overfitting risk.** Testing dozens of ideas against the same out-of-sample window over time means some will pass by chance eventually. Use a three-way split — train / validation (for any parameter selection) / test (final, untouched verdict) — once past Hypothesis #1.
- **Friction assumptions may be too optimistic.** Run a slippage sensitivity analysis: backtest at 1.5x, 2x, and 3x the assumed slippage. If the strategy dies at 2x, it's too fragile to trust live.
- **Risk management framework needs defining before paper trading**, not after — fixed-fractional position sizing (e.g., 0.5% risk/trade), max daily loss, and (once multiple strategies run) max correlation between open positions. Reuse Invincible's risk modules.
- **Experiment log from day one.** Every hypothesis test — killed or promoted — logged with parameters, data range, metrics, and reason for the verdict. Simple CSV or Markdown is enough. Prevents accidentally re-testing the same idea later and builds a searchable record of what doesn't work.
- **Regime-awareness before killing, not after.** If Hypothesis #1 only works in low-volatility periods, that's information, not necessarily a kill — segment the data by volatility regime (e.g., ATR percentile) before writing off a hypothesis that failed only because the test window happened to be trending.
- **ML gate, timing:** justified only after ~10 rule-based hypotheses across families 1–3 have been exhausted and a persistent pattern emerges that's hard to formalize as a simple rule. Mandatory feature-leakage audit (every feature checked for hindsight-only availability) before any baseline comparison.

---

## Hypothesis #1 — Parameter Set (pre-committed; two independent AI-suggested variants shown — pick one before running, do not average or blend them)

**Both are unvalidated starting guesses, not backed by data — the backtest result is what earns trust, not which AI proposed the number.**

| Parameter | Variant A | Variant B |
|---|---|---|
| Instrument | EURUSD | EURUSD |
| Timeframe | 1H | 1H |
| Session window (UTC) | 22:00–07:00 | 22:00–06:00 |
| MA period | 20 | 20 (SMA) |
| SD threshold (X) | 2.0 | 2.0 |
| Reversion target | Close back inside 1 SD band | Return to 20 SMA or 1.5 ATR |
| Max hold (N bars) | 8 | 4 |
| Stop-loss | 1.5× entry SD distance | 1.5 SD beyond entry extreme |
| Friction | Invincible baseline stack | 0.3 pip spread + 0.2 pip slippage buffer |
| In-sample period | (fill in) | 2021–2023 |
| Out-of-sample period | (fill in — must be genuinely unseen) | 2024–2025 |

**Rule from Gate 4:** pick one variant now as the single pre-committed run. Do not test both and keep the better-looking one — that's the exact grid-search behavior Gate 4 exists to prevent.

---

## Immediate Next Action

Not another AI review pass — that's past the point of diminishing returns. Write the `validate_data()` script against the real Dukascopy pipeline and run Gate 1 on actual historical data. Everything above is still a plan until real data has been checked.

---

## v3 Amendments — Kimi/DeepSeek Cross-Review Rulings

*Resolved after Kimi and DeepSeek pressure-tested each other's additions. Where the two disagreed, the sharper/harder version was kept — see note on the one resolved contradiction below.*

### Finalized Rulings

1. **Opportunity cost floor:** hard, non-negotiable minimum acceptable return — 10% annualized after costs at target risk. Below this, kill regardless of profitability. Time is the non-renewable resource for a solo builder; capital is not.
2. **No parallel hypothesis testing.** Pick one timeframe/hypothesis, write down why, lock it, run it. If it dies, the next variant (e.g., "Hypothesis #1b, 15-min") is a separate, independently pre-committed cycle — not a simultaneous comparison. Parallel testing is uncommitted exploration disguised as rigor; it doubles false-positive risk.
3. **Execution Fidelity Score is binary, not a calibration knob.** Threshold: ≤0.5 after 10 paper trades. Above 0.5 → the broker/execution environment can't capture this edge. Don't adjust the friction model to make peace with bad fills — treat it as a kill signal or a reason to test a different broker, not a reason to loosen the model. *(Amended below — see note.)*
4. **Process versioning is exile, not calibration.** Any change to a validation rule (kill thresholds, sample floors, robustness bands) increments a `process_version` integer. Results from a prior version are never compared against or averaged with results from a new version — they're discarded outright, not flagged or footnoted. This is the single most important rule in this document: it's the only defense against a validation process that quietly loosens itself every time a strategy narrowly fails.
5. **Cost/friction model set once, not re-optimized to rescue a result** — but *can* be updated if real paper-trading fills prove the original assumption wrong (this is a correction to ruling 5 as originally stated; "never refine" was too rigid — the kill thresholds stay fixed, but a friction model actively disproven by live fill data should be corrected, otherwise every future hypothesis is evaluated against a model already known to be broken).
6. **Volatility-of-volatility filter: not added for Hypothesis #1**, even though DeepSeek correctly identified that 1H candles can't distinguish genuine microstructure overshoot-reversion from flat-price noise dressed up as reversion. This is a known, accepted gap for the first run — not an oversight. Track ATR quartile per trade for post-hoc analysis; decide whether to add the filter only after seeing whether it would have mattered.
7. **Kill log format**, standardized, one line per hypothesis:
   ```
   H-001 | 2026-09-01 | v1.3 | MR | Z>2 MA20 Asian 1H | WHY: low-liquidity overshoot | KILL: OOS_PF=0.82 | FAIL: trigger fires in flat vol | NEXT: add ATR filter
   ```
   The `WHY` field (why it was pre-committedly expected to work) is mandatory — it's what makes the post-mortem falsifiable instead of just descriptive.

### Structural DNA Check — Resolved Time Budget

Kimi's original "1 hour per retired bot" (11 hours total) was correctly challenged by DeepSeek as its own form of procrastination — a large, sunk-cost-generating task that pressures you to find overlaps that may not exist, just to justify the time spent. **Resolved: 30 minutes total, not per bot:**
- 10 min: write down the 2–3 bots you remember clearly (trigger type + bet direction only)
- 10 min: skim code/filenames for "MA," "Z-score," "Asian," "session"
- 10 min: check specifically whether any retired bot was mean-reversion on EURUSD

Anything unclear after a quick skim is marked `UNKNOWN — not a duplicate risk unless proven otherwise`. Burden of proof is on the new hypothesis to be original, not on the archive to be exhaustively documented. This is a smoke detector, not a forensic lab.

### The Actual Next Action (not "run Hypothesis #1" — too big a unit)

**60 minutes, right now, in three steps:**

1. **Data fingerprint (20 min):** run existing EURUSD 1H data through weekend contamination check, rollover spread-spike check (21:55–22:05 UTC), timestamp monotonicity check. Output one line: `CLEAN` or `FLAGGED: [reason]`. Fix before proceeding if flagged.
2. **Pre-mortem run (30 min):** one backtest, sentry set only (EURUSD 1H, 23:00–05:00 UTC, MA20, Z>2, 1 SD reversion target, max hold 8 bars, existing friction model), **in-sample only.** No OOS yet, no equity-curve inspection — just PF, win rate, n, max drawdown.
3. **Apply the kill script (10 min):** run the pre-committed `should_kill()` logic. Log the result in the format above.
   - PF < 1.0 → kill, log it, move to Hypothesis #2. The process worked.
   - PF > 2.0 → be suspicious, not excited — likely a leakage or friction-model bug. Debug before trusting it.
   - PF 1.2–1.8 → the dangerous zone. Log it, stop, don't tweak, decide tomorrow whether it earns OOS.

The point isn't to find a winner in 60 minutes. It's to prove the machine can run and kill something cheaply — which, per the core principle at the top of this document, is the actual goal.
