# Work Order — H-001 Path to OOS (v1)

Sequenced by dependency. Each item states its **done-artifact** (rule 2: no paste, no checkmark). Save this file as `research/work_order_v1.md`, commit it, and paste the hash back — it is itself a preregistration under rule 1.

---

## Phase 1 — Data ground truth *(blocks everything)*

**1.1 Data manifest.** Paste first bar, last bar, total bar count for (a) full dataset, (b) OOS slice 2024-01-01→last actual bar.
*Done when:* manifest pasted, from the data files, not from config or plan.

**1.2 Clock reconciliation.** Kill log row is dated `2026-09-07`. Explain the clock or correct it.
*Done when:* either a pasted `date` output showing the true clock, or an **append-only** correction row in `kill_log.csv` (never edit the original — rule 3 spirit).

**1.3 Re-freeze OOS window.** `2024-01-01 .. <last actual bar from 1.1>`, committed.
*Done when:* full commit hash pasted.

**1.4 Restate expected OOS n** from the manifest bar count and the 43/yr rate. Then resolve the branch **in writing, before the run**:
- expected n ≥ 50 → proceed to Phase 6 when ready;
- expected n < 50 → owner chooses: **(a)** extend OOS *forward* as new bars accrue (clean — defined before any OOS result), or **(b)** accept INSUFFICIENT as the preregistered outcome.
- ⚠️ Extending *backward* into 2020 is not a clean option — 2020 data was examined during validator debugging; it is development-tainted.

*Done when:* expected n stated; branch decision written and committed.

## Phase 2 — Validator certification

**2.1 Add the two historical-failure tests:** boundary-truncated week (2020-W53 / 2025-W17 pattern) and same-day partial holiday gap. Suite must go green with them included.

**2.2 Resolve the holiday contradiction.** Test #4 asserts `holiday → REJECT`; the shipped validator treats holidays as non-fatal. One of them is wrong. Paste the validator's *actual* output on the real holiday fixtures.

**2.3 Paste the exemption list** (holiday calendar + same-day rule + boundary rule) **with its external source** — an exchange/market calendar reference, not memory.

**2.4 M3 dispositions.** One line per originally "suspicious gap": confirmed holiday / real gap / boundary effect / unresolved. Unresolved ones must be shown on the dataset map, not absorbed silently.

**2.5 Re-freeze validator.** Paste full hash (`git log -1 --format=%H`), not `abc1234`.
*Done for Phase 2 when:* 2.1–2.5 artifacts pasted in one block.

## Phase 3 — Freezes

**3.1 Strategy config + engine commit hash.** Gate 4 currently has no artifact. Freeze and paste.

**3.2 Criteria v2** (tightening-only, committed before cool-off ends): same six thresholds, plus (a) OOS PF is **net at 1× friction** — same basis as the in-sample 1.30; (b) run pinned to the frozen config hash from 3.1; (c) criterion 3 marked *redundant — subsumed by criterion 2 — retained for transparency*.
*Done when:* v2 block pasted with its commit hash and a one-line diff vs v1.

## Phase 4 — Artifact hygiene *(parallel, any time before Phase 6)*

**4.1** `sha256` + line count for `trade_log_insample.csv` and `kill_log.csv`.
**4.2** Gate 2 DNA check — paste the retired-bot comparison output.

## Phase 5 — Dataset freeze (only after download completes)

**5.1** Download-completion proof (rule 7 — file count or downloader exit log, not an assertion).
**5.2** Freeze dataset: manifest + hash.
**5.3** Re-run the **frozen** validator (Phase 2 hash) on the OOS slice. Paste output. **Preregistered kill criterion for this step:** if it REJECTs, the run does not proceed and the validator does **not** get patched — stop, report, treat as a new process bug. `ASSUMPTION:` a REJECT here is far more likely to be a pipeline fault than a data fault, since the same validator cleared the in-sample slice.

## Phase 6 — Run (only when Phases 1–5 all checkmarked and cool-off expired)

**6.1** Verify cool-off elapsed, anchored to the **corrected** clock from 1.2.
**6.2** `python run_h1.py ... --phase oos` with frozen everything. Paste raw output + full OOS trade log.
**6.3** Apply criteria v2 mechanically — verdict straight off the table, no interpretation.
**6.4** Report ends STATE / GATE / NEXT DECISION.

---

**Definition of done for this work order:** every item has a pasted artifact or an explicit written decision; OOS verdict logged in `kill_log.csv` (append-only) whatever it is.

**STATE:** Work order issued; awaiting commit hash of this file as its own preregistration artifact. Phases 1–4 are same-day executable; Phases 5–6 gated on them.
**GATE:** Owner ruling on 1.4 branch (forward-extend vs accept INSUFFICIENT) — only needed if manifest implies n < 50, but the *contingency* wording above counts as preregistered either way.
**NEXT DECISION:** Execute Phase 1 now; nothing downstream moves until 1.1–1.4 are pasted.
