# Phase 2: FTMO Demo Pre-Flight Check
**Date**: 2025-12-09 19:09 UTC  
**Status**: ✅ READY TO LAUNCH

---

## System Configuration

### MT5 Connection
- **Account**: 1520843035
- **Server**: FTMO-Demo2
- **Leverage**: 1:100
- **Status**: ✅ Connected

### Environment Settings
- **Mode**: `ftmo_demo`
- **Account Size**: $98,639
- **Real Orders**: `enabled` (true)

### Risk Parameters
- **Per Trade Risk**: 0.5% ($493.20)
- **Per Symbol Cap**: 1.5% ($1,479.59)
- **Daily Soft Stop**: -1.0% ($986.39)
- **Daily Hard Stop**: -2.0% ($1,972.78)

### FTMO Limits
- **Max Daily Loss**: -5.0% ($4,931.95)
- **Max Total Loss**: -10.0% ($9,863.90)
- **Profit Target**: +10.0% ($9,863.90)

---

## Execution Guards (ALL ENABLED)

### 1. Broker Stop-Level Guard ✅
- **Enabled**: true
- **Spread Buffer**: 2.0x
- **Min Stop Level**: 10 points
- **Log Rejections**: true

### 2. Margin Guard ✅
- **Enabled**: true
- **Min Margin Level**: 200%
- **Max Free Margin Usage**: 30%
- **Max Total Open Risk**: 4.5%
- **Log Blocked Trades**: true

### 3. Position Close Tracking ✅
- **Enabled**: true
- **Check Interval**: 10 seconds
- **Log All Closes**: true
- **Track Close Reasons**: true

### 4. Legacy Exit Fallback ✅
- **Enabled**: true
- **Fallback to ATR**: true
- **Reject if No Fallback**: false
- **Log Fallback Reasons**: true

### 5. SL/TP Rescaling ✅
- **Enabled**: true
- **Max Attempts**: 3
- **Widening Factors**: [1.0, 1.2, 1.6, 2.4]
- **Maintain Risk via Volume**: true
- **Log Each Attempt**: true

---

## Run Command

```bash
python run_live_mt5.py --symbols EURUSD XAUUSD GBPUSD USDJPY --mode live --poll-seconds 10
```

---

## Target Metrics

- **Duration**: 4-6 hours
- **Target Trades**: 20-30 real executions
- **Symbols**: EURUSD, XAUUSD, GBPUSD, USDJPY

---

## Critical Monitoring

### Real-Time Monitor
```bash
tail -f logs/live_mt5_*.json | grep -E "order_send_result|position_closed|margin_guard|broker_stop"
```

### Post-Run Checks

**1. Zero Broker Errors (CRITICAL)**
```bash
grep -i "retcode.*10016\|retcode.*10019" logs/live_mt5_*.json
```
Expected: **No matches**

**2. Margin Guard Activity**
```bash
grep "margin_check_passed\|margin_guard_blocked" logs/live_mt5_*.json | wc -l
```
Expected: **Multiple margin_check_passed events**

**3. Broker Stop Checks**
```bash
grep "broker_stop_check\|sl_too_close_for_broker\|tp_too_close_for_broker" logs/live_mt5_*.json | wc -l
```
Expected: **At least some checks logged**

**4. Position Close Logging**
```bash
grep "position_closed" logs/live_mt5_*.json | jq '{ticket, symbol, profit, close_reason}'
```
Expected: **Every executed trade has a close event**

---

## Post-Run Analysis Plan

### 1. Guard Behavior Report
- Margin checks: passed vs blocked
- Broker stop checks: passed vs failed
- Position close reconciliation with MT5 history

### 2. Legacy Usage Analysis
- % by symbol
- % by time-of-day
- RR pass rate by exit method
- Exit planner rejection breakdown

### 3. Execution Quality
- Total trades vs closed positions
- Guard block rate
- Error-free execution confirmation

---

## Status: ✅ ALL SYSTEMS GO

**Ready to launch Phase 2 FTMO demo run!** 🚀
