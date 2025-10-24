# Dry-Run Test Parameters & Validation Guide

## Overview

This document provides test parameters and validation criteria for the MT5 Executor in dry-run mode.

---

## Test Scenarios

### Scenario 1: Valid Orders (Should Pass)

**Setup**:
- Symbol: EURUSD
- Entry: 1.0950 (ASK for BUY)
- SL: 1.0920 (30 pips = 300 points)
- TP: 1.0995 (45 pips = 450 points)
- RR: 450/300 = 1.5 ✅
- Volume: 0.5 lots

**Expected Result**: ✅ PASS
- Validation passes all checks
- Log: `order_validation_passed`
- RR = 1.5 (meets minimum)
- SL/TP distances within limits (50–5000 points)

---

### Scenario 2: RR Too Low (Should Fail)

**Setup**:
- Symbol: EURUSD
- Entry: 1.0950
- SL: 1.0930 (20 pips = 200 points)
- TP: 1.0980 (30 pips = 300 points)
- RR: 300/200 = 1.5 ✅ (borderline)
- Volume: 0.5 lots

**Test Variation**: Lower TP to 1.0970 (20 pips = 200 points)
- RR: 200/200 = 1.0 ❌ (below minimum 1.5)

**Expected Result**: ❌ FAIL
- Validation fails: "RR 1.0 < min 1.5"
- Log: `order_validation_failed`
- Reason: RR below threshold

---

### Scenario 3: SL Distance Too Small (Should Fail)

**Setup**:
- Symbol: EURUSD
- Entry: 1.0950
- SL: 1.0948 (2 pips = 20 points)
- TP: 1.0980 (30 pips = 300 points)
- RR: 300/20 = 15.0 ✅ (high)
- Volume: 0.5 lots

**Expected Result**: ❌ FAIL
- Validation fails: "SL distance 20 pts < min 50 pts"
- Log: `order_validation_failed`
- Reason: SL distance below broker minimum

---

### Scenario 4: SL Distance Too Large (Should Fail)

**Setup**:
- Symbol: EURUSD
- Entry: 1.0950
- SL: 1.0450 (500 pips = 5000 points)
- TP: 1.1450 (500 pips = 5000 points)
- RR: 5000/5000 = 1.0 ❌ (also fails RR)
- Volume: 0.5 lots

**Test Variation**: Adjust TP to 1.1950 (1000 pips = 10000 points)
- RR: 10000/5000 = 2.0 ✅

**Expected Result**: ❌ FAIL
- Validation fails: "SL distance 5000 pts > max 5000 pts" (or TP distance > max)
- Log: `order_validation_failed`
- Reason: SL/TP distance exceeds broker maximum

---

### Scenario 5: Volume Too Small (Should Fail)

**Setup**:
- Symbol: EURUSD
- Entry: 1.0950
- SL: 1.0920 (30 pips = 300 points)
- TP: 1.0995 (45 pips = 450 points)
- RR: 1.5 ✅
- Volume: 0.001 lots (below minimum 0.01)

**Expected Result**: ❌ FAIL
- Validation fails: "Volume 0.001 < min 0.01"
- Log: `order_validation_failed`
- Reason: Volume below broker minimum

---

### Scenario 6: Volume Too Large (Should Fail)

**Setup**:
- Symbol: EURUSD
- Entry: 1.0950
- SL: 1.0920 (30 pips = 300 points)
- TP: 1.0995 (45 pips = 450 points)
- RR: 1.5 ✅
- Volume: 150.0 lots (above maximum 100.0)

**Expected Result**: ❌ FAIL
- Validation fails: "Volume 150.0 > max 100.0"
- Log: `order_validation_failed`
- Reason: Volume exceeds broker maximum

---

### Scenario 7: Volume Not Multiple of Step (Should Fail)

**Setup**:
- Symbol: EURUSD
- Entry: 1.0950
- SL: 1.0920 (30 pips = 300 points)
- TP: 1.0995 (45 pips = 450 points)
- RR: 1.5 ✅
- Volume: 0.5 lots
- Volume step: 0.01 (0.5 is valid: 0.5 = 50 × 0.01) ✅

**Test Variation**: Volume 0.515 lots
- Volume step: 0.01 (0.515 is NOT valid: 0.515 ≠ N × 0.01)

**Expected Result**: ❌ FAIL
- Validation fails: "Volume 0.515 not multiple of step 0.01"
- Log: `order_validation_failed`
- Reason: Volume doesn't align with broker step

---

### Scenario 8: SL on Wrong Side for BUY (Should Fail)

**Setup**:
- Symbol: EURUSD
- Order Type: BUY
- Entry: 1.0950
- SL: 1.0980 (above entry) ❌
- TP: 1.0920 (below entry) ❌
- Volume: 0.5 lots

**Expected Result**: ❌ FAIL
- Validation fails: "BUY: SL 1.0980 must be < entry 1.0950"
- Validation fails: "BUY: TP 1.0920 must be > entry 1.0950"
- Log: `order_validation_failed`
- Reason: SL/TP on wrong side

---

### Scenario 9: SL on Wrong Side for SELL (Should Fail)

**Setup**:
- Symbol: EURUSD
- Order Type: SELL
- Entry: 1.0950
- SL: 1.0920 (below entry) ❌
- TP: 1.0980 (above entry) ❌
- Volume: 0.5 lots

**Expected Result**: ❌ FAIL
- Validation fails: "SELL: SL 1.0920 must be > entry 1.0950"
- Validation fails: "SELL: TP 1.0980 must be < entry 1.0950"
- Log: `order_validation_failed`
- Reason: SL/TP on wrong side

---

### Scenario 10: Symbol Not Registered (Should Fail)

**Setup**:
- Symbol: XYZABC (not in broker_symbols.json)
- Entry: 1.0950
- SL: 1.0920
- TP: 1.0995
- Volume: 0.5 lots

**Expected Result**: ❌ FAIL
- Validation fails: "Symbol XYZABC not registered with broker info"
- Log: `order_validation_failed`
- Reason: Symbol constraints not available

---

## Validation Checklist

### Pre-Backtest

- [ ] `core/execution/mt5_executor.py` created
- [ ] `configs/structure.json` has execution section:
  ```json
  {
    "execution": {
      "enabled": true,
      "mode": "dry-run",
      "min_rr": 1.5,
      "price_side": {"BUY": "ASK", "SELL": "BID"},
      "emergency_close": {"deviation": 20, "type_filling": "IOC", "max_retries": 3}
    }
  }
  ```
- [ ] `configs/broker_symbols.json` created with symbol constraints
- [ ] Executor integrated into `pipeline.py`:
  - [ ] Imported: `from .execution.mt5_executor import MT5Executor, BrokerSymbolInfo`
  - [ ] Initialized: `self.executor = MT5Executor(exec_config, logger)`
  - [ ] Symbols registered: `self._register_broker_symbols_from_config()`
  - [ ] Called after decisions: `self.executor.execute_order(...)`
  - [ ] Summary logged at session close: `self.executor.log_dry_run_summary()`

### Backtest Execution

- [ ] Run backtest with dry-run mode
- [ ] Verify logs contain:
  - [ ] `order_validation_passed` events (valid orders)
  - [ ] `order_validation_failed` events (invalid orders)
  - [ ] `dry_run_summary` at session close

### Metrics Validation

- [ ] Pass rate ≥95% (most orders valid)
- [ ] All passed orders have RR ≥1.5
- [ ] All passed orders have SL/TP within limits
- [ ] All passed orders have volume within limits
- [ ] Failed orders have clear error messages

### Log Analysis

- [ ] Review `order_validation_failed` events:
  - [ ] Are errors expected? (e.g., RR too low, SL too close)
  - [ ] Are error messages clear?
  - [ ] Can you reproduce each failure?
- [ ] Review `order_validation_passed` events:
  - [ ] Are all fields correct? (symbol, type, volume, entry, SL, TP)
  - [ ] Are RR values reasonable? (1.5–3.0 typical)
  - [ ] Are payloads complete?

---

## Expected Results (Backtest)

### Typical Distribution

Assuming 1000 bars with ~50 decisions generated:

| Outcome | Count | Rate | Notes |
|---------|-------|------|-------|
| Validation passed | 48 | 96% | Valid orders ready to send |
| Validation failed | 2 | 4% | Invalid orders blocked |
| **Total** | **50** | **100%** | |

### Failure Reasons (Typical)

| Reason | Count | Action |
|--------|-------|--------|
| RR < 1.5 | 1 | Review SL/TP planning |
| SL distance < min | 0 | OK (rare) |
| SL distance > max | 0 | OK (rare) |
| Volume invalid | 0 | OK (rare) |
| Symbol not registered | 0 | OK (all symbols registered) |

---

## Live Dry-Run (Week 1)

### Daily Checklist

- [ ] Check `dry_run_summary` (pass rate ≥95%)
- [ ] Review any `order_validation_failed` events
- [ ] Verify all passed orders have RR ≥1.5
- [ ] Check execution latency (<1ms)
- [ ] Monitor for any new error patterns

### Success Criteria (After 1 Week)

- [ ] Pass rate ≥95% consistently
- [ ] 0 validation errors for passed orders
- [ ] All RR ≥1.5
- [ ] All SL/TP within broker limits
- [ ] All volumes valid
- [ ] No symbol registration issues
- [ ] Execution latency <1ms

### If Success Criteria Met

1. Switch to paper mode:
   ```json
   {"execution": {"mode": "paper"}}
   ```
2. Run 1 week in paper mode
3. Validate fills, slippage, execution quality
4. Switch to live mode:
   ```json
   {"execution": {"mode": "live"}}
   ```

### If Success Criteria NOT Met

1. Identify failure pattern
2. Fix root cause (SL/TP planning, volume logic, etc.)
3. Restart dry-run for 1 week
4. Repeat until criteria met

---

## Troubleshooting

### High Failure Rate (Pass Rate <90%)

**Likely Causes**:
1. SL/TP planning generating invalid distances
2. Broker constraints too strict (min_stop_distance too high)
3. Volume logic incorrect

**Debug Steps**:
1. Review failed orders in logs
2. Check SL/TP planning logic
3. Verify broker constraints in `broker_symbols.json`
4. Adjust if needed and retry

### Specific Error Patterns

**"RR X < min 1.5"**
- SL/TP planning not respecting min_rr
- Fix: Adjust SL/TP planning to ensure RR ≥1.5

**"SL distance X pts < min 50 pts"**
- SL too close to entry
- Fix: Increase SL distance in SL/TP planning

**"Volume X not multiple of step 0.01"**
- Volume rounding issue
- Fix: Round volume to nearest step (e.g., 0.5 → 0.50)

**"Symbol XXXX not registered"**
- Symbol missing from `broker_symbols.json`
- Fix: Add symbol to config or register at runtime

---

## Next Steps

1. **Wire executor into pipeline.py** (15 min)
2. **Load broker symbols from config** (10 min)
3. **Run backtest in dry-run** (30 min)
4. **Validate results** (30 min)
5. **Deploy live in dry-run for 1 week** (ongoing)
6. **Switch to paper/live once validated** (1 week)

Once dry-run is validated with 0 errors, integrate AI decision layer (LLaMA reasoning).
