# Phase 2A: Critical Fixes Applied
**Date**: 2025-12-09 23:48 UTC  
**Status**: ✅ FIXES IMPLEMENTED

---

## **Issues Identified in Phase 2A Run**

### **Run Summary**
- **Duration**: 3h 35min (20:10 - 23:45 UTC)
- **Decisions**: 6 generated, 5 attempted
- **Successful**: 2 trades (EURUSD SELL, EURUSD BUY)
- **Failed**: 1 trade (USDJPY - 10016 error)
- **Blocked**: 2 trades (XAUUSD margin guard, USDJPY pre-check)

---

## **Issue #1: Margin Guard Risk Calculation Bug**

### **Problem**
Margin guard incorrectly calculated risk for XAUUSD, showing 498% risk instead of ~1.4%.

**Root Cause**: Hardcoded contract size of 100,000 (FX standard) used for all symbols.

```python
# WRONG (line 195, 199):
pos_risk = pos.volume * sl_distance * 100000  # Approximate for FX
new_trade_risk = estimated_volume * estimated_sl_distance * 100000
```

**Impact**: 
- XAUUSD trade incorrectly blocked
- Risk calculations wrong for all non-FX symbols (metals, indices, stocks)

### **Fix Applied**
Use actual contract size from MT5 symbol info for each symbol.

**File**: `core/orchestration/pipeline.py`  
**Lines**: 189-207

```python
# FIXED:
# For open positions
pos_symbol_info = mt5.symbol_info(pos.symbol)
if pos_symbol_info:
    contract_size = pos_symbol_info.trade_contract_size
    pos_risk = pos.volume * sl_distance * contract_size

# For new trade
symbol_info = mt5.symbol_info(symbol)
contract_size = symbol_info.trade_contract_size
new_trade_risk = estimated_volume * estimated_sl_distance * contract_size
```

**Expected Result**: 
- XAUUSD risk: ~$489 (0.5% of $98k) ✅
- Correct risk calculations for all symbol types ✅

---

## **Issue #2: SL/TP Rescaling Logic Mismatch**

### **Problem**
When 10016 error occurred, rescaling logic used different calculation than pre-check, resulting in stops that were still too close.

**Example from logs**:
```
Pre-check: min_required_pts = 30 (stops_level=10 + spread*2.0)
Rescaling: min_sl_pts = 16 (stops_level=0 + spread + buffer)
Result: Still got 10016 error
```

**Root Cause**: Rescaling logic didn't use:
1. `min_stops_level_when_zero` config (10pts)
2. `spread_buffer_multiplier` config (2.0x)

### **Fix Applied**
Align rescaling calculation with pre-check logic.

**File**: `core/execution/mt5_executor.py`  
**Lines**: 636-645

```python
# BEFORE:
spread_points = int(abs(ask - bid) / point)
stop_level = getattr(info, "stop_level", 0)
min_sl_pts = max(int(stop_level), spread_points + self.sl_buffer_points, hard_floor_points)

# AFTER:
spread = getattr(info, "spread", 0)
stops_level = getattr(info, "stops_level", 0)

# Use configured minimum if broker returns 0 (match pre-check logic)
if stops_level == 0:
    stops_level = self.min_stops_level_when_zero

# Calculate minimum required distance: stops_level + spread buffer (match pre-check)
min_sl_pts = stops_level + int(spread * self.spread_buffer_multiplier)
```

**Expected Result**:
- Rescaling uses same 30pt minimum as pre-check ✅
- If rescaling still can't meet requirements, pre-check will reject ✅
- No more 10016 errors after rescaling attempts ✅

---

## **Guard Performance Summary**

| Guard | Phase 2A Status | Post-Fix Expected |
|-------|----------------|-------------------|
| **Margin Check** | ⚠️ Wrong calculation | ✅ Correct for all symbols |
| **Broker Stop Pre-Check** | ✅ Working | ✅ Working |
| **SL/TP Rescaling** | ❌ Failed (10016) | ✅ Aligned with pre-check |
| **Position Tracking** | ❓ Not tested | ⏳ Needs validation |
| **Legacy Fallback** | ✅ Working (0% legacy) | ✅ Working |

---

## **What Was Validated in Phase 2A**

### **✅ Working Correctly**
1. **Margin guard activation** - Fires in LIVE mode ✅
2. **Broker stop-level pre-check** - Catches invalid stops ✅
3. **Guard logging** - All events logged correctly ✅
4. **Successful execution** - 2 clean trades with real tickets ✅
5. **Exit method diversity** - Rejection (1), ATR (1) ✅

### **⚠️ Issues Found & Fixed**
1. **Margin risk calculation** - Fixed contract size bug ✅
2. **Rescaling logic** - Aligned with pre-check ✅

### **❓ Not Yet Validated**
1. **Position close tracking** - No positions closed during run
2. **Full rescaling success** - Need to test with fixed logic

---

## **Testing Plan for Next Run**

### **Phase 2A Rerun (Short)**
**Duration**: 2-3 hours  
**Target**: 5-10 trades  
**Focus**: Validate fixes

**Expected Outcomes**:
1. ✅ Zero 10016 errors (rescaling now correct)
2. ✅ XAUUSD trades not blocked by margin guard (risk calc fixed)
3. ✅ All margin checks show correct risk percentages
4. ✅ If rescaling needed, it produces valid stops

**Monitoring**:
```bash
# Watch for 10016 errors (should be zero)
tail -f logs/live_mt5_*.json | grep "10016"

# Watch margin guard (should show correct percentages)
tail -f logs/live_mt5_*.json | grep "margin_check_passed\|margin_guard_blocked"

# Watch rescaling (should succeed if triggered)
tail -f logs/live_mt5_*.json | grep "order_send_volume_rescaled\|order_send_stops_adjusted"
```

### **Phase 2B: Full Validation Run**
**Duration**: 6-8 hours  
**Target**: 30-50 trades  
**Focus**: Full system validation + position close tracking

**Expected Outcomes**:
1. ✅ Clean execution across all symbols
2. ✅ Position close logging working
3. ✅ Guards behaving correctly under load
4. ✅ Ready for Phase 3 (strategy optimization)

---

## **Files Modified**

### **1. core/orchestration/pipeline.py**
**Lines**: 189-214  
**Change**: Use `symbol_info.trade_contract_size` for risk calculations

### **2. core/execution/mt5_executor.py**
**Lines**: 636-645  
**Change**: Align rescaling logic with pre-check calculation

---

## **Configuration Verified**

All execution guards remain enabled:
```json
{
  "broker_stop_level_guard": {
    "enabled": true,
    "spread_buffer_multiplier": 2.0,
    "min_stops_level_when_zero": 10
  },
  "margin_guard": {
    "enabled": true,
    "min_margin_level_pct": 200.0,
    "max_free_margin_usage_pct": 30.0,
    "max_total_open_risk_pct": 4.5
  }
}
```

---

## **Next Steps**

1. ✅ **Fixes Applied** - Ready for testing
2. ⏳ **Phase 2A Rerun** - Validate fixes (2-3 hours)
3. ⏳ **Phase 2B Full Run** - Complete validation (6-8 hours)
4. ⏳ **Phase 3** - Strategy optimization (if Phase 2B clean)

---

**Status**: 🟢 **READY FOR PHASE 2A RERUN**

All critical issues identified and fixed. System ready for validation run.
