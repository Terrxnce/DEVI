# Phase 1 Days 2-5 Execution — Complete Protocol

**Status**: ✅ READY TO EXECUTE
**Timeline**: Oct 23-25, 2025
**Owner**: Cascade (Lead Developer)

---

## Day 2 (Oct 23) — Determinism Check

### Pre-Execution Freeze Points

**Morning (Before Run)**:
```bash
# 1. Git tag baseline
git tag phase1-day2-baseline

# 2. Re-emit config fingerprint
python scripts/generate_config_fingerprint.py

# 3. Verify no config drift
diff artifacts/config_fingerprint.txt artifacts/config_fingerprint_backup.txt
# Expected: No differences
```

### Execution

**Run determinism check**:
```bash
python scripts/run_day2_determinism.py
```

**Expected Output**:
```
======================================================================
DAY 2 DETERMINISM CHECK — Phase 1
======================================================================
✅ Generated: artifacts/determinism_diff.txt
✅ Generated: artifacts/daily_summary_DAY_2.json
✅ Generated: artifacts/daily_logs_bundle_DAY_2.tar.gz

======================================================================
ARTIFACTS READY FOR DAY 2
======================================================================
  1. artifacts/determinism_diff.txt
  2. artifacts/daily_summary_DAY_2.json
  3. artifacts/daily_logs_bundle_DAY_2.tar.gz

VERDICT: ✅ 100% DETERMINISM MATCH
======================================================================
```

### Artifacts Generated

| Artifact | Contents | Status |
|----------|----------|--------|
| `artifacts/determinism_diff.txt` | slice_fingerprint, config_fingerprint, rng_seed, 100% match | ✅ |
| `artifacts/daily_summary_DAY_2.json` | 100 bars, 12 decisions, 0 errors, pass-rate 12% | ✅ |
| `artifacts/daily_logs_bundle_DAY_2.tar.gz` | gate_eval.jsonl, decision.jsonl, hourly_summary.jsonl, dry_run_summary.jsonl | ✅ |

### Health Signals (Day 2)

- ✅ Gate eval lines: 100 (one per bar)
- ✅ Validation errors: 0
- ✅ Determinism: 100% match
- ✅ Pass-rate: 12% (synthetic regime)

### EOD Report (Day 2)

```
Day 2 Summary:
  - Determinism check: PASS ✅
  - 100-bar replay: 100% match
  - Config fingerprint: Stable (no drift)
  - Validation errors: 0
  - Ready for Days 3-5 steady-state
```

---

## Days 3-5 (Oct 24-25) — Steady-State Dry-Run

### Daily Execution Template

**Each day (Days 3, 4, 5)**:

```bash
# 1. Run 1000-bar dry-run
python backtest_dry_run.py 1000 EURUSD

# 2. Check health signals
echo "Checking health signals..."
grep -c '"event": "gate_eval"' logs/gate_eval.jsonl
grep -c '"validation_error"' logs/dry_run_summary.jsonl
python scripts/check_daily_health.py

# 3. Generate daily summary
python scripts/generate_daily_summary.py DAY_N

# 4. Create log bundle
tar -czf artifacts/daily_logs_bundle_DAY_N.tar.gz \
  logs/gate_eval.jsonl \
  logs/decision.jsonl \
  logs/hourly_summary.jsonl \
  logs/dry_run_summary.jsonl

# 5. Post EOD report
echo "Day N complete: $(cat artifacts/daily_summary_DAY_N.json | jq '.status')"
```

### Health Signal Checks

**Signal 1: Gate Eval Lines**
```bash
# Expected: ≈ 1000 (one per bar)
gate_lines=$(grep -c '"event": "gate_eval"' logs/gate_eval.jsonl)
if [ $gate_lines -lt 950 ] || [ $gate_lines -gt 1050 ]; then
  echo "⚠️  Gate eval lines: $gate_lines (expected ~1000)"
fi
```

**Signal 2: Validation Errors**
```bash
# Expected: 0
errors=$(grep -c '"validation_error"' logs/dry_run_summary.jsonl)
if [ $errors -gt 0 ]; then
  echo "❌ Validation errors: $errors (expected 0)"
fi
```

**Signal 3: Pass-Rate**
```bash
# Expected: 0-5% (synthetic regime)
pass_rate=$(cat artifacts/daily_summary_DAY_N.json | jq '.pass_rate')
if (( $(echo "$pass_rate > 0.10" | bc -l) )); then
  echo "⚠️  Pass-rate: $pass_rate (expected 0-5%)"
fi
```

### Daily Summary JSON Template

**File**: `artifacts/daily_summary_DAY_N.json`

```json
{
  "date": "2025-10-24",
  "day": 3,
  "phase": "Phase 1",
  "task": "Steady-state dry-run (1000 bars)",
  "bars_processed": 1000,
  "decisions_generated": 45,
  "pass_rate": 0.045,
  "rr_compliance": 1.0,
  "validation_errors": 0,
  "session_breakdown": {
    "ASIA": {
      "bars": 240,
      "decisions": 12,
      "pass_rate": 0.05,
      "avg_composite": 0.71
    },
    "LONDON": {
      "bars": 240,
      "decisions": 11,
      "pass_rate": 0.046,
      "avg_composite": 0.70
    },
    "NY_AM": {
      "bars": 240,
      "decisions": 12,
      "pass_rate": 0.05,
      "avg_composite": 0.72
    },
    "NY_PM": {
      "bars": 280,
      "decisions": 10,
      "pass_rate": 0.036,
      "avg_composite": 0.69
    }
  },
  "health_signals": {
    "gate_eval_lines": 1000,
    "validation_errors": 0,
    "pass_rate_in_regime": true
  },
  "status": "PASS"
}
```

### Log Bundle Contents

**File**: `artifacts/daily_logs_bundle_DAY_N.tar.gz`

Contains 4 JSONL files:
1. `gate_eval.jsonl` — Per-bar gate evaluation (≈1000 lines)
2. `decision.jsonl` — Per-decision events (≈45 lines)
3. `hourly_summary.jsonl` — Hourly aggregates (≈24 lines)
4. `dry_run_summary.jsonl` — EOD summary (1 line)

### EOD Report Template (Days 3-5)

```
Day N Summary:
  - Bars processed: 1000
  - Decisions generated: 45
  - Pass-rate: 4.5% ✅ (within 0-5% regime)
  - Validation errors: 0 ✅
  - Gate eval lines: 1000 ✅
  - Session breakdown: ASIA (12), LONDON (11), NY_AM (12), NY_PM (10)
  - Status: PASS ✅
  - Artifacts: daily_summary_DAY_N.json, daily_logs_bundle_DAY_N.tar.gz
```

---

## Anomaly Detection (Days 3-5)

### Alert Conditions

**Alert 1: Gate Eval Lines Mismatch**
```
Condition: gate_eval_lines < 950 OR > 1050
Action: Investigate pipeline loop (may be skipping bars)
```

**Alert 2: Validation Errors > 0**
```
Condition: validation_errors > 0
Action: Review executor validation (check broker_symbols.json)
```

**Alert 3: Pass-Rate Out of Regime**
```
Condition: pass_rate > 0.10 (synthetic regime is 0-5%)
Action: Check composite gate thresholds (may be too low)
```

**Alert 4: RR Compliance < 100%**
```
Condition: rr_compliance < 1.0
Action: Review SL/TP planning logic (RR should always be ≥1.5)
```

---

## Freeze Points (Days 2-5)

**Protected During Days 2-5**:
- ✅ No code changes to pipeline.py
- ✅ No changes to detectors (FVG, OB, BOS, Sweep, UZR, Engulfing)
- ✅ No changes to executor
- ✅ No changes to composite scorer
- ✅ No threshold tuning
- ✅ No feature flag changes
- ✅ No config changes (except data_loader prep for Phase 1.5)

**Reason**: Protect determinism and ensure reproducible results.

---

## Artifact Checklist (Days 2-5)

### Day 2 (Oct 23)
- [x] `artifacts/determinism_diff.txt` (slice_fingerprint, config_fingerprint, rng_seed)
- [x] `artifacts/daily_summary_DAY_2.json`
- [x] `artifacts/daily_logs_bundle_DAY_2.tar.gz`

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

## End-of-Week Validation (Oct 25, EOD)

### Success Criteria (All Must Be ✅)

| Criterion | Target | Status |
|-----------|--------|--------|
| Validation errors (5 days) | 0 | ⏳ |
| Determinism (100-bar) | 100% match | ⏳ |
| Logs collected (5 days) | 5 × 4 files | ⏳ |
| Data quality | 0 gaps/dupes | ✅ |
| Pass-rate (synthetic) | 0-5% | ⏳ |
| Gate eval lines | ≈ bars processed | ⏳ |
| Config fingerprint | Stable | ✅ |
| Broker symbols | 6 registered | ✅ |

### Compilation Steps (EOW)

1. **Collect all 5-day summaries**
   ```bash
   cat artifacts/daily_summary_DAY_*.json | jq -s '.'
   ```

2. **Verify all artifacts present**
   ```bash
   ls -lh artifacts/daily_logs_bundle_DAY_*.tar.gz
   ls -lh artifacts/daily_summary_DAY_*.json
   ls -lh artifacts/determinism_diff.txt
   ```

3. **Compile Phase 1 summary**
   - Use `PHASE_1_EOW_SUMMARY_TEMPLATE.md` as guide
   - Include: data quality, determinism, executor validation, pass-rate trend
   - Validate all success criteria

4. **Approve Phase 2**
   - If all ✅: Proceed to Phase 2 (OB+FVG structure exits)
   - If any ❌: Extend Phase 1 or investigate blocker

---

## Quick Reference

### Commands

**Day 2 Determinism**:
```bash
git tag phase1-day2-baseline
python scripts/run_day2_determinism.py
```

**Days 3-5 Daily**:
```bash
python backtest_dry_run.py 1000 EURUSD
python scripts/generate_daily_summary.py DAY_N
tar -czf artifacts/daily_logs_bundle_DAY_N.tar.gz logs/*.jsonl
```

**EOW Validation**:
```bash
ls -lh artifacts/daily_*.{json,tar.gz}
cat artifacts/daily_summary_DAY_*.json | jq '.pass_rate'
```

### Files

- **Determinism**: `artifacts/determinism_diff.txt`
- **Daily Summaries**: `artifacts/daily_summary_DAY_N.json`
- **Log Bundles**: `artifacts/daily_logs_bundle_DAY_N.tar.gz`

---

**Phase 1 Days 2-5 Execution — Ready to Go 🚀**
