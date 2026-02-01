# Phase 2B Restart Checklist

**Date**: 2025-12-12  
**Objective**: Restart Phase 2B with pre-check disabled and enhanced logging

---

## ✅ PRE-FLIGHT VERIFICATION

### 1. Code Changes Applied
- [x] **Enhanced logging** added to `mt5_executor.py`
  - `trade_validation_detail` event before every order send
  - Captures: SL/TP distances, broker settings, our calculations
- [x] **Pre-check disabled** in `execution_guards.json`
  - `broker_stop_level_guard.enabled = false`

### 2. Configuration Status
- [x] **Soft stop disabled** (`daily_soft_stop_pct = -100.0`)
- [x] **Hard stop disabled** (`daily_hard_stop_pct = -100.0`)
- [x] **Margin guard enabled** (protects against over-leverage)
- [x] **3-failure pause enabled** (protects against infinite retries)
- [x] **FTMO limits active** (-5% daily, -10% total)

### 3. Environment
- [x] **Mode**: `ftmo_demo`
- [x] **Symbols**: EURUSD, XAUUSD, GBPUSD, USDJPY
- [x] **Risk per trade**: 0.5%
- [x] **MT5 connection**: Ready

---

## 🎯 EXPECTED BEHAVIOR

### What Will Happen
1. **More 10016 errors** (pre-check not blocking)
2. **Rescaling kicks in** (widens stops, adjusts volume)
3. **Some trades succeed** after rescaling
4. **Some symbols pause** after 3 consecutive failures
5. **Rich logging data** for every trade attempt

### What We're Collecting
- **Accepted trades**: SL/TP distances broker accepts
- **Rejected trades**: SL/TP distances broker rejects
- **Broker settings**: `stops_level`, `spread`, `point` for each symbol
- **Our calculations**: `our_min_sl_pts` to compare against reality

---

## 🚀 LAUNCH COMMAND

```powershell
python run_live_mt5.py
```

---

## 👀 MONITORING

### Key Log Events to Watch

#### 1. Trade Validation Detail (Every Trade)
```json
{
  "event": "trade_validation_detail",
  "symbol": "GBPUSD",
  "sl_distance_pts": 5.9,
  "broker_stops_level": 0,
  "broker_spread": 6,
  "our_min_sl_pts": 20,
  "pre_check_enabled": false
}
```

#### 2. Order Send Result (Broker Response)
```json
{
  "event": "order_send_result",
  "symbol": "GBPUSD",
  "retcode": 10016,  // or 10009 for success
  "success": false,
  "attempt": 1
}
```

#### 3. Rescaling (On 10016)
```json
{
  "event": "order_send_volume_rescaled",
  "symbol": "GBPUSD",
  "original_volume": 7.94,
  "new_volume": 23.42,
  "scale_factor": 2.95
}
```

#### 4. Success After Rescaling
```json
{
  "event": "order_send_result",
  "retcode": 10009,
  "success": true,
  "attempt": 2
}
```

#### 5. Symbol Pause (After 3 Failures)
```json
{
  "event": "symbol_paused",
  "symbol": "GBPUSD",
  "reason": "max_consecutive_send_failures"
}
```

---

## 🛑 STOP CONDITIONS

### Manual Stop After:
1. **30-50 trades executed** (Phase 2B target met)
2. **Sufficient data collected** (mix of accepted/rejected)
3. **FTMO limits approached** (near -5% daily or -10% total)

### Auto Stop On:
1. **FTMO hard limit hit** (-5% daily or -10% total)
2. **Critical error** (not 10016-related)

---

## 📊 SUCCESS CRITERIA

- ✅ **30-50 trades executed** (regardless of success/failure)
- ✅ **Diverse outcomes** (some accepted, some rejected)
- ✅ **Rich logging data** (every trade has `trade_validation_detail`)
- ✅ **Pattern emerges** (can identify broker's formula from data)

---

## 📝 POST-RUN TASKS

1. **Stop the run** (Ctrl+C)
2. **Note log file path** (e.g., `logs/live_mt5_20251212_*.json`)
3. **Share log file** for analysis
4. **Extract ground truth** (accepted vs rejected trades)
5. **Identify broker formula** (reverse-engineer from pattern)
6. **Implement corrected pre-check** (update code)
7. **Re-enable pre-check** (set `enabled: true`)
8. **Validate fix** (small test run)

---

## 🎯 READY TO LAUNCH

All systems go. Pre-check disabled. Enhanced logging active.

**Launch when ready**:
```powershell
python run_live_mt5.py
```

Monitor the console and logs for `trade_validation_detail` events.

Let's collect that data! 🚀
