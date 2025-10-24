# Phase 1 Execution Ready — Days 2-5 Complete Protocol

**Status**: ✅ ALL SYSTEMS GO
**Date**: Oct 22, 2025, 2:39 PM UTC+01:00
**Timeline**: Oct 23-25, 2025
**Owner**: Cascade (Lead Developer)

---

## Quick Start

### Day 2 (Oct 23) — Determinism Check

```bash
# Morning: Freeze baseline
git tag phase1-day2-baseline
python scripts/generate_config_fingerprint.py

# Execute determinism check
python scripts/run_day2_determinism.py

# Expected: ✅ 100% DETERMINISM MATCH
```

**Artifacts**:
- `artifacts/determinism_diff.txt` (slice_fingerprint, config_fingerprint, rng_seed)
- `artifacts/daily_summary_DAY_2.json`
- `artifacts/daily_logs_bundle_DAY_2.tar.gz`

---

### Days 3-5 (Oct 24-25) — Steady-State Dry-Run

**Each day**:
```bash
# Run 1000-bar dry-run
python backtest_dry_run.py 1000 EURUSD

# Generate daily summary
python scripts/generate_daily_summary.py DAY_N

# Create log bundle
tar -czf artifacts/daily_logs_bundle_DAY_N.tar.gz logs/*.jsonl
```

**Health checks** (should all pass):
- Gate eval lines: ≈ 1000 ✅
- Validation errors: 0 ✅
- Pass-rate: 0-5% ✅

---

### EOW (Oct 25) — Validation & Approval

```bash
# Verify all artifacts
ls -lh artifacts/daily_*.{json,tar.gz}

# Check pass-rates
cat artifacts/daily_summary_DAY_*.json | jq '.pass_rate'

# Compile Phase 1 summary (use template)
# Approve Phase 2 (if all ✅)
```

---

## Determinism Check Details

### What It Does

Runs the same 100-bar slice twice with fixed seed (42) and compares:
- Structure IDs
- Composite tech scores
- Entry/SL/TP prices
- Risk-reward ratios

### Expected Output

```
======================================================================
DETERMINISM CHECK RESULTS — Phase 1 Day 2
======================================================================

FINGERPRINTS
----------------------------------------------------------------------
slice_fingerprint (100 bars):  [SHA256 hash]
config_fingerprint (SHA256):   [SHA256 hash]
rng_seed:                      42

SUMMARY
----------------------------------------------------------------------
Run 1 Decisions: 12
Run 2 Decisions: 12
Count Match: YES
Decisions Match: YES
Mismatches: 0

VERDICT: ✅ 100% DETERMINISM MATCH
```

### Failure Scenarios

**If mismatch detected**:
1. Check config_fingerprint.txt (rule out drift)
2. Investigate: RNG seed? Config changed? Detector logic?
3. Revert to `phase1-day2-baseline` tag
4. Fix and re-run

---

## Daily Execution Template

### Morning (Each Day)

```bash
# 1. Run dry-run
python backtest_dry_run.py 1000 EURUSD

# 2. Check health signals
echo "Gate eval lines:"
grep -c '"event": "gate_eval"' logs/gate_eval.jsonl

echo "Validation errors:"
grep -c '"validation_error"' logs/dry_run_summary.jsonl

# 3. Generate summary
python scripts/generate_daily_summary.py DAY_N

# 4. Create bundle
tar -czf artifacts/daily_logs_bundle_DAY_N.tar.gz logs/*.jsonl
```

### Expected Results

```json
{
  "date": "2025-10-24",
  "day": 3,
  "bars_processed": 1000,
  "decisions_generated": 45,
  "pass_rate": 0.045,
  "validation_errors": 0,
  "status": "PASS"
}
```

---

## Artifact Checklist

### Day 2 (Oct 23)
- [ ] `artifacts/determinism_diff.txt`
- [ ] `artifacts/daily_summary_DAY_2.json`
- [ ] `artifacts/daily_logs_bundle_DAY_2.tar.gz`

### Day 3 (Oct 24)
- [ ] `artifacts/daily_summary_DAY_3.json`
- [ ] `artifacts/daily_logs_bundle_DAY_3.tar.gz`

### Day 4 (Oct 24)
- [ ] `artifacts/daily_summary_DAY_4.json`
- [ ] `artifacts/daily_logs_bundle_DAY_4.tar.gz`

### Day 5 (Oct 25)
- [ ] `artifacts/daily_summary_DAY_5.json`
- [ ] `artifacts/daily_logs_bundle_DAY_5.tar.gz`

**Total**: 9 artifacts (1 diff + 8 daily)

---

## Success Criteria (All Must Be ✅)

| Criterion | Target | Check |
|-----------|--------|-------|
| Validation errors (5 days) | 0 | `grep -c "validation_error"` |
| Determinism (100-bar) | 100% match | `cat artifacts/determinism_diff.txt` |
| Logs collected (5 days) | 5 × 4 files | `ls artifacts/daily_logs_bundle_*` |
| Pass-rate (synthetic) | 0-5% | `jq '.pass_rate' artifacts/daily_summary_DAY_*.json` |
| Gate eval lines | ≈ bars | `grep -c "gate_eval"` |
| Config fingerprint | Stable | `diff artifacts/config_fingerprint.txt` |

---

## Freeze Points (Days 2-5)

**Protected**:
- ✅ No code changes to pipeline.py
- ✅ No changes to detectors
- ✅ No changes to executor
- ✅ No changes to composite scorer
- ✅ No threshold tuning
- ✅ No feature flag changes

**Allowed**:
- ✅ Add data_loader config section (Phase 1.5 prep)
- ✅ Create new validation scripts
- ✅ Create new summary generators

---

## Phase 1.5 Light Prep (EOW, Oct 25)

### Tasks (30 min, no code changes)

- [ ] Verify DataLoader switch exists
- [ ] Verify pull_mt5_history.py interface
- [ ] Add data_loader config section to system.json
- [ ] Create validate_mt5_continuity.py
- [ ] Create canary_job.py (optional)

### Next Week (Oct 28-31)

**Monday**: Pull 1000 M15 bars from real MT5
**Tuesday**: Switch DataLoader to MT5 source
**Wed-Fri**: Re-run 5-day dry-run with real data
**Friday EOD**: Phase 1.5 summary + ready for Phase 2

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/run_day2_determinism.py` | Day 2 determinism check |
| `scripts/generate_daily_summary.py` | Daily summary generator |
| `PHASE_1_DAYS_2_5_EXECUTION.md` | Detailed protocol |
| `PHASE_1_5_LIGHT_PREP_CHECKLIST.md` | Phase 1.5 prep |
| `PHASE_1_COMPLETE_FRAMEWORK.md` | Complete overview |

---

## Troubleshooting

### Issue: Gate Eval Lines < 950

**Cause**: Pipeline loop may be skipping bars
**Action**: Check pipeline.py for bar iteration logic

### Issue: Validation Errors > 0

**Cause**: Executor validation failed
**Action**: Review executor logs, check broker_symbols.json

### Issue: Pass-Rate > 10%

**Cause**: Composite gate threshold too low
**Action**: Check composite scorer thresholds

### Issue: Determinism Mismatch

**Cause**: Config drift or RNG seed issue
**Action**: Revert to `phase1-day2-baseline` tag, investigate

---

## EOW Approval Checklist

**Before Phase 2 Approval**:
- [ ] All 5 days complete
- [ ] All 9 artifacts present
- [ ] 0 validation errors across 5 days
- [ ] Determinism 100% on 100-bar slice
- [ ] Pass-rate within 0-5% regime
- [ ] Config fingerprint stable
- [ ] All logs collected and analyzed

**If all ✅**: Approve Phase 2 (OB+FVG structure exits)
**If any ❌**: Extend Phase 1 or investigate blocker

---

## Phase 2 Locked Specs (Ready Next Week)

**OB + FVG Exits** (Week 2):
- SL just beyond zone edge ± sl_atr_buffer
- TP to opposite edge or origin extension
- Broker clamp + RR re-check (reject if RR < 1.5)
- Log exit_reason: "structure" | "structure+atr_buffer" | "atr_fallback"
- Target: ≥95% "structure" exits

**Feature Flag**:
```json
{
  "sltp_planning": {
    "use_structure_exits": false,  // Phase 1
    "structure_exit_types": ["order_block", "fair_value_gap"],
    "atr_fallback_enabled": true
  }
}
```

---

## Status Summary

✅ **Day 1**: Complete
🟡 **Day 2**: Ready (determinism check)
🟡 **Days 3-5**: Ready (daily execution)
🟡 **EOW**: Ready (validation & approval)
🟡 **Phase 1.5**: Ready (light prep)

**Phase 1 is 100% ready for execution.**

---

**Start Day 2 execution now. All protocols, scripts, and templates are ready. 🚀**
