# Integration & Validation Checklist

## Pre-Backtest Validation (Day 0)

### Configuration Checks
- [ ] `configs/structure.json` has `execution` section with:
  - [ ] `enabled: true`
  - [ ] `mode: "dry-run"`
  - [ ] `min_rr: 1.5`
  - [ ] `price_side: {"BUY": "ASK", "SELL": "BID"}`
  - [ ] `emergency_close` settings
- [ ] `configs/broker_symbols.json` exists with:
  - [ ] EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD
  - [ ] Each symbol has: bid, ask, point, digits, volume_min, volume_max, volume_step, min_stop_distance, max_stop_distance, spread

### Code Integration Checks
- [ ] `core/orchestration/pipeline.py` imports:
  - [ ] `import json`
  - [ ] `from ..execution.mt5_executor import MT5Executor, BrokerSymbolInfo`
- [ ] `__init__()` initializes:
  - [ ] `self.executor = MT5Executor(exec_config, logger)`
  - [ ] `self._register_broker_symbols()`
  - [ ] `self.execution_results = []`
  - [ ] `self.session_execution_logs = []`
- [ ] `process_bar()` calls executor:
  - [ ] After decision generation (Stage 10)
  - [ ] Calls `executor.execute_order()` for each decision
  - [ ] Calls `_log_execution_result()`
  - [ ] Stores result in `self.execution_results`
- [ ] Helper methods exist:
  - [ ] `_register_broker_symbols()` — loads broker config
  - [ ] `_generate_magic_number()` — creates unique magic number
  - [ ] `_log_execution_result()` — logs passed/failed
  - [ ] `finalize_session()` — logs dry-run summary
  - [ ] Updated `get_pipeline_stats()` — includes executor info
  - [ ] Updated `reset()` — clears execution tracking

### Broker Symbol Registration
- [ ] All 5 symbols registered at pipeline init
- [ ] Each symbol has valid constraints:
  - [ ] volume_min < volume_max
  - [ ] min_stop_distance < max_stop_distance
  - [ ] point > 0
  - [ ] digits > 0

---

## Backtest Execution (Day 1-2)

### Run Backtest
- [ ] Command: `python scripts/backtest.py --config configs/structure.json --mode dry-run --symbol EURUSD --start 2025-01-01 --end 2025-10-20`
- [ ] Backtest completes without errors
- [ ] Log file generated: `logs/pipeline.json`

### Log Analysis
- [ ] Logs contain `order_validation_passed` events
- [ ] Logs contain `order_validation_failed` events (if any)
- [ ] Logs contain `dry_run_summary` at session close
- [ ] Each event has required fields:
  - [ ] `symbol`, `type`, `volume`, `entry`, `sl`, `tp`, `rr`
  - [ ] `mode: "dry-run"`
  - [ ] For failed: `errors` array with reasons

### Metrics Validation
- [ ] Pass rate ≥95%
  - [ ] Formula: passed / (passed + failed)
  - [ ] Example: 48 / 50 = 96% ✅
- [ ] All passed orders have RR ≥1.5
  - [ ] Check: `rr >= 1.5` for all `order_validation_passed` events
- [ ] All SL/TP distances within limits
  - [ ] Check: `sl_distance >= min_stop_distance`
  - [ ] Check: `sl_distance <= max_stop_distance`
  - [ ] Check: `tp_distance >= min_stop_distance`
  - [ ] Check: `tp_distance <= max_stop_distance`
- [ ] All volumes valid
  - [ ] Check: `volume >= volume_min`
  - [ ] Check: `volume <= volume_max`
  - [ ] Check: `(volume - volume_min) % volume_step == 0`

### Error Analysis
- [ ] Review all `order_validation_failed` events
- [ ] Categorize errors:
  - [ ] RR too low (count)
  - [ ] SL distance invalid (count)
  - [ ] TP distance invalid (count)
  - [ ] Volume invalid (count)
  - [ ] Other (count)
- [ ] Errors are expected/acceptable
- [ ] No unexpected validation failures

---

## Live Dry-Run (Week 1)

### Daily Monitoring

**Each Day**:
- [ ] Check `dry_run_summary` logged at session close
- [ ] Verify pass rate ≥95%
- [ ] Review any `order_validation_failed` events
- [ ] Check for new error patterns
- [ ] Monitor execution latency (should be <1ms)
- [ ] Verify all RR ≥1.5
- [ ] Confirm all SL/TP within limits

**Daily Metrics**:
- [ ] Pass rate: ___% (target ≥95%)
- [ ] Total orders: ___ (expected 40-60 per day)
- [ ] Passed: ___ (expected 38-57)
- [ ] Failed: ___ (expected 0-3)
- [ ] Avg RR: ___ (expected 1.6-1.9)
- [ ] Errors: ___ (target 0)

### Weekly Summary

**After 1 Week**:
- [ ] Pass rate ≥95% consistently (all 5 days)
- [ ] 0 validation errors across all days
- [ ] All RR ≥1.5 across all days
- [ ] All SL/TP within limits across all days
- [ ] All volumes valid across all days
- [ ] No symbol registration issues
- [ ] Execution latency <1ms consistently
- [ ] No unexpected error patterns

### Success Criteria Met?

If YES to all above:
- [ ] Proceed to paper mode
- [ ] Update config: `mode: "paper"`
- [ ] Run 1 week in paper mode
- [ ] Validate fills and execution quality
- [ ] Then switch to live mode

If NO to any above:
- [ ] Identify root cause
- [ ] Fix (SL/TP planning, volume logic, broker constraints, etc.)
- [ ] Restart dry-run for 1 week
- [ ] Repeat validation

---

## Paper Mode (Week 2)

### Configuration
- [ ] Update `configs/structure.json`:
  ```json
  {
    "execution": {
      "enabled": true,
      "mode": "paper"
    }
  }
  ```
- [ ] Restart pipeline

### Monitoring
- [ ] Monitor fills (should be instant in paper)
- [ ] Monitor slippage (should be 0 in paper)
- [ ] Monitor execution quality
- [ ] Monitor for any new errors
- [ ] Verify trades match expected entry/SL/TP

### Success Criteria
- [ ] All orders fill successfully
- [ ] No slippage (paper mode)
- [ ] Execution quality good
- [ ] No validation errors
- [ ] Metrics stable

---

## Live Mode (Week 3+)

### Configuration
- [ ] Update `configs/structure.json`:
  ```json
  {
    "execution": {
      "enabled": true,
      "mode": "live"
    }
  }
  ```
- [ ] Restart pipeline
- [ ] **CRITICAL**: Verify mode is "live" before starting

### Monitoring
- [ ] Monitor fills (may have slippage)
- [ ] Monitor execution quality
- [ ] Monitor for validation errors
- [ ] Monitor for broker rejections
- [ ] Verify trades match expected entry/SL/TP
- [ ] Monitor account equity and drawdown

### Daily Checks
- [ ] Verify all trades executed
- [ ] Check for any broker errors
- [ ] Monitor slippage (expected 1-3 pips typical)
- [ ] Verify SL/TP hit correctly
- [ ] Monitor P&L

---

## Troubleshooting

### High Failure Rate (Pass Rate <90%)

**Check**:
1. Are broker symbol constraints correct?
2. Is SL/TP planning generating valid distances?
3. Are RR calculations correct?

**Fix**:
1. Verify `broker_symbols.json` (min_stop_distance, volume_step)
2. Review SL/TP planning logic in pipeline
3. Adjust min_rr if needed (e.g., 1.4 instead of 1.5)

### Validation Errors in Live Dry-Run

**Check**:
1. Did broker constraints change?
2. Is market volatility affecting SL/TP distances?
3. Are symbol constraints still valid?

**Fix**:
1. Update broker symbol info from MT5
2. Adjust SL/TP planning for current volatility
3. Review failed orders in logs

### Execution Latency High (>1ms)

**Check**:
1. Is validation logic slow?
2. Is logging overhead high?
3. Is system under load?

**Fix**:
1. Profile validation logic
2. Cache broker symbol info
3. Batch log writes
4. Check system resources

### Symbol Not Registered

**Check**:
1. Is symbol in `broker_symbols.json`?
2. Is symbol name correct (case-sensitive)?
3. Did pipeline init complete?

**Fix**:
1. Add symbol to `broker_symbols.json`
2. Verify symbol name matches exactly
3. Restart pipeline

---

## Sign-Off

### Pre-Backtest
- [ ] All configuration checks passed
- [ ] All code integration checks passed
- [ ] All broker symbols registered
- [ ] Ready to run backtest

### Post-Backtest
- [ ] Pass rate ≥95%
- [ ] All metrics valid
- [ ] Error analysis complete
- [ ] Ready for live dry-run

### Post-Live Dry-Run (Week 1)
- [ ] Pass rate ≥95% consistently
- [ ] 0 validation errors
- [ ] All metrics stable
- [ ] Ready for paper mode

### Post-Paper Mode (Week 2)
- [ ] All orders filled successfully
- [ ] Execution quality good
- [ ] No validation errors
- [ ] Ready for live mode

### Post-Live Mode (Week 3+)
- [ ] All trades executed correctly
- [ ] Slippage acceptable
- [ ] P&L tracking correctly
- [ ] System stable
- **READY FOR SCALING**

---

## Next Steps After Validation

Once dry-run is validated with 0 errors for 1 week:

1. **Switch to paper mode** (1 week)
2. **Switch to live mode** (ongoing)
3. **Start AI decision layer** (2-3 weeks in parallel)
   - Signal enricher
   - LLaMA reasoning
   - Decision filtering
4. **Integrate AI with executor** (1-2 weeks)
5. **Full end-to-end testing** (1 week)
6. **Scale live exposure** (ongoing)

---

## Status: 🚀 Ready for Validation

✅ Executor wired into pipeline
✅ Broker symbols configured
✅ Logging schema ready
✅ Dry-run mode enabled
✅ **Ready for backtest & live validation**
