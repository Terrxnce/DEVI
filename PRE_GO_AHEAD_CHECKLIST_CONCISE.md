# D.E.V.I 2.0 — Pre-Go-Ahead Confirmation Checklist (Concise)

**Date**: Oct 22, 2025, 11:42 AM UTC+01:00
**Status**: Pre-Implementation Validation

---

## 🔹 1. MT5 Data Source

**1a. Which MT5 server/account?**
- [ ] Confirm MT5 server name (e.g., "ICMarkets-Demo")
- [ ] Confirm account type (Demo/Live)
- [ ] Verify connection is active

**1b. Data source: MT5 live, cache, or mock?**
- [ ] **For Phase 1: Use MT5 live feed (not mock)**
- [ ] Implement `DataLoader` class with source selection

**1c. Can fetch 1000 M15 bars without gaps/duplicates?**
- [ ] Create `test_data_quality.py` to verify
- [ ] Check: no gaps, no duplicates, valid OHLC relationships
- [ ] **Expected**: 1000 bars = 1000 consecutive 15-min candles

**1d. Timestamps in UTC or broker time?**
- [ ] **All timestamps must be UTC**
- [ ] Convert broker time → UTC on ingestion
- [ ] Log timezone conversion at startup

---

## 🔹 2. Broker Configuration

**2a. broker_symbols.json complete?**
- [ ] All 6 pairs registered: EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, XAUUSD
- [ ] Each has: bid, ask, point, digits, volume_min/max/step, min/max_stop_distance, spread
- [ ] Create `test_broker_config.py` to validate

**2b. Additional pairs needed?**
- [ ] **For Phase 1: Use only 6 FX pairs**
- [ ] Add more pairs later if needed

**2c. Symbol registration at startup?**
- [ ] Call `executor.register_symbol_info()` for all symbols in `pipeline.__init__()`
- [ ] Log success/failure for each symbol

---

## 🔹 3. Session Windows & Timezone

**3a. Session windows in UTC (confirm these):**
- [ ] ASIA: 22:00 UTC (Sun) - 06:00 UTC (Mon-Fri)
- [ ] LONDON: 08:00 UTC - 17:00 UTC (Mon-Fri)
- [ ] NY_AM: 13:00 UTC - 17:00 UTC (Mon-Fri)
- [ ] NY_PM: 21:00 UTC - 06:00 UTC (next day)

**3b. Align with structure.json?**
- [ ] Session names match: ASIA, LONDON, NY_AM, NY_PM
- [ ] Each session has min_composite + min_final_score thresholds
- [ ] Create `test_config_alignment.py` to verify

---

## 🔹 4. Execution Mode & Validation

**4a. execution.mode = "dry-run"?**
- [ ] `system.json` has `"execution": {"mode": "dry-run"}`
- [ ] Logged at startup
- [ ] Executor never sends to MT5

**4b. Validations active?**
- [ ] Volume validation (min/max/step)
- [ ] RR validation (≥1.5)
- [ ] SL/TP distance validation (min/max)
- [ ] Price side validation (BUY/SELL)
- [ ] All failures logged with reason
- [ ] Create `test_executor_validation.py` to verify

**4c. Expected: 0 validation errors across 5 days**
- [ ] Track validation_passed / validation_failed
- [ ] Log daily summary with counts
- [ ] **If any fail, investigate immediately**

---

## 🔹 5. Determinism Check

**5a. Replay test ready?**
- [ ] Create `test_determinism.py`
- [ ] Run same 100 bars twice
- [ ] Compare: structure IDs, composite scores, decisions
- [ ] **Expected: 100% match**

**5b. Diff output example:**
```
Determinism Test Results
========================
Run 1: 100 bars → 8 decisions
Run 2: 100 bars → 8 decisions

Decision 0: ✅ MATCH (structure_id=OB_EURUSD_M15_42_abc123, composite=0.71)
Decision 1: ✅ MATCH (structure_id=FVG_EURUSD_M15_55_def456, composite=0.68)
...
Overall: ✅ DETERMINISM VERIFIED (100% match)
```

---

## 🔹 6. Logging & Artifacts

**6a. All outputs working?**
- [ ] gate_eval.jsonl (per-bar, 240 per day)
- [ ] decision.jsonl (per trade, ~10-50 per day)
- [ ] dry_run_summary.jsonl (EOD, 1 per day)
- [ ] hourly_summary.jsonl (per hour, 24 per day)
- [ ] Create `test_logging_outputs.py` to verify

**6b. Log storage location?**
- [ ] Logs stored in `c:\Users\Index\DEVI\logs\`
- [ ] Rotated: 100MB per file, keep 10 backups
- [ ] Format: JSONL (one JSON object per line)

---

## 🔹 7. Structure Exits Prep (Phase 2)

**7a. Feature flag use_structure_exits?**
- [ ] Add to `configs/structure.json`
- [ ] Default: `false` (Phase 1)
- [ ] Phase 2 Week 1: set to `true` with OB+FVG only
- [ ] Phase 2 Week 2: expand to Engulf+UZR+Sweep

**7b. OB + FVG only in Week 2?**
- [ ] Config supports selective structure types
- [ ] Example:
  ```json
  {
    "sltp_planning": {
      "use_structure_exits": false,
      "structure_exit_types": ["order_block", "fair_value_gap"],
      "atr_fallback_enabled": true
    }
  }
  ```

**7c. Post-clamp RR validation?**
- [ ] After broker clamp, re-check RR
- [ ] If RR < 1.5, **reject trade** (don't degrade silently)
- [ ] Log rejection reason
- [ ] Example:
  ```python
  # Calculate SL/TP from structure
  sl, tp = calculate_structure_exits(...)
  
  # Broker clamp
  sl_clamped = clamp_to_broker_limits(sl, ...)
  tp_clamped = clamp_to_broker_limits(tp, ...)
  
  # Re-check RR
  rr = calculate_rr(entry, sl_clamped, tp_clamped)
  if rr < 1.5:
      logger.warning(f"Post-clamp RR too low: {rr} < 1.5, rejecting trade")
      return None  # Reject
  ```

---

## Pre-Go-Ahead Sign-Off

**Developer Checklist** (before Phase 1):
- [ ] MT5 data source verified (1000 bars, no gaps)
- [ ] Broker symbols registered (all 6 pairs)
- [ ] Session windows confirmed (UTC)
- [ ] Execution mode = dry-run
- [ ] Validations active (volume, RR, SL/TP)
- [ ] Determinism test passing (100% match)
- [ ] All logging outputs working
- [ ] Feature flag for structure exits ready

**Test Suite** (run before Phase 1):
- [ ] `test_data_quality.py` ✅
- [ ] `test_broker_config.py` ✅
- [ ] `test_config_alignment.py` ✅
- [ ] `test_executor_validation.py` ✅
- [ ] `test_determinism.py` ✅
- [ ] `test_logging_outputs.py` ✅

**Expected Phase 1 Outcomes**:
- ✅ 0 validation errors across 5 days
- ✅ Pass-rate 5-15% (noise filter healthy)
- ✅ RR compliance 100% ≥1.5
- ✅ Determinism verified (replay tests pass)
- ✅ All logs collected and analyzed

---

**Status**: Ready for Phase 1 Go-Ahead ✅
