# Phase 2B - Continuation Plan
**Date**: 2025-12-11  
**Status**: Soft stop disabled, ready to continue

---

## **Changes Made**

### **Disabled Daily Soft Stop**
```json
// configs/system.json
"daily_soft_stop_pct": -100.0,  // Was: -1.0
"daily_hard_stop_pct": -100.0   // Was: -2.0
```

**Why**: Soft stop at -1% blocked 88 trades after only 7 executions. Need 30-50 trades for valid analysis.

**Safety**: FTMO limits still active (-5% daily, -10% total).

---

## **Launch Phase 2B Continuation**

### **Command**
```bash
python run_live_mt5.py --symbols EURUSD XAUUSD GBPUSD USDJPY --mode live --poll-seconds 10
```

### **Target**
- **30-50 total trades** (23-43 more needed)
- **12-24 hours** estimated duration
- **Stop manually** after target reached

### **Monitoring**

**Real-time trade count**:
```bash
findstr /C:"order_send_result" logs\live_mt5_*.json | find /C "10009"
```

**Watch for errors**:
```bash
findstr /C:"10016" /C:"10019" logs\live_mt5_*.json
```

**Check equity**:
```bash
python -c "import MetaTrader5 as mt5; mt5.initialize(); acc = mt5.account_info(); print(f'Equity: ${acc.equity:,.2f}, DD: {((acc.equity/97916.02)-1)*100:.2f}%'); mt5.shutdown()"
```

---

## **What to Expect**

### **Trade Frequency**
Based on first run:
- **7 trades in 2.5 hours** = ~2.8 trades/hour
- **To get 30 trades**: ~11 hours
- **To get 50 trades**: ~18 hours

### **Risk Profile**
- **Per trade**: 0.5% risk
- **Max open risk**: 4.5% (9 positions)
- **FTMO daily limit**: -5%
- **FTMO total limit**: -10%

### **Expected Structures**
From first run, system detected:
- Order Block: 16
- Rejection: 28
- ATR: 20
- FVG: 9
- Legacy: 22

**Total**: ~95 structures in 11 hours

---

## **Stop Conditions**

### **Success: 30-50 Trades**
Stop manually when you hit 30-50 successful executions.

### **FTMO Limits**
System will auto-stop if:
- Daily loss hits -5%
- Total loss hits -10%

### **Manual Stop**
Stop if you see:
- Repeated broker errors (10016/10019)
- Margin issues
- Unusual behavior

---

## **After Completion**

Send me the log file for full analysis:
- Win rate by symbol
- Win rate by exit method
- Drawdown patterns
- Symbol selection decisions
- Exit method optimization
- Phase 2B+ recommendations

---

## **Quick Reference**

**Start**:
```bash
python run_live_mt5.py --symbols EURUSD XAUUSD GBPUSD USDJPY --mode live --poll-seconds 10
```

**Check trades**:
```bash
findstr /C:"order_send_result" logs\live_mt5_*.json | find /C "10009"
```

**Check equity**:
```bash
python -c "import MetaTrader5 as mt5; mt5.initialize(); acc = mt5.account_info(); print(f'${acc.equity:,.2f}'); mt5.shutdown()"
```

**Stop**: `Ctrl+C` when you hit 30-50 trades

---

**Status**: ✅ **READY TO LAUNCH**
