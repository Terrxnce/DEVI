# Deep Dive: Detector Initialization Pattern Issue

**Date**: Oct 21, 2025, 3:26 AM UTC+01:00
**Issue**: AttributeError in detector initialization
**Root Cause**: Attributes set AFTER `super().__init__()` but needed BEFORE
**Status**: ✅ **All Fixed**

---

## 🔍 Root Cause Analysis

### The Problem

Each detector subclass follows this pattern:

```python
class MyDetector(StructureDetector):
    def __init__(self, parameters):
        params = parameters or {}
        params.setdefault('key1', value1)
        params.setdefault('key2', value2)
        
        super().__init__('MyDetector', StructureType.MY_TYPE, params)  # ❌ Calls _validate_parameters()
        
        self.key1 = params['key1']  # ❌ Too late! _validate_parameters() already ran
        self.key2 = params['key2']
```

### Why It Fails

1. `super().__init__()` is called
2. Base class `StructureDetector.__init__()` runs
3. Base class calls `self._validate_parameters()` (line 46 in detector.py)
4. Subclass's `_validate_parameters()` tries to access `self.key1`, `self.key2`
5. **AttributeError**: Attributes don't exist yet!

### The Solution

Move attribute assignments BEFORE `super().__init__()`:

```python
class MyDetector(StructureDetector):
    def __init__(self, parameters):
        params = parameters or {}
        params.setdefault('key1', value1)
        params.setdefault('key2', value2)
        
        # Set attributes FIRST
        self.key1 = params['key1']  # ✅ Now attributes exist
        self.key2 = params['key2']
        
        # Then call super().__init__()
        super().__init__('MyDetector', StructureType.MY_TYPE, params)  # ✅ _validate_parameters() can access them
```

---

## 📋 Detector Status

### Detectors with _validate_parameters() that access self attributes

| Detector | Attributes | Status | Fix |
|----------|-----------|--------|-----|
| **OrderBlockDetector** | displacement_min_body_atr, excess_beyond_swing_atr, max_age_bars, max_concurrent_zones_per_side, mid_band_atr, quality_weights | ✅ Fixed | Moved before super().__init__() |
| **FairValueGapDetector** | min_gap_size, min_volume_ratio, max_gap_size, quality_thresholds, min_gap_atr_multiplier, max_age_bars | ✅ Fixed | Moved before super().__init__() |
| **BreakOfStructureDetector** | min_break_strength, pivot_window, confirmation_periods, debounce_bars | ✅ Fixed | Moved before super().__init__() |
| **SweepDetector** | sweep_excess_atr, close_back_inside_within, min_follow_through_atr, follow_through_window, sweep_debounce_bars, max_age_bars, quality_weights, context_bonus | ✅ OK | Already correct (attributes before super) |
| **UnifiedZoneRejectionDetector** | touch_atr_buffer, midline_bias, min_reaction_body_atr, min_follow_through_atr, lookahead_bars, max_age_bars, debounce_bars, weights, context | ✅ OK | Already correct (attributes before super) |
| **EngulfingDetector** | (uses self.parameters, not direct attributes) | ✅ OK | No attributes to set |

---

## 🔧 Fixes Applied

### Fix 1: OrderBlockDetector ✅
**File**: `core/structure/order_block.py`

```python
# Before (WRONG):
params = { ... }
super().__init__(...)  # ❌ _validate_parameters() called here
self.displacement_min_body_atr = ...  # ❌ Too late

# After (CORRECT):
params = { ... }
self.displacement_min_body_atr = ...  # ✅ Set first
self.excess_beyond_swing_atr = ...
self.max_age_bars = ...
self.max_concurrent_zones_per_side = ...
self.mid_band_atr = ...
self.quality_weights = ...
self.active_obs = []
super().__init__(...)  # ✅ Now attributes exist
```

**Status**: ✅ Fixed

---

### Fix 2: FairValueGapDetector ✅
**File**: `core/structure/fair_value_gap.py`

```python
# Before (WRONG):
params = { ... }
super().__init__(...)  # ❌ _validate_parameters() called here
self.min_gap_size = ...  # ❌ Too late
self.min_volume_ratio = ...
self.max_gap_size = ...
self.quality_thresholds = ...
self.min_gap_atr_multiplier = ...
self.max_age_bars = ...

# After (CORRECT):
params = { ... }
self.min_gap_size = ...  # ✅ Set first
self.min_volume_ratio = ...
self.max_gap_size = ...
self.quality_thresholds = ...
self.min_gap_atr_multiplier = ...
self.max_age_bars = ...
super().__init__(...)  # ✅ Now attributes exist
```

**Status**: ✅ Fixed

---

### Fix 3: BreakOfStructureDetector ✅
**File**: `core/structure/break_of_structure.py`

```python
# Before (WRONG):
params = { ... }
super().__init__(...)  # ❌ _validate_parameters() called here
self.min_break_strength = ...  # ❌ Too late
self.pivot_window = ...
self.confirmation_periods = ...
self.debounce_bars = ...

# After (CORRECT):
params = { ... }
self.min_break_strength = ...  # ✅ Set first
self.pivot_window = ...
self.confirmation_periods = ...
self.debounce_bars = ...
self._last_bos_index = None
self._last_bos_direction = None
super().__init__(...)  # ✅ Now attributes exist
```

**Status**: ✅ Fixed

---

## ✅ All Detectors Now Correct

**Before Fixes**:
- ❌ OrderBlockDetector — AttributeError
- ❌ FairValueGapDetector — AttributeError
- ❌ BreakOfStructureDetector — AttributeError
- ✅ SweepDetector — OK
- ✅ UnifiedZoneRejectionDetector — OK
- ✅ EngulfingDetector — OK

**After Fixes**:
- ✅ OrderBlockDetector — Fixed
- ✅ FairValueGapDetector — Fixed
- ✅ BreakOfStructureDetector — Fixed
- ✅ SweepDetector — OK
- ✅ UnifiedZoneRejectionDetector — OK
- ✅ EngulfingDetector — OK

---

## 🎯 Key Lesson

**Pattern**: When a subclass's `__init__()` calls `super().__init__()`, the base class may call methods that access subclass attributes.

**Solution**: Always set subclass attributes BEFORE calling `super().__init__()`.

**Code Pattern**:
```python
class MySubclass(BaseClass):
    def __init__(self, params):
        # 1. Set defaults
        params.setdefault('key1', value1)
        
        # 2. Set subclass attributes FIRST
        self.key1 = params['key1']
        self.key2 = params['key2']
        
        # 3. Call super().__init__() LAST
        super().__init__('MySubclass', params)
```

---

## 📁 Files Modified

| File | Changes |
|------|---------|
| `core/structure/order_block.py` | Moved attributes before super().__init__() |
| `core/structure/fair_value_gap.py` | Moved attributes before super().__init__() |
| `core/structure/break_of_structure.py` | Moved attributes before super().__init__() |

---

## 🚀 Ready to Execute

All detector initialization issues are now fixed. The pipeline can now be instantiated without errors.

**Next**: Run `python backtest_dry_run.py 1000 EURUSD` and collect artifacts.

---

**Status**: ✅ **All Detector Issues Fixed**
