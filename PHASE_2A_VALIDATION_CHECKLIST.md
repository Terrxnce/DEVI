# Phase 2A Validation Run - Checklist
**Date**: 2025-12-09 23:58 UTC  
**Target**: 5-10 trades  
**Duration**: ~2-3 hours

---

## **Critical Success Criteria**

### **1. Zero Broker Errors** ✅/❌
```bash
# Check after run
grep -i "retcode.*10016\|retcode.*10019" logs/live_mt5_*.json
```
**Expected**: No matches  
**Status**: ⏳ Pending

---

### **2. XAUUSD Risk Calculation** ✅/❌
```bash
# Check XAUUSD margin checks
grep "XAUUSD" logs/live_mt5_*.json | grep "margin_check_passed\|margin_guard_blocked"
```
**Expected**: Risk % between 0.4-0.6% (for 0.5% target)  
**Previous Bug**: 498% (wrong contract size)  
**Status**: ⏳ Pending

---

### **3. Rescaling Logic** ✅/❌
```bash
# Check if rescaling occurs and succeeds
grep "order_send_volume_rescaled\|order_send_stops_adjusted" logs/live_mt5_*.json
```
**Expected**: If triggered, `new_sl_distance_pts >= min_required_pts`  
**Previous Bug**: 16pts < 30pts required  
**Status**: ⏳ Pending

---

### **4. Position Close Logging** ✅/❌
```bash
# Check position close events
grep "position_closed" logs/live_mt5_*.json | jq '{ticket, symbol, profit, close_reason}'
```
**Expected**: Every executed trade has a matching close event  
**Status**: ⏳ Pending

---

## **Detailed Validation Steps**

### **During Run**

**Real-time monitoring**:
```bash
tail -f logs/live_mt5_*.json | grep -E "order_send_result|position_closed|margin_check|10016|10019"
```

**Watch for**:
- ✅ `margin_check_passed` with reasonable risk %
- ✅ `order_send_result` with `retcode: 10009` (success)
- ❌ Any `retcode: 10016` or `10019`
- ✅ `position_closed` events after trades close

---

### **Post-Run Analysis**

#### **1. Error Check**
```bash
# Should return 0
grep -c "retcode.*10016" logs/live_mt5_*.json
grep -c "retcode.*10019" logs/live_mt5_*.json
```

#### **2. Margin Guard Validation**
```bash
# Extract all margin checks
grep "margin_check_passed" logs/live_mt5_*.json | jq '{symbol, total_risk_pct, new_trade_risk, open_positions}'
```

**Validate**:
- EURUSD/GBPUSD/USDJPY: `total_risk_pct` ≈ 0.5% per trade
- XAUUSD: `total_risk_pct` ≈ 0.5% per trade (NOT 498%)
- All symbols: `new_trade_risk` ≈ $490 (0.5% of $98k)

#### **3. Rescaling Validation**
```bash
# Check if any rescaling occurred
grep "order_send_volume_rescaled" logs/live_mt5_*.json | jq '{symbol, original_sl_distance_pts, new_sl_distance_pts}'
```

**Validate**:
- `new_sl_distance_pts >= 30` (broker minimum for most symbols)
- No 10016 errors after rescaling

#### **4. Position Close Reconciliation**
```bash
# Count executions
grep -c "order_send_result.*10009" logs/live_mt5_*.json

# Count closes
grep -c "position_closed" logs/live_mt5_*.json
```

**Validate**:
- Executed trades = Closed positions (or close events pending)
- Each close has: ticket, symbol, profit, close_reason

#### **5. MT5 History Cross-Check**
```python
# Run after session
python -c "
import MetaTrader5 as mt5
from datetime import datetime, timedelta
mt5.initialize()
deals = mt5.history_deals_get(datetime.now() - timedelta(hours=4), datetime.now())
print(f'MT5 Deals: {len(deals)}')
for d in deals:
    if d.entry == 1:  # OUT
        print(f'Ticket: {d.position_id}, Symbol: {d.symbol}, Profit: {d.profit:.2f}')
mt5.shutdown()
"
```

**Validate**: Logs match MT5 terminal history

---

## **Success Thresholds**

| Metric | Target | Status |
|--------|--------|--------|
| **Trades Executed** | 5-10 | ⏳ |
| **10016 Errors** | 0 | ⏳ |
| **10019 Errors** | 0 | ⏳ |
| **XAUUSD Risk %** | 0.4-0.6% | ⏳ |
| **Rescaling Success** | 100% if triggered | ⏳ |
| **Position Closes Logged** | 100% | ⏳ |

---

## **If Validation Passes**

Proceed to **Phase 2B: Full Validation Run**
- Duration: 6-8 hours
- Target: 30-50 trades
- Focus: Complete system validation under load

---

## **If Issues Found**

1. Document the issue
2. Implement fix
3. Rerun validation (5-10 trades)
4. Repeat until clean

---

## **Launch Command**

```bash
python run_live_mt5.py --symbols EURUSD XAUUSD GBPUSD USDJPY --mode live --poll-seconds 10
```

---

**Status**: 🟢 Ready to launch validation run
