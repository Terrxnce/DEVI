# Phase 1 Analysis Report — DEVI 2.0

**Date**: Oct 24, 2025
**Symbol/TF**: EURUSD M15
**Mode**: Dry-run

---

## Summary

- **Determinism (100 bars x2)**: PASS
  - Artifact: `artifacts/determinism_diff.txt`
  - Result: IDENTICAL (100 vs 100 decisions, no diffs)
- **Decision generation errors**: 0 (eliminated)
- **Latest run (CSV 300 bars)**:
  - Bars processed: 193
  - Decisions: 332
  - Executor results: 332
  - Pass-rate: 78.6% (261/332)
  - RR validation failures: 71 (all remaining failures are RR < 1.5)

---

## Detector Activity (latest run)

- OrderBlockDetector: seen=286, fired=29
- FairValueGapDetector: seen=286, fired=45
- SweepDetector: seen=150, fired=34
- UnifiedZoneRejectionDetector: seen=286, fired=151
- EngulfingDetector: seen=286, fired=2
- BreakOfStructureDetector: seen=0, fired=0

---

## Quality & Compliance

- **RR ≥ 1.5 compliance (executed)**: 100% (executor rejects below threshold)
- **Validation errors**: all due to RR < 1.5 (71 occurrences)
- **Decimal/float errors**: 0 across detectors

---

## Determinism Proof

- Command: `python backtest_dry_run.py 100 EURUSD` run twice
- Diff file: `artifacts/determinism_diff.txt`
- Outcome: identical decision sets

---

## Config Fingerprints (SHA256)

- File: `artifacts/config_fingerprint.txt`
- Includes: structure.json, system.json, scoring.json, sessions.json, sltp.json, indicators.json, guards.json, broker_symbols.json

---

## Notes on Scale Run (1–2k bars)

- Current CSV `infra/data/eurusd_m15_clean.csv` contains 300 bars.
- To complete the 1–2k bar scale test:
  1) Provide a larger CSV at the same path (≥2000 rows), or
  2) Allow switch to synthetic generator for 2000 bars (code change), or
  3) Point the loader to an alternate CSV path (minor CLI change).

---

## Recommendations (Phase 1 wrap-up)

- Provide 1–2k bar CSV for the scale run; re-run and archive results.
- Optional: Slightly bias SL/TP planning toward higher RR by increasing take-profit factor when feasible, or by filtering low-quality structures pre-execution via scoring (config-only change).

---

## Phase 2 Preparation (Flagged rollout plan)

- Introduce feature flag for structure-based exits (OB + FVG first):
```json
{
  "sltp_planning": {
    "use_structure_exits": false,
    "structure_exit_types": ["order_block", "fair_value_gap"],
    "atr_fallback_enabled": true,
    "min_rr_gate": 1.5
  }
}
```
- Behavior: If `use_structure_exits = true`, plan SL at zone edge ± buffer, TP to opposing edge; post-clamp RR gate applied; reject trade if RR < 1.5.
- Unit tests to add:
  - OB exit planning yields SL beyond zone edge and TP at opposing; RR gate enforced.
  - FVG exit planning analogous; ATR fallback used if opposing structure missing.
  - Post-clamp RR < 1.5 → decision rejected.

---

## Action Items

- Provide larger CSV for scale test or approve synthetic/CLI change.
- Approve Phase 2 flag addition and corresponding unit tests.
- Optional: Tune scoring thresholds to reduce RR failures pre-execution.

---

Prepared by: Cascade
