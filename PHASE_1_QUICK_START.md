# Phase 1 Quick Start — Dry-Run Backtest

**Status**: ✅ Ready to Execute
**Data Source**: Synthetic (Deterministic)
**Target**: ≥95% pass rate, RR ≥1.5, 0 invalid SL/TP

---

## 🚀 Run Phase 1 Backtest

### Command
```bash
python backtest_dry_run.py 1000 EURUSD
```

### What It Does
1. Generates 1000 synthetic M15 bars (deterministic)
2. Processes through full pipeline (detection → scoring → execution)
3. Validates each decision against broker rules
4. Logs `order_validation_passed/failed` events
5. Outputs summary with metrics

### Expected Output
```
Pass rate: 95-96% ✅
Avg RR: 1.75-1.85 ✅
Errors: 0-2 (expected) ✅
Execution latency: <1ms ✅
```

---

## ✅ Data Source Confirmation

| Aspect | Value |
|--------|-------|
| **Source** | Synthetic (procedural generation) |
| **Determinism** | ✅ YES (same candles every run) |
| **Timeframe** | M15 |
| **Bars** | 1000 |
| **Time Range** | Last 10 days (from now) |
| **Volatility** | Simulated (realistic) |
| **Timestamps** | Sequential, chronological |

---

## 🔄 Verify Determinism

**Run 1**:
```bash
python backtest_dry_run.py 1000 EURUSD > run1.txt
```

**Run 2**:
```bash
python backtest_dry_run.py 1000 EURUSD > run2.txt
```

**Compare**:
```bash
diff run1.txt run2.txt
# Should output: (no differences)
```

**Expected**: Identical results (same bars, same decisions, same metrics)

---

## 📊 Success Criteria

- ✅ Pass rate ≥95%
- ✅ All RR ≥1.5
- ✅ 0 invalid SL/TP
- ✅ Logs contain validation events
- ✅ Execution latency <1ms
- ✅ Determinism verified (run twice = same results)

---

## 📁 Output Files

**Logs**:
```
logs/dry_run_backtest_20251021_HHMMSS.json
```

**Contains**:
- `order_validation_passed` events (valid orders)
- `order_validation_failed` events (invalid orders)
- `dry_run_summary` (metrics at session close)

---

## 🔍 What to Check

### Metrics
```json
{
  "pass_rate": 0.96,
  "total_orders": 50,
  "passed": 48,
  "failed": 2,
  "avg_rr": 1.78,
  "min_rr": 1.50,
  "max_rr": 2.45
}
```

### Errors (Expected)
```json
{
  "RR 1.0 < min 1.5": 1,
  "SL distance 30 pts < min 50 pts": 1
}
```

### Determinism
- Run 1 metrics = Run 2 metrics ✅
- Same structure detections ✅
- Same decisions ✅

---

## 📈 Next Steps

### After Phase 1 Clean ✅
1. Deploy in live dry-run for 1 week
2. Monitor daily summaries
3. Validate 0 errors for 5-7 days
4. Then: AI integration → Paper → Live

### Phase 2 (Optional, After Phase 1 Clean)
- Implement MT5 data loader
- Run backtest with real historical data
- Compare synthetic vs. real metrics
- Validate executor handles real market conditions

---

## 📞 Troubleshooting

### Pass Rate <95%
1. Check failed orders in logs
2. Identify error pattern (RR, SL distance, volume, etc.)
3. Fix root cause
4. Re-run backtest

### RR <1.5 for Any Order
1. Check SL/TP planning logic
2. Verify min_rr config (should be 1.5)
3. Adjust SL/TP planning

### Determinism Mismatch
1. Check for randomness in code
2. Verify no external API calls
3. Ensure Decimal precision
4. Re-run both times

---

## 🎯 Timeline

**Phase 1** (Today): Controlled backtest → collect metrics
**Phase 2** (This week): Live dry-run for 1 week → monitor daily
**Phase 3** (Next week): AI integration (if clean) → LLaMA reasoning
**Phase 4** (Week 3+): Paper → Live (if AI ready)

---

**Ready to execute. Run the command above and share the summary JSON.** 🚀
