# Phase 1 Days 3-5 — Steady-State Monitoring Protocol

**Dates**: Oct 24-25, 2025
**Objective**: Daily 1000-bar dry-runs + health signal monitoring
**Owner**: Cascade (Lead Developer)
**Approver**: Terry (Systems Architect)

---

## Daily Execution (Days 3, 4, 5)

### Morning: Run 1000-Bar Dry-Run

```bash
python backtest_dry_run.py 1000 EURUSD
```

**Expected Output**:
- Bars processed: 1000
- Decisions generated: 0-5 (synthetic data, conservative gate)
- Validation errors: 0
- Log file: `logs/dry_run_backtest_YYYYMMDD_HHMMSS.json`
- Execution time: ~5-10 seconds

### Midday: Health Signal Checks

**Check 1: Gate Eval Lines ≈ Bars Processed**
```bash
wc -l logs/gate_eval.jsonl
# Expected: ~1000 lines (one per bar)
```

**Check 2: Validation Errors = 0**
```bash
grep -c "validation_error" logs/dry_run_summary.jsonl
# Expected: 0
```

**Check 3: Pass-Rate in Synthetic Regime**
```bash
# Extract pass_rate from daily_summary_DAY_N.json
# Expected: 0-5% (0% is acceptable for synthetic)
```

### EOD: Package & Report

**1. Create Daily Summary**
```bash
# Use template below
# File: artifacts/daily_summary_DAY_N.json
```

**2. Package Logs**
```bash
tar -czf artifacts/daily_logs_bundle_DAY_N.tar.gz \
  logs/gate_eval.jsonl \
  logs/decision.jsonl \
  logs/hourly_summary.jsonl \
  logs/dry_run_summary.jsonl
```

**3. Post EOD Report**
```
✅ Phase 1 Day N — Steady-State Monitoring

Bars processed: 1000 ✅
Validation errors: 0 ✅
Pass-rate: 0.0% (synthetic regime) ✅
Health signals: All nominal ✅

Artifacts:
  - artifacts/daily_summary_DAY_N.json ✅
  - artifacts/daily_logs_bundle_DAY_N.tar.gz ✅
```

---

## Daily Summary Template (DAY_N.json)

```json
{
  "date": "2025-10-24",
  "day": 3,
  "phase": "Phase 1 - Steady-State Monitoring",
  "execution_summary": {
    "status": "SUCCESS",
    "bars_processed": 1000,
    "decisions_generated": 0,
    "validation_errors": 0,
    "executor_mode": "dry-run"
  },
  "metrics": {
    "pass_rate_percent": 0.0,
    "rr_compliance_percent": "N/A",
    "validation_error_count": 0,
    "execution_results_count": 0
  },
  "session_breakdown": {
    "ASIA": {
      "bars": 250,
      "decisions": 0,
      "pass_rate": 0.0,
      "avg_composite_score": 0.0
    },
    "LONDON": {
      "bars": 250,
      "decisions": 0,
      "pass_rate": 0.0,
      "avg_composite_score": 0.0
    },
    "NY_AM": {
      "bars": 250,
      "decisions": 0,
      "pass_rate": 0.0,
      "avg_composite_score": 0.0
    },
    "NY_PM": {
      "bars": 250,
      "decisions": 0,
      "pass_rate": 0.0,
      "avg_composite_score": 0.0
    }
  },
  "data_quality": {
    "symbol": "EURUSD",
    "timeframe": "M15",
    "total_bars": 1000,
    "gaps": 0,
    "duplicates": 0,
    "ohlc_validity_percent": 100.0,
    "timestamp_continuity": "100% (15-min intervals)"
  },
  "broker_symbols": {
    "registered": 6,
    "symbols": ["AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDJPY", "XAUUSD"],
    "status": "OK"
  },
  "health_signals": {
    "gate_eval_lines": 1000,
    "bars_processed": 1000,
    "lines_match_bars": true,
    "validation_errors": 0,
    "pass_rate_regime": "0-5% (synthetic)"
  },
  "artifacts": {
    "log_file": "logs/dry_run_backtest_20251024_HHMMSS.json",
    "gate_eval_jsonl": "logs/gate_eval.jsonl",
    "decision_jsonl": "logs/decision.jsonl",
    "hourly_summary_jsonl": "logs/hourly_summary.jsonl",
    "dry_run_summary_jsonl": "logs/dry_run_summary.jsonl"
  },
  "issues_blockers": [],
  "notes": "Day 3: Steady-state validation. Pipeline operational. All health signals nominal.",
  "next_action": "Continue daily monitoring. Days 4-5 follow same pattern."
}
```

---

## Health Signal Monitoring

### Signal 1: Gate Eval Lines ≈ Bars Processed

**What to Check**:
```
Expected: gate_eval.jsonl lines ≈ 1000 (one per bar)
Actual: [count from wc -l]
Status: ✅ PASS or ❌ FAIL
```

**If Mismatch**:
- Check pipeline bar processing loop
- Verify logging is enabled
- Review composite scorer initialization
- Investigate: Are some bars skipped?

**Action**:
- If lines < 900: Investigate blocker
- If lines = 1000: ✅ PASS

### Signal 2: Validation Errors = 0

**What to Check**:
```
Expected: 0 validation errors
Actual: [count from grep]
Status: ✅ PASS or ❌ FAIL
```

**If Errors Found**:
- Check broker_symbols.json (all fields present?)
- Verify executor initialization
- Review order validation logic
- Investigate: Which validation failed?

**Action**:
- If errors = 0: ✅ PASS
- If errors > 0: Investigate immediately

### Signal 3: Pass-Rate in Synthetic Regime

**What to Check**:
```
Expected: 0-5% (synthetic data, conservative gate)
Actual: [pass_rate from daily_summary]
Status: ✅ PASS or ⚠️ WARN
```

**If Pass-Rate Spikes**:
- Check composite gate thresholds
- Verify EMA alignment scoring
- Review zone proximity calculation
- Investigate: Did config change?

**Action**:
- If 0-5%: ✅ PASS
- If 5-10%: ⚠️ WARN (monitor)
- If > 10%: ❌ FAIL (investigate)

---

## Anomaly Detection

### Anomaly A: Gate Eval Lines Drop Suddenly
**Symptom**: Day 3 = 1000 lines, Day 4 = 800 lines
**Cause**: Pipeline bar processing loop issue
**Action**: Check for exceptions in logs, investigate blocker

### Anomaly B: Validation Errors Appear
**Symptom**: Day 3 = 0 errors, Day 4 = 5 errors
**Cause**: Executor validation failure
**Action**: Check broker_symbols.json, verify executor state

### Anomaly C: Pass-Rate Spikes
**Symptom**: Day 3 = 0%, Day 4 = 8%
**Cause**: Composite gate too loose or detector drift
**Action**: Check config fingerprint, verify no changes

---

## EOD Checklist (Each Day)

- [ ] Run `python backtest_dry_run.py 1000 EURUSD`
- [ ] Verify 0 validation errors
- [ ] Check gate_eval lines ≈ 1000
- [ ] Check pass-rate 0-5%
- [ ] Create `daily_summary_DAY_N.json`
- [ ] Create `daily_logs_bundle_DAY_N.tar.gz`
- [ ] Note any anomalies in issues_blockers
- [ ] Post EOD report in chat

---

## Status Indicators (Each Day)

| Signal | Expected | Action if Fail |
|--------|----------|----------------|
| Bars processed | 1000 | Check pipeline loop |
| Validation errors | 0 | Investigate executor |
| Gate eval lines | ≈1000 | Check logging |
| Pass-rate | 0-5% | Check composite gate |
| Broker symbols | 6 registered | Verify broker_symbols.json |

---

## Failure Scenarios

### Scenario A: Validation Errors > 0
**Action**:
1. Check executor logs for validation failures
2. Verify broker_symbols.json (all fields?)
3. Review order validation logic
4. Fix and re-run

### Scenario B: Gate Eval Lines < 900
**Action**:
1. Check pipeline bar processing loop
2. Verify logging is enabled
3. Review composite scorer initialization
4. Investigate: Are some bars skipped?

### Scenario C: Pass-Rate > 10%
**Action**:
1. Check composite gate thresholds
2. Verify EMA alignment scoring
3. Review zone proximity calculation
4. Investigate: Did config change?

---

## Success Criteria (Days 3-5)

| Criterion | Target | Status |
|-----------|--------|--------|
| Validation errors | 0 each day | ⏳ In progress |
| Gate eval lines | ≈1000 each day | ⏳ In progress |
| Pass-rate | 0-5% each day | ⏳ In progress |
| Logs collected | 3 days × 4 files | ⏳ In progress |
| Broker symbols | 6 registered | ✅ Verified |
| No anomalies | None | ⏳ In progress |

**All must be ✅ to pass Phase 1**

---

## Transition to EOW Summary (Oct 25)

**Morning (Oct 25)**:
1. Run final 1000-bar dry-run (Day 5)
2. Create daily_summary_DAY_5.json
3. Package daily_logs_bundle_DAY_5.tar.gz

**Afternoon (Oct 25)**:
1. Compile all 5-day results
2. Use `PHASE_1_EOW_SUMMARY_TEMPLATE.md` as guide
3. Validate all success criteria met
4. Prepare Phase 1 summary document

**EOD (Oct 25)**:
1. Post Phase 1 summary in chat
2. Confirm ready for Phase 2 approval
3. Prepare Phase 1.5 MT5 integration (next week)

---

## Next Phase

**Phase 1.5** (Week 2): MT5 Integration
- Pull 1000 bars per symbol from real MT5 feed
- Verify UTC continuity (0 gaps)
- Re-run 5-day dry-run with real data
- Verify determinism still holds

**Phase 2** (Week 2-3): Structure Exits
- Implement OB + FVG structure exits
- Set feature flag: `use_structure_exits = true`
- Validate RR ≥1.5 rejection rule
- Collect metrics: pass-rate, RR compliance, structure-exit %

---

**Phase 1 Days 3-5 — Steady-State Protocol Ready**
