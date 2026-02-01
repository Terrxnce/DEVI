# Phase 2B - 10016 Error Fix Implementation

**Date**: 2025-12-12  
**Status**: Ready for Testing  
**Approach**: Option B - Disable Pre-Check + Enhanced Logging

---

## 🎯 OBJECTIVE

Fix the re-emerged `10016 "Invalid stops"` errors blocking Phase 2B trade collection by:
1. **Temporarily disabling** the broker stop-level pre-check
2. **Adding enhanced logging** to capture ground truth data
3. **Collecting 30-50 trades** to reverse-engineer broker's exact stop-distance formula
4. **Re-implementing pre-check** with correct formula after analysis

---

## 🔍 ROOT CAUSE ANALYSIS

### The Problem
The broker stop-level pre-check in `mt5_executor.py` has an **inconsistent calculation** that:
- ✅ **Correctly blocks** some trades (e.g., USDJPY: 1.0 pts vs 32 pts required)
- ❌ **Incorrectly passes** others (e.g., GBPUSD: 5.9 pts vs 20 pts required)

This leads to:
1. Pre-check passes → Order sent → Broker rejects with 10016
2. Rescaling attempts (using same flawed math) → Still rejected
3. 3 consecutive failures → Symbol paused by safety mechanism

### Why Phase 2A Didn't Catch This
- **Phase 2A**: 7 trades, 2.5 hours, wider SL distances
- **Phase 2B**: Longer run, tighter market conditions, smaller SL distances
- The edge cases only appeared with tighter stops

### The Mismatch
```python
# Our calculation (suspected):
min_required_pts = stops_level + (spread * spread_buffer_multiplier)

# Broker's actual calculation (unknown):
min_required_pts = ??? (need ground truth to determine)
```

---

## ✅ IMPLEMENTATION

### 1. Enhanced Logging Added

**File**: `c:\Users\Index\DEVI\core\execution\mt5_executor.py`

**Location**: `execute_order()` method, before `order_send_attempt`

**New Event**: `trade_validation_detail`

Logs for **every trade attempt**:
```json
{
  "event": "trade_validation_detail",
  "symbol": "GBPUSD",
  "order_type": "BUY",
  "entry": 1.33743,
  "sl": 1.33684,
  "tp": 1.33869,
  "volume": 7.94,
  "sl_distance_pts": 5.9,
  "tp_distance_pts": 12.6,
  "broker_stops_level": 0,
  "broker_spread": 6,
  "broker_point": 0.00001,
  "our_min_sl_pts": 20,
  "pre_check_enabled": false,
  "pre_check_would_pass": false
}
```

**Also Enhanced**: `order_send_result` now includes `"success": true/false`

### 2. Pre-Check Disabled

**File**: `c:\Users\Index\DEVI\configs\execution_guards.json`

**Change**:
```json
"broker_stop_level_guard": {
  "enabled": false,  // Changed from true
  "comment": "TEMPORARILY DISABLED for Phase 2B data collection"
}
```

**Effect**:
- `validate_broker_stops_before_order()` returns `(True, None)` immediately
- Orders are **not blocked** by pre-check
- Rescaling logic still active (handles broker rejections)
- 3-consecutive-failure safety pause still active

---

## 📊 WHAT HAPPENS NOW

### Trade Flow (Pre-Check Disabled)
1. ✅ **Structure detected** → Decision generated
2. ✅ **Margin guard** → Checks available margin/risk
3. ⚠️ **Pre-check** → **SKIPPED** (disabled)
4. 📝 **Enhanced logging** → Captures all variables
5. 📤 **Order sent** → To broker
6. 🎲 **Broker response**:
   - ✅ **10009 (success)** → Trade executed
   - ❌ **10016 (invalid stops)** → Rescaling triggered
7. 🔄 **Rescaling** → Widens SL/TP, adjusts volume
8. 📤 **Retry** → Send adjusted order
9. 🎲 **Broker response** → Success or failure
10. 🛑 **Safety pause** → After 3 consecutive failures per symbol

### Data We'll Collect

**For Accepted Trades**:
- Exact SL/TP distances that broker **accepts**
- Broker's `stops_level`, `spread`, `point` at acceptance time
- Our calculated `min_sl_pts` (for comparison)

**For Rejected Trades**:
- Exact SL/TP distances that broker **rejects**
- Broker's `stops_level`, `spread`, `point` at rejection time
- Our calculated `min_sl_pts` (shows where we're wrong)
- Rescaling attempts and final outcome

**Pattern Analysis**:
- Compare accepted vs rejected to find the **threshold**
- Identify if it's symbol-specific, time-dependent, or formula-based
- Reverse-engineer broker's exact calculation

---

## 🎯 PHASE 2B CONTINUATION PLAN

### Run Command
```powershell
python run_live_mt5.py
```

### Expected Behavior
1. **More 10016 errors initially** (pre-check not blocking)
2. **Rescaling handles most** (widens stops, adjusts volume)
3. **Some symbols may pause** (3 consecutive failures)
4. **Overall: More trades execute** than with pre-check enabled
5. **Rich logging data** for post-run analysis

### Monitoring
Watch for:
- ✅ `trade_validation_detail` events (every trade)
- ⚠️ `order_send_result` with `retcode: 10016`
- 🔄 `order_send_volume_rescaled` events
- ✅ `order_send_result` with `retcode: 10009` (success)
- 🛑 Symbol pauses due to consecutive failures

### Success Criteria
- **30-50 trades executed** (Phase 2B target)
- **Diverse mix** of accepted and rejected trades
- **Sufficient data** to identify broker's formula

### Stop Conditions
- **FTMO limits hit** (-5% daily, -10% total)
- **Manual stop** after 30-50 trades collected
- **Critical error** (not 10016-related)

---

## 📈 POST-RUN ANALYSIS PLAN

### Step 1: Extract Ground Truth
Parse log file for all `trade_validation_detail` and `order_send_result` pairs:
```python
# Pseudo-code
accepted_trades = [
    {
        "symbol": "GBPUSD",
        "sl_distance_pts": 20.5,
        "broker_stops_level": 0,
        "broker_spread": 6,
        "result": "accepted"
    },
    # ...
]

rejected_trades = [
    {
        "symbol": "GBPUSD",
        "sl_distance_pts": 5.9,
        "broker_stops_level": 0,
        "broker_spread": 6,
        "result": "rejected_10016"
    },
    # ...
]
```

### Step 2: Identify Pattern
- Group by symbol
- Find **minimum accepted distance** per symbol
- Compare to broker's `stops_level` and `spread`
- Test hypotheses:
  - `min = stops_level + spread`
  - `min = max(stops_level, spread * 2)`
  - `min = stops_level + spread + buffer`
  - Symbol-specific rules

### Step 3: Implement Corrected Pre-Check
Update `validate_broker_stops_before_order()` with discovered formula:
```python
# Example (actual formula TBD from data):
min_required_pts = stops_level + spread + 5  # +5 buffer discovered from data
```

### Step 4: Re-Enable and Validate
- Set `"enabled": true` in `execution_guards.json`
- Run small test (5-10 trades)
- Verify:
  - ✅ No false positives (blocking valid trades)
  - ✅ No false negatives (passing invalid trades)
  - ✅ Zero 10016 errors

---

## 🔒 SAFETY MECHANISMS STILL ACTIVE

Even with pre-check disabled, these guards protect us:

1. **Margin Guard**
   - Blocks trades if margin < 200%
   - Blocks if free margin usage > 30%
   - Blocks if total open risk > 4.5%

2. **3-Consecutive-Failure Pause**
   - Symbol paused after 3 failed order sends
   - Prevents infinite retry loops
   - Logs `max_consecutive_send_failures` event

3. **FTMO Limits**
   - Daily loss limit: -5%
   - Total loss limit: -10%
   - Hard stops enforced

4. **Rescaling Logic**
   - Widens SL/TP on 10016 errors
   - Adjusts volume to maintain risk
   - Max 2 attempts per trade

---

## 📝 FILES MODIFIED

### 1. `c:\Users\Index\DEVI\core\execution\mt5_executor.py`
**Lines Modified**: 140-172, 637-651

**Changes**:
- Added `trade_validation_detail` logging before every order send
- Enhanced `order_send_result` to include `success` field
- Captures all broker variables for ground truth analysis

### 2. `c:\Users\Index\DEVI\configs\execution_guards.json`
**Lines Modified**: 2-7

**Changes**:
- Set `"enabled": false` for `broker_stop_level_guard`
- Added comment explaining temporary disable

---

## 🚀 NEXT STEPS

### Immediate (Now)
1. ✅ **Verify changes** (this document)
2. ✅ **Restart Phase 2B** (`python run_live_mt5.py`)
3. 👀 **Monitor logs** for `trade_validation_detail` events

### During Run
1. Watch for diverse trade outcomes (accepted + rejected)
2. Let it run until 30-50 trades collected
3. Stop manually or when FTMO limits approached

### After Run
1. **Extract log data** (accepted vs rejected trades)
2. **Analyze pattern** (find broker's formula)
3. **Implement corrected pre-check** (update `validate_broker_stops_before_order`)
4. **Re-enable pre-check** (`"enabled": true`)
5. **Validate fix** (small test run, zero 10016 errors)
6. **Continue Phase 2B** (if more trades needed)

---

## 🎯 BIG PICTURE

**We're still on track.**

This is **not a deviation** from the plan. This is **exactly what Phase 2 is about**:
- Hardening the execution layer
- Fixing edge cases in live conditions
- Building a robust, production-ready system

**Phase 2A**: Fixed obvious issues (contract sizes, basic rescaling)  
**Phase 2B**: Fixing subtle issues (stop-distance calculation edge cases)  
**Next**: Complete execution layer hardening, move to strategy optimization

---

## ✅ READY TO LAUNCH

All changes implemented. Pre-check disabled. Enhanced logging active.

**Command to restart Phase 2B**:
```powershell
python run_live_mt5.py
```

Monitor for `trade_validation_detail` events in the log.

Let's collect that ground truth data. 🚀
