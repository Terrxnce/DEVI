# Phase 1.5 Light Prep Checklist — No Code Changes

**Status**: ✅ READY FOR EOW (Oct 25)
**Purpose**: Prepare scaffolding for real MT5 integration (next week)
**Owner**: Cascade (Lead Developer)

---

## What's Already Built (Reuse)

### 3 Files Created Earlier ✅
- ✅ `infra/broker/mt5_connector.py` (MT5 connection handler)
- ✅ `infra/data/data_loader.py` (switchable data source)
- ✅ `scripts/pull_mt5_history.py` (fetch & validate history)

**Status**: Ready to use as-is. No changes needed today.

---

## EOW Prep Tasks (Oct 25, 30 min total)

### Task 1: Verify DataLoader Switch (5 min)

**File**: `infra/data/data_loader.py`

**Check**:
```python
# Verify this method exists and works
loader = DataLoader(mode="synthetic")  # Phase 1 (current)
loader = DataLoader(mode="mt5")        # Phase 1.5 (next week)
loader = DataLoader(mode="cache")      # Optional fallback
```

**Action**: ✅ Verify the switch is there (no code change).

---

### Task 2: Verify Pull Script (5 min)

**File**: `scripts/pull_mt5_history.py`

**Check**:
```bash
# Verify script exists and has help
python scripts/pull_mt5_history.py --help
```

**Expected Output**:
```
Usage: pull_mt5_history.py [OPTIONS]
  --symbol TEXT          Symbol (e.g., EURUSD)
  --timeframe TEXT       Timeframe (e.g., M15)
  --bars INTEGER         Number of bars (default: 1000)
  --output TEXT          Output file (default: data.json)
```

**Action**: ✅ Verify the interface (no code change).

---

### Task 3: Add DataLoader Config Section (10 min)

**File**: `configs/system.json`

**Add this section**:
```json
{
  "data_loader": {
    "mode": "synthetic",
    "synthetic": {
      "seed": 42,
      "volatility": 0.0008
    },
    "mt5": {
      "broker": "ICMarkets",
      "server": "ICMarkets-Demo",
      "account": "XXXXXXXX",
      "password": "XXXXXXXX",
      "timeout": 30
    },
    "cache": {
      "directory": "data/cache",
      "ttl_hours": 24
    }
  }
}
```

**Action**: ✅ Add this section to `configs/system.json` (no functional change, just config).

---

### Task 4: Create UTC Continuity Validator (5 min)

**File**: `scripts/validate_mt5_continuity.py` (NEW, simple)

**Purpose**: Validate UTC continuity in MT5 data (gaps, duplicates, ordering).

**Action**: ✅ Create this file (simple validation, no MT5 connection).

---

### Task 5: Optional Canary Job Setup (5 min)

**File**: `scripts/canary_job.py` (NEW, optional)

**Purpose**: Test downstream SL/TP + executor paths without touching main run.

**Action**: ✅ Create this file (optional, for early smoke test).

---

## Checklist (EOW Oct 25)

- [ ] Verify DataLoader switch exists (5 min)
- [ ] Verify pull_mt5_history.py interface (5 min)
- [ ] Add data_loader config section to system.json (10 min)
- [ ] Create validate_mt5_continuity.py (5 min)
- [ ] Create canary_job.py (optional, 5 min)
- [ ] Git commit: "Phase 1.5 prep: DataLoader switch + validation scripts"

**Total Time**: 30 min (or 25 min without canary)

---

## Phase 1.5 Execution Plan (Next Week, Oct 28-31)

### Monday (Oct 28): Pull Real Data

```bash
# Pull 1000 M15 bars for EURUSD from MT5
python scripts/pull_mt5_history.py \
  --symbol EURUSD \
  --timeframe M15 \
  --bars 1000 \
  --output data/mt5_eurusd_m15.json

# Validate continuity
python scripts/validate_mt5_continuity.py data/mt5_eurusd_m15.json
```

**Expected Output**:
```json
{
  "total_bars": 1000,
  "chronological_order": true,
  "gaps": [],
  "gap_count": 0,
  "duplicates": 0,
  "ohlc_valid": true,
  "status": "PASS"
}
```

---

### Tuesday (Oct 28): Switch DataLoader

```python
# In configs/system.json, change:
"data_loader": {
  "mode": "mt5"  # was "synthetic"
}

# Or use canary first:
python scripts/canary_job.py
# Then run with: python backtest_dry_run.py 1000 EURUSD --config configs/structure_canary.json
```

---

### Wednesday-Friday (Oct 29-31): Re-run 5-Day Dry-Run

```bash
# Same as Phase 1, but with real MT5 data
python backtest_dry_run.py 1000 EURUSD
# Repeat daily (Oct 29, 30, 31)
```

**Expected Outcomes**:
- ✅ Determinism still holds (100% match on 100-bar replay)
- ✅ Pass-rate 5-15% (real data, more structure)
- ✅ 0 validation errors
- ✅ All logs collected

---

### End of Week (Oct 31): Phase 1.5 Summary

```
Phase 1.5 Results:
  - Real MT5 data: 1000 bars, 0 gaps ✅
  - Determinism: 100% match ✅
  - Pass-rate: 8-12% (real data) ✅
  - Validation errors: 0 ✅
  - Ready for Phase 2 ✅
```

---

## Freeze Points (Protect Phase 1)

**Important**: Do NOT change any code during Phase 1 (Days 2-5).

- ✅ No config changes to structure.json (except data_loader section)
- ✅ No changes to pipeline.py
- ✅ No changes to detectors
- ✅ No changes to executor
- ✅ No changes to composite scorer

**All changes are additive only** (new files, new config sections).

---

## Files to Create (EOW)

| File | Purpose | Lines | Status |
|------|---------|-------|--------|
| `scripts/validate_mt5_continuity.py` | UTC continuity check | 50+ | ⏳ |
| `scripts/canary_job.py` | Optional canary setup | 40+ | ⏳ |
| `configs/system.json` (add section) | DataLoader config | 20+ | ⏳ |

**Total**: ~110 lines of new code (all simple, no logic changes).

---

## Next Week (Phase 1.5)

**Monday**: Pull real MT5 data
**Tuesday**: Switch DataLoader
**Wed-Fri**: Re-run 5-day dry-run with real data
**Friday EOD**: Phase 1.5 summary + ready for Phase 2

---

## Key Notes

- **No code changes today**: Phase 1 is still running (Days 2-5)
- **Additive only**: New files, new config sections
- **Scaffolding ready**: MT5 connector, data loader, pull script already exist
- **Next week**: Switch to real data, verify determinism holds, proceed to Phase 2

---

**Phase 1.5 Light Prep — Ready for EOW ✅**
