# ⚡ Monday Quick Start - FTMO Launch

## 🎯 5-Minute Launch Protocol

### **1. Update Config** (30 seconds)
**File**: `configs/system.json` (Line 12-15)

**Change**:
```json
"env": {
  "mode": "ftmo_demo",
  "account_size": 100000
}
```

### **2. Verify MT5** (1 minute)
- ✅ FTMO demo account loaded (100k balance)
- ✅ Green connection indicator
- ✅ Symbols visible: EURUSD, XAUUSD, GBPUSD, USDJPY
- ✅ 15m charts loaded with history

### **3. Launch Bot** (30 seconds)
```bash
python run_live_mt5.py --symbols EURUSD XAUUSD GBPUSD USDJPY --mode live --poll-seconds 10
```

### **4. Watch First 10 Minutes** (10 minutes)
✅ **Good Signs**:
- Structures detected
- Orders executing
- No FTMO warnings
- No errors

🚨 **Stop If**:
- >20% order rejections
- FTMO warnings appear
- Python errors
- No structures detected (after 30 min)

---

## 📊 Quick Log Checks

```bash
# Count trades
grep "trade_executed_enhanced" logs/live_mt5_*.json | wc -l

# Check for problems
grep "order_rejected" logs/live_mt5_*.json
grep "ftmo" logs/live_mt5_*.json
grep "ERROR" logs/live_mt5_*.json
```

---

## 🛑 Emergency Stop

**Press**: `Ctrl+C`  
**Send Me**: `logs/live_mt5_*.json` + description

---

## ✅ Success = 50-100 Trades

**Then**: Send me full log for analysis  
**Next**: Phase 2B (MTF Confluence)

---

**Launch Window**: Monday 08:00-09:00 UTC  
**Good Luck! 🚀**
