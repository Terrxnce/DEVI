# Phase 1 Days 3-5 — Steady-State Monitoring Template

**Purpose**: Template for Days 3, 4, 5 daily summaries and health checks

---

## Daily Execution (Days 3-5)

### Each Day: Run 1000-bar dry-run

```bash
python backtest_dry_run.py 1000 EURUSD
```

### Expected Output
- Bars processed: 1000
- Decisions generated: 0-5 (synthetic data, conservative gate)
- Validation errors: 0
- Log file: `logs/dry_run_backtest_YYYYMMDD_HHMMSS.json`

---

## Health Signals to Watch (3 Quick Checks)

### 1. Gate Eval Line Count ≈ Bars Processed
```
Expected: gate_eval.jsonl lines ≈ 1000 (one per bar)
If mismatch: Check composite scorer initialization
```

### 2. Validation Errors Stay 0
```
Expected: validation_errors = 0 across all days
If > 0: Investigate executor validation logic
```

### 3. Pass-Rate Stays in Expected Regime
```
Expected: 0-5% on synthetic data (conservative composite gate)
If > 10%: Composite gate may be too loose
If < 0%: Expected (flat synthetic data)
```

---

## Daily Summary Template (DAY_N.json)

Use this structure for `artifacts/daily_summary_DAY_3.json`, `DAY_4.json`, `DAY_5.json`:

```json
{
  "date": "2025-10-24",
  "day": 3,
  "phase": "Phase 1 - Synthetic Data Validation",
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
  "artifacts": {
    "log_file": "logs/dry_run_backtest_20251024_HHMMSS.json",
    "gate_eval_jsonl": "logs/gate_eval.jsonl",
    "decision_jsonl": "logs/decision.jsonl",
    "hourly_summary_jsonl": "logs/hourly_summary.jsonl",
    "dry_run_summary_jsonl": "logs/dry_run_summary.jsonl"
  },
  "issues_blockers": [],
  "notes": "Day 3: Steady-state validation. Pipeline operational. All health signals nominal.",
  "next_action": "Continue daily monitoring. Prepare for determinism check on Day 2."
}
```

---

## Daily Logs Bundle (DAY_N.tar.gz)

Create tar.gz with 4 JSONL files:

```bash
# After each day's run, package logs:
tar -czf artifacts/daily_logs_bundle_DAY_3.tar.gz \
  logs/gate_eval.jsonl \
  logs/decision.jsonl \
  logs/hourly_summary.jsonl \
  logs/dry_run_summary.jsonl
```

---

## Anomaly Detection (If Needed)

### If Pass-Rate Spikes
- Check composite gate thresholds
- Verify EMA alignment scoring
- Review zone proximity calculation

### If Validation Errors Appear
- Check broker_symbols.json (all fields present?)
- Verify executor initialization
- Review order validation logic

### If Gate Eval Lines < Bars
- Check pipeline bar processing loop
- Verify logging is enabled
- Review composite scorer initialization

---

## EOD Checklist (Each Day)

- [ ] Run `python backtest_dry_run.py 1000 EURUSD`
- [ ] Verify 0 validation errors
- [ ] Create `daily_summary_DAY_N.json`
- [ ] Create `daily_logs_bundle_DAY_N.tar.gz`
- [ ] Check health signals (gate_eval lines, validation errors, pass-rate)
- [ ] Note any anomalies in issues_blockers
- [ ] Confirm all 4 JSONL files present in bundle

---

## Status Indicators

| Signal | Expected | Action if Fail |
|--------|----------|----------------|
| Bars processed | 1000 | Check pipeline loop |
| Validation errors | 0 | Investigate executor |
| Gate eval lines | ≈1000 | Check logging |
| Pass-rate | 0-5% | Check composite gate |
| Broker symbols | 6 registered | Verify broker_symbols.json |

---

## Next Phase

**Day 2**: Run determinism check (100-bar replay test)
**Days 3-5**: Continue daily monitoring
**End of Week**: Compile Phase 1 summary + approve Phase 2
