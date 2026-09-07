# Phase 1 — Correction (append-only, final)

## F1 Correction: Expected OOS n = ~58 (not ~99)

The original calculation used 2024's full-year bar count (6,240) as the divisor for the OOS slice, but OOS only spans 498 days (1.36 years). Correct calculation: 8,485 bars × (128/18,705) = **58.1 trades**.

**Commit**: `94faadb5f3c64064324a0a07926c0d66194520cb`
