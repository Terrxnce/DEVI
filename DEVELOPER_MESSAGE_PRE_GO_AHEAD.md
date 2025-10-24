# Message to Dev — Pre-Go-Ahead Confirmation

**Date**: Oct 22, 2025, 11:42 AM UTC+01:00
**Status**: Ready for Alignment Review
**Purpose**: Confirm setup, data, and expectations before Phase 1 + Phase 2

---

## Hey Dev,

Before we fully green-light Phase 1 + Phase 2, I need you to confirm the following so we're aligned on setup, data, and expectations. This is a **7-point checklist** covering everything from MT5 connectivity to structure exits.

---

## 🔹 1. MT5 Data Source

**Questions**:
- Which MT5 server/account are you pulling historical data from?
- Are candles coming from MT5 directly (via MetaTrader5 Python module) or a local cache/mock feed?
- Can you currently fetch 1,000 M15 bars per symbol without gaps or duplicates?
- Are timestamps stored in UTC or broker time?

**What I Need**:
- [ ] Confirm MT5 server name (e.g., "ICMarkets-Demo", "XM-Live")
- [ ] Confirm account type (Demo or Live)
- [ ] Verify connection is active and stable
- [ ] **For Phase 1: Use MT5 live feed (not mock)**
- [ ] Implement `DataLoader` class with source selection (mt5, cache, mock)
- [ ] Create `test_data_quality.py` to verify 1000 bars, no gaps, no duplicates
- [ ] **All timestamps must be UTC** (convert broker time on ingestion)

**Expected Outcome**:
- 1000 M15 bars = 1000 consecutive 15-minute candles
- 0 gaps, 0 duplicates
- Valid OHLC relationships (low ≤ high, open/close within range)

---

## 🔹 2. Broker Configuration

**Questions**:
- Is `broker_symbols.json` updated with min stop, step, volume limits, and spread for all six pairs?
- Do we need any additional pairs for testing?
- Is the symbol registration step running automatically at startup?

**What I Need**:
- [ ] Confirm all 6 pairs registered: EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, XAUUSD
- [ ] Each pair has: bid, ask, point, digits, volume_min, volume_max, volume_step, min_stop_distance, max_stop_distance, spread
- [ ] Create `test_broker_config.py` to validate all fields
- [ ] Symbol registration called in `pipeline.__init__()` with logging
- [ ] **For Phase 1: Use only 6 FX pairs** (add more later if needed)

**Expected Outcome**:
- All 6 pairs registered at startup
- Validation passes (all fields present, no nulls)
- Logged: "✅ All symbols registered"

---

## 🔹 3. Session Windows & Timezone

**Questions**:
- Please confirm the current session time windows (ASIA, LONDON, NY_AM, NY_PM) in UTC.
- Verify they align with the config in `structure.json`.

**What I Need**:
- [ ] Confirm session windows (UTC):
  - ASIA: 22:00 UTC (Sun) - 06:00 UTC (Mon-Fri)
  - LONDON: 08:00 UTC - 17:00 UTC (Mon-Fri)
  - NY_AM: 13:00 UTC - 17:00 UTC (Mon-Fri)
  - NY_PM: 21:00 UTC - 06:00 UTC (next day)
- [ ] Session names in `structure.json` match rotator (ASIA, LONDON, NY_AM, NY_PM)
- [ ] Each session has min_composite + min_final_score thresholds
- [ ] Create `test_config_alignment.py` to verify alignment

**Expected Outcome**:
- Session rotator and config are aligned
- No typos or mismatches
- Validation passes: "✅ Session config alignment verified"

---

## 🔹 4. Execution Mode & Validation

**Questions**:
- Confirm `execution.mode = "dry-run"` for Phase 1.
- Confirm executor validations (volume, RR, SL/TP distance) are active and logging results.
- Expected outcome = 0 validation errors across 5 days.

**What I Need**:
- [ ] `system.json` has `"execution": {"mode": "dry-run"}`
- [ ] Logged at startup: "Execution mode: dry-run"
- [ ] Executor never sends to MT5 in dry-run mode
- [ ] All validations active:
  - Volume (min/max/step)
  - RR (≥1.5)
  - SL/TP distance (min/max)
  - Price side (BUY/SELL)
- [ ] All failures logged with reason
- [ ] Create `test_executor_validation.py` to verify all validations
- [ ] Track validation_passed / validation_failed in pipeline
- [ ] Log daily summary with counts

**Expected Outcome**:
- 0 validation errors across 5 days
- All orders pass validation
- If any fail, investigate immediately

---

## 🔹 5. Determinism Check

**Questions**:
- Are we ready to run a determinism replay test?
- (100 bars → same structures + scores + decisions on rerun.)
- Please include a simple diff output example once tested.

**What I Need**:
- [ ] Create `test_determinism.py`
- [ ] Run same 100 bars twice
- [ ] Compare: structure IDs, composite scores, decisions
- [ ] **Expected: 100% match**
- [ ] Generate diff output in this format:

```
Determinism Test Results
========================
Run 1: 100 bars → 8 decisions
Run 2: 100 bars → 8 decisions

Decision Comparison:
  Decision 0: ✅ MATCH (structure_id=OB_EURUSD_M15_42_abc123, composite=0.71, entry=1.0948)
  Decision 1: ✅ MATCH (structure_id=FVG_EURUSD_M15_55_def456, composite=0.68, entry=1.0955)
  Decision 2: ✅ MATCH (structure_id=OB_EURUSD_M15_68_ghi789, composite=0.73, entry=1.0962)
  ...
  Decision 7: ✅ MATCH (structure_id=UZR_EURUSD_M15_98_jkl012, composite=0.70, entry=1.0971)

Overall: ✅ DETERMINISM VERIFIED (100% match)
```

**Expected Outcome**:
- Determinism test passes
- 100% match on replay
- Diff output shows all decisions match

---

## 🔹 6. Logging & Artifacts

**Questions**:
- Confirm these outputs are currently working:
  - gate_eval (per-bar)
  - decision (per trade)
  - dry_run_summary (EOD)
  - Hourly mini-summary logs (pass-rate, errors)
- Where are logs stored? (Local /logs dir or remote path?)

**What I Need**:
- [ ] All 4 log types working:
  - gate_eval.jsonl (per-bar, ~240 per day)
  - decision.jsonl (per trade, ~10-50 per day)
  - dry_run_summary.jsonl (EOD, 1 per day)
  - hourly_summary.jsonl (per hour, 24 per day)
- [ ] Create `test_logging_outputs.py` to verify all outputs
- [ ] Logs stored in `c:\Users\Index\DEVI\logs\`
- [ ] Rotated: 100MB per file, keep 10 backups
- [ ] Format: JSONL (one JSON object per line)

**Expected Outcome**:
- All log files created
- All logs are valid JSONL
- Rotation working correctly

---

## 🔹 7. Structure Exits Prep (Phase 2)

**Questions**:
- For the upcoming structure-first SL/TP:
  - Do you already have the placeholder or feature flag (`use_structure_exits`) set?
  - Can we start with OB + FVG only in Week 2, leaving Engulf/UZR/Sweep for later?
  - Will post-clamp RR validation reject trades that fall below 1.5 R?

**What I Need**:
- [ ] Add feature flag to `configs/structure.json`:
  ```json
  {
    "sltp_planning": {
      "use_structure_exits": false,
      "structure_exit_types": ["order_block", "fair_value_gap"],
      "atr_fallback_enabled": true
    }
  }
  ```
- [ ] **Phase 1**: use_structure_exits = false (ATR-only exits)
- [ ] **Phase 2 Week 1**: use_structure_exits = true, types = [OB, FVG]
- [ ] **Phase 2 Week 2**: expand types = [OB, FVG, Engulfing, UZR, Sweep]
- [ ] Post-clamp RR validation:
  - After broker clamp, re-check RR
  - If RR < 1.5, **reject trade** (don't degrade silently)
  - Log rejection reason

**Expected Outcome**:
- Feature flag works correctly
- OB + FVG exits can be enabled independently
- Post-clamp RR validation rejects low-RR trades

---

## Pre-Go-Ahead Sign-Off Checklist

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

## Next Steps

**Once you confirm all 7 areas**:
1. We'll have full alignment on setup and expectations
2. Phase 1 can start immediately (1 week live dry-run)
3. Phase 2 can follow (structure-first exits, 3-5 days)
4. Phase 3 can parallelize (profit protection + recovery, 3-4 days)
5. Phase 4 can execute (paper → live ramp, 2 weeks)

**Timeline**:
- Week 1: Phase 1 (live dry-run on real MT5 data)
- Week 2-3: Phase 2 (structure-first SL/TP)
- Week 4-5: Phase 3 (profit protection + recovery)
- Week 6-7+: Phase 4 (paper → live ramp)

---

**Status**: Ready for Developer Confirmation ✅

Please confirm all 7 areas and we'll green-light Phase 1 + Phase 2.
