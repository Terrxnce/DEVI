# 🚀 FTMO Demo Launch Checklist - Monday Dec 9, 2025

## ✅ PRE-LAUNCH VERIFICATION (Complete)

### **1. Core System Components**
- ✅ **FTMO Daily Reset Logic** - Captures equity at midnight UTC, initializes daily_equity_low correctly
- ✅ **FTMO Monitoring** - Tracks intra-day equity low, warns at -3%/-7%, stops at -5%/-10%
- ✅ **Enhanced Exit Logging** - Captures requested vs final SL/TP, clamp flags, distances in points
- ✅ **Legacy Tracking** - Explicit logging + session summary breakdown by structure type
- ✅ **Exit Planner** - Structure-first priority (OB → FVG → UZR → ATR → Legacy)
- ✅ **Risk Management** - Equity-based drawdown, daily soft/hard stops, volume rescaling
- ✅ **MT5 Executor** - Paper/live mode support, order retry logic, position management

### **2. Configuration Files**
- ✅ `configs/system.json` - FTMO limits configured, env section ready
- ✅ `configs/sltp.json` - Exit priority, buffers, RR gate settings
- ✅ `configs/structure.json` - All detectors configured
- ✅ `configs/guards.json` - Risk guards active

### **3. Paper Mode Validation Results**
- ✅ **23-hour run completed** - 75 trades executed
- ✅ **Overall RR Pass Rate**: 94.77%
- ✅ **Structure Exit RR Pass**: 100% (rejection/OB/FVG/ATR)
- ✅ **Legacy RR Pass**: 82.98% (acceptable)
- ✅ **Legacy Usage**: 31.3% (within target 20-35%)
- ✅ **ATR Fallback**: Working correctly with auto-extension

---

## 📋 MONDAY MORNING CHECKLIST

### **Step 1: Config Update** (5 minutes before launch)

**File**: `configs/system.json`

**Change Line 12-15 from**:
```json
"env": {
  "mode": "paper",
  "account_size": 10000
}
```

**To**:
```json
"env": {
  "mode": "ftmo_demo",
  "account_size": 100000
}
```

**Verify Other Settings**:
```json
"execution": {
  "enabled": true,
  "mode": "dry-run",  // ← Should be "dry-run" for paper, or leave as is
  "enable_real_mt5_orders": true  // ← Must be true for FTMO demo
}

"risk": {
  "per_trade_pct": 0.005,  // ← 0.5% risk per trade
  "daily_soft_stop_pct": -1.0,
  "daily_hard_stop_pct": -2.0
}

"ftmo_limits": {
  "max_daily_loss_pct": -5.0,
  "max_total_loss_pct": -10.0,
  "profit_target_pct": 10.0
}
```

### **Step 2: MT5 Connection Verification**

**Open MT5 Terminal**:
1. ✅ FTMO demo account loaded (100,000 balance)
2. ✅ Account number visible in terminal
3. ✅ Connection status: Green (connected to FTMO server)
4. ✅ Market Watch: All symbols visible (EURUSD, XAUUSD, GBPUSD, USDJPY)
5. ✅ Historical data synced (15m charts loaded)

**Test Connection**:
```python
import MetaTrader5 as mt5
mt5.initialize()
print(mt5.account_info())  # Should show FTMO demo account
print(mt5.terminal_info())  # Should show connected=True
mt5.shutdown()
```

### **Step 3: Launch Timing**

**Optimal Window**: Monday 08:00-09:00 UTC (London Open)

**Why**:
- Highest liquidity of the week
- Tightest spreads
- Most reliable execution
- Clean daily baseline (no overnight positions)

**Check Economic Calendar**:
- Avoid launching during high-impact news (NFP, CPI, FOMC, etc.)
- If major news scheduled, wait until after event + 30 minutes

### **Step 4: Launch Command**

**From repo root**:
```bash
python run_live_mt5.py --symbols EURUSD XAUUSD GBPUSD USDJPY --mode live --poll-seconds 10
```

**Expected Output**:
```
======================================================================
D.E.V.I 2.0 LIVE/PAPER MT5 LOOP
======================================================================

[1/4] Setting up logging...
      Logs: logs/live_mt5_20251209_080000.json

[2/4] Loading configuration...
      Config hash: a1b2c3d4e5f6g7h8...
      Data source: MT5

[3/4] Initializing executor and pipeline...
      Pipeline ready (executor enabled: True)
      Executor mode: LIVE
      Broker symbols registered: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']

[4/4] Starting live loop...
      MT5 streaming mode: polling for new completed bars.
      Press Ctrl+C to stop gracefully.
```

---

## 🔍 FIRST 10 MINUTES - WATCH FOR

### **✅ Normal Behavior**:
1. **Structure Detection Logs**:
   ```json
   {"event": "structure_detected", "type": "rejection", "symbol": "EURUSD"}
   {"event": "structure_detected", "type": "order_block", "symbol": "XAUUSD"}
   ```

2. **Decision Generation Logs**:
   ```json
   {"event": "decision_generated", "symbol": "EURUSD", "type": "BUY", "rr": 2.5}
   ```

3. **Execution Logs**:
   ```json
   {"event": "trade_executed_enhanced", "symbol": "EURUSD", "exit_method": "rejection"}
   ```

4. **No FTMO Warnings**:
   - Should NOT see `approaching_ftmo_daily_limit`
   - Should NOT see `ftmo_daily_limit_hit`

### **🚨 Red Flags - STOP IMMEDIATELY**:

1. **Mass Order Rejections** (>20% failure rate):
   ```json
   {"event": "order_rejected", "reason": "invalid_stops"}
   {"event": "order_rejected", "reason": "insufficient_margin"}
   ```
   **Action**: Stop bot, check MT5 account settings, verify margin requirements

2. **All Orders Clamped**:
   ```json
   {"event": "trade_executed_enhanced", "clamped": true, "sl_requested": 1.0840, "sl_final": 1.0850}
   ```
   **If 100% clamped**: Broker min stop distance too wide, may need buffer adjustment

3. **FTMO Warnings Appearing**:
   ```json
   {"event": "approaching_ftmo_daily_limit", "daily_dd_pct": -3.5}
   ```
   **Action**: Internal stops failed, risk calculation error - STOP AND DEBUG

4. **No Structures Detected** (after 30 minutes):
   ```json
   // No structure_detected logs at all
   ```
   **Action**: Data feed issue or detector disabled - check MT5 connection

5. **Python Errors/Exceptions**:
   ```
   Traceback (most recent call last):
   ...
   ```
   **Action**: Stop bot, send me the full error + log file

---

## 📊 MONITORING PROTOCOL

### **First Hour** (Critical Window)
**Check Every 15 Minutes**:
- [ ] Structures being detected (at least 1-2 per symbol per hour)
- [ ] Orders executing successfully (>80% success rate)
- [ ] No FTMO warnings in logs
- [ ] No Python exceptions/crashes

**Quick Log Check**:
```bash
# Count executed trades
grep "trade_executed_enhanced" logs/live_mt5_*.json | wc -l

# Check for rejections
grep "order_rejected" logs/live_mt5_*.json

# Check for FTMO warnings
grep "ftmo" logs/live_mt5_*.json

# Check for errors
grep "ERROR" logs/live_mt5_*.json
```

### **First 10 Trades** (Quick Sanity Check)
**After ~10 trades executed**, verify:
1. ✅ Exit method distribution looks normal (mix of rejection/OB/FVG/ATR/legacy)
2. ✅ RR values are reasonable (most >1.5)
3. ✅ Clamp rate <50% (not all orders clamped)
4. ✅ No repeated errors/warnings

**If Everything Looks Good**: Let it run for full 50-100 trades  
**If Red Flags**: Stop and send me the log file immediately

### **Daily Check** (While Running)
**Once per day**:
- [ ] Check log file size (should grow steadily)
- [ ] Verify bot is still running (no crashes)
- [ ] Check MT5 terminal (still connected)
- [ ] Review any unusual log entries

---

## 📈 SUCCESS CRITERIA (After 50-100 Trades)

### **Must Pass**:
1. ✅ **Overall RR Pass Rate ≥ 90%**
2. ✅ **Structure + ATR RR Pass Rate = 100%** (match paper)
3. ✅ **Broker Rejection Rate ≤ 10%**
4. ✅ **Legacy Usage 20-35%** (within expected range)
5. ✅ **Zero FTMO Limit Breaches** (internal stops fire first)

### **Acceptable Variance**:
- **Slippage ≤ 2 points average** (FTMO spreads may be wider)
- **Clamp rate ≤ 30%** (some broker enforcement expected)
- **Execution rate ≥ 90%** (≤10% order failures)

### **Analysis Required**:
- **Clamp rate 30-50%**: Analyze if SL buffers need adjustment
- **Legacy usage 35-40%**: Consider MTF confluence sooner
- **RR pass 85-90%**: Investigate which methods failing

---

## 🛑 EMERGENCY STOP PROCEDURES

### **When to Stop Immediately**:
1. 🚨 FTMO warning logs appear
2. 🚨 Broker rejection rate >20%
3. 🚨 Python exceptions/crashes
4. 🚨 Unexpected drawdown (>-2% daily)
5. 🚨 All orders failing

### **How to Stop Gracefully**:
1. Press `Ctrl+C` in terminal (triggers graceful shutdown)
2. Wait for "Live Loop Summary" to print
3. Verify log file saved: `logs/live_mt5_YYYYMMDD_HHMMSS.json`
4. Check MT5 for any open positions (close manually if needed)

### **What to Send Me**:
1. Full log file: `logs/live_mt5_*.json`
2. Screenshot of error (if any)
3. Brief description of what you observed
4. Approximate trade count before stopping

---

## 📦 POST-RUN ANALYSIS (After 50-100 Trades)

### **What to Send Me**:
1. **Full log file**: `logs/live_mt5_YYYYMMDD_HHMMSS.json`
2. **Quick summary**:
   - Total trades executed
   - Any unusual behavior noticed
   - Screenshots of anything weird

### **What I'll Analyze**:
- Exit method performance matrix (RR pass rate by method)
- Clamp impact analysis (% clamped, average widening)
- RR pass rate comparison (FTMO vs Paper)
- Legacy usage trends (Engulfing vs BOS)
- FTMO guard behavior (should be zero events)
- Execution quality metrics (slippage, rejections)

### **Decision Tree**:
```
FTMO Results
├─ RR Pass Rate ≥ 90% & Low Clamp Impact
│  └─ ✅ System validated → Proceed to Phase 2B (MTF Confluence)
│
├─ RR Pass Rate ≥ 90% but High Clamp Impact (>50%)
│  └─ ⚠️ Adjust SL buffers → Re-test with wider buffers
│
├─ RR Pass Rate < 90% (Structure exits failing)
│  └─ 🔍 Debug exit planner → Check structure geometry
│
├─ Legacy Usage > 40%
│  └─ 🔍 Investigate detection → May need MTF confluence sooner
│
└─ FTMO Warnings Triggered
   └─ 🚨 Fix risk calculation → Internal stops not working
```

---

## ✅ FINAL PRE-LAUNCH STATUS

**System Health**: 🟢 Production-Ready  
**Paper Validation**: ✅ 94.77% RR Pass Rate (75 trades)  
**FTMO Compliance**: ✅ Shadow Limits Active  
**Enhanced Logging**: ✅ Full Observability  
**Exit Planner**: ✅ Structure-First with ATR Fallback  
**Risk Management**: ✅ Equity-Based with Daily Reset  

**Code Freeze**: 🔒 Active (No changes until data collected)  
**Launch Window**: 🕐 Monday 08:00-09:00 UTC (London Open)  
**Target**: 🎯 50-100 Clean Trades  
**Phase**: 📊 2A - FTMO Demo Validation  

---

## 🎯 REMEMBER

1. **This is validation, not optimization** - We're measuring, not changing
2. **Clean data is critical** - Don't launch during low liquidity or news
3. **Stop if red flags appear** - Better to debug early than burn through trades
4. **Trust the system** - Paper mode validated it, FTMO just confirms execution quality
5. **No new features** - Code is frozen until we collect 50-100 trades

---

**Everything is ready. See you Monday at London open. 🚀**

**Last Updated**: Dec 5, 2025 21:57 UTC  
**Status**: ✅ READY FOR LAUNCH
