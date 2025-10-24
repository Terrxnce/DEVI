# Phase 1.5 Light Prep — No Code Changes Today

**Date**: Oct 22, 2025
**Purpose**: Prepare scaffolding for real MT5 integration (next week)
**Owner**: Cascade (Lead Developer)
**Status**: Ready for EOW (Oct 25)

---

## What's Already Built (Reuse)

### 3 Files Created (Earlier)
- ✅ `infra/broker/mt5_connector.py` (MT5 connection handler)
- ✅ `infra/data/data_loader.py` (switchable data source)
- ✅ `scripts/pull_mt5_history.py` (fetch & validate history)

**No changes needed today.** These are ready to use as-is.

---

## Light Prep Tasks (EOW, Oct 25)

### Task 1: Verify DataLoader Switch (5 min)

**File**: `infra/data/data_loader.py`

**Check**:
```python
# Verify this method exists and works
loader = DataLoader(mode="synthetic")  # Phase 1 (current)
loader = DataLoader(mode="mt5")        # Phase 1.5 (next week)
loader = DataLoader(mode="cache")      # Optional fallback
```

**Action**: No code change. Just verify the switch is there.

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

**Action**: No code change. Just verify the interface.

### Task 3: Create DataLoader Config Switch (10 min)

**File**: `configs/system.json` (add section)

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

**Action**: Add this section to `configs/system.json` (no functional change, just config).

### Task 4: Create UTC Continuity Report Template (10 min)

**File**: `scripts/validate_mt5_continuity.py` (NEW, simple)

```python
#!/usr/bin/env python3
"""
Validate UTC continuity in MT5 data.
Checks for gaps, duplicates, and timestamp ordering.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

def validate_continuity(data_file):
    """Validate UTC continuity in OHLCV data."""
    with open(data_file) as f:
        data = json.load(f)
    
    bars = data.get("bars", [])
    
    # Check 1: Chronological order
    timestamps = [bar["timestamp"] for bar in bars]
    is_ordered = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
    
    # Check 2: Gaps (15-min intervals)
    gaps = []
    for i in range(len(timestamps)-1):
        t1 = datetime.fromisoformat(timestamps[i])
        t2 = datetime.fromisoformat(timestamps[i+1])
        if (t2 - t1) != timedelta(minutes=15):
            gaps.append({"index": i, "gap_minutes": (t2 - t1).total_seconds() / 60})
    
    # Check 3: Duplicates
    duplicates = len(timestamps) - len(set(timestamps))
    
    # Check 4: OHLC validity
    ohlc_valid = all(
        bar["low"] <= bar["open"] <= bar["high"] and
        bar["low"] <= bar["close"] <= bar["high"]
        for bar in bars
    )
    
    report = {
        "file": str(data_file),
        "total_bars": len(bars),
        "chronological_order": is_ordered,
        "gaps": gaps,
        "gap_count": len(gaps),
        "duplicates": duplicates,
        "ohlc_valid": ohlc_valid,
        "status": "PASS" if (is_ordered and not gaps and duplicates == 0 and ohlc_valid) else "FAIL"
    }
    
    return report

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: validate_mt5_continuity.py <data_file>")
        sys.exit(1)
    
    report = validate_continuity(sys.argv[1])
    print(json.dumps(report, indent=2))
```

**Action**: Create this file (simple validation, no MT5 connection).

### Task 5: Optional Canary Job Setup (15 min)

**File**: `scripts/canary_job.py` (NEW, optional)

```python
#!/usr/bin/env python3
"""
Canary job: Test downstream SL/TP + executor paths without touching main run.
Uses use_structure_exits=false + min_composite threshold nudge (-0.02).
"""

import json
from pathlib import Path

def setup_canary_config():
    """Create a canary config with threshold nudge."""
    config_file = Path("configs/structure.json")
    with open(config_file) as f:
        config = json.load(f)
    
    # Nudge: Lower min_composite by 0.02 to trigger more decisions
    for session in ["ASIA", "LONDON", "NY_AM", "NY_PM"]:
        if "scoring" in config and "scales" in config["scoring"]:
            scales = config["scoring"]["scales"]["M15"]["fx"][session]
            scales["min_composite"] -= 0.02
    
    # Ensure use_structure_exits = false (Phase 1)
    if "sltp_planning" not in config:
        config["sltp_planning"] = {}
    config["sltp_planning"]["use_structure_exits"] = False
    
    # Save canary config
    canary_file = Path("configs/structure_canary.json")
    with open(canary_file, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"Canary config created: {canary_file}")
    print(f"Changes: min_composite -0.02 per session, use_structure_exits=false")
    return canary_file

if __name__ == "__main__":
    setup_canary_config()
```

**Action**: Create this file (optional, for early smoke test).

---

## EOW Checklist (Oct 25)

- [ ] Verify DataLoader switch exists (5 min)
- [ ] Verify pull_mt5_history.py interface (5 min)
- [ ] Add data_loader config section to system.json (10 min)
- [ ] Create validate_mt5_continuity.py (10 min)
- [ ] Create canary_job.py (optional, 15 min)
- [ ] Git commit: "Phase 1.5 prep: DataLoader switch + validation scripts"

---

## Phase 1.5 Execution Plan (Next Week, Oct 28)

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

## No Code Changes Today

**Important**: Do NOT change any code today. Just:
1. Verify existing scaffolding
2. Add config section
3. Create simple validation scripts
4. Prepare for next week

**Reason**: Phase 1 is still running (Days 2-5). Any code changes could break determinism or introduce new bugs.

---

## Freeze Points (Protect Phase 1)

- ✅ No config changes to structure.json (except data_loader section)
- ✅ No changes to pipeline.py
- ✅ No changes to detectors
- ✅ No changes to executor
- ✅ No changes to composite scorer

**All changes are additive only** (new files, new config sections).

---

## Files to Create (EOW)

| File | Purpose | Lines |
|------|---------|-------|
| `scripts/validate_mt5_continuity.py` | UTC continuity check | 50+ |
| `scripts/canary_job.py` | Optional canary setup | 40+ |
| `configs/system.json` (add section) | DataLoader config | 20+ |

**Total**: ~110 lines of new code (all simple, no logic changes).

---

## Next Week (Phase 1.5)

**Monday**: Pull real MT5 data
**Tuesday**: Switch DataLoader
**Wed-Fri**: Re-run 5-day dry-run with real data
**Friday EOD**: Phase 1.5 summary + ready for Phase 2

---

**Phase 1.5 Light Prep — Ready for EOW**
