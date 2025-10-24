# Phase 1 Day 2 — Determinism Check Protocol

**Date**: Oct 23, 2025
**Objective**: Verify 100% determinism on 100-bar fixed slice
**Owner**: Cascade (Lead Developer)
**Approver**: Terry (Systems Architect)

---

## Pre-Execution Freeze (Critical)

### Step 1: Git Tag Baseline
```bash
git tag phase1-day2-baseline
git log --oneline -1
```

**Purpose**: Lock repo state before determinism test. If any mismatch found, revert to this tag.

### Step 2: Re-emit Config Fingerprint
```bash
python scripts/generate_config_fingerprint.py
# Output: artifacts/config_fingerprint.txt (SHA256 hashes)
```

**Verify**:
- structure.json hash matches Day 1 (no config drift)
- system.json hash matches Day 1
- broker_symbols.json hash matches Day 1

**If mismatch**: Investigate immediately. Do NOT proceed with determinism test.

### Step 3: Confirm Freeze Points
- [ ] No config changes since Day 1
- [ ] No threshold tuning
- [ ] No feature flag changes
- [ ] RNG seed = 42 (hardcoded)
- [ ] Same 100-bar slice (bars 0-99)
- [ ] Same EURUSD M15 synthetic data generator

---

## Determinism Test Execution

### Run 1: First Pass
```bash
python scripts/determinism_check.py --bars 100 --seed 42 --output run1.json
```

**Expected Output**:
- `run1.json`: 100 decisions (or 0 if synthetic data is flat)
- Execution time: ~2-5 seconds
- No errors

### Run 2: Second Pass (Identical)
```bash
python scripts/determinism_check.py --bars 100 --seed 42 --output run2.json
```

**Expected Output**:
- `run2.json`: 100 decisions (identical to run1.json)
- Execution time: ~2-5 seconds
- No errors

### Comparison
```bash
python scripts/compare_determinism.py run1.json run2.json --output artifacts/determinism_diff.txt
```

---

## Determinism Diff Report Format

**File**: `artifacts/determinism_diff.txt`

```
================================================================================
DETERMINISM CHECK RESULTS — Phase 1 Day 2
================================================================================

EXECUTION METADATA
  Date: 2025-10-23
  Bars: 100 (slice 0-99)
  Symbol: EURUSD
  Timeframe: M15
  Seed: 42
  Executor Mode: dry-run

SLICE FINGERPRINT
  First timestamp: 2025-10-22 12:00:00 UTC
  Last timestamp: 2025-10-22 13:45:00 UTC
  Slice hash (SHA256): [hash of all 100 timestamps]
  
CONFIG FINGERPRINT
  structure.json: [SHA256 hash]
  system.json: [SHA256 hash]
  broker_symbols.json: [SHA256 hash]
  Config matches Day 1: YES ✅

RNG SEED
  Seed: 42
  Generator: Python random (deterministic)
  
================================================================================
COMPARISON RESULTS
================================================================================

Run 1 Decisions: [N]
Run 2 Decisions: [N]
Count Match: YES ✅

Decision-by-Decision Comparison:
  Total decisions: [N]
  Identical: [N]
  Mismatches: 0 ✅

FIELD-LEVEL VERIFICATION
  Structure IDs: 100% match ✅
  Composite scores: 100% match ✅
  Entry prices: 100% match ✅
  Stop loss: 100% match ✅
  Take profit: 100% match ✅
  Risk/reward: 100% match ✅

================================================================================
VERDICT
================================================================================

Determinism Status: 100% MATCH ✅
Replay-Safe: YES ✅
Ready for Phase 1.5: YES ✅

First mismatch (if any): None
Config drift detected: NO ✅
Seed verified: YES (42) ✅

================================================================================
DECISION
================================================================================

✅ PASS: Determinism verified. Proceed to Days 3-5 steady-state monitoring.
```

---

## Artifacts to Generate

### 1. Determinism Diff
**File**: `artifacts/determinism_diff.txt`
- Header: slice_fingerprint, config_fingerprint, rng_seed
- Body: run1 vs run2 comparison
- Verdict: 100% match or first mismatch index

### 2. Daily Logs Bundle
**File**: `artifacts/daily_logs_bundle_DAY_2.tar.gz`
```bash
tar -czf artifacts/daily_logs_bundle_DAY_2.tar.gz \
  logs/gate_eval.jsonl \
  logs/decision.jsonl \
  logs/hourly_summary.jsonl \
  logs/dry_run_summary.jsonl
```

### 3. Daily Summary
**File**: `artifacts/daily_summary_DAY_2.json`

```json
{
  "date": "2025-10-23",
  "day": 2,
  "phase": "Phase 1 - Determinism Check",
  "execution_summary": {
    "status": "SUCCESS",
    "bars_processed": 100,
    "decisions_generated": 0,
    "validation_errors": 0,
    "executor_mode": "dry-run"
  },
  "determinism": {
    "run1_decisions": 0,
    "run2_decisions": 0,
    "count_match": true,
    "decisions_match": true,
    "mismatches": 0,
    "verdict": "100% MATCH"
  },
  "metrics": {
    "pass_rate_percent": 0.0,
    "rr_compliance_percent": "N/A",
    "validation_error_count": 0,
    "execution_results_count": 0
  },
  "config_fingerprint": {
    "structure_json": "[SHA256]",
    "system_json": "[SHA256]",
    "broker_symbols_json": "[SHA256]",
    "matches_day_1": true
  },
  "health_signals": {
    "gate_eval_lines": 100,
    "bars_processed": 100,
    "lines_match_bars": true,
    "validation_errors": 0,
    "pass_rate_regime": "0-5% (synthetic)"
  },
  "issues_blockers": [],
  "notes": "Day 2: Determinism verified (100% match on 100-bar replay). Config fingerprint matches Day 1. Ready for Days 3-5 steady-state monitoring.",
  "next_action": "Days 3-5: Continue daily 1000-bar dry-runs. Monitor health signals."
}
```

---

## Health Signal Checks (Day 2)

### Check 1: Gate Eval Lines ≈ Bars Processed
```
Expected: gate_eval.jsonl lines = 100 (one per bar)
Actual: [count]
Status: ✅ PASS
```

### Check 2: Validation Errors = 0
```
Expected: 0
Actual: [count]
Status: ✅ PASS
```

### Check 3: Pass-Rate in Synthetic Regime
```
Expected: 0-5% (synthetic data)
Actual: 0.0%
Status: ✅ PASS
```

---

## Failure Scenarios

### Scenario A: Mismatch Found
**Action**:
1. Capture first differing decision index
2. Dump both JSON objects for that index
3. Check config_fingerprint.txt (rule out drift)
4. Investigate:
   - RNG seed not 42?
   - Config changed mid-week?
   - Detector logic non-deterministic?
5. If blocker: Revert to `phase1-day2-baseline` tag
6. Fix issue and re-run

### Scenario B: Config Drift Detected
**Action**:
1. Compare Day 1 and Day 2 config fingerprints
2. If different: Investigate what changed
3. Revert to Day 1 config
4. Re-run determinism test
5. Document blocker

### Scenario C: Validation Errors > 0
**Action**:
1. Investigate executor validation failures
2. Check broker_symbols.json (all fields present?)
3. Review error logs
4. Fix and re-run

---

## Success Criteria (Day 2)

| Criterion | Target | Status |
|-----------|--------|--------|
| Determinism | 100% match | ⏳ In progress |
| Config drift | None | ⏳ In progress |
| Validation errors | 0 | ⏳ In progress |
| Gate eval lines | ≈ 100 | ⏳ In progress |
| Pass-rate | 0-5% | ⏳ In progress |
| Artifacts | 3 files | ⏳ In progress |

**All must be ✅ to proceed to Days 3-5**

---

## EOD Checklist (Day 2)

- [ ] Run determinism check (2 passes)
- [ ] Generate determinism_diff.txt
- [ ] Verify 100% match (or capture first mismatch)
- [ ] Re-emit config_fingerprint.txt
- [ ] Verify config matches Day 1
- [ ] Create daily_summary_DAY_2.json
- [ ] Package logs → daily_logs_bundle_DAY_2.tar.gz
- [ ] Check all 3 health signals
- [ ] Post EOD report in chat

---

## EOD Report Template

```
✅ Phase 1 Day 2 — Determinism Check Complete

Determinism: 100% MATCH ✅
Config drift: None ✅
Validation errors: 0 ✅
Health signals: All nominal ✅

Artifacts:
  - artifacts/determinism_diff.txt ✅
  - artifacts/daily_logs_bundle_DAY_2.tar.gz ✅
  - artifacts/daily_summary_DAY_2.json ✅

Ready for Days 3-5 steady-state monitoring.
```

---

## Freeze Points Summary

**Before Day 2 Run**:
- ✅ Git tag: `phase1-day2-baseline`
- ✅ Config fingerprint re-emitted
- ✅ No config changes allowed
- ✅ RNG seed = 42 (hardcoded)
- ✅ Same 100-bar slice (bars 0-99)

**During Day 2 Run**:
- ✅ Run 1: 100 bars, seed 42
- ✅ Run 2: 100 bars, seed 42 (identical)
- ✅ Compare: 100% match expected

**After Day 2 Run**:
- ✅ Determinism verified or blocker captured
- ✅ Config drift checked
- ✅ Ready for Days 3-5 or backout

---

**Phase 1 Day 2 — Determinism Protocol Ready**
